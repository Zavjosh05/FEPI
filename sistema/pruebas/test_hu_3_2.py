"""HU-3.2 · Elaboración del contrato."""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from contrato import contratos
from contrato.models import Adendum, Contrato, ModeloContrato, TipoModelo
from nucleo.models import Ejercicio, Expediente, Modalidad, bandeja

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def test_hu_3_2_criterios_y_necesidades_vienen_del_modelo(modelo):
    hu = historia(modelo, "HU-3.2")
    assert "modelo validado" in hu["criterios"][0] and "fecha y la hora del envío" in hu["criterios"][1]


# ----------------------------------------------------------------------------- modelos de contrato
def test_hu_3_2_plantilla_base_propia_marcada_como_borrador_y_por_validar(usuarios, cc):
    m = contratos.crear_plantilla_base(usuarios["dir_drff"], cc)
    v = m.vigente
    assert m.es_base and "BORRADOR – modelo por validar" in m.nombre
    assert v.texto.startswith("BORRADOR – modelo por validar") and v.estado == "pendiente" and not m.validado
    for tipo in (TipoModelo.CONVENIO_CONCERTACION, TipoModelo.ADENDUM):
        assert contratos.crear_plantilla_base(usuarios["dir_drff"], cc, tipo).vigente.texto.startswith("BORRADOR")
    with pytest.raises(ValidationError, match="Ya existe"):
        contratos.crear_plantilla_base(usuarios["dir_drff"], cc)


def test_hu_3_2_el_area_responsable_registra_y_la_unidad_juridica_valida_con_fecha_hora_y_observaciones(usuarios, cc):
    m = contratos.registrar_modelo(usuarios["dir_drff"], cc, "contrato_adhesion", "Contrato CC 2026", "Contrato {{folio_contrato}} de {{persona}}.")
    v = m.vigente
    assert v.estado == "pendiente" and v.revisada_en is None
    for quien in ("del_amecameca", "comite", "dir_drff"):   # solo la Unidad Jurídica valida
        with pytest.raises(PermissionDenied):
            contratos.validar_version(usuarios[quien], v)
    antes = timezone.now()
    contratos.validar_version(usuarios["juridica"], v, "Cláusulas conformes con las ROP.")
    v.refresh_from_db()
    assert v.estado == "validada" and v.revisada_por == usuarios["juridica"] and antes <= v.revisada_en <= timezone.now()
    assert v.observaciones == "Cláusulas conformes con las ROP." and m.validado
    with pytest.raises(ValidationError, match="ya se revisó"):
        contratos.validar_version(usuarios["juridica"], v)


def test_hu_3_2_la_unidad_juridica_puede_devolver_con_observaciones(usuarios, cc):
    m = contratos.registrar_modelo(usuarios["dir_drff"], cc, "contrato_adhesion", "Contrato por devolver", "Contrato de {{persona}}.")
    with pytest.raises(ValidationError, match="observaciones"):
        contratos.devolver_version(usuarios["juridica"], m.vigente, "")
    contratos.devolver_version(usuarios["juridica"], m.vigente, "Falta la cláusula de reintegro.")
    v = m.vigente
    assert v.estado == "devuelta" and v.observaciones and not m.validado


def test_hu_3_2_un_modelo_cambiado_despues_de_validarse_vuelve_a_quedar_sin_validar(usuarios, cc, modelo_validado):
    m = modelo_validado(cc)
    assert m.validado and m.vigente.numero == 1
    with pytest.raises(ValidationError, match="no cambió"):
        contratos.modificar_modelo(usuarios["dir_drff"], m, m.vigente.texto)
    v2 = contratos.modificar_modelo(usuarios["dir_drff"], m, m.vigente.texto + "\n\nQUINTA. Jurisdicción.")
    assert v2.numero == 2 and v2.estado == "pendiente" and not m.validado
    assert m.versiones.get(numero=1).estado == "validada"   # la versión anterior se conserva
    with pytest.raises(ValidationError, match="vigente"):
        contratos.validar_version(usuarios["juridica"], m.versiones.get(numero=1))
    contratos.validar_version(usuarios["juridica"], v2)
    assert m.validado


