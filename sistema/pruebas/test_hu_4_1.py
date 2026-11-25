"""HU-4.1 · Envío de comprobaciones (por el portal o en la Delegación, con el mismo registro)."""
from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from ejecucion import comprobaciones
from ejecucion.models import Comprobacion, MedioEnvio
from nucleo import plazos, reloj
from nucleo.models import Evento, Hito, bandeja
from pagos import solicitudes

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m4 import *  # noqa: F401,F403
from .fixtures_m4 import CONTRASENA_PORTAL
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db
CONTRATO = "2026-08-03 10:00"   # el contrato se firma y se paga en agosto (calendario de la Convocatoria)


def _pagada(pagada, programa, **kw):
    with reloj.en(CONTRATO):
        return pagada(programa, **kw)


def test_hu_4_1_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-4.1")
    assert "trazabilidad" in hu["criterios"][-1]
    assert hu["criterios"][:-1] == ["Cada envío tiene su acuse con la fecha y la hora.",
                               "Una entrega en persona en la Delegación tiene el mismo registro."]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M4.1")
    assert {"CC-BEN-01", "CC-BEN-02", "MFS-BEN-01", "PS-BEN-01", "PS-BEN-02", "RHF-BEN-02", "PSA-BEN-01", "PEG-BEN-01",
            "PEG-BEN-02"} <= set(funcion["necesidades"])
    assert "15 días hábiles" in necesidades["CC-BEN-02"]["texto"]


@pytest.mark.parametrize("programa,tipos", [
    ("CC", ["aviso_termino", "informe_final", "caso_fortuito"]),
    ("PS", ["aviso_termino", "cambio_poligono", "justificacion_ajuste", "caso_fortuito"]),
    ("RHF", ["aviso_termino", "caso_fortuito"]),
    ("PSA", ["informe_final", "caso_fortuito"]),
])
def test_hu_4_1_cada_programa_recibe_lo_que_piden_sus_reglas(programa, tipos, contratadas):
    with reloj.en(CONTRATO):
        _, (exp,) = contratadas(programa)
    lista = comprobaciones.tipos_de_envio(exp)
    assert [t["clave"] for t in lista] == tipos
    assert all("ROP" in t["fundamento"] and "línea" in t["fundamento"] for t in lista)


def test_hu_4_1_mfs_recibe_el_entregable_de_su_regimen_y_peg_sus_reportes(contratadas, peg_contratado):
    with reloj.en(CONTRATO):
        _, (etf, fsc) = contratadas("MFS", cuantas=2)
        guardabosque = peg_contratado()
    assert [t["clave"] for t in comprobaciones.tipos_de_envio(etf)] == ["bitacora_etf"]
    assert [t["clave"] for t in comprobaciones.tipos_de_envio(fsc)] == ["solicitud_auditoria_fsc"]
    assert [t["clave"] for t in comprobaciones.tipos_de_envio(guardabosque)] == ["reporte_mensual", "acuse_deposito",
                                                                                 "evidencia_informe_nucleo"]


