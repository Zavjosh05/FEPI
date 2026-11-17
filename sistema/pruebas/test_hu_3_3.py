"""HU-3.3 · Firma del contrato."""
from datetime import timedelta
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.utils import timezone

from contrato import firma
from contrato.models import ElementoFormalizacion, FirmaContrato, SinFirma
from nucleo import extensiones, plazos
from nucleo.models import Evento, Hito, Notificacion, bandeja

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def verificar(exp):
    return [p["clave"] for p in firma.puntos_de_verificacion(exp)]


def firmar(usuarios, exp, pdf, **kw):
    """Registra la firma con todo lo necesario (la Delegación del expediente)."""
    deleg = delegado_de(usuarios, exp)
    elementos = {e["clave"]: {"archivo": pdf(f"{e['clave']}.pdf"), "dato": "RFN-123" if e.get("dato") else ""}
                 for e in firma.formalizacion_propia(exp)["elementos"]}
    datos = dict(firmado_en=None, firmante="persona", firmante_nombre=exp.solicitante.nombre, archivo=pdf("firmado.pdf"),
                 verificacion=verificar(exp), elementos=elementos)
    datos.update(kw)
    return firma.registrar_firma(deleg, exp, **datos)


def vencer(exp, dias=40):
    """Hace que la publicación y la notificación sean de hace ``dias`` días (para vencer los plazos)."""
    Hito.objects.filter(expediente=exp, clave="publicacion_resultados").update(
        fecha_hora=timezone.now() - timedelta(days=dias))
    Notificacion.objects.filter(expediente=exp, tipo="resultados").update(
        notificada_en=timezone.now() - timedelta(days=dias), enviada_en=timezone.now() - timedelta(days=dias + 1))


def test_hu_3_3_criterios_y_necesidades_vienen_del_modelo(modelo):
    hu = historia(modelo, "HU-3.3")
    assert "fecha y la hora de la firma" in hu["criterios"][0] and "credencial" in hu["criterios"][1]
    assert "señalado para liberar el recurso" in hu["criterios"][2]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M3.3")
    assert "PEG-DRF-02" in funcion["necesidades"] and "MFS-PSF-02" in funcion["necesidades"]