def test_hu_3_2_los_campos_de_la_plantilla_se_validan(usuarios, cc):
    with pytest.raises(ValidationError, match="campo_inventado"):
        contratos.registrar_modelo(usuarios["dir_drff"], cc, "contrato_adhesion", "X", "Hola {{campo_inventado}}")
    with pytest.raises(ValidationError, match="texto"):
        contratos.registrar_modelo(usuarios["dir_drff"], cc, "contrato_adhesion", "X", "  ")
    with pytest.raises(PermissionDenied):
        contratos.registrar_modelo(usuarios["dir_dpf"], cc, "contrato_adhesion", "Y", "Texto")   # no es su programa
    assert contratos.llenar("A {{ persona }} y {{predio}} {{ folio_predio }}", {"persona": "Ana", "predio": ""}) == "A Ana y — —"


# ----------------------------------------------------------------------------- criterio 1: contrato sobre modelo validado
def test_hu_3_2_existe_un_contrato_por_solicitud_aprobada_sobre_un_modelo_validado(notificadas, modelo_validado, usuarios):
    """Criterio 1: existe un contrato por solicitud aprobada, elaborado sobre un modelo validado, con sus datos."""
    sesion, (exp,) = notificadas("PS")
    m = modelo_validado(exp.ejercicio)
    c = contratos.elaborar_contrato(usuarios["dir_drff"], exp, m)
    exp.refresh_from_db()
    assert exp.estado.clave == "contrato_elaborado" and exp.contrato == c
    assert c.version_modelo == m.vigente and c.version_modelo.estado == "validada" and c.tipo == "contrato_adhesion"
    assert c.archivo.open("rb").read(4) == b"%PDF" and len(c.huella) == 64 and c.folio.startswith("CTO-PS-2026-")
    d = c.datos
    assert d["persona"] == exp.solicitante.nombre and d["predio"] == exp.predio.nombre and d["municipio"] == "Tlalmanalco"
    assert d["superficie_ha"] and d["monto_total"].startswith("$") and "ministración" in d["ministraciones"]
    for dato in (d["persona"], d["predio"], d["municipio"], d["monto_total"], d["delegacion"], d["modalidad"]):
        assert dato in c.texto
    assert "{{" not in c.texto and exp.eventos.filter(tipo="contrato_elaborado").exists()


def test_hu_3_2_el_servicio_impide_elaborar_sobre_un_modelo_sin_validar(notificadas, usuarios):
    sesion, (exp,) = notificadas("PS")
    pendiente = contratos.crear_plantilla_base(usuarios["dir_drff"], exp.ejercicio)   # borrador por validar
    with pytest.raises(ValidationError, match="no está validado"):
        contratos.elaborar_contrato(usuarios["dir_drff"], exp, pendiente)
    contratos.devolver_version(usuarios["juridica"], pendiente.vigente, "Quitar el borrador.")
    with pytest.raises(ValidationError, match="no está validado"):
        contratos.elaborar_contrato(usuarios["dir_drff"], exp, pendiente)
    assert not Contrato.objects.exists() and exp.estado.clave == "notificada"


def test_hu_3_2_un_modelo_cambiado_despues_de_validarse_ya_no_sirve_hasta_revalidarlo(notificadas, modelo_validado, usuarios):
    sesion, (exp,) = notificadas("RHF")
    m = modelo_validado(exp.ejercicio)
    contratos.modificar_modelo(usuarios["dir_drff"], m, m.vigente.texto + "\n\nSEXTA. Otra.")
    assert contratos.modelos_elegibles(exp) == []
    with pytest.raises(ValidationError, match="no está validado"):
        contratos.elaborar_contrato(usuarios["dir_drff"], exp, m)
    contratos.validar_version(usuarios["juridica"], m.vigente)
    assert contratos.elaborar_contrato(usuarios["dir_drff"], exp, m).version_modelo.numero == 2