# ----------------------------------------------------------------------------- criterio 1: acuse con fecha y hora
def test_hu_4_1_cada_envio_por_el_portal_tiene_su_acuse_con_la_fecha_y_la_hora(pagada, cuenta_portal, pdf):
    """Criterio 1. La persona envía desde el portal el aviso de término y el Informe Final de CC: cada uno con su acuse,
    su fecha y hora, su renglón de bitácora y su hito; el primero inicia la ejecución y deja la comprobación por verificar."""
    exp = _pagada(pagada, "CC")
    with reloj.en(CONTRATO):
        persona = cuenta_portal(exp)
    with reloj.en("2026-11-12 09:15:30"):
        aviso = comprobaciones.registrar_envio(persona, exp, "aviso_termino", fecha_hecho=date(2026, 11, 11),
                                               descripcion="Concluimos la reforestación.")
    assert aviso.medio == MedioEnvio.PORTAL and aviso.enviada_por == persona and aviso.recibida_por is None
    assert f"{aviso.enviada_en:%Y-%m-%d}" == "2026-11-12"
    renglones = dict(aviso.acuse.contenido["renglones"])
    assert renglones["Fecha y hora"].startswith("12/11/2026 09:15:30") and renglones["Medio"] == "Portal de personas beneficiarias"
    assert aviso.acuse.tipo == "comprobacion" and aviso.acuse.archivo.open("rb").read(4) == b"%PDF"
    assert aviso.en_plazo is True and aviso.vence == date(2026, 11, 13)          # concluir a más tardar el 13-nov (CC)
    assert Hito.objects.get(expediente=exp, clave="conclusion_actividades").fecha_hora.date() == date(2026, 11, 11)
    assert exp.eventos.filter(tipo="comprobacion", usuario=persona, acuse=aviso.acuse).exists()
    exp.refresh_from_db()
    assert exp.estado.clave == "comprobacion_enviada" and aviso.cambio_estado == "comprobacion_enviada"
    inicio = exp.eventos.get(tipo="inicio_ejecucion")
    assert inicio.estado_origen.clave == "pagada" and inicio.estado_destino.clave == "en_ejecucion" and inicio.usuario is None
    with reloj.en("2026-11-20 12:00"):
        informe = comprobaciones.registrar_envio(persona, exp, "informe_final", archivo=pdf("informe_final.pdf"))
    assert informe.acuse.folio != aviso.acuse.folio and informe.en_plazo is True    # 15 días hábiles desde el 13-nov
    assert informe.cambio_estado == "" and len(informe.huella) == 64                # ya estaba por verificar
    assert Hito.objects.filter(expediente=exp, clave="informe_final").exists()


# ----------------------------------------------------------------------------- criterio 2: misma entrega en ventanilla
def test_hu_4_1_la_entrega_en_ventanilla_tiene_el_mismo_registro(pagada, cuenta_portal, usuarios, pdf):
    """Criterio 2. La Delegación registra la misma entrega recibida en persona: mismo modelo, mismo tipo de acuse y los
    mismos datos, más quién la entregó y quién la recibió; el cambio de estado lo firma su usuario."""
    portal_exp, ventanilla_exp = _pagada(pagada, "PS", cuantas=2)
    with reloj.en(CONTRATO):
        persona = cuenta_portal(portal_exp)
    deleg = delegado_de(usuarios, ventanilla_exp)
    with reloj.en("2026-09-28 11:00"):
        por_portal = comprobaciones.registrar_envio(persona, portal_exp, "aviso_termino", fecha_hecho=date(2026, 9, 25))
        en_persona = comprobaciones.registrar_envio(deleg, ventanilla_exp, "aviso_termino", fecha_hecho=date(2026, 9, 25),
                                                    persona_entrega="Abel Contreras Vega")
    assert isinstance(en_persona, Comprobacion) and en_persona.medio == MedioEnvio.VENTANILLA
    assert en_persona.recibida_por == deleg and en_persona.persona_entrega == "Abel Contreras Vega"
    assert en_persona.acuse.tipo == por_portal.acuse.tipo == "comprobacion"
    claves_portal = {k for k, _ in por_portal.acuse.contenido["renglones"]}
    claves_ventanilla = {k for k, _ in en_persona.acuse.contenido["renglones"]}
    assert claves_portal - {"Envía"} <= claves_ventanilla and {"Entrega", "Recibe"} <= claves_ventanilla
    assert dict(en_persona.acuse.contenido["renglones"])["Fecha y hora"].startswith("28/09/2026 11:00")
    assert en_persona.en_plazo is True and en_persona.vence == date(2026, 9, 30)  # último día hábil de septiembre (PS)
    ventanilla_exp.refresh_from_db()
    assert ventanilla_exp.estado.clave == "comprobacion_enviada"
    assert ventanilla_exp.eventos.filter(estado_destino__clave="comprobacion_enviada", usuario=deleg).exists()
    assert {u for u in (deleg.username, "dir_drff", "juridica") if ventanilla_exp in bandeja(usuarios[u])} == {deleg.username, "dir_drff"}


