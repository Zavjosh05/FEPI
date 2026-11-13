"""HU-1.4 · Validación del expediente."""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from nucleo import dias_habiles
from nucleo.demo import completar_requisitos
from recepcion import servicios
from recepcion.models import EstadoRevision, ResultadoValidacion

from .conftest import historia

pytestmark = pytest.mark.django_db


@pytest.fixture
def enviado(nueva_solicitud, usuarios):
    def _crear(**kw):
        exp = nueva_solicitud(**kw)
        delegacion = usuarios[kw.get("usuario", "del_amecameca")]
        completar_requisitos(delegacion, exp)
        servicios.enviar_a_direccion(delegacion, exp)
        exp.refresh_from_db()
        return exp
    return _crear


def _refrendo_enviado(nueva_solicitud, usuarios, anios_documentacion):
    exp = nueva_solicitud(refrendo=True)
    hoy = timezone.localdate()
    fecha = hoy.replace(year=hoy.year - anios_documentacion)
    completar_requisitos(usuarios["del_amecameca"], exp, fecha_archivo=fecha)
    servicios.enviar_a_direccion(usuarios["del_amecameca"], exp)
    exp.refresh_from_db()
    return exp


def test_hu_1_4_criterios_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-1.4")
    assert len(hu["criterios"]) == 2 and "3 años" in hu["criterios"][1]
    assert "refrendos" in necesidades["CC-ARP-01"]["texto"]


def test_hu_1_4_expediente_validado(enviado, usuarios):
    """Criterio 1 (validado): el expediente queda validado, con constancia y bitácora."""
    exp = enviado()
    val = servicios.validar_expediente(usuarios["dir_drff"], exp)
    exp.refresh_from_db()
    assert val.resultado == ResultadoValidacion.VALIDADO and exp.estado.clave == "validada"
    assert val.acuse.archivo.open("rb").read(4) == b"%PDF"
    assert exp.eventos.filter(tipo="validacion", estado_destino__clave="validada").exists()


def test_hu_1_4_aviso_de_faltantes_con_fecha_limite(enviado, usuarios, cc):
    """Criterio 1 (faltantes): existe un aviso de faltantes con fecha límite calculada con el plazo del programa."""
    exp = enviado()
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    val = servicios.validar_expediente(usuarios["dir_drff"], exp, [plano.pk], "Plano ilegible")
    exp.refresh_from_db()
    plazo = cc.plazo("complemento_documentacion_faltante")
    assert val.resultado == ResultadoValidacion.FALTANTES and exp.estado.clave == "faltantes"
    assert val.fecha_limite == dias_habiles.sumar_dias_habiles(val.fecha_hora, plazo.cantidad)
    assert plazo.unidad == "dias_habiles" and str(plazo.cantidad) in val.plazo_aplicado
    assert list(val.faltantes.all()) == [plano]
    plano.refresh_from_db()
    assert plano.estado == EstadoRevision.FALTANTE
    renglones = dict(val.acuse.contenido["renglones"])
    assert renglones["Fecha límite para entregar"] == f"{val.fecha_limite:%d/%m/%Y}"
    assert "por conducto de" in val.acuse.destinatario
    # El aviso va a la bandeja de la Delegación, que lo notifica a la persona solicitante.
    from nucleo.models import bandeja
    assert exp in bandeja(usuarios["del_amecameca"])