def test_hu_3_2_solo_se_elabora_de_una_solicitud_aprobada_publicada_y_notificada(aprobadas, modelo_validado, usuarios):
    sesion, exps = aprobadas("CC", presupuesto=12000, no_factible=True)   # beneficiaria, lista de espera, no factible
    por_resultado = {e.resoluciones_comite.get().resultado: e for e in exps}
    m = modelo_validado(sesion.ejercicio)
    with pytest.raises(ValidationError, match="aún no se publican"):
        contratos.elaborar_contrato(usuarios["dir_drff"], por_resultado["beneficiaria"], m)
    from contrato import publicacion
    publicacion.publicar(usuarios["dir_drff"], sesion)
    b = por_resultado["beneficiaria"]
    b.refresh_from_db()
    with pytest.raises(ValidationError, match="notifique a la persona"):
        contratos.elaborar_contrato(usuarios["dir_drff"], b, m)
    for otro in ("lista_espera", "no_factible"):
        with pytest.raises(ValidationError, match="aprobada, publicada y notificada"):
            contratos.elaborar_contrato(usuarios["dir_drff"], por_resultado[otro], m)
    assert not Contrato.objects.exists()


def test_hu_3_2_un_solo_contrato_por_solicitud_y_se_rehace_mientras_no_se_envie(notificadas, modelo_validado, usuarios):
    sesion, (exp,) = notificadas("PS")
    m = modelo_validado(exp.ejercicio)
    c1 = contratos.elaborar_contrato(usuarios["dir_drff"], exp, m)
    huella = c1.huella
    c2 = contratos.elaborar_contrato(usuarios["dir_drff"], exp, m)   # rehacer, no duplicar
    assert c2.pk == c1.pk and c2.folio == c1.folio and c2.rehechos == 1 and Contrato.objects.count() == 1
    assert exp.eventos.filter(tipo="contrato_rehecho").exists() and c2.huella != "" and huella != ""
    contratos.enviar_a_delegacion(usuarios["dir_drff"], c2)
    exp.refresh_from_db()
    with pytest.raises(ValidationError, match="ya se envió"):
        contratos.elaborar_contrato(usuarios["dir_drff"], exp, m)
    assert Contrato.objects.count() == 1


def test_hu_3_2_psahem_con_fondos_concurrentes_lleva_convenio_de_concertacion(notificadas, modelo_validado, usuarios):
    sesion, (exp,) = notificadas("PSA")
    Expediente.objects.filter(pk=exp.pk).update(modalidad=Modalidad.objects.get(ejercicio=exp.ejercicio, clave="fondos_concurrentes"))
    exp.refresh_from_db()
    assert contratos.tipo_requerido(exp) == "convenio_concertacion"
    adhesion = modelo_validado(exp.ejercicio)
    with pytest.raises(ValidationError, match="Convenio de Concertación"):
        contratos.elaborar_contrato(usuarios["dir_drff"], exp, adhesion)
    convenio = modelo_validado(exp.ejercicio, TipoModelo.CONVENIO_CONCERTACION, "Convenio de prueba")
    c = contratos.elaborar_contrato(usuarios["dir_drff"], exp, convenio)
    assert c.tipo == "convenio_concertacion" and "CONVENIO DE CONCERTACIÓN" in c.texto


def test_hu_3_2_el_modelo_debe_ser_del_programa_y_ejercicio_de_la_solicitud(notificadas, modelo_validado, usuarios):
    sesion, (exp,) = notificadas("PS")
    ajeno = modelo_validado(Ejercicio.objects.get(programa__clave="RHF", anio=2026))
    with pytest.raises(ValidationError, match="no es del programa"):
        contratos.elaborar_contrato(usuarios["dir_drff"], exp, ajeno)


def test_hu_3_2_solo_el_area_responsable_elabora_y_envia(notificadas, modelo_validado, usuarios):
    sesion, (exp,) = notificadas("PS")
    m = modelo_validado(exp.ejercicio)
    for quien in ("del_amecameca", "juridica", "comite", "dir_dpf"):
        with pytest.raises(PermissionDenied):
            contratos.elaborar_contrato(usuarios[quien], exp, m)
    c = contratos.elaborar_contrato(usuarios["dir_drff"], exp, m)
    for quien in ("del_amecameca", "juridica"):
        with pytest.raises(PermissionDenied):
            contratos.enviar_a_delegacion(usuarios[quien], c)