# ----------------------------------------------------------------------------- plazos
def test_hu_4_1_fuera_de_plazo_se_registra_igual_y_queda_senalado(pagada, usuarios):
    exp = _pagada(pagada, "CC")
    with reloj.en("2026-11-17 10:00"):
        c = comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "aviso_termino", fecha_hecho=date(2026, 11, 16))
    assert c.en_plazo is False and c.situacion_plazo == "fuera de plazo" and c.vence == date(2026, 11, 13)
    assert "Fuera de plazo" in c.acuse.contenido["nota"]
    exp.refresh_from_db()
    assert exp.estado.clave == "comprobacion_enviada"


def test_hu_4_1_el_aviso_de_caso_fortuito_registra_el_siniestro_y_su_plazo_de_15_dias_habiles(pagada, usuarios, pdf):
    a_tiempo, tarde = _pagada(pagada, "RHF", cuantas=2)
    with reloj.en("2026-09-10 10:00"):
        c = comprobaciones.registrar_envio(delegado_de(usuarios, a_tiempo), a_tiempo, "caso_fortuito", pdf("denuncia.pdf"),
                                           "Incendio en el predio.", fecha_hecho=date(2026, 9, 1))
    assert c.en_plazo is True and c.vence == date(2026, 9, 23)          # 15 días hábiles (16-sep inhábil) desde el 1-sep
    assert Hito.objects.get(expediente=a_tiempo, clave="siniestro").fecha_hora.date() == date(2026, 9, 1)
    a_tiempo.refresh_from_db()
    assert a_tiempo.estado.clave == "caso_fortuito"                       # flujo alterno D: lo revisa el área y el Comité
    with reloj.en("2026-10-20 10:00"):
        t = comprobaciones.registrar_envio(delegado_de(usuarios, tarde), tarde, "caso_fortuito", pdf("acta.pdf"),
                                           fecha_hecho=date(2026, 9, 1))
    assert t.en_plazo is False and t.acuse is not None
    with pytest.raises(ValidationError, match="Falta el documento"):
        comprobaciones.registrar_envio(delegado_de(usuarios, tarde), tarde, "caso_fortuito", fecha_hecho=date(2026, 9, 1))
    with pytest.raises(ValidationError, match="posterior al envío"):
        comprobaciones.registrar_envio(delegado_de(usuarios, tarde), tarde, "caso_fortuito", pdf("x.pdf"),
                                       fecha_hecho=date(2099, 1, 1))


def test_hu_4_1_en_rhf_la_modalidad_uno_concluye_en_octubre_y_las_demas_en_septiembre(pagada, usuarios, monkeypatch):
    """R-19: los conceptos de RHF que concluyen en octubre (Restauración Forestal Integral Modalidad uno) toman su fecha
    límite y su plazo de entrega de la verificación desde octubre (ROP RHF 10.1 t, líneas 3588 a 3592)."""
    monkeypatch.setitem(SOLICITUDES_M3, "RHF", [
        ("del_amecameca", "Ozumba", "Cañada Uno", "Raquel Montes Alba", "rfi_modalidad_uno", 3),
        ("del_valle", "Amanalco", "Ojo de Agua", "Guadalupe Reyes Albarrán", "bosques_de_agua", 2)])
    uno, agua = _pagada(pagada, "RHF", cuantas=2)
    assert plazos.vencimiento(uno, "fecha_limite_conclusion").vencimiento == date(2026, 10, 30)
    assert plazos.vencimiento(uno, "entrega_comprobacion").vencimiento == date(2026, 11, 17)   # 10 días hábiles (2-nov inhábil)
    assert plazos.vencimiento(agua, "fecha_limite_conclusion").vencimiento == date(2026, 9, 30)
    assert plazos.vencimiento(agua, "entrega_comprobacion").vencimiento == date(2026, 10, 14)
    with reloj.en("2026-10-28 10:00"):
        c = comprobaciones.registrar_envio(delegado_de(usuarios, uno), uno, "aviso_termino", fecha_hecho=date(2026, 10, 27))
        t = comprobaciones.registrar_envio(delegado_de(usuarios, agua), agua, "aviso_termino", fecha_hecho=date(2026, 10, 27))
    assert c.en_plazo is True and t.en_plazo is False


