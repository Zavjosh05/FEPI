"""HU-5.3 · Entrega de cheques (PSAHEM)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.utils import timezone

from nucleo import extensiones, notificaciones
from nucleo.models import Hito, bandeja
from pagos import cheques, pagos
from pagos.models import Cheque, EstadoSolicitud

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def test_hu_5_3_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-5.3")
    assert "asociado a su persona beneficiaria y a su ministración" in hu["criterios"][0]
    assert hu["criterios"][1] == "Existe la fecha de entrega de cada cheque."
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M5.3")
    assert set(funcion["necesidades"]) == {"PSA-DRF-03", "PSA-FID-01"}
    assert "3 meses" in necesidades["PSA-DRF-03"]["texto"]


# ----------------------------------------------------------------------------- emisión y envío (criterio 1)
def test_hu_5_3_cada_cheque_esta_asociado_a_su_persona_y_a_su_ministracion_con_fecha_y_hora_del_envio(remitida, usuarios):
    """Criterio 1: cheque de la ministración, a nombre de la persona beneficiaria, con fecha y hora de envío."""
    exp, sol = remitida()
    c = cheques.emitir_cheque(usuarios["fiduciaria"], sol, "CHQ-7001")
    exp.refresh_from_db()
    assert exp.estado.clave == "cheque_emitido" and c.persona == exp.solicitante and c.solicitud == sol
    assert c.ministracion == 1 and c.importe == sol.importe == Decimal("73500.00") and c.numero == "CHQ-7001"
    assert c.acuse_emision.tipo == "emision_cheque" and c.remision == sol.remision and not c.enviado
    antes = timezone.now()
    cheques.enviar_a_delegacion(usuarios["fiduciaria"], c)
    c.refresh_from_db()
    exp.refresh_from_db()
    assert antes <= c.enviado_en <= timezone.now() and c.delegacion == exp.delegacion and c.acuse_envio.tipo == "envio_cheque"
    assert exp.estado.clave == "cheque_enviado" and exp in bandeja(delegado_de(usuarios, exp))
    assert "Fecha y hora del envío" in dict(c.acuse_envio.contenido["renglones"])


def test_hu_5_3_el_envio_avisa_a_la_persona_por_conducto_de_la_delegacion(remitida, usuarios):
    exp, sol = remitida()
    c = cheques.emitir_cheque(usuarios["fiduciaria"], sol, "CHQ-7002")
    cheques.enviar_a_delegacion(usuarios["fiduciaria"], c)
    c.refresh_from_db()
    assert c.aviso.tipo == "pago" and c.aviso.delegacion == exp.delegacion and c.aviso in notificaciones.pendientes_de_notificar(exp.delegacion)


def test_hu_5_3_un_cheque_por_persona_y_ministracion_con_importe_igual_al_solicitado(remitida, usuarios):
    exp, sol = remitida()
    fid = usuarios["fiduciaria"]
    with pytest.raises(ValidationError, match="debe ser igual al solicitado"):
        cheques.emitir_cheque(fid, sol, "CHQ-1", importe=Decimal("1.00"))
    with pytest.raises(ValidationError, match="número de cheque"):
        cheques.emitir_cheque(fid, sol, " ")
    with pytest.raises(ValidationError, match="futura"):
        cheques.emitir_cheque(fid, sol, "CHQ-1", fecha_emision=timezone.localdate() + timedelta(days=1))
    cheques.emitir_cheque(fid, sol, "CHQ-1")
    with pytest.raises(ValidationError, match="un cheque por persona y ministración"):
        cheques.emitir_cheque(fid, sol, "CHQ-2")
    assert Cheque.objects.count() == 1


def test_hu_5_3_solo_se_emite_lo_remitido_y_solo_la_fiduciaria(aceptada, remitida, usuarios):
    exp, sol = aceptada("PSA")  # aceptada pero todavía no remitida
    with pytest.raises(PermissionDenied):  # la Fiduciaria ni ve lo que la Secretaría Técnica aún no le solicita
        cheques.emitir_cheque(usuarios["fiduciaria"], sol, "CHQ-1")
    pagos.remitir_a_fiduciaria(usuarios["comite"], sol)
    for quien in ("finanzas", "dir_drff", "comite"):
        with pytest.raises(PermissionDenied):
            cheques.emitir_cheque(usuarios[quien], sol, "CHQ-1")
    assert not Cheque.objects.exists()


def test_hu_5_3_solo_la_fiduciaria_envia_y_una_vez(remitida, usuarios):
    exp, sol = remitida()
    c = cheques.emitir_cheque(usuarios["fiduciaria"], sol, "CHQ-3")
    for quien in ("finanzas", "dir_drff"):
        with pytest.raises(PermissionDenied):
            cheques.enviar_a_delegacion(usuarios[quien], c)
    cheques.enviar_a_delegacion(usuarios["fiduciaria"], c)
    with pytest.raises(ValidationError, match="ya se envió"):
        cheques.enviar_a_delegacion(usuarios["fiduciaria"], c)


# ----------------------------------------------------------------------------- entrega (criterio 2)
def test_hu_5_3_existe_la_fecha_de_entrega_de_cada_cheque(remitida, usuarios):
    """Criterio 2: la Delegación registra la entrega con fecha y hora, quién recibe, acuse y el hito entrega_cheque."""
    exp, sol = remitida()
    c = cheques.emitir_cheque(usuarios["fiduciaria"], sol, "CHQ-4")
    deleg = delegado_de(usuarios, exp)
    with pytest.raises(ValidationError, match="todavía no llega"):
        cheques.registrar_entrega(deleg, c, "Persona")
    cheques.enviar_a_delegacion(usuarios["fiduciaria"], c)
    with pytest.raises(ValidationError, match="Indique quién recibe"):
        cheques.registrar_entrega(deleg, c, " ")
    with pytest.raises(ValidationError, match="futuras"):
        cheques.registrar_entrega(deleg, c, "Persona", entregado_en=timezone.now() + timedelta(hours=2))
    c = cheques.registrar_entrega(deleg, c, exp.solicitante.nombre)
    exp.refresh_from_db()
    sol.refresh_from_db()
    assert c.entregado_en and c.recibe_nombre == exp.solicitante.nombre and c.acuse_entrega.tipo == "entrega_cheque"
    assert exp.estado.clave == "cheque_entregado" and sol.estado == EstadoSolicitud.PAGADA
    hito = Hito.objects.get(expediente=exp, clave="entrega_cheque")
    assert hito.fecha_hora == c.entregado_en and hito.referencia == "CHQ-4"
    with pytest.raises(ValidationError, match="ya se entregó"):
        cheques.registrar_entrega(deleg, c, "Otra")


def test_hu_5_3_solo_la_delegacion_del_cheque_lo_entrega(remitida, usuarios):
    exp, sol = remitida()
    c = cheques.emitir_cheque(usuarios["fiduciaria"], sol, "CHQ-5")
    cheques.enviar_a_delegacion(usuarios["fiduciaria"], c)
    for quien in ("fiduciaria", "dir_drff", "finanzas"):
        with pytest.raises(PermissionDenied):
            cheques.registrar_entrega(usuarios[quien], c, "X")
    otra = next(u for u in usuarios.values() if u.tipo_unidad == "delegacion" and u.unidad_id != exp.delegacion_id)
    with pytest.raises((PermissionDenied, ValidationError)):
        cheques.registrar_entrega(otra, c, "X")


# ----------------------------------------------------------------------------- cobro en 3 meses
def test_hu_5_3_el_cobro_vence_a_los_3_meses_de_la_entrega(entregado):
    exp, c = entregado()
    v = cheques.vencimiento_cobro(c)
    assert v.plazo.cantidad == 3 and v.plazo.unidad == "meses" and c.vence_cobro == v.vencimiento
    assert 85 <= (c.vence_cobro - timezone.localdate()).days <= 93 and v.estado() == "en plazo"


def test_hu_5_3_se_registra_que_el_cheque_fue_cobrado(entregado, usuarios):
    exp, c = entregado()
    with pytest.raises(PermissionDenied):
        cheques.registrar_cobro(usuarios["finanzas"], c)
    with pytest.raises(ValidationError, match="futura"):
        cheques.registrar_cobro(usuarios["fiduciaria"], c, timezone.localdate() + timedelta(days=1))
    c = cheques.registrar_cobro(usuarios["fiduciaria"], c)
    assert c.cobrado_en == timezone.localdate() and c.situacion == "Cobrado"
    with pytest.raises(ValidationError, match="ya está registrado como cobrado"):
        cheques.registrar_cobro(usuarios["fiduciaria"], c)
    assert exp.eventos.filter(tipo="cheque_cobrado").exists()


def _envejecer(c, dias):
    antes = timezone.now() - timedelta(days=dias)
    c.entregado_en = antes
    c.vence_cobro = cheques.vencimiento_cobro(c).vencimiento
    c.save(update_fields=["entregado_en", "vence_cobro"])
    Hito.objects.filter(expediente=c.expediente, clave="entrega_cheque").update(fecha_hora=antes)


def test_hu_5_3_revisar_plazos_avisa_de_los_cheques_por_vencer_y_vencidos_una_vez(entregado, usuarios):
    exp, c = entregado()
    assert cheques.revisar_cobros(timezone.localdate()) == 0  # en plazo
    _envejecer(c, 88)
    call_command("revisar_plazos")
    call_command("revisar_plazos")
    assert exp.eventos.filter(tipo="cheque_por_vencer").count() == 1
    _envejecer(c, 120)
    call_command("revisar_plazos")
    c.refresh_from_db()
    assert exp.eventos.filter(tipo="cheque_vencido").count() == 1 and c.aviso_cobro == "vencido"
    assert exp.estado.clave == "cheque_entregado"  # solo aviso: la baja es del sprint 3
    with pytest.raises(ValidationError, match="venció"):
        cheques.registrar_cobro(usuarios["fiduciaria"], c)


def test_hu_5_3_un_cheque_cobrado_ya_no_se_avisa(entregado, usuarios):
    exp, c = entregado()
    cheques.registrar_cobro(usuarios["fiduciaria"], c)
    _envejecer(c, 120)
    assert cheques.revisar_cobros(timezone.localdate()) == 0


def test_hu_5_3_la_segunda_ministracion_se_pide_con_el_cheque_entregado(entregado, usuarios, monkeypatch):
    from pagos import solicitudes
    from pruebas.fixtures_m5 import instruir_pago

    exp, c = entregado()
    monkeypatch.setitem(solicitudes.FUENTES, "verificacion_campo", lambda e, n: (True, "Verificada.", "V-1", ""))
    instruir_pago(usuarios, exp, 2)
    sol2 = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 2)
    assert sol2.ministracion == 2 and sol2.importe == Decimal("31500.00")


# ----------------------------------------------------------------------------- pantallas
def test_hu_5_3_pantallas_de_la_fiduciaria_y_de_la_delegacion(client, remitida, usuarios, contrasena):
    exp, sol = remitida()
    client.login(username="fiduciaria", password=contrasena)
    html = client.get("/bandeja/").content.decode()
    assert 'data-prueba="panel-cheques-por-emitir"' in html and exp.folio in html
    assert "Emitir el cheque" in client.get(f"/recepcion/expediente/{exp.folio}/").content.decode()
    pestana = f"/recepcion/expediente/{exp.folio}/?pestana=pagos"
    assert 'data-prueba="form-emision-m1"' in client.get(pestana).content.decode()
    r = client.post(f"/pagos/cheques/solicitud/{sol.pk}/emitir/", {
        "numero": "CHQ-8001", "importe": "73500.00", "fecha_emision": timezone.localdate().isoformat()}, follow=True)
    assert 'data-prueba="cheque-m1"' in r.content.decode() and "CHQ-8001" in r.content.decode()
    c = Cheque.objects.get()
    r = client.post(f"/pagos/cheques/{c.pk}/enviar/", follow=True)
    assert 'data-prueba="envio-cheque"' in r.content.decode()
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    assert 'data-prueba="panel-cheques-por-entregar"' in client.get("/bandeja/").content.decode()
    r = client.post(f"/pagos/cheques/{c.pk}/entregar/", {"recibe_nombre": "Felipe Hernández Ramos"}, follow=True)
    html = r.content.decode()
    assert 'data-prueba="entrega-cheque"' in html and "Debe cobrarlo a más tardar" in html
    r = client.post(f"/pagos/cheques/{c.pk}/cobro/", {}, follow=True)
    assert "Cobrado el" in r.content.decode()
    assert "CHQ-8001" in client.get("/pagos/cheques/").content.decode()
    assert any(m["url"] == "pagos:cheques" for m in extensiones.MENU)


def test_hu_5_3_pantalla_rechaza_cheque_con_importe_distinto(client, remitida, usuarios, contrasena):
    exp, sol = remitida()
    client.login(username="fiduciaria", password=contrasena)
    r = client.post(f"/pagos/cheques/solicitud/{sol.pk}/emitir/", {
        "numero": "CHQ-1", "importe": "5.00", "fecha_emision": timezone.localdate().isoformat()}, follow=True)
    assert "debe ser igual al solicitado" in r.content.decode() and not Cheque.objects.exists()


def test_hu_5_3_otras_unidades_ven_los_cheques_pero_no_actuan(client, entregado, usuarios, contrasena):
    exp, c = entregado()
    for usuario in ("finanzas", "dir_drff"):
        client.login(username=usuario, password=contrasena)
        html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=pagos").content.decode()
        assert 'data-prueba="cheque-m1"' in html and "Registrar que fue cobrado" not in html
        assert client.post(f"/pagos/cheques/{c.pk}/cobro/").status_code in (302, 403, 404)
    c.refresh_from_db()
    assert not c.cobrado