# ----------------------------------------------------------------------------- criterio 2: envío a la Delegación
def test_hu_3_2_existe_la_fecha_y_la_hora_del_envio_a_la_delegacion_con_su_acuse(notificadas, modelo_validado, usuarios):
    """Criterio 2: existe la fecha y la hora del envío a la Delegación (y su acuse); pasa a su bandeja."""
    sesion, (exp,) = notificadas("PS")
    c = contratos.elaborar_contrato(usuarios["dir_drff"], exp, modelo_validado(exp.ejercicio))
    assert c.enviado_en is None and exp not in bandeja(usuarios["del_amecameca"])
    antes = timezone.now()
    acuse = contratos.enviar_a_delegacion(usuarios["dir_drff"], c)
    c.refresh_from_db()
    exp.refresh_from_db()
    assert antes <= c.enviado_en <= timezone.now() and c.enviado_por == usuarios["dir_drff"] and c.acuse_envio == acuse
    assert c.estado == "enviado" and exp.estado.clave == "contrato_en_delegacion"
    assert acuse.archivo.open("rb").read(4) == b"%PDF" and dict(acuse.contenido["renglones"])["Fecha y hora del envío"]
    assert dict(acuse.contenido["renglones"])["Huella del PDF (SHA-256)"] == c.huella
    assert exp in bandeja(usuarios["del_amecameca"]) and exp not in bandeja(usuarios["dir_drff"])
    assert exp.eventos.filter(tipo="contrato_enviado", acuse=acuse).exists()
    with pytest.raises(ValidationError, match="ya se envió"):
        contratos.enviar_a_delegacion(usuarios["dir_drff"], c)


@pytest.mark.parametrize("programa", ["CC", "PS", "RHF", "PSA"])
def test_hu_3_2_el_recorrido_corre_en_los_cuatro_programas(notificadas, modelo_validado, usuarios, programa):
    sesion, (exp,) = notificadas(programa)
    m = modelo_validado(exp.ejercicio)
    c = contratos.elaborar_contrato(usuarios["dir_drff"], exp, m)
    contratos.enviar_a_delegacion(usuarios["dir_drff"], c)
    exp.refresh_from_db()
    assert exp.estado.clave == "contrato_en_delegacion" and c.datos["programa"] == exp.programa.nombre
    assert c.datos["monto_total"] != "—"


def test_hu_3_2_queda_preparado_el_adendum_ligado_al_contrato(notificadas, modelo_validado, usuarios):
    """MFS aún no tiene reglas: solo el modelo de datos del adendum / ampliación de plazo (sin pantalla)."""
    sesion, (exp,) = notificadas("PS")
    c = contratos.elaborar_contrato(usuarios["dir_drff"], exp, modelo_validado(exp.ejercicio))
    a = Adendum.objects.create(contrato=c, motivo="Causa externa (prueba).", plazo_original=timezone.localdate(),
                               plazo_nuevo=timezone.localdate() + timedelta(days=30), creado_por=usuarios["dir_drff"])
    assert c.adendums.get() == a and TipoModelo.ADENDUM in TipoModelo.values