# ----------------------------------------------------------------------------- MFS y PEG
def test_hu_4_1_la_bitacora_de_mfs_es_el_soporte_de_su_segunda_ministracion(pagada, usuarios, pdf):
    exp = _pagada(pagada, "MFS")
    soporte = next(s for s in solicitudes.soportes(exp, 2) if s["clave"] == "entregable_etf")
    assert not soporte["cumple"] and "Bitácora" in soporte["detalle"]
    with reloj.en("2026-10-02 10:00"):
        c = comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "bitacora_etf", pdf("bitacora.pdf"))
    assert c.en_plazo is None and "sin plazo en las reglas" in c.plazo_texto        # R-17: lapso sin días
    soporte = next(s for s in solicitudes.soportes(exp, 2) if s["clave"] == "entregable_etf")
    assert soporte["cumple"] and soporte["referencia"] == c.acuse.folio and soporte["url"]
    exp.refresh_from_db()
    assert exp.estado.clave == "comprobacion_enviada"
    with pytest.raises(ValidationError, match="no recibe"):
        comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "solicitud_auditoria_fsc", pdf("a.pdf"))


def test_hu_4_1_mfs_fsc_entrega_la_solicitud_de_auditoria(contratadas, usuarios, pdf):
    with reloj.en(CONTRATO):
        _, (_, fsc) = contratadas("MFS", cuantas=2)
    with reloj.en("2026-10-05 10:00"):
        comprobaciones.registrar_envio(delegado_de(usuarios, fsc), fsc, "solicitud_auditoria_fsc", pdf("auditoria.pdf"))
    assert comprobaciones.fuente_entregable(fsc, 2)[0] is True


def test_hu_4_1_peg_entrega_sus_reportes_mensuales_y_el_acuse_de_deposito(peg_contratado, cuenta_portal, usuarios, pdf):
    with reloj.en("2026-06-16 10:00"):
        exp = peg_contratado()
        guardabosque = cuenta_portal(exp)
    estado = exp.estado.clave
    with reloj.en("2026-08-03 10:00"):
        julio = comprobaciones.registrar_envio(guardabosque, exp, "reporte_mensual", pdf("reporte_julio.pdf"), periodo="2026-07")
        with pytest.raises(ValidationError, match="Ya se entregó"):
            comprobaciones.registrar_envio(guardabosque, exp, "reporte_mensual", pdf("otra.pdf"), periodo="2026-07")
        with pytest.raises(ValidationError, match="todavía no empieza"):
            comprobaciones.registrar_envio(guardabosque, exp, "reporte_mensual", pdf("x.pdf"), periodo="2026-10")
        with pytest.raises(ValidationError, match="periodo"):
            comprobaciones.registrar_envio(guardabosque, exp, "reporte_mensual", pdf("x.pdf"))
        deposito = comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "acuse_deposito", pdf("acuse.pdf"),
                                                  fecha_hecho=date(2026, 7, 14))
    assert julio.periodo == "2026-07" and julio.en_plazo is None and "R-18" in julio.plazo_texto
    assert dict(julio.acuse.contenido["renglones"])["Periodo que reporta"] == "Julio 2026"
    assert Hito.objects.get(expediente=exp, clave="reporte_mensual", datos__periodo="2026-07").datos["periodo"] == "2026-07"
    assert deposito.medio == MedioEnvio.VENTANILLA and deposito.fecha_hecho == date(2026, 7, 14)
    exp.refresh_from_db()
    assert exp.estado.clave == estado                     # la evaluación de los reportes (HU-4.3) no cambia el estado


