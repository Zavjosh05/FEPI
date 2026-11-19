"""HU-1.2 · Revisión del expediente."""
import pytest
from django.core.exceptions import ValidationError

from nucleo.demo import completar_requisitos
from recepcion import servicios
from recepcion.models import EstadoRevision

from .conftest import historia

pytestmark = pytest.mark.django_db


def _claves(exp):
    return set(exp.revisiones.values_list("requisito__clave", flat=True))


def test_hu_1_2_criterios_del_modelo(modelo):
    assert len(historia(modelo, "HU-1.2")["criterios"]) == 2


def test_hu_1_2_requisitos_segun_programa_tipo_de_persona_y_modalidad(nueva_solicitud, cc):
    """Criterio 1 (parte 1): la lista de requisitos sale de las reglas para el tipo de persona y la modalidad."""
    fisica = nueva_solicitud(tipo="fisica", modalidad="reforestacion")
    nucleo = nueva_solicitud(tipo="nucleo_agrario", modalidad="plantacion_maderable", nombre="Ejido")
    esperados_fisica = {r.clave for r in cc.requisitos.all()
                        if (not r.tipos_persona.exists() or r.tipos_persona.filter(clave="fisica").exists())
                        and (not r.modalidades.exists() or r.modalidades.filter(clave="reforestacion").exists())}
    assert _claves(fisica) == esperados_fisica
    assert "CC-REQ-09" in _claves(nucleo) and "CC-REQ-09" not in _claves(fisica)      # carpeta básica: núcleo agrario
    assert "CC-REQ-19" in _claves(nucleo) and "CC-REQ-19" not in _claves(fisica)      # registro de plantación: modalidad
    assert "CC-REQ-10" in _claves(fisica) and "CC-REQ-10" not in _claves(nucleo)


def test_hu_1_2_cada_requisito_queda_entregado_o_faltante(nueva_solicitud, usuarios, pdf):
    """Criterio 1: cada requisito está revisado como entregado (con su archivo digitalizado), faltante o, si es condicional, no aplica."""
    exp = nueva_solicitud()
    assert exp.revisiones.filter(estado=EstadoRevision.PENDIENTE).count() == exp.revisiones.count()
    completar_requisitos(usuarios["del_amecameca"], exp, faltar=("CC-REQ-08",))
    estados = dict(exp.revisiones.values_list("requisito__clave", "estado"))
    assert EstadoRevision.PENDIENTE not in estados.values()
    assert estados["CC-REQ-08"] == EstadoRevision.FALTANTE
    entregados = exp.revisiones.filter(estado=EstadoRevision.ENTREGADO, requisito__requiere_documento=True)
    assert entregados.exists() and all(r.documento and r.documento.archivo for r in entregados)
    assert exp.eventos.filter(tipo="revision_requisito").count() == exp.revisiones.count()


def test_hu_1_2_requisito_obligatorio_no_puede_marcarse_no_aplica(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    curp = exp.revisiones.get(requisito__clave="CC-REQ-08")
    with pytest.raises(ValidationError):
        servicios.revisar_requisito(usuarios["del_amecameca"], curp, EstadoRevision.NO_APLICA)


def test_hu_1_2_entregado_requiere_archivo_digitalizado(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    r = exp.revisiones.get(requisito__clave="CC-REQ-08")
    with pytest.raises(ValidationError):
        servicios.revisar_requisito(usuarios["del_amecameca"], r, EstadoRevision.ENTREGADO)


def test_hu_1_2_no_se_envia_con_faltantes_ni_sin_revisar(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    with pytest.raises(ValidationError, match="sin revisar"):
        servicios.enviar_a_direccion(usuarios["del_amecameca"], exp)
    completar_requisitos(usuarios["del_amecameca"], exp, faltar=("CC-REQ-05",))
    with pytest.raises(ValidationError, match="faltantes"):
        servicios.enviar_a_direccion(usuarios["del_amecameca"], exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "recibida"


def test_hu_1_2_expediente_digital_en_la_direccion_con_fecha_y_hora(nueva_solicitud, usuarios):
    """Criterio 2: el expediente digital está en la Dirección, con la fecha y la hora del envío."""
    exp = nueva_solicitud()
    completar_requisitos(usuarios["del_amecameca"], exp)
    acuse = servicios.enviar_a_direccion(usuarios["del_amecameca"], exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "enviada_direccion"
    assert exp.estado.tipo_unidad_bandeja == "direccion"
    assert exp.enviado_direccion is not None
    from nucleo.models import bandeja
    assert exp in bandeja(usuarios["dir_drff"]) and exp not in bandeja(usuarios["del_amecameca"])
    assert acuse.tipo == "envio_direccion" and acuse.archivo.open("rb").read(4) == b"%PDF"
    assert dict(acuse.contenido["renglones"])["Fecha y hora del envío"]
    ev = exp.eventos.get(tipo="envio")
    assert ev.acuse == acuse and ev.estado_destino.clave == "enviada_direccion"


def test_hu_1_2_revision_por_htmx_devuelve_la_fila(client, nueva_solicitud, contrasena, pdf):
    exp = nueva_solicitud()
    r = exp.revisiones.get(requisito__clave="CC-REQ-08")
    client.login(username="del_amecameca", password=contrasena)
    resp = client.post(f"/recepcion/expediente/{exp.folio}/requisito/{r.pk}/",
                       {"estado": "entregado", "archivo": pdf("curp.pdf")}, HTTP_HX_REQUEST="true")
    assert resp.status_code == 200 and resp["HX-Trigger"] == "requisitos-actualizados"
    assert f'id="req-{r.pk}"' in resp.content.decode()
    r.refresh_from_db()
    assert r.estado == "entregado" and r.documento is not None


def test_hu_1_2_requisito_que_no_es_documento_se_cumple_sin_archivo(nueva_solicitud, usuarios, cc):
    """Ajuste: los requisitos que son condiciones (datos/sistema.json) no exigen archivo."""
    req = cc.requisitos.get(clave="CC-REQ-01")
    assert req.requiere_documento is False and cc.requisitos.get(clave="CC-REQ-08").requiere_documento
    exp = nueva_solicitud()
    r = exp.revisiones.get(requisito=req)
    servicios.revisar_requisito(usuarios["del_amecameca"], r, EstadoRevision.ENTREGADO)
    r.refresh_from_db()
    assert r.estado == EstadoRevision.ENTREGADO and r.documento is None
    completar_requisitos(usuarios["del_amecameca"], exp)
    assert servicios.problemas_para_enviar(exp) == []
    assert all(e.valida for e in servicios.evaluar_para_validacion(exp))
