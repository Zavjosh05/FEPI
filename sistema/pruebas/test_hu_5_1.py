"""HU-5.1 · Solicitud de pago."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from nucleo import extensiones, montos
from nucleo.models import Evento, Hito, bandeja
from pagos import solicitudes
from pagos.models import EstadoSolicitud, OficioPago, SolicitudPago

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m5 import *  # noqa: F401,F403
from .fixtures_m5 import instruir_pago

pytestmark = pytest.mark.django_db


def test_hu_5_1_criterios_y_necesidades_vienen_del_modelo(modelo):
    hu = historia(modelo, "HU-5.1")
    assert hu["criterios"] == ["La solicitud tiene todos sus soportes.",
                               "Existe la fecha y la hora del envío a Administración y Finanzas."]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M5.1")
    assert {"CC-ARP-05", "PS-ARP-05", "RHF-ARP-05", "PSA-ARP-05", "PEG-DPF-06"} <= set(funcion["necesidades"])


# ----------------------------------------------------------------------------- oficio de la Delegación
@pytest.mark.pdf_real
def test_hu_5_1_la_delegacion_emite_el_oficio_en_cuanto_el_contrato_esta_firmado(contratadas, usuarios):
    _, (exp,) = contratadas("PS")
    oficio = solicitudes.emitir_oficio(delegado_de(usuarios, exp), exp)
    assert oficio.folio.startswith("OFP-PS-2026-") and oficio.archivo.read().startswith(b"%PDF")
    assert oficio.acuse.tipo == "oficio_solicitud_pago" and oficio.acuse.archivo and len(oficio.huella) == 64
    assert any("BORRADOR" in r[1] for r in oficio.acuse.contenido["renglones"])
    assert exp.eventos.filter(tipo="oficio_solicitud_pago", acuse=oficio.acuse).exists()
    with pytest.raises(ValidationError, match="ya emitió"):
        solicitudes.emitir_oficio(delegado_de(usuarios, exp), exp)


def test_hu_5_1_el_oficio_no_se_emite_sin_contrato_firmado_ni_por_otra_unidad(en_delegacion, contratadas, usuarios):
    _, (sin_firma,) = en_delegacion("PS")
    with pytest.raises(ValidationError, match="todavía no se firma"):
        solicitudes.emitir_oficio(delegado_de(usuarios, sin_firma), sin_firma)
    _, (exp,) = contratadas("RHF")
    for quien in ("dir_drff", "finanzas", "juridica"):
        with pytest.raises(PermissionDenied):
            solicitudes.emitir_oficio(usuarios[quien], exp)
    otra = next(u for u in usuarios.values() if u.tipo_unidad == "delegacion" and u.unidad_id != exp.delegacion_id)
    with pytest.raises(PermissionDenied):
        solicitudes.emitir_oficio(otra, exp)


# ----------------------------------------------------------------------------- criterio 1: todos los soportes
@pytest.mark.parametrize("programa,claves", [
    ("CC", ["contrato_firmado", "oficio_delegacion", "comprobante_cuenta"]),
    ("PS", ["contrato_firmado", "oficio_delegacion", "comprobante_cuenta"]),
    ("RHF", ["contrato_firmado", "oficio_delegacion", "comprobante_cuenta"]),
    ("PSA", ["contrato_firmado", "oficio_delegacion", "dictamen", "instruccion_comite"]),
])
def test_hu_5_1_la_solicitud_tiene_todos_sus_soportes_por_programa(programa, claves, con_soportes, usuarios):
    """Criterio 1: la solicitud se envía con todos los soportes que piden las reglas del programa."""
    exp = con_soportes(programa)
    assert [s["clave"] for s in solicitudes.soportes(exp, 1)] == claves
    sol = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)
    assert [s["clave"] for s in sol.soportes] == claves and all(s["cumple"] for s in sol.soportes)
    esperado = montos.monto_aprobado(exp).ministraciones[0]
    assert sol.importe == esperado.importe and sol.porcentaje == esperado.porcentaje and sol.ministracion == 1
    exp.refresh_from_db()
    assert exp.estado.clave == "ministracion_solicitada"
    assert sol.tipo_pago == ("cheque_fiduciaria" if programa == "PSA" else "transferencia")


@pytest.mark.parametrize("quitar,mensaje", [
    ({"oficio": False}, "Oficio de solicitud de pago"),
    ({"comprobante": False}, "Comprobante de la cuenta bancaria"),
])
def test_hu_5_1_sin_un_soporte_el_servicio_no_envia_y_dice_cual_falta(quitar, mensaje, con_soportes, usuarios):
    exp = con_soportes("CC", **quitar)
    with pytest.raises(ValidationError, match=mensaje):
        solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)
    exp.refresh_from_db()
    assert exp.estado.clave == "contratada"
    sol = SolicitudPago.objects.get(expediente=exp)
    assert sol.estado == EstadoSolicitud.BORRADOR and sol.enviada_en is None  # queda por enviar


def test_hu_5_1_psahem_pide_la_instruccion_de_pago_del_comite_para_cada_ministracion(con_soportes, usuarios):
    exp = con_soportes("PSA", instruccion=False)
    with pytest.raises(ValidationError, match="instruye el pago de la ministración 1"):
        solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)
    instruir_pago(usuarios, exp, 1)
    sol = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)
    ref = next(s for s in sol.soportes if s["clave"] == "instruccion_comite")
    assert ref["cumple"] and "/" in ref["referencia"]


def test_hu_5_1_psahem_no_pide_comprobante_de_cuenta(con_soportes, usuarios, pdf):
    exp = con_soportes("PSA")
    with pytest.raises(ValidationError, match="no pide comprobante"):
        solicitudes.adjuntar_comprobante(delegado_de(usuarios, exp), exp, pdf("cuenta.pdf"))


def test_hu_5_1_sin_contrato_firmado_no_se_solicita_el_pago(en_delegacion, usuarios):
    _, (exp,) = en_delegacion("PS")
    with pytest.raises(ValidationError, match="Sin contrato firmado"):
        solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)
    assert not SolicitudPago.objects.exists()


def test_hu_5_1_el_comprobante_solo_se_acepta_como_pdf_o_imagen(con_soportes, usuarios, pdf):
    exp = con_soportes("PS", comprobante=False)
    deleg = delegado_de(usuarios, exp)
    with pytest.raises(ValidationError, match="PDF, JPG o PNG"):
        solicitudes.adjuntar_comprobante(deleg, exp, pdf("cuenta.txt"))
    with pytest.raises(ValidationError, match="Falta el archivo"):
        solicitudes.adjuntar_comprobante(deleg, exp, None)
    c = solicitudes.adjuntar_comprobante(deleg, exp, pdf("cuenta.pdf"), "Banco de prueba")
    assert c.huella and exp.comprobantes_cuenta.count() == 1


# ----------------------------------------------------------------------------- criterio 2: fecha y hora del envío
def test_hu_5_1_existe_la_fecha_y_la_hora_del_envio_con_su_acuse(con_soportes, usuarios):
    """Criterio 2: el envío a Administración y Finanzas queda con fecha, hora y acuse."""
    exp = con_soportes("CC")
    antes = timezone.now()
    sol = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1, "Soportes completos.")
    assert antes <= sol.enviada_en <= timezone.now() and sol.enviada_por == usuarios["dir_drff"] and sol.envios == 1
    assert sol.acuse_envio.tipo == "solicitud_pago" and sol.acuse_envio.archivo and len(sol.acuse_envio.huella) == 64
    renglones = dict(sol.acuse_envio.contenido["renglones"])
    assert "Fecha y hora del envío" in renglones and renglones["Importe"].startswith("$") and "Administración" in renglones["Dirigida a"]
    evento = exp.eventos.get(tipo="solicitud_pago")
    assert evento.acuse == sol.acuse_envio and evento.estado_destino.clave == "ministracion_solicitada"


def test_hu_5_1_psahem_el_envio_arranca_los_5_dias_habiles_de_la_secretaria_tecnica(con_soportes, usuarios):
    exp = con_soportes("PSA")
    sol = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)
    hito = Hito.objects.get(expediente=exp, clave="solicitud_pago_fiduciaria")
    assert hito.fecha_hora == sol.enviada_en and hito.referencia == sol.folio
    plazo = solicitudes.plazo_remision(sol)
    assert plazo.plazo.cantidad == 5 and plazo.plazo.unidad == "dias_habiles" and plazo.tiene_fecha
    assert plazo.vencimiento > timezone.localdate()


def test_hu_5_1_fuera_de_psahem_no_hay_hito_de_fiduciaria(solicitada):
    exp = solicitada("CC")
    assert not Hito.objects.filter(expediente=exp, clave="solicitud_pago_fiduciaria").exists()
    assert solicitudes.plazo_remision(exp.solicitudes_pago.get()) is None


# ----------------------------------------------------------------------------- ministraciones
def test_hu_5_1_cc_hasta_5_ha_es_pago_unico_y_arriba_son_dos_ministraciones(con_soportes, usuarios):
    unico = con_soportes("CC", ha=4)
    filas = solicitudes.ministraciones(unico)
    assert [f["numero"] for f in filas] == [1] and filas[0]["porcentaje"] == 100
    sol = solicitudes.enviar_solicitud(usuarios["dir_drff"], unico, 1)
    assert sol.importe == montos.monto_aprobado(unico).total == Decimal("8000.00")


def test_hu_5_1_la_segunda_ministracion_no_se_puede_solicitar_hasta_que_exista_la_verificacion(solicitada, usuarios):
    exp = solicitada("CC")
    filas = solicitudes.ministraciones(exp)
    assert [f["numero"] for f in filas] == [1, 2] and filas[1]["porcentaje"] == 30
    puede, motivo = solicitudes.puede_solicitar(exp, 2)
    assert not puede and "ministración 1" in motivo  # primero la 1
    # Con la primera pagada (la paga HU-5.2), la segunda sigue bloqueada por la verificación en campo (sprint 3).
    SolicitudPago.objects.filter(expediente=exp, ministracion=1).update(estado=EstadoSolicitud.PAGADA)
    type(exp).objects.filter(pk=exp.pk).update(estado=type(exp.estado).objects.get(clave="pagada"))
    exp.refresh_from_db()
    assert solicitudes.puede_solicitar(exp, 2) == (True, "")
    with pytest.raises(ValidationError, match="Verificación en campo o evaluación de reportes"):
        solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 2)
    faltan = [s["clave"] for s in solicitudes.faltantes(solicitudes.soportes(exp, 2))]
    assert faltan == ["verificacion_campo"]


def test_hu_5_1_el_sprint_3_conecta_la_verificacion_sin_cambiar_el_servicio(solicitada, usuarios, monkeypatch):
    exp = solicitada("CC")
    SolicitudPago.objects.filter(expediente=exp, ministracion=1).update(estado=EstadoSolicitud.PAGADA)
    type(exp).objects.filter(pk=exp.pk).update(estado=type(exp.estado).objects.get(clave="pagada"))
    exp.refresh_from_db()
    monkeypatch.setitem(solicitudes.FUENTES, "verificacion_campo",
                        lambda e, n: (True, "Verificada en campo.", "VER-001", ""))
    sol = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 2)
    assert sol.ministracion == 2 and sol.importe == montos.monto_aprobado(exp).ministraciones[1].importe
    assert any(s["clave"] == "verificacion_campo" and s["referencia"] == "VER-001" for s in sol.soportes)


def test_hu_5_1_una_ministracion_enviada_no_se_vuelve_a_solicitar(solicitada, usuarios):
    exp = solicitada("PS")
    with pytest.raises(ValidationError, match="ya está solicitada"):
        solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)
    assert SolicitudPago.objects.filter(expediente=exp).count() == 1


def test_hu_5_1_solo_el_area_responsable_del_programa_solicita(con_soportes, usuarios):
    exp = con_soportes("CC")
    for quien in ("dir_dpf", "finanzas", "juridica", "comite"):
        with pytest.raises(PermissionDenied):
            solicitudes.enviar_solicitud(usuarios[quien], exp, 1)
    with pytest.raises(PermissionDenied):
        solicitudes.enviar_solicitud(delegado_de(usuarios, exp), exp, 1)


def test_hu_5_1_los_importes_son_los_de_montos_aprobado_en_todos_los_programas(con_soportes, usuarios):
    for programa in ("PS", "RHF", "PSA"):
        exp = con_soportes(programa)
        sol = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)
        assert sol.importe == montos.monto_aprobado(exp).ministraciones[0].importe, programa


# ----------------------------------------------------------------------------- pantallas
def test_hu_5_1_pantallas_de_la_delegacion_y_del_area_responsable(client, contratadas, usuarios, contrasena):
    _, (exp,) = contratadas("CC")
    deleg = delegado_de(usuarios, exp)
    client.login(username=deleg.username, password=contrasena)
    bandeja_html = client.get("/bandeja/").content.decode()
    assert 'data-prueba="panel-oficios-por-emitir"' in bandeja_html and exp.folio in bandeja_html
    assert "Emitir el oficio de solicitud de pago" in client.get(f"/recepcion/expediente/{exp.folio}/").content.decode()
    r = client.post(f"/pagos/oficio/{exp.folio}/emitir/", follow=True)
    assert "emitido" in r.content.decode() and OficioPago.objects.filter(expediente=exp).exists()
    assert client.get(f"/pagos/oficio/{exp.folio}/pdf/").status_code == 200
    assert client.get("/pagos/solicitudes/").status_code == 200
    client.login(username="dir_drff", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=pagos").content.decode()
    assert 'data-prueba="solicitud-m1"' in html and "comprobante de la cuenta bancaria" in html.lower()
    assert "Lo resuelve la Delegación" in html and 'data-prueba="faltan-soportes-m1"' not in html
    r = client.post(f"/pagos/solicitud/{exp.folio}/1/enviar/", follow=True)  # falta el comprobante
    cuerpo = r.content.decode()
    assert cuerpo.count("No se puede enviar la solicitud") == 1 and "lo resuelve la Delegación" in cuerpo
    assert 'data-prueba="panel-por-solicitar"' in client.get("/bandeja/").content.decode()
    lista = client.get("/pagos/solicitudes/").content.decode()
    assert 'data-prueba="por-solicitar"' in lista and exp.folio in lista


def test_hu_5_1_otras_unidades_no_ven_la_solicitud_ajena(client, solicitada, usuarios, contrasena):
    exp = solicitada("CC")
    otra = next(u for u in usuarios.values() if u.tipo_unidad == "delegacion" and u.unidad_id != exp.delegacion_id)
    client.login(username=otra.username, password=contrasena)
    assert client.get(f"/pagos/expediente/{exp.folio}/").status_code == 404
    assert client.post(f"/pagos/oficio/{exp.folio}/emitir/").status_code == 404
    client.login(username="finanzas", password=contrasena)
    assert client.get(f"/pagos/expediente/{exp.folio}/").status_code == 302  # la ve: está en su bandeja
    assert exp in bandeja(usuarios["finanzas"])


def test_hu_5_1_siguiente_paso_y_menu_de_pagos(client, contratadas, usuarios, contrasena):
    _, (exp,) = contratadas("CC")
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/").content.decode()
    assert "Emitir el oficio de solicitud de pago" in html and "/pagos/solicitudes/" in html
    assert any(m["url"] == "pagos:solicitudes" for m in extensiones.MENU)