# ----------------------------------------------------------------------------- permisos y validaciones
def test_hu_4_1_solo_la_persona_desde_su_portal_o_la_delegacion_del_expediente(pagada, cuenta_portal, usuarios, pdf):
    exp, otro = _pagada(pagada, "CC", cuantas=2)
    with reloj.en(CONTRATO):
        ajeno = cuenta_portal(otro, curp="ROSR700101HMCRLM05")
    for quien in (usuarios["dir_drff"], usuarios["finanzas"], usuarios["juridica"], usuarios["del_valle"]):
        with pytest.raises(PermissionDenied):
            comprobaciones.registrar_envio(quien, exp, "informe_final", pdf("i.pdf"))
    with pytest.raises(PermissionDenied, match="no es suyo"):
        comprobaciones.registrar_envio(ajeno, exp, "informe_final", pdf("i.pdf"))
    with pytest.raises(ValidationError, match="no recibe"):
        comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "reporte_mensual", pdf("r.pdf"))
    assert not Comprobacion.objects.filter(expediente=exp).exists()


def test_hu_4_1_sin_contrato_firmado_no_hay_comprobaciones(en_delegacion, usuarios, pdf):
    _, (exp,) = en_delegacion("CC")
    with pytest.raises(ValidationError, match="firmado el contrato"):
        comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "informe_final", pdf("i.pdf"))


# ----------------------------------------------------------------------------- bandeja de la Delegación y pantallas
def test_hu_4_1_la_delegacion_ve_lo_recibido_por_el_portal_y_lo_revisa(pagada, cuenta_portal, usuarios, client, contrasena, pdf):
    exp = _pagada(pagada, "PSA")
    with reloj.en(CONTRATO):
        persona = cuenta_portal(exp)
    c = comprobaciones.registrar_envio(persona, exp, "informe_final", pdf("informe.pdf"))
    deleg = delegado_de(usuarios, exp)
    assert list(comprobaciones.por_revisar(deleg)) == [c] and not comprobaciones.por_revisar(usuarios["dir_drff"]).exists()
    client.login(username=deleg.username, password=contrasena)
    html = client.get(reverse("nucleo:bandeja")).content.decode()
    assert 'data-prueba="panel-comprobaciones-por-revisar"' in html and exp.folio in html
    pestana = client.get(reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=ejecucion").content.decode()
    assert "Informe Final de Actividades" in pestana and c.acuse.folio in pestana and "Marcar como revisado" in pestana
    with pytest.raises(PermissionDenied):
        comprobaciones.marcar_revisada(usuarios["dir_drff"], c)
    client.post(reverse("ejecucion:revisada", args=[c.pk]))
    c.refresh_from_db()
    assert c.revisada_por == deleg and c.revisada_en
    assert exp.eventos.filter(tipo="comprobacion_revisada", usuario=deleg).exists()
    assert client.get(reverse("ejecucion:archivo", args=[c.pk])).status_code == 200
    assert client.get(reverse("ejecucion:comprobaciones")).status_code == 200


def test_hu_4_1_el_portal_envia_y_un_externo_no_ve_ni_envia_a_lo_ajeno(pagada, cuenta_portal, client, pdf):
    exp, otro = _pagada(pagada, "CC", cuantas=2)
    with reloj.en(CONTRATO):
        persona = cuenta_portal(exp)
        cuenta_portal(otro, curp="ROSR700101HMCRLM05")
    assert client.login(username=persona.username, password=CONTRASENA_PORTAL)
    pagina = client.get(reverse("portal:expediente", args=[exp.folio])).content.decode()
    assert 'data-prueba="mis-envios"' in pagina and "Enviar a la Delegación" in pagina
    r = client.post(reverse("ejecucion_portal:enviar", args=[exp.folio]),
                    {"tipo": "informe_final", "descripcion": "Informe", "archivo": pdf("informe.pdf")})
    assert r.status_code == 302
    c = exp.comprobaciones.get()
    assert c.medio == MedioEnvio.PORTAL and c.enviada_por == persona
    pagina = client.get(reverse("portal:expediente", args=[exp.folio])).content.decode()
    assert c.acuse.folio in pagina
    assert client.get(reverse("portal:acuse", args=[exp.folio, c.acuse.folio])).status_code == 200
    assert client.get(reverse("ejecucion_portal:archivo", args=[exp.folio, c.pk])).status_code == 200
    # Lo ajeno: 404 al verlo, al enviarle y al pedir su documento; las pantallas internas lo regresan al portal.
    assert client.get(reverse("portal:expediente", args=[otro.folio])).status_code == 404
    assert client.post(reverse("ejecucion_portal:enviar", args=[otro.folio]), {"tipo": "informe_final"}).status_code == 404
    assert client.get(reverse("ejecucion_portal:archivo", args=[otro.folio, c.pk])).status_code == 404
    assert client.get(reverse("ejecucion:archivo", args=[c.pk])).status_code == 302
    assert client.post(reverse("ejecucion:registrar", args=[exp.folio]), {"tipo": "informe_final"}).status_code == 403
    assert not otro.comprobaciones.exists()


def test_hu_4_1_la_consulta_sin_cuenta_ve_los_envios_pero_no_envia(pagada, cuenta_portal, usuarios, client, pdf):
    exp = _pagada(pagada, "CC")
    with reloj.en(CONTRATO):
        _, _, codigo_consulta = cuenta_portal(exp, con_codigos=True)
    if codigo_consulta is None:   # ya se había emitido al firmar: se emite uno nuevo para la prueba
        from django.contrib.auth.hashers import make_password

        from portal.models import CodigoConsulta
        codigo_consulta = "ABCD-EFGH"
        CodigoConsulta.objects.filter(expediente=exp).update(codigo_hash=make_password("ABCD-EFGH"))
    c = comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "informe_final", pdf("informe.pdf"))
    client.post(reverse("portal:consulta"), {"folio": exp.folio, "codigo": codigo_consulta})
    pagina = client.get(reverse("portal:expediente", args=[exp.folio])).content.decode()
    assert c.acuse.folio in pagina and 'data-prueba="consulta-sin-envio"' in pagina and "form-envio-portal" not in pagina
    assert client.post(reverse("ejecucion_portal:enviar", args=[exp.folio]), {"tipo": "informe_final"}).status_code == 403
    assert Evento.objects.filter(expediente=exp, tipo="comprobacion").count() == 1


