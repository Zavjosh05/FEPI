"""HU-5.2 · Pago de la ministración (y, en PSAHEM, remisión a la Fiduciaria; R-16)."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.utils import timezone

from nucleo import extensiones, notificaciones, plazos
from nucleo.models import Evento, Hito, Notificacion, Transicion, TransicionNoPermitida, bandeja
from pagos import pagos, solicitudes
from pagos.models import EstadoSolicitud, Pago, RemisionFiduciaria, RevisionSolicitud, SolicitudPago

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def pagar(usuarios, sol, **kw):
    datos = dict(referencia="SPEI-0001", fecha_pago=timezone.localdate())
    datos.update(kw)
    return pagos.registrar_pago(usuarios["finanzas"], sol, **datos)


def test_hu_5_2_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-5.2")
    assert hu["criterios"] == ["Cada pago está asociado a su solicitud, con la fecha del pago.",
                               "En PSAHEM existe la fecha de remisión a la Fiduciaria."]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M5.2")
    assert {"CC-AF-01", "PSA-AF-01", "PEG-AF-01"} <= set(funcion["necesidades"])
    assert "10.1, fr. XIV" in necesidades["PSA-AF-01"]["texto"]


# ----------------------------------------------------------------------------- revisión
def test_hu_5_2_administracion_y_finanzas_acepta_la_solicitud_con_acuse(solicitada, usuarios):
    exp = solicitada("CC")
    sol = exp.solicitudes_pago.get()
    r = pagos.revisar_solicitud(usuarios["finanzas"], sol, "aceptada")
    sol.refresh_from_db()
    exp.refresh_from_db()
    assert sol.estado == EstadoSolicitud.ACEPTADA and exp.estado.clave == "ministracion_solicitada"
    assert r.resultado == "aceptada" and r.acuse.tipo == "revision_solicitud_pago" and r.envio == 1
    assert exp.eventos.filter(tipo="solicitud_pago_aceptada", acuse=r.acuse).exists()
    with pytest.raises(ValidationError, match="solo se revisa una solicitud enviada"):
        pagos.revisar_solicitud(usuarios["finanzas"], sol, "aceptada")


def test_hu_5_2_solo_administracion_y_finanzas_revisa_y_solo_lo_que_ve(solicitada, usuarios):
    exp = solicitada("CC")
    sol = exp.solicitudes_pago.get()
    for quien in ("dir_drff", "comite", "juridica", "fiduciaria"):
        with pytest.raises(PermissionDenied):
            pagos.revisar_solicitud(usuarios[quien], sol, "aceptada")
    with pytest.raises(ValidationError, match="aceptan o se devuelven|si la solicitud se acepta"):
        pagos.revisar_solicitud(usuarios["finanzas"], sol, "quizá")


def test_hu_5_2_no_se_acepta_una_solicitud_cuyos_soportes_ya_no_estan_completos(solicitada, usuarios):
    exp = solicitada("CC")
    exp.oficio_pago.delete()
    exp.refresh_from_db()
    with pytest.raises(ValidationError, match="No se acepta la solicitud: falta Oficio de solicitud de pago"):
        pagos.revisar_solicitud(usuarios["finanzas"], exp.solicitudes_pago.get(), "aceptada")


def test_hu_5_2_devuelve_con_observaciones_y_el_area_la_corrige_y_la_reenvia(solicitada, usuarios):
    exp = solicitada("CC")
    sol = exp.solicitudes_pago.get()
    with pytest.raises(ValidationError, match="observaciones"):
        pagos.revisar_solicitud(usuarios["finanzas"], sol, "devuelta", "  ")
    r = pagos.revisar_solicitud(usuarios["finanzas"], sol, "devuelta", "El comprobante no es legible.")
    sol.refresh_from_db()
    exp.refresh_from_db()
    assert sol.estado == EstadoSolicitud.DEVUELTA and exp.estado.clave == "contratada"
    evento = exp.eventos.get(tipo="solicitud_pago_devuelta")
    assert evento.motivo == "El comprobante no es legible." and evento.acuse == r.acuse
    assert exp in bandeja(usuarios["dir_drff"]) and exp not in bandeja(usuarios["finanzas"])
    with pytest.raises(ValidationError, match="solo se paga una solicitud aceptada"):
        pagar(usuarios, sol)
    sol2 = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1, "Comprobante nuevo.")
    assert sol2.pk == sol.pk and sol2.envios == 2 and sol2.estado == EstadoSolicitud.ENVIADA
    pagos.revisar_solicitud(usuarios["finanzas"], sol2, "aceptada")
    assert [x.resultado for x in RevisionSolicitud.objects.filter(solicitud=sol).order_by("id")] == ["devuelta", "aceptada"]


# ----------------------------------------------------------------------------- criterio 1: pago asociado a su solicitud
@pytest.mark.parametrize("programa", ["CC", "PS", "RHF"])
def test_hu_5_2_cada_pago_esta_asociado_a_su_solicitud_con_la_fecha_del_pago(programa, aceptada, usuarios):
    """Criterio 1: el pago cuelga de la solicitud aceptada, con su fecha, importe igual al solicitado y acuse."""
    exp, sol = aceptada(programa)
    hoy = timezone.localdate()
    pago = pagar(usuarios, sol, referencia="SPEI-778899", fecha_pago=hoy)
    sol.refresh_from_db()
    exp.refresh_from_db()
    assert pago.solicitud == sol and sol.pago == pago and pago.fecha_pago == hoy and pago.ministracion == 1
    assert pago.importe == sol.importe and pago.tipo == "transferencia" and pago.referencia == "SPEI-778899"
    assert sol.estado == EstadoSolicitud.PAGADA and exp.estado.clave == "pagada"
    assert pago.acuse.tipo == "pago_ministracion" and pago.acuse.archivo
    assert Hito.objects.filter(expediente=exp, clave="pago_ministracion", referencia=sol.folio).exists()
    assert exp.eventos.filter(tipo="pago_ministracion", acuse=pago.acuse).exists()


def test_hu_5_2_la_persona_recibe_el_aviso_de_pago_por_conducto_de_la_delegacion(aceptada, usuarios):
    exp, sol = aceptada("CC")
    pago = pagar(usuarios, sol)
    aviso = pago.aviso
    assert aviso.tipo == "pago" and aviso.delegacion_id == exp.delegacion_id and aviso.notificada_en is None
    assert aviso.enviada_por == usuarios["finanzas"] and aviso.acuse_envio == pago.acuse
    assert aviso in notificaciones.pendientes_de_notificar(exp.delegacion)
    notificaciones.registrar_notificacion(delegado_de(usuarios, exp), aviso, "telefono")
    aviso.refresh_from_db()
    assert aviso.notificada_en and aviso.medio == "telefono" and aviso.acuse_notificacion


def test_hu_5_2_el_importe_debe_ser_igual_al_solicitado_y_las_fechas_validas(aceptada, usuarios):
    exp, sol = aceptada("CC")
    with pytest.raises(ValidationError, match="debe ser igual al solicitado"):
        pagar(usuarios, sol, importe=sol.importe - 1)
    with pytest.raises(ValidationError, match="futura"):
        pagar(usuarios, sol, fecha_pago=timezone.localdate() + timedelta(days=1))
    with pytest.raises(ValidationError, match="anterior al envío"):
        pagar(usuarios, sol, fecha_pago=timezone.localdate() - timedelta(days=3))
    with pytest.raises(ValidationError, match="referencia"):
        pagar(usuarios, sol, referencia=" ")
    assert not Pago.objects.exists()
    assert pagar(usuarios, sol, importe=sol.importe).importe == sol.importe


def test_hu_5_2_la_misma_ministracion_no_se_paga_dos_veces(aceptada, usuarios):
    exp, sol = aceptada("CC")
    pagar(usuarios, sol)
    with pytest.raises(ValidationError, match="no se paga dos veces"):
        pagar(usuarios, sol, referencia="OTRA")
    assert Pago.objects.filter(solicitud=sol).count() == 1


def test_hu_5_2_un_pago_siempre_cuelga_de_una_solicitud_aceptada(solicitada, usuarios):
    exp = solicitada("CC")
    sol = exp.solicitudes_pago.get()
    with pytest.raises(ValidationError, match="solo se paga una solicitud aceptada"):
        pagar(usuarios, sol)  # enviada, todavía sin revisar
    assert not Pago.objects.exists()


def test_hu_5_2_solo_administracion_y_finanzas_paga(aceptada, usuarios):
    exp, sol = aceptada("CC")
    for quien in ("dir_drff", "comite", "fiduciaria", "juridica"):
        with pytest.raises(PermissionDenied):
            pagos.registrar_pago(usuarios[quien], sol, "X-1", timezone.localdate())
    assert not Pago.objects.exists()


def test_hu_5_2_el_cheque_solo_como_caso_excepcional_con_motivo(aceptada, usuarios):
    exp, sol = aceptada("CC")
    with pytest.raises(ValidationError, match="caso excepcional: indique el motivo"):
        pagar(usuarios, sol, tipo="cheque_excepcional", referencia="CHQ-1")
    with pytest.raises(ValidationError, match="Forma de pago no válida"):
        pagar(usuarios, sol, tipo="deposito")  # el depósito es de Guardabosques
    pago = pagar(usuarios, sol, tipo="cheque_excepcional", referencia="CHQ-1", motivo_cheque="Sin cuenta bancaria vigente.")
    assert pago.tipo == "cheque_excepcional" and pago.motivo_cheque and "caso excepcional" in str(
        dict(pago.acuse.contenido["renglones"]).keys())


def test_hu_5_2_segunda_ministracion_tiene_su_propia_solicitud_y_su_propio_pago(aceptada, usuarios, monkeypatch):
    exp, sol = aceptada("CC")
    pagar(usuarios, sol)
    exp.refresh_from_db()
    monkeypatch.setitem(solicitudes.FUENTES, "verificacion_campo", lambda e, n: (True, "Verificada.", "VER-1", ""))
    sol2 = solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 2)
    pagos.revisar_solicitud(usuarios["finanzas"], sol2, "aceptada")
    pago2 = pagar(usuarios, sol2, referencia="SPEI-2")
    assert pago2.solicitud == sol2 and pago2.ministracion == 2 and Pago.objects.filter(expediente=exp).count() == 2
    assert pago2.importe == Decimal("3600.00") and sol.pago != pago2


# ----------------------------------------------------------------------------- Guardabosques: depósito
def test_hu_5_2_peg_el_pago_es_un_deposito_al_guardabosque(peg_contratado, usuarios):
    exp = peg_contratado()
    sol = solicitudes.enviar_solicitud(usuarios["dir_dpf"], exp, 1)
    assert sol.tipo_pago == "deposito" and sol.importe == Decimal("7500.00")
    pagos.revisar_solicitud(usuarios["finanzas"], sol, "aceptada")
    with pytest.raises(ValidationError, match="Forma de pago no válida"):
        pagar(usuarios, sol, tipo="transferencia")
    pago = pagar(usuarios, sol, referencia="DEP-0001")
    assert pago.tipo == "deposito" and pagos.tipos_de_pago(exp) == ["deposito", "cheque_excepcional"]
    exp.refresh_from_db()
    assert exp.estado.clave == "pagada"


# ----------------------------------------------------------------------------- PSAHEM
def test_hu_5_2_psahem_no_se_paga_por_transferencia_sino_por_la_fiduciaria(aceptada, usuarios):
    exp, sol = aceptada("PSA")
    with pytest.raises(ValidationError, match="la Fiduciaria con cheque"):
        pagar(usuarios, sol)
    assert pagos.tipos_de_pago(exp) == []


def test_hu_5_2_r16_las_rop_ponen_la_solicitud_a_la_fiduciaria_en_la_secretaria_tecnica(catalogos):
    """R-16: 10.1 fr. X (líneas 2290 a 2292) la dan a la Secretaría Técnica; Administración y Finanzas no la remite."""
    t = Transicion.objects.get(origen__clave="ministracion_solicitada", destino__clave="remitida_fiduciaria")
    assert t.tipo_unidad == "secretaria_comite" and t.programa.clave == "PSA"
    assert pagos.USO_REMISION == "instruccion_pago_fiduciaria"


def test_hu_5_2_existe_la_fecha_de_remision_a_la_fiduciaria_en_psahem(aceptada, usuarios):
    """Criterio 2: en PSAHEM la remisión queda con fecha y hora, acuse, hito y el plazo de 5 días hábiles."""
    exp, sol = aceptada("PSA")
    antes = timezone.now()
    r = pagos.remitir_a_fiduciaria(usuarios["comite"], sol, "ST-FIPASAHEM/001/2026", "Con la instrucción del Comité.")
    exp.refresh_from_db()
    sol.refresh_from_db()
    assert antes <= r.remitida_en <= timezone.now() and r.recibida_en == sol.enviada_en
    assert exp.estado.clave == "remitida_fiduciaria" and sol.estado == EstadoSolicitud.REMITIDA and sol.remision == r
    assert r.acuse.tipo == "remision_fiduciaria" and "Fecha y hora de la remisión a la Fiduciaria" in dict(r.acuse.contenido["renglones"])
    assert r.vence_el is not None and r.en_plazo and r.vence_el > timezone.localdate()
    hito = Hito.objects.get(expediente=exp, clave="remision_fiduciaria")
    assert hito.fecha_hora == r.remitida_en and hito.referencia == sol.folio
    assert Hito.objects.filter(expediente=exp, clave="solicitud_pago_fiduciaria").exists()  # lo que arrancó el plazo
    assert exp in bandeja(usuarios["fiduciaria"])


def test_hu_5_2_el_plazo_de_5_dias_habiles_se_calcula_desde_la_solicitud_del_area(aceptada, usuarios):
    exp, sol = aceptada("PSA")
    esperado = plazos.vencimiento(exp, "instruccion_pago_fiduciaria", fecha_evento=sol.enviada_en)
    assert esperado.plazo.cantidad == 5 and esperado.plazo.unidad == "dias_habiles"
    tarde = timezone.now() + timedelta(days=20)
    r = pagos.remitir_a_fiduciaria(usuarios["comite"], sol, momento=tarde)
    assert r.vence_el == esperado.vencimiento and not r.en_plazo  # se remite, pero queda señalada fuera de plazo
    assert Hito.objects.get(expediente=exp, clave="remision_fiduciaria").datos["en_plazo"] is False


def test_hu_5_2_solo_la_secretaria_tecnica_remite_y_solo_lo_aceptado(solicitada, usuarios):
    exp = solicitada("PSA")
    sol = exp.solicitudes_pago.get()
    with pytest.raises(ValidationError, match="todavía no acepta"):
        pagos.remitir_a_fiduciaria(usuarios["comite"], sol)
    pagos.revisar_solicitud(usuarios["finanzas"], sol, "aceptada")
    for quien in ("finanzas", "dir_drff", "fiduciaria"):
        with pytest.raises(PermissionDenied):
            pagos.remitir_a_fiduciaria(usuarios[quien], sol)
    with pytest.raises(TransicionNoPermitida):  # la tabla de estados tampoco se lo permite a Administración y Finanzas
        exp.cambiar_estado("remitida_fiduciaria", usuarios["finanzas"])
    pagos.remitir_a_fiduciaria(usuarios["comite"], sol)
    with pytest.raises(ValidationError, match="ya se remitió"):
        pagos.remitir_a_fiduciaria(usuarios["comite"], sol)


def test_hu_5_2_fuera_de_psahem_no_hay_remision_a_la_fiduciaria(aceptada, usuarios):
    exp, sol = aceptada("CC")
    with pytest.raises(ValidationError, match="solo PSAHEM"):
        pagos.remitir_a_fiduciaria(usuarios["comite"], sol)
    assert not RemisionFiduciaria.objects.exists()


def test_hu_5_2_revisar_plazos_senala_una_vez_la_remision_vencida(aceptada, usuarios):
    exp, sol = aceptada("PSA")
    SolicitudPago.objects.filter(pk=sol.pk).update(enviada_en=timezone.now() - timedelta(days=30))
    call_command("revisar_plazos")
    call_command("revisar_plazos")
    assert exp.eventos.filter(tipo="remision_vencida").count() == 1
    pagos.remitir_a_fiduciaria(usuarios["comite"], sol)
    assert pagos.revisar_remisiones(timezone.localdate()) == 0  # ya remitida


# ----------------------------------------------------------------------------- pantallas
def test_hu_5_2_pantallas_de_administracion_y_finanzas(client, solicitada, usuarios, contrasena):
    exp = solicitada("CC")
    sol = exp.solicitudes_pago.get()
    client.login(username="finanzas", password=contrasena)
    html = client.get("/bandeja/").content.decode()
    assert 'data-prueba="panel-por-revisar"' in html and exp.folio in html
    assert "Revisar la solicitud de pago de la ministración 1" in client.get(f"/recepcion/expediente/{exp.folio}/").content.decode()
    assert 'data-prueba="form-revision-m1"' in client.get(f"/recepcion/expediente/{exp.folio}/?pestana=pagos").content.decode()
    r = client.post(f"/pagos/solicitud-pago/{sol.pk}/revisar/", {"resultado": "devuelta", "observaciones": ""}, follow=True)
    assert "indique las observaciones" in r.content.decode()
    r = client.post(f"/pagos/solicitud-pago/{sol.pk}/revisar/", {"resultado": "aceptada"}, follow=True)
    assert "aceptada" in r.content.decode() and 'data-prueba="form-pago-m1"' in r.content.decode()
    assert 'data-prueba="panel-por-pagar"' in client.get("/bandeja/").content.decode()
    r = client.post(f"/pagos/solicitud-pago/{sol.pk}/pagar/", {
        "tipo": "transferencia", "referencia": "SPEI-55", "fecha_pago": timezone.localdate().isoformat(),
        "importe": "8400.00"}, follow=True)
    html = r.content.decode()
    assert 'data-prueba="pago-m1"' in html and "SPEI-55" in html and "Pagada" in html
    lista = client.get("/pagos/revision/").content.decode()
    assert 'data-prueba="pagos-registrados"' in lista and "SPEI-55" in lista
    assert Pago.objects.get().importe == Decimal("8400.00")


def test_hu_5_2_pantalla_rechaza_un_importe_distinto(client, aceptada, usuarios, contrasena):
    exp, sol = aceptada("CC")
    client.login(username="finanzas", password=contrasena)
    r = client.post(f"/pagos/solicitud-pago/{sol.pk}/pagar/", {
        "tipo": "transferencia", "referencia": "SPEI-1", "fecha_pago": timezone.localdate().isoformat(),
        "importe": "100.00"}, follow=True)
    assert "debe ser igual al solicitado" in r.content.decode() and not Pago.objects.exists()


def test_hu_5_2_pantallas_de_la_secretaria_tecnica_y_filtro_de_la_bandeja(client, aceptada, usuarios, contrasena):
    exp, sol = aceptada("PSA")
    assert exp not in bandeja(usuarios["finanzas"])  # aceptada: ya espera a la Secretaría Técnica
    client.login(username="comite", password=contrasena)
    assert 'data-prueba="panel-por-remitir"' in client.get("/bandeja/").content.decode()
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=pagos").content.decode()
    assert 'data-prueba="form-remision-m1"' in html and 'data-prueba="plazo-remision"' in html
    r = client.post(f"/pagos/solicitud-pago/{sol.pk}/remitir/", {"oficio": "ST/001"}, follow=True)
    html = r.content.decode()
    assert 'data-prueba="remision-m1"' in html and "en plazo" in html and "ST/001" in html
    assert any(m["url"] == "pagos:pagos" for m in extensiones.MENU)
    client.login(username="finanzas", password=contrasena)
    assert "Pagos solicitados a la Fiduciaria" in client.get("/pagos/revision/").content.decode()


def test_hu_5_2_la_delegacion_y_la_direccion_ven_el_pago_en_la_pestana(client, aceptada, usuarios, contrasena):
    exp, sol = aceptada("CC")
    pagar(usuarios, sol, referencia="SPEI-99")
    for usuario in (delegado_de(usuarios, exp).username, "dir_drff", "juridica"):
        client.login(username=usuario, password=contrasena)
        html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=pagos").content.decode()
        assert 'data-prueba="pago-m1"' in html and "SPEI-99" in html, usuario
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    assert "Notificar el pago a la persona beneficiaria" in client.get(f"/recepcion/expediente/{exp.folio}/").content.decode()