# ----------------------------------------------------------------------------- pantallas
def test_hu_3_2_pantallas_de_modelos_alta_base_version_y_revision(notificadas, usuarios, client, contrasena, cc):
    client.login(username="dir_drff", password=contrasena)
    r = client.get("/contrato/modelos/")
    assert r.status_code == 200 and 'id="form-plantilla-base"' in r.content.decode()
    r = client.post("/contrato/modelos/", {"accion": "base", "ejercicio": cc.pk, "tipo": "contrato_adhesion"}, follow=True)
    html = r.content.decode()
    assert "BORRADOR – modelo por validar" in html and 'data-prueba="estado-version"' in html
    m = ModeloContrato.objects.get(es_base=True)
    r = client.post("/contrato/modelos/", {"ejercicio": cc.pk, "tipo": "contrato_adhesion", "nombre": "Mal modelo",
                                           "texto": "Hola {{ nada }}"})
    assert "Campos desconocidos" in r.content.decode()
    client.post(f"/contrato/modelos/{m.pk}/version/", {"texto": m.vigente.texto.replace("BORRADOR – modelo por validar", "").strip()})
    assert m.versiones.count() == 2 and m.vigente.estado == "pendiente"
    client.login(username="juridica", password=contrasena)
    assert 'data-prueba="panel-modelos-por-validar"' in client.get("/bandeja/").content.decode()
    assert 'id="form-revision"' in client.get(f"/contrato/modelos/{m.pk}/").content.decode()
    r = client.post(f"/contrato/modelos/{m.pk}/revisar/", {"decision": "devolver", "observaciones": ""}, follow=True)
    assert "observaciones" in r.content.decode() and m.vigente.estado == "pendiente"
    client.post(f"/contrato/modelos/{m.pk}/revisar/", {"decision": "validar", "observaciones": "Conforme"})
    assert m.vigente.estado == "validada" and m.validado
    assert client.get("/contrato/modelos/").status_code == 200
    client.login(username="del_amecameca", password=contrasena)
    assert client.get("/contrato/modelos/").status_code == 403


def test_hu_3_2_pantallas_de_elaboracion_envio_y_pdf(notificadas, modelo_validado, usuarios, client, contrasena):
    sesion, (exp,) = notificadas("PS")
    client.login(username="dir_drff", password=contrasena)
    assert "Elaborar el contrato" in client.get(f"/recepcion/expediente/{exp.folio}/").content.decode()
    assert 'data-prueba="por-elaborar-exp"' in client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    assert exp.folio in client.get("/contrato/contratos/").content.decode()
    sin_modelo = client.get(f"/contrato/contratos/{exp.folio}/elaborar/").content.decode()
    assert 'data-prueba="sin-modelo-validado"' in sin_modelo
    m = modelo_validado(exp.ejercicio)
    assert "Modelo de prueba" in client.get(f"/contrato/contratos/{exp.folio}/elaborar/").content.decode()
    r = client.post(f"/contrato/contratos/{exp.folio}/elaborar/", {"modelo": m.pk}, follow=True)
    html = r.content.decode()
    assert 'data-prueba="contrato"' in html and "CTO-PS-2026-" in html and "Todavía no se envía a la Delegación" in html
    pdf = client.get(f"/contrato/contratos/{exp.folio}/pdf/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf" and b"".join(pdf.streaming_content)[:4] == b"%PDF"
    # La Delegación no ve el PDF mientras no se le envíe.
    client.login(username="del_amecameca", password=contrasena)
    assert client.get(f"/contrato/contratos/{exp.folio}/pdf/").status_code == 404
    client.login(username="dir_drff", password=contrasena)
    r = client.post(f"/contrato/contratos/{exp.folio}/enviar/", follow=True)
    assert 'data-prueba="envio-contrato"' in r.content.decode() and "acuse AC-" in r.content.decode()
    client.login(username="del_amecameca", password=contrasena)
    assert client.get(f"/contrato/contratos/{exp.folio}/pdf/").status_code == 200
    assert exp.folio in client.get("/bandeja/").content.decode()
    client.login(username="del_toluca", password=contrasena)   # otra Delegación no ve el expediente
    assert client.get(f"/contrato/contratos/{exp.folio}/pdf/").status_code == 404


def test_hu_3_2_pantalla_de_contratos_pide_sesion_y_unidad(client, contrasena):
    assert client.get("/contrato/contratos/").status_code == 302
    client.login(username="del_amecameca", password=contrasena)
    assert client.get("/contrato/contratos/").status_code == 403


def test_hu_3_2_ya_no_figura_como_pendiente_en_la_pestana(notificadas, usuarios, client, contrasena):
    sesion, (exp,) = notificadas("RHF")
    client.login(username="dir_drff", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    pendientes = html.split('data-prueba="por-construir"')[-1]
    assert "HU-3.2" not in pendientes and "HU-3.3" not in pendientes and "HU-3.4 Entrega de planta" in pendientes