def test_hu_1_4_notificacion_por_conducto_de_la_delegacion_y_reenvio(enviado, usuarios, pdf):
    exp = enviado()
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    val = servicios.validar_expediente(usuarios["dir_drff"], exp, [plano.pk])
    with pytest.raises(PermissionDenied):
        servicios.registrar_notificacion(usuarios["dir_drff"], val)
    acuse = servicios.registrar_notificacion(usuarios["del_amecameca"], val)
    val.refresh_from_db()
    assert val.notificado_en and val.acuse_notificacion == acuse
    plano.refresh_from_db()
    servicios.revisar_requisito(usuarios["del_amecameca"], plano, EstadoRevision.ENTREGADO, archivo=pdf("plano.pdf"))
    servicios.enviar_a_direccion(usuarios["del_amecameca"], exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "enviada_direccion"
    servicios.validar_expediente(usuarios["dir_drff"], exp)
    exp.refresh_from_db()
    assert exp.estado.clave == "validada"


def test_hu_1_4_dias_inhabiles_mueven_la_fecha_limite(enviado, usuarios):
    from nucleo.models import DiaInhabil

    exp = enviado()
    hoy = timezone.localdate()
    for i in range(1, 15):
        DiaInhabil.objects.get_or_create(fecha=hoy + timedelta(days=i), defaults={"descripcion": "Prueba"})
    val = servicios.validar_expediente(usuarios["dir_drff"], exp, [exp.revisiones.first().pk])
    assert val.fecha_limite > hoy + timedelta(days=14)


def test_hu_1_4_refrendo_documentacion_legal_de_hasta_3_anios_es_valida(nueva_solicitud, usuarios):
    """Criterio 2: en un refrendo, la documentación legal vigente de hasta 3 años es válida."""
    exp = _refrendo_enviado(nueva_solicitud, usuarios, 2)
    archivo = exp.revisiones.filter(en_archivo_probosque=True)
    assert archivo.filter(requisito__es_documento_legal=True).exists()
    evaluacion = servicios.evaluar_para_validacion(exp)
    assert all(e.valida for e in evaluacion)
    val = servicios.validar_expediente(usuarios["dir_drff"], exp)
    assert val.resultado == ResultadoValidacion.VALIDADO


def test_hu_1_4_refrendo_documentacion_de_mas_de_3_anios_no_es_valida(nueva_solicitud, usuarios):
    """Criterio 2 (caso contrario): con más de 3 años no vale; la Dirección la marca como faltante."""
    exp = _refrendo_enviado(nueva_solicitud, usuarios, 2)
    vieja = exp.revisiones.filter(en_archivo_probosque=True, requisito__es_documento_legal=True).first()
    vieja.fecha_documento = vieja.fecha_documento.replace(year=vieja.fecha_documento.year - 2)  # 4 años
    vieja.save()
    evaluacion = {e.revision.pk: e for e in servicios.evaluar_para_validacion(exp)}
    assert not evaluacion[vieja.pk].valida and "no es válida" in evaluacion[vieja.pk].motivo
    val = servicios.validar_expediente(usuarios["dir_drff"], exp)
    assert val.resultado == ResultadoValidacion.FALTANTES and vieja in val.faltantes.all()


def test_hu_1_4_la_vigencia_de_3_anios_sale_de_las_reglas(nueva_solicitud, usuarios, cc):
    exp = _refrendo_enviado(nueva_solicitud, usuarios, 2)
    plazo = cc.plazo("vigencia_documentacion_legal_refrendo")
    plazo.cantidad = 1  # si las reglas dijeran 1 año, la de 2 años ya no valdría
    plazo.save()
    assert not all(e.valida for e in servicios.evaluar_para_validacion(exp))


def test_hu_1_4_delegacion_no_acepta_archivo_de_mas_de_3_anios(nueva_solicitud, usuarios):
    exp = nueva_solicitud(refrendo=True)
    r = exp.revisiones.filter(requisito__aplica_en_refrendo=False, requisito__es_documento_legal=True).first()
    hoy = timezone.localdate()
    with pytest.raises(ValidationError, match="más de 3"):
        servicios.revisar_requisito(usuarios["del_amecameca"], r, EstadoRevision.ENTREGADO,
                                    en_archivo_probosque=True, fecha_documento=hoy.replace(year=hoy.year - 4))


def test_hu_1_4_sin_refrendo_no_vale_el_archivo_de_probosque(nueva_solicitud, usuarios):
    exp = nueva_solicitud(refrendo=False)
    r = exp.revisiones.filter(requisito__aplica_en_refrendo=False).first()
    with pytest.raises(ValidationError, match="Solo en un refrendo"):
        servicios.revisar_requisito(usuarios["del_amecameca"], r, EstadoRevision.ENTREGADO,
                                    en_archivo_probosque=True, fecha_documento=timezone.localdate())


def test_hu_1_4_solo_la_direccion_valida(enviado, usuarios):
    exp = enviado()
    with pytest.raises(PermissionDenied):
        servicios.validar_expediente(usuarios["del_amecameca"], exp)


def test_hu_1_4_pantalla_de_validacion(client, enviado, contrasena):
    exp = enviado()
    client.login(username="dir_drff", password=contrasena)
    r = client.get(f"/recepcion/expediente/{exp.folio}/validar/")
    assert r.status_code == 200 and "Validación del expediente" in r.content.decode()
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    r = client.post(f"/recepcion/expediente/{exp.folio}/validar/", {"accion": "validar", "faltante": [plano.pk]})
    assert r.status_code == 200  # no valida si hay faltantes marcados
    r = client.post(f"/recepcion/expediente/{exp.folio}/validar/", {"accion": "faltantes", "faltante": [plano.pk]})
    assert r.status_code == 302
    exp.refresh_from_db()
    assert exp.estado.clave == "faltantes"