# ----------------------------------------------------------------------------- criterio 1
@pytest.mark.pdf_real
def test_hu_3_3_existe_el_contrato_firmado_con_fecha_hora_y_dentro_del_plazo(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    antes = timezone.now()
    f = firmar(usuarios, exp, pdf)
    exp.refresh_from_db()
    assert exp.estado.clave == "contratada"
    assert f.firmado_en >= antes and f.firmado_en <= timezone.now() and f.dentro_de_plazo
    assert f.archivo.read().startswith(b"%PDF") and len(f.huella) == 64
    assert f.contrato == exp.contrato and f.firmante == "persona"
    assert f.acuse and f.acuse.tipo == "firma_contrato" and f.acuse.archivo
    hito = exp.hitos.get(clave="firma_contrato")
    assert hito.fecha_hora == f.firmado_en and hito.referencia == exp.contrato.folio
    assert exp.eventos.filter(tipo="contrato_firmado", acuse=f.acuse).exists()
    assert f.en_fecha_programada and f.fecha_programada and f.fecha_liberacion


def test_hu_3_3_la_firma_registra_quien_firma_y_la_fecha_hora_indicadas(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    enviado = exp.contrato.enviado_en
    momento = enviado + (timezone.now() - enviado) / 2
    f = firmar(usuarios, exp, pdf, firmado_en=momento, firmante="representante", firmante_nombre="Ana Pérez (apoderada)")
    assert f.firmado_en == momento and f.firmante == "representante" and "apoderada" in f.firmante_nombre


def test_hu_3_3_la_firma_no_puede_ser_futura_ni_anterior_al_envio_del_contrato(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    with pytest.raises(ValidationError, match="futuras"):
        firmar(usuarios, exp, pdf, firmado_en=timezone.now() + timedelta(hours=2))
    with pytest.raises(ValidationError, match="anterior al envío"):
        firmar(usuarios, exp, pdf, firmado_en=exp.contrato.enviado_en - timedelta(hours=1))
    assert not FirmaContrato.objects.exists() and exp.estado.clave == "contrato_en_delegacion"


def test_hu_3_3_el_contrato_firmado_digitalizado_es_obligatorio(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    with pytest.raises(ValidationError, match="Falta el archivo"):
        firmar(usuarios, exp, pdf, archivo=None)
    with pytest.raises(ValidationError, match="PDF, JPG o PNG"):
        firmar(usuarios, exp, pdf, archivo=pdf("contrato.exe"))


def test_hu_3_3_se_verifican_las_firmas_y_el_sello_y_sin_todos_los_puntos_no_se_recibe(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    puntos = verificar(exp)
    assert puntos == ["firma_persona", "firma_probosque"]
    with pytest.raises(ValidationError, match="Falta verificar: Firma por PROBOSQUE"):
        firmar(usuarios, exp, pdf, verificacion=puntos[:1])
    f = firmar(usuarios, exp, pdf)
    assert [p["clave"] for p in f.verificacion] == puntos and all(p["cumple"] for p in f.verificacion)


def test_hu_3_3_los_puntos_de_verificacion_salen_de_los_datos_por_tipo_de_persona():
    def tipo(clave):
        return SimpleNamespace(tipo_persona=SimpleNamespace(clave=clave))

    assert [p["clave"] for p in firma.puntos_de_verificacion(tipo("nucleo_agrario"))] == [
        "firma_presidencia", "firma_secretaria", "firma_tesoreria", "sello_nucleo", "firma_probosque"]
    assert [p["clave"] for p in firma.puntos_de_verificacion(tipo("juridica_colectiva"))][0] == "firma_representante"
    assert firma.puntos_de_verificacion(tipo("dependencia_publica")) == firma.puntos_de_verificacion(tipo("juridica_colectiva"))
    assert firma.puntos_de_verificacion(tipo("algo_nuevo")) == firma.puntos_de_verificacion(tipo("fisica"))


def test_hu_3_3_solo_la_delegacion_del_expediente_registra_la_firma(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    for quien in ("dir_drff", "juridica", "comite", "vivero"):
        with pytest.raises(PermissionDenied):
            firma.registrar_firma(usuarios[quien], exp, None, "persona", "X", pdf(), verificar(exp))
    otra = usuarios["del_toluca"]
    with pytest.raises(PermissionDenied):
        firma.registrar_firma(otra, exp, None, "persona", "X", pdf(), verificar(exp))


def test_hu_3_3_solo_se_firma_un_contrato_que_ya_esta_en_la_delegacion(notificadas, usuarios, pdf):
    _, (exp,) = notificadas("PS")
    with pytest.raises(ValidationError, match="solo se registra la firma"):
        firma.registrar_firma(delegado_de(usuarios, exp), exp, None, "persona", "X", pdf(), [])


def test_hu_3_3_no_se_firma_dos_veces(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    firmar(usuarios, exp, pdf)
    with pytest.raises(ValidationError, match="solo se registra la firma"):
        firmar(usuarios, exp, pdf)


# ----------------------------------------------------------------------------- dos fechas (R-03)
def test_hu_3_3_las_dos_fechas_vienen_de_la_configuracion_por_programa(en_delegacion):
    _, (exp,) = en_delegacion("PS")
    programada, liberacion = firma.fechas_de_firma(exp)
    assert programada.uso == "firma_programada" and liberacion.uso == "firma_liberacion"
    assert programada.tiene_fecha and liberacion.tiene_fecha
    assert programada.evento == "notificacion_persona" and liberacion.evento == "publicacion_resultados"  # PS (R-13)


def test_hu_3_3_firma_posterior_a_la_programada_y_anterior_a_la_de_liberacion_es_valida_y_se_marca(
        en_delegacion, usuarios, pdf):
    # CC: la programada corre desde la publicación y la de liberación desde la notificación.
    _, (exp,) = en_delegacion("CC")
    Hito.objects.filter(expediente=exp, clave="publicacion_resultados").update(
        fecha_hora=timezone.now() - timedelta(days=25))
    programada, liberacion = firma.fechas_de_firma(exp)
    assert programada.vencimiento < timezone.localdate() < liberacion.vencimiento
    f = firmar(usuarios, exp, pdf)
    exp.refresh_from_db()
    assert exp.estado.clave == "contratada" and f.dentro_de_plazo and not f.en_fecha_programada
    assert f.situacion == "Fuera de la fecha programada"
    assert ("Dentro del plazo, fuera de la fecha programada", ) == tuple(
        v for k, v in [tuple(r) for r in f.acuse.contenido["renglones"]] if k == "Situación")


def test_hu_3_3_firma_despues_del_vencimiento_para_liberar_el_recurso_no_se_recibe(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    vencer(exp)
    with pytest.raises(ValidationError, match="vencimiento para liberar el recurso"):
        firmar(usuarios, exp, pdf)
    exp.refresh_from_db()
    assert exp.estado.clave == "contrato_en_delegacion" and not FirmaContrato.objects.exists()


def test_hu_3_3_los_dias_que_faltan_cuentan_dias_habiles(en_delegacion):
    _, (exp,) = en_delegacion("PS")
    _, liberacion = firma.fechas_de_firma(exp)
    assert firma.dias_que_faltan(liberacion) == 10 or 8 <= firma.dias_que_faltan(liberacion) <= 10
    assert firma.dias_que_faltan(liberacion, liberacion.vencimiento + timedelta(days=7)) < 0
    assert firma.dias_que_faltan(None) is None


# ----------------------------------------------------------------------------- criterio 2: MFS y PEG
def test_hu_3_3_mfs_exige_contrato_de_servicios_tecnicos_con_rfn_y_carta_compromiso(mfs, contrato_manual, usuarios, pdf):
    exp = contrato_manual(mfs, tipo="fisica", modalidad=None)
    clavep = [e["clave"] for e in firma.formalizacion_propia(exp)["elementos"]]
    assert clavep == ["contrato_servicios_tecnicos", "carta_compromiso_psf"]
    deleg = delegado_de(usuarios, exp)
    base = dict(firmado_en=None, firmante="persona", firmante_nombre="Persona MFS", archivo=pdf(), verificacion=verificar(exp))
    with pytest.raises(ValidationError, match="Falta el archivo: Contrato de servicios técnicos"):
        firma.registrar_firma(deleg, exp, **base)
    sin_rfn = {"contrato_servicios_tecnicos": {"archivo": pdf(), "dato": ""}, "carta_compromiso_psf": {"archivo": pdf(), "dato": ""}}
    with pytest.raises(ValidationError, match="RFN del prestador"):
        firma.registrar_firma(deleg, exp, elementos=sin_rfn, **base)
    solo_contrato = {"contrato_servicios_tecnicos": {"archivo": pdf(), "dato": "RFN-45"}}
    with pytest.raises(ValidationError, match="Carta compromiso"):
        firma.registrar_firma(deleg, exp, elementos=solo_contrato, **base)
    assert exp.estado.clave == "contrato_en_delegacion" or not FirmaContrato.objects.exists()
    completos = {"contrato_servicios_tecnicos": {"archivo": pdf(), "dato": "RFN-45"}, "carta_compromiso_psf": {"archivo": pdf(), "dato": ""}}
    f = firma.registrar_firma(deleg, exp, elementos=completos, **base)
    exp.refresh_from_db()
    assert exp.estado.clave == "contratada"
    por_clave = {e.clave: e for e in f.elementos.all()}
    assert por_clave["contrato_servicios_tecnicos"].dato == "RFN-45" and por_clave["carta_compromiso_psf"].archivo
    assert "RFN-45" in " ".join(v for _, v in f.acuse.contenido["renglones"])


def test_hu_3_3_peg_exige_la_credencial_del_guardabosque_entregada(peg, contrato_manual, usuarios, pdf):
    exp = contrato_manual(peg, direccion="dir_dpf", **PEG_SOLICITUD)
    assert [e["clave"] for e in firma.formalizacion_propia(exp)["elementos"]] == ["credencial_guardabosque"]
    deleg = delegado_de(usuarios, exp)
    base = dict(firmado_en=None, firmante="persona", firmante_nombre="Guardabosque", archivo=pdf(), verificacion=verificar(exp))
    with pytest.raises(ValidationError, match="Credencial del Guardabosque"):
        firma.registrar_firma(deleg, exp, **base)
    with pytest.raises(ValidationError, match="Folio de la credencial"):
        firma.registrar_firma(deleg, exp, elementos={"credencial_guardabosque": {"archivo": pdf(), "dato": ""}}, **base)
    f = firma.registrar_firma(deleg, exp, elementos={"credencial_guardabosque": {"archivo": pdf(), "dato": "CRED-0007"}}, **base)
    exp.refresh_from_db()
    assert exp.estado.clave == "contratada" and f.elementos.get().dato == "CRED-0007"


def test_hu_3_3_los_programas_con_reglas_no_piden_formalizacion_propia(en_delegacion):
    for programa in ("CC", "PS", "RHF", "PSA"):
        _, (exp,) = en_delegacion(programa)
        assert firma.formalizacion_propia(exp)["elementos"] == []


# ----------------------------------------------------------------------------- criterio 3: sin firma al vencer
def test_hu_3_3_un_contrato_sin_firma_al_vencer_el_plazo_queda_senalado_para_liberar_el_recurso(en_delegacion, usuarios):
    _, (vigente, vencido) = en_delegacion("PS", cuantas=2)
    vencer(vencido)
    n = firma.revisar_firmas(timezone.localdate())
    assert n == 1
    vigente.refresh_from_db(); vencido.refresh_from_db()
    assert vigente.estado.clave == "contrato_en_delegacion" and vencido.estado.clave == "sin_firma_en_plazo"
    s = SinFirma.objects.get()
    assert s.expediente == vencido and s.vencio_el < timezone.localdate() and not s.liberado
    ev = vencido.eventos.get(tipo="sin_firma_en_plazo")
    assert ev.usuario is None and "Venció el" in ev.motivo and ev.estado_destino.clave == "sin_firma_en_plazo"
    assert vencido in bandeja(usuarios["dir_drff"])  # aviso en la bandeja de la Dirección
    assert firma.revisar_firmas(timezone.localdate()) == 0  # una sola vez


def test_hu_3_3_el_senalamiento_alcanza_los_contratos_aun_no_enviados(notificadas):
    _, (exp,) = notificadas("PS")
    vencer(exp)
    assert firma.revisar_firmas(timezone.localdate()) == 1
    exp.refresh_from_db()
    assert exp.estado.clave == "sin_firma_en_plazo"


def test_hu_3_3_revisar_plazos_senala_los_contratos_sin_firma(en_delegacion):
    _, (exp,) = en_delegacion("RHF")
    Notificacion.objects.filter(expediente=exp, tipo="resultados").update(notificada_en=timezone.now() - timedelta(days=40))
    call_command("revisar_plazos")
    exp.refresh_from_db()
    assert exp.estado.clave == "sin_firma_en_plazo" and firma.revisar_firmas in extensiones.REVISIONES_PLAZO


def test_hu_3_3_sin_fecha_de_liberacion_no_se_senala(notificadas):
    _, (exp,) = notificadas("CC")
    Notificacion.objects.filter(expediente=exp).update(notificada_en=None)
    assert firma.revisar_firmas(timezone.localdate() + timedelta(days=400)) == 0


def test_hu_3_3_una_firma_cuando_ya_esta_senalado_se_rechaza_con_un_mensaje_claro(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("PS")
    vencer(exp)
    firma.revisar_firmas(timezone.localdate())
    with pytest.raises(ValidationError, match="ya está señalado como «sin firma en plazo»"):
        firmar(usuarios, exp, pdf)


def test_hu_3_3_liberar_el_recurso_no_es_automatico_y_lo_confirma_el_area_responsable_con_un_motivo(
        en_delegacion, usuarios):
    _, (exp,) = en_delegacion("PS")
    vencer(exp)
    firma.revisar_firmas(timezone.localdate())
    exp.refresh_from_db()
    assert exp.estado.clave == "sin_firma_en_plazo"  # no se libera solo
    for quien in ("del_amecameca", "juridica", "vivero"):
        with pytest.raises(PermissionDenied):
            firma.liberar_recurso(usuarios[quien], exp, "motivo")
    with pytest.raises(ValidationError, match="motivo"):
        firma.liberar_recurso(usuarios["dir_drff"], exp, "  ")
    llamadas = []
    extensiones.AL_LIBERAR_RECURSO.append(lambda e, u: llamadas.append((e.pk, u.username)))
    try:
        s = firma.liberar_recurso(usuarios["dir_drff"], exp, "La persona no acudió a firmar.")
    finally:
        extensiones.AL_LIBERAR_RECURSO.pop()
    exp.refresh_from_db()
    assert exp.estado.clave == "recurso_liberado" and s.liberado and s.liberado_por == usuarios["dir_drff"]
    assert s.acuse_liberacion and "Pendiente" in " ".join(v for _, v in s.acuse_liberacion.contenido["renglones"])
    assert llamadas == [(exp.pk, "dir_drff")]
    assert exp.eventos.filter(tipo="recurso_liberado", motivo="La persona no acudió a firmar.").exists()
    with pytest.raises(ValidationError, match="Solo se libera"):
        firma.liberar_recurso(usuarios["dir_drff"], exp, "otra vez")


def test_hu_3_3_no_se_libera_lo_que_no_esta_senalado(en_delegacion, usuarios):
    _, (exp,) = en_delegacion("PS")
    with pytest.raises(ValidationError, match="Solo se libera"):
        firma.liberar_recurso(usuarios["dir_drff"], exp, "motivo")


def test_hu_3_3_cambiar_estado_por_sistema_exige_que_la_transicion_exista(en_delegacion):
    from nucleo.models import TransicionNoPermitida

    _, (exp,) = en_delegacion("PS")
    with pytest.raises(TransicionNoPermitida):
        exp.cambiar_estado("pagada", None, por_sistema=True)


# ----------------------------------------------------------------------------- los cuatro programas
@pytest.mark.parametrize("programa", ["CC", "PS", "RHF", "PSA"])
def test_hu_3_3_el_recorrido_corre_en_los_cuatro_programas(en_delegacion, usuarios, pdf, programa):
    _, (exp,) = en_delegacion(programa)
    f = firmar(usuarios, exp, pdf)
    exp.refresh_from_db()
    assert exp.estado.clave == "contratada" and f.dentro_de_plazo
    assert plazos.vencimiento(exp, "firma_programada").fecha_evento is not None


# ----------------------------------------------------------------------------- pantallas
def test_hu_3_3_pantalla_de_firmas_de_la_delegacion_con_las_dos_fechas_y_los_dias(en_delegacion, usuarios, client, contrasena):
    _, (exp,) = en_delegacion("PS")
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    html = client.get("/contrato/firmas/").content.decode()
    assert 'data-prueba="por-firmar"' in html and exp.folio in html and "Registrar la firma" in html
    assert "Fecha programada" in html and "Vence para liberar el recurso" in html
    assert 'data-prueba="panel-por-firmar"' in client.get("/bandeja/").content.decode()
    assert "Registrar la firma del contrato" in client.get(f"/recepcion/expediente/{exp.folio}/").content.decode()
    assert client.get("/contrato/firmas/").status_code == 200
    client.login(username="comite", password=contrasena)
    assert client.get("/contrato/firmas/").status_code == 403


def test_hu_3_3_registro_de_la_firma_por_pantalla_y_pestana_contrato(en_delegacion, usuarios, client, contrasena, pdf):
    _, (exp,) = en_delegacion("PS")
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    html = client.get(f"/contrato/contratos/{exp.folio}/firmar/").content.decode()
    assert 'id="form-firma"' in html and "Firma por PROBOSQUE" in html and "Fecha programada de firma" in html
    # incompleta: falta marcar un punto
    r = client.post(f"/contrato/contratos/{exp.folio}/firmar/", {
        "firmante": "persona", "firmante_nombre": "Abel Contreras Vega", "archivo": pdf("firmado.pdf"),
        "v_firma_persona": "on"}, follow=True)
    assert "Falta verificar" in r.content.decode() or "Falta verificar" in "".join(str(m) for m in r.context["messages"])
    exp.refresh_from_db()
    assert exp.estado.clave == "contrato_en_delegacion"
    r = client.post(f"/contrato/contratos/{exp.folio}/firmar/", {
        "firmante": "persona", "firmante_nombre": "Abel Contreras Vega", "archivo": pdf("firmado.pdf"),
        "v_firma_persona": "on", "v_firma_probosque": "on", "observaciones": "Firmó en la Delegación."}, follow=True)
    html = r.content.decode()
    exp.refresh_from_db()
    assert exp.estado.clave == "contratada"
    assert 'data-prueba="firma-contrato"' in html and "Contrato firmado" in html and "En la fecha programada" in html
    assert "Firma por PROBOSQUE: <strong>verificado" in html
    # el contrato firmado se descarga
    r = client.get(f"/contrato/contratos/{exp.folio}/firmado/contrato/")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert client.get(f"/contrato/contratos/{exp.folio}/firmado/contrato/?descargar=1")["Content-Disposition"].startswith("attachment")
    # ya no hay nada por firmar
    assert exp.folio not in client.get("/contrato/firmas/").content.decode().split('data-prueba="firmados"')[0]


def test_hu_3_3_pantalla_de_mfs_pide_los_elementos_de_formalizacion(mfs, contrato_manual, usuarios, client, contrasena, pdf):
    exp = contrato_manual(mfs, modalidad=None)
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    html = client.get(f"/contrato/contratos/{exp.folio}/firmar/").content.decode()
    assert "Contrato de servicios técnicos con el prestador" in html and "RFN del prestador" in html and "Carta compromiso" in html
    r = client.post(f"/contrato/contratos/{exp.folio}/firmar/", {
        "firmante": "representante", "firmante_nombre": "Apoderado", "archivo": pdf(), "v_firma_persona": "on",
        "v_firma_probosque": "on", "e_contrato_servicios_tecnicos_archivo": pdf("cst.pdf"),
        "e_contrato_servicios_tecnicos_dato": "RFN-9", "e_carta_compromiso_psf_archivo": pdf("carta.pdf")}, follow=True)
    html = r.content.decode()
    assert "Contrato de servicios técnicos" in html and "RFN-9" in html
    assert client.get(f"/contrato/contratos/{exp.folio}/firmado/carta_compromiso_psf/").status_code == 200


def test_hu_3_3_pantalla_del_area_responsable_con_los_senalados_y_la_accion_de_liberar(en_delegacion, usuarios, client, contrasena):
    _, (exp,) = en_delegacion("PS")
    vencer(exp)
    call_command("revisar_plazos")
    client.login(username="dir_drff", password=contrasena)
    assert 'data-prueba="panel-sin-firma"' in client.get("/bandeja/").content.decode()
    html = client.get("/contrato/firmas/").content.decode()
    assert 'data-prueba="sin-firma"' in html and exp.folio in html and "Liberar el recurso" in html
    pestana = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    assert 'data-prueba="sin-firma-exp"' in pestana and 'id="form-liberar"' in pestana
    assert "Confirmar la liberación del recurso" in client.get(f"/recepcion/expediente/{exp.folio}/").content.decode()
    # sin motivo no se libera
    client.post(f"/contrato/contratos/{exp.folio}/liberar/", {"prefijo": "pestana", "pestana-motivo": ""})
    exp.refresh_from_db()
    assert exp.estado.clave == "sin_firma_en_plazo"
    # la Delegación ya no puede registrar la firma y la pantalla lo dice
    c2 = client.__class__()
    c2.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    assert "ya no se puede registrar" in c2.get(f"/contrato/contratos/{exp.folio}/firmar/").content.decode()
    r = client.post(f"/contrato/contratos/{exp.folio}/liberar/", {
        "prefijo": "pestana", "pestana-motivo": "No acudió a firmar.", "volver": f"/recepcion/expediente/{exp.folio}/?pestana=contrato"},
        follow=True)
    exp.refresh_from_db()
    assert exp.estado.clave == "recurso_liberado" and 'data-prueba="liberacion"' in r.content.decode()
    assert c2.post(f"/contrato/contratos/{exp.folio}/liberar/", {"prefijo": "p", "p-motivo": "x"}).status_code in (302, 403)
    exp.refresh_from_db()
    assert exp.estado.clave == "recurso_liberado"


def test_hu_3_3_la_pestana_ya_no_dice_que_esta_pendiente(en_delegacion, usuarios, client, contrasena):
    _, (exp,) = en_delegacion("PS")
    client.login(username="dir_drff", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    assert "HU-3.3 Firma del contrato" not in html and 'data-prueba="por-firmar-exp"' in html
    assert "Fecha programada de firma" in html and "Vencimiento para liberar el recurso" in html