def _filas_de(exp, registro):
    from nucleo.trazabilidad import historial_expediente

    return [f for f in historial_expediente(exp) if f["registro"] == registro]


# ----------------------------------------------------------------------------- criterio 3: trazabilidad
def test_hu_4_1_trazabilidad_de_los_envios_por_el_portal_y_en_ventanilla(pagada, cuenta_portal, usuarios, pdf):
    """Criterio 3: cada envío queda en el historial con quien lo hizo (la cuenta del portal o la Delegación), y la revisión
    de la Delegación como cambio del mismo registro; los dos aparecen en la pestaña «Trazabilidad»."""
    portal_exp, ventanilla_exp = _pagada(pagada, "PS", cuantas=2)
    with reloj.en(CONTRATO):
        persona = cuenta_portal(portal_exp)
    deleg = delegado_de(usuarios, ventanilla_exp)
    with reloj.en("2026-09-28 11:00"):
        por_portal = comprobaciones.registrar_envio(persona, portal_exp, "aviso_termino", fecha_hecho=date(2026, 9, 25))
        en_persona = comprobaciones.registrar_envio(deleg, ventanilla_exp, "aviso_termino", fecha_hecho=date(2026, 9, 25),
                                                    persona_entrega="Abel Contreras Vega")
    assert por_portal.history.get(history_type="+").history_user == persona
    assert en_persona.history.get(history_type="+").history_user == deleg
    revisa = delegado_de(usuarios, portal_exp)
    comprobaciones.marcar_revisada(revisa, por_portal)
    cambio = por_portal.history.filter(history_type="~").latest("history_date")
    assert cambio.history_user == revisa and cambio.revisada_en is not None
    filas = _filas_de(portal_exp, "Comprobación")
    assert any(f["usuario"] == persona and f["tipo"] == "Alta" for f in filas)
    assert any(f["usuario"] == revisa and f["tipo"] == "Cambio" for f in filas)
    assert any(f["usuario"] == deleg for f in _filas_de(ventanilla_exp, "Comprobación"))
