"""HU-6.1 · Lista de espera y sustituciones: propuesta de reasignación del recurso liberado en el orden de la lista de espera;
solicitudes de sustitución y de desistimiento con su acuse; casos especiales (caso fortuito, sobrevivencia menor, prórroga de MFS)."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from contrato import firma
from dictamen import seguimiento as dictamen_seguimiento
from dictamen import sesiones
from dictamen.models import TipoSesion
from ejecucion import comprobaciones, verificacion
from nucleo import extensiones, plazos, reloj
from nucleo.models import Expediente, Hito, Notificacion, Persona
from seguimiento import reasignacion
from seguimiento.models import Propuesta, RecursoLiberado

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m2 import documento_sesion, fecha_sesion
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de, direccion_de
from .fixtures_m4 import *  # noqa: F401,F403
from .fixtures_m4 import CONTRASENA_PORTAL
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def _archivo(nombre="escrito.pdf"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from nucleo.demo import _pdf_demo
    return SimpleUploadedFile(nombre, _pdf_demo(nombre), content_type="application/pdf")


def _sesion(usuarios, ejercicio):
    s = sesiones.crear_sesion(usuarios["comite"], ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(6), "Sala",
                              "Quórum\nSeguimiento de casos")
    sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(), "Casos")
    sesiones.enviar_convocatoria(usuarios["comite"], s)
    return s


def _acordar_y_cumplir(usuarios, propuesta, aprueba=True):
    """La Secretaría Técnica lleva la propuesta a una sesión de seguimiento y el área responsable cumple el acuerdo."""
    s = _sesion(usuarios, propuesta.ejercicio)
    acuerdo = reasignacion.llevar_a_sesion(usuarios["comite"], propuesta, s, aprueba)
    direccion = direccion_de(usuarios, propuesta.ejercicio)
    assert acuerdo.unidad_responsable == direccion.unidad and acuerdo in dictamen_seguimiento.acuerdos_pendientes(direccion.unidad)
    dictamen_seguimiento.cumplir(direccion, acuerdo, "Cumplido.")
    propuesta.refresh_from_db()
    assert propuesta.estado == "ejecutada"
    return acuerdo


def _desistir(usuarios, exp, momento=None):
    return reasignacion.registrar_solicitud(delegado_de(usuarios, exp), exp, "desistimiento", _archivo("desistimiento.pdf"),
                                            motivo="Cambio de residencia.", firmas=reasignacion.puntos_firma(exp),
                                            momento=momento)


def test_hu_6_1_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-6.1")
    assert "trazabilidad" in hu["criterios"][-1]
    assert hu["criterios"][:-1] == ["Cada propuesta indica el recurso liberado y sigue el orden de la lista de espera.",
                               "Cada solicitud de sustitución o de desistimiento tiene su acuse con la fecha y la hora."]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M6.1")
    assert {"CC-BEN-03", "CC-ARP-06", "MFS-ARP-06", "PS-ARP-06", "RHF-ARP-06", "PSA-ARP-06"} <= set(funcion["necesidades"])
    assert "30 días hábiles" in necesidades["CC-BEN-03"]["texto"] and "causa externa" in necesidades["MFS-ARP-06"]["texto"]


# ----------------------------------------------------------------------------- criterio 1
def test_hu_6_1_la_propuesta_indica_el_recurso_liberado_y_sigue_el_orden_de_la_lista_de_espera(notificadas, usuarios, client,
                                                                                                contrasena):
    """CC con recurso para una de tres (6 ha, $12,000 cada una): la beneficiaria desiste antes de firmar, el Comité acuerda la
    baja y se liberan $12,000; la propuesta de reasignación alcanza al lugar 1 de la lista de espera y no al lugar 2. Al
    cumplirse el acuerdo, el lugar 1 pasa a «aprobada», se le notifica y su firma corre desde esa notificación."""
    with reloj.en("2026-08-03 10:00", tic=1):
        _, (uno, dos, tres) = notificadas("CC", cuantas=3, presupuesto=12000)
        assert (uno.estado.clave, dos.estado.clave, tres.estado.clave) == ("notificada", "lista_espera", "lista_espera")
        cc = uno.ejercicio
        _desistir(usuarios, uno)
        baja = reasignacion.proponer(usuarios["dir_drff"], uno, "desistimiento")
        assert baja.monto_liberado == Decimal("12000.00") and "liberar $12,000.00" in baja.descripcion
        _acordar_y_cumplir(usuarios, baja)
        uno.refresh_from_db()
        assert uno.estado.clave == "recurso_liberado"
        recurso = RecursoLiberado.objects.get(expediente=uno)
        assert recurso.origen == "desistimiento" and recurso.monto == Decimal("12000.00")
        calculo = reasignacion.calcular(cc)
        assert calculo["total"] == Decimal("12000.00")
        assert [(r["expediente"], r["lugar"], r["alcanza"]) for r in calculo["renglones"]] == [(dos, 1, True), (tres, 2, False)]
        with pytest.raises(PermissionDenied):
            reasignacion.proponer_reasignacion(usuarios["del_amecameca"], cc)
        p = reasignacion.proponer_reasignacion(usuarios["dir_drff"], cc, "Recurso del desistimiento.")
    assert p.monto_liberado == Decimal("12000.00") and p.monto_asignado == Decimal("12000.00") and p.saldo == 0
    assert list(p.expedientes.all()) == [dos] and list(p.recursos.all()) == [recurso]
    assert [(r["folio"], r["lugar"], r["alcanza"]) for r in p.datos["renglones"]] == [(dos.folio, 1, True), (tres.folio, 2, False)]
    renglones = dict(p.acuse.contenido["renglones"])
    assert renglones["Recurso liberado"].startswith("$12,000.00") and "lista de espera" in renglones["Orden"]
    assert [d["estado"] for d in p.acuse.contenido["detalle"]] == ["$12,000.00", "Alcanza", "No alcanza"]
    assert reasignacion.calcular(cc)["total"] == 0                    # el recurso ya está en la propuesta
    client.login(username="comite", password=contrasena)
    assert 'data-prueba="panel-propuestas-por-llevar"' in client.get(reverse("nucleo:bandeja")).content.decode()
    client.login(username="dir_drff", password=contrasena)
    with reloj.en("2026-08-10 10:00", tic=1):
        acuerdo = _acordar_y_cumplir(usuarios, p)
        dos.refresh_from_db()
        tres.refresh_from_db()
        assert dos.estado.clave == "aprobada" and tres.estado.clave == "lista_espera" and plazos.es_reasignada(dos)
        assert Hito.objects.filter(expediente=dos, clave="aprobacion_comite").exists()
        recurso.refresh_from_db()
        assert recurso.reasignado_en is not None
        aviso = dos.notificaciones.filter(tipo="resultados").order_by("-enviada_en").first()
        assert "reasignación" in aviso.asunto and aviso.datos["acuerdo"] == acuerdo.pk
        notificada = reasignacion_notificar(usuarios, dos, aviso)
    dos.refresh_from_db()
    assert dos.estado.clave == "notificada"
    v = plazos.vencimiento(dos, "firma_liberacion")
    assert v.fecha_evento == notificada.notificada_en and v.tiene_fecha and not v.evento_despues_del_tope   # tope 30-sep (CC)


def reasignacion_notificar(usuarios, exp, aviso):
    from contrato import publicacion

    publicacion.registrar_entrega(delegado_de(usuarios, exp), aviso, "personal")
    aviso.refresh_from_db()
    return aviso


def test_hu_6_1_sin_firma_en_plazo_libera_el_recurso_y_un_recurso_menor_no_alcanza_al_primer_lugar(notificadas, usuarios):
    """El recurso de un contrato sin firma lo registra el gancho ``AL_LIBERAR_RECURSO`` al confirmarse la liberación (HU-3.3). Si
    no alcanza para el primer lugar, la propuesta no se arma: no se salta el orden (decisión propia, configurable)."""
    from .test_hu_3_3 import vencer

    _, (uno, dos, _tres) = notificadas("CC", cuantas=3, presupuesto=12000)
    vencer(uno)
    firma.revisar_firmas(timezone.localdate())
    firma.liberar_recurso(usuarios["dir_drff"], uno, "No acudió a firmar en el plazo de las reglas.")
    assert reasignacion.al_liberar_recurso in extensiones.AL_LIBERAR_RECURSO
    r = RecursoLiberado.objects.get(expediente=uno)
    assert r.origen == "sin_firma" and r.monto == Decimal("12000.00") and r.referencia.startswith("AC-")
    r.monto = Decimal("5000")
    r.save()
    with pytest.raises(ValidationError, match="no alcanza para la primera"):
        reasignacion.proponer_reasignacion(usuarios["dir_drff"], uno.ejercicio)
    assert reasignacion.calcular(uno.ejercicio)["renglones"][0]["expediente"] == dos


def test_hu_6_1_el_comite_puede_no_aprobar_la_reasignacion_y_el_recurso_queda_disponible(notificadas, usuarios):
    _, (uno, dos, _) = notificadas("CC", cuantas=3, presupuesto=12000)
    reasignacion.registrar_recurso(uno, "cancelacion", Decimal("12000"), usuarios["dir_drff"], "prueba")
    p = reasignacion.proponer_reasignacion(usuarios["dir_drff"], uno.ejercicio)
    with pytest.raises(PermissionDenied):
        reasignacion.llevar_a_sesion(usuarios["dir_drff"], p, _sesion(usuarios, uno.ejercicio))
    _acordar_y_cumplir(usuarios, p, aprueba=False)
    dos.refresh_from_db()
    assert dos.estado.clave == "lista_espera" and reasignacion.calcular(uno.ejercicio)["total"] == Decimal("12000.00")


# ----------------------------------------------------------------------------- criterio 2
def test_hu_6_1_la_sustitucion_por_fallecimiento_tiene_su_acuse_y_su_plazo_de_30_dias_habiles(contratadas, usuarios):
    _, (exp,) = contratadas("CC")
    deleg = delegado_de(usuarios, exp)
    with reloj.en("2026-09-07 10:00"):
        aviso = reasignacion.registrar_solicitud(deleg, exp, "fallecimiento", _archivo("acta_defuncion.pdf"), "Hija",
                                                 fecha_hecho=date(2026, 9, 1))
    assert aviso.acuse.tipo == "solicitud_fallecimiento" and dict(aviso.acuse.contenido["renglones"])["Fecha y hora"].startswith(
        "07/09/2026 10:00")
    assert Hito.objects.get(expediente=exp, clave="fallecimiento_titular").fecha_hora.date() == date(2026, 9, 1)
    exp.refresh_from_db()
    assert exp.estado.clave == "sustitucion"
    with pytest.raises(ValidationError, match="segunda persona"):
        reasignacion.registrar_solicitud(deleg, exp, "sustitucion", _archivo(), segunda={})
    with reloj.en("2026-10-12 12:30"):   # 30 días hábiles desde el 1-sep (calendario de días inhábiles) vencen el 14-oct
        s = reasignacion.registrar_solicitud(deleg, exp, "sustitucion", _archivo("interes.pdf"),
                                             segunda={"nombre": "Rosa Díaz Luna", "curp": "DILR900212MMCZNS01"})
    assert s.causa == "fallecimiento" and s.en_plazo is True and s.vence == date(2026, 10, 14)
    renglones = dict(s.acuse.contenido["renglones"])
    assert renglones["Fecha y hora"].startswith("12/10/2026 12:30") and "Rosa Díaz Luna" in renglones["Segunda persona beneficiaria"]
    assert "EN PLAZO" in renglones["Plazo"]
    with reloj.en("2026-10-20 10:00"):
        tarde = reasignacion.registrar_solicitud(deleg, exp, "sustitucion", _archivo(), segunda={"nombre": "Otra Persona"})
    assert tarde.en_plazo is False and "Fuera de plazo" in tarde.acuse.contenido["nota"]


def test_hu_6_1_la_sustitucion_aprobada_cambia_la_persona_beneficiaria_con_historial(contratadas, usuarios):
    _, (exp,) = contratadas("PS")
    deleg = delegado_de(usuarios, exp)
    anterior = exp.beneficiaria
    s = reasignacion.registrar_solicitud(deleg, exp, "sustitucion", _archivo(), motivo="Enfermedad grave del titular.",
                                         causa="imposibilidad", segunda={"nombre": "Luis Contreras Vega", "parentesco": "Hijo"})
    assert s.causa == "imposibilidad" and s.en_plazo is None
    with pytest.raises(PermissionDenied):
        reasignacion.proponer(deleg, exp, "sustitucion")
    p = reasignacion.proponer(usuarios["dir_drff"], exp, "sustitucion")
    assert p.monto_liberado == 0 and "Ninguno" in dict(p.acuse.contenido["renglones"])["Recurso liberado"]
    assert reasignacion.tipos_propuesta(exp) == []                          # una propuesta a la vez
    _acordar_y_cumplir(usuarios, p)
    exp.refresh_from_db()
    assert exp.beneficiaria.nombre == "Luis Contreras Vega" and exp.estado.clave == "contratada"
    assert exp.history.filter(persona_beneficiaria__isnull=True).exists()          # el historial conserva a la anterior
    assert exp.history.filter(persona_beneficiaria=exp.persona_beneficiaria).exists()
    assert exp.eventos.filter(tipo="sustitucion_beneficiaria", descripcion__contains=anterior.nombre).exists()


@pytest.mark.parametrize("programa", ["CC", "MFS", "PS", "RHF", "PSA", "PEG"])
def test_hu_6_1_el_desistimiento_tiene_su_acuse_y_libera_el_recurso_en_los_seis_programas(programa, contratadas, usuarios):
    _, (exp,) = contratadas(programa)
    puntos = reasignacion.puntos_firma(exp)
    if exp.tipo_persona.clave == "nucleo_agrario":          # MFS (Ejido San Pedro Nexapa) y PEG: Presidencia, Secretaría y Tesorería
        assert len(puntos) == 4 and "Sello del núcleo agrario" in puntos
    with pytest.raises(ValidationError, match="no se recibe sin"):
        reasignacion.registrar_solicitud(delegado_de(usuarios, exp), exp, "desistimiento", _archivo(), motivo="x", firmas=puntos[:1]
                                         if len(puntos) > 1 else [])
    with reloj.en(timezone.now() + timedelta(minutes=5)):
        s = _desistir(usuarios, exp)
    assert s.acuse and s.presentada_en and s.firmas == puntos
    assert dict(s.acuse.contenido["renglones"])["Fecha y hora"] == f"{timezone.localtime(s.presentada_en):%d/%m/%Y %H:%M:%S} h"
    total = reasignacion.total_aprobado(exp)
    p = reasignacion.proponer(direccion_de(usuarios, exp.ejercicio), exp, "desistimiento")
    assert p.monto_liberado == total and total > 0
    _acordar_y_cumplir(usuarios, p)
    exp.refresh_from_db()
    assert exp.estado.clave == "recurso_liberado" and RecursoLiberado.objects.get(expediente=exp).monto == total


def test_hu_6_1_el_desistimiento_por_el_portal_tiene_el_mismo_acuse(contratadas, cuenta_portal, usuarios, client):
    _, (exp,) = contratadas("CC")
    cuenta = cuenta_portal(exp)
    client.login(username=cuenta.username, password=CONTRASENA_PORTAL)
    html = client.get(reverse("portal:expediente", args=[exp.folio])).content.decode()
    assert 'data-prueba="desistimiento-sustitucion"' in html and "Desistimiento por escrito" in html
    r = client.post(reverse("seguimiento_portal:enviar", args=[exp.folio]),
                    {"tipo": "desistimiento", "archivo": _archivo(), "motivo": "Ya no podré atenderlo.",
                     "firmas": reasignacion.puntos_firma(exp)})
    assert r.status_code == 302
    s = exp.solicitudes_seguimiento.get()
    assert s.medio == "portal" and s.presentada_por == cuenta and s.acuse.tipo == "solicitud_desistimiento"
    assert dict(s.acuse.contenido["renglones"])["Cuenta del portal"] == cuenta.username
    exp.refresh_from_db()
    ev = exp.eventos.get(estado_destino__clave="sustitucion")
    assert exp.estado.clave == "sustitucion" and ev.usuario is None and "desde el portal" in ev.descripcion
    assert client.post(reverse("seguimiento:proponer", args=[exp.folio]), {"tipo": "desistimiento"}).status_code in (302, 403)
    assert not exp.propuestas_seguimiento.exists()


def test_hu_6_1_con_ministraciones_pagadas_la_baja_cancela_y_libera_solo_lo_no_ministrado(pagada, usuarios):
    exp = pagada("CC")                                               # 6 ha: $8,400 pagados de $12,000
    _desistir(usuarios, exp)
    p = reasignacion.proponer(usuarios["dir_drff"], exp, "desistimiento")
    assert p.monto_liberado == Decimal("3600.00") and "se debe reintegrar" in p.descripcion
    _acordar_y_cumplir(usuarios, p)
    exp.refresh_from_db()
    assert exp.estado.clave == "cancelada" and RecursoLiberado.objects.get(expediente=exp).monto == Decimal("3600.00")


def test_hu_6_1_peg_no_tiene_segunda_persona_y_la_defuncion_libera_el_lugar(peg_contratado, usuarios):
    exp = peg_contratado()
    assert [t["clave"] for t in reasignacion.tipos_solicitud(exp)] == ["fallecimiento", "desistimiento"]
    with pytest.raises(ValidationError, match="no recibe"):
        reasignacion.registrar_solicitud(delegado_de(usuarios, exp), exp, "sustitucion", _archivo(), segunda={"nombre": "X"})
    reasignacion.registrar_solicitud(delegado_de(usuarios, exp), exp, "fallecimiento", _archivo(), "Comisariado",
                                     fecha_hecho=timezone.localdate())
    assert plazos.vencimiento(exp, "interes_segunda_beneficiaria") is None
    p = reasignacion.proponer(usuarios["dir_dpf"], exp, "fallecimiento")
    assert "8.1.9.2 g" in p.fundamento
    _acordar_y_cumplir(usuarios, p)
    exp.refresh_from_db()
    assert exp.estado.clave in ("recurso_liberado", "cancelada")


# ----------------------------------------------------------------------------- casos especiales
def test_hu_6_1_el_caso_fortuito_se_atiende_con_propuesta_y_acuerdo_y_reanuda(pagada, usuarios):
    exp = pagada("RHF")
    comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "caso_fortuito", _archivo("denuncia.pdf"),
                                   "Incendio en el predio.", fecha_hecho=timezone.localdate())
    exp.refresh_from_db()
    assert exp.estado.clave == "caso_fortuito"
    assert [t for t, _ in reasignacion.tipos_propuesta(exp)][0] == "caso_fortuito"   # y, de HU-6.2, cancelación y suspensión
    with pytest.raises(ValidationError, match="Elija"):
        reasignacion.proponer(usuarios["dir_drff"], exp, "caso_fortuito")
    p = reasignacion.proponer(usuarios["dir_drff"], exp, "caso_fortuito", resolucion="continuar")
    assert p.monto_liberado == 0 and p.datos["estado_previo"] == "pagada"
    _acordar_y_cumplir(usuarios, p)
    exp.refresh_from_db()
    assert exp.estado.clave == "pagada"                                # vuelve al estado del que salió


def test_hu_6_1_el_caso_fortuito_puede_terminar_sin_sancion_y_liberar_lo_no_ministrado(pagada, usuarios):
    exp = pagada("PS")
    comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "caso_fortuito", _archivo(), "Helada.",
                                   fecha_hecho=timezone.localdate())
    p = reasignacion.proponer(usuarios["dir_drff"], exp, "caso_fortuito", resolucion="liberar")
    assert p.monto_liberado == reasignacion.por_ministrar(exp) > 0
    _acordar_y_cumplir(usuarios, p)
    exp.refresh_from_db()
    assert exp.estado.clave == "recurso_liberado" and RecursoLiberado.objects.get(expediente=exp).origen == "caso_fortuito"


def test_hu_6_1_sobrevivencia_menor_por_causas_no_imputables_la_aprueba_el_comite(pagada, usuarios):
    exp = pagada("PS", cuantas=2)[1]                                 # mantenimiento de plantaciones: sobrevivencia mínima 50 %
    deleg = delegado_de(usuarios, exp)
    comprobaciones.registrar_envio(deleg, exp, "aviso_termino", fecha_hecho=timezone.localdate() - timedelta(days=1))
    verificacion.registrar_verificacion(deleg, exp, "formato_verificacion", _archivo("formato.pdf"), timezone.localdate(),
                                        "2.5", "40")
    exp.refresh_from_db()
    assert verificacion.vigente(exp).resultado == "incumplimiento"
    assert not verificacion.fuente_verificacion(exp, 2)[0]
    p = reasignacion.proponer(usuarios["dir_drff"], exp, "sobrevivencia_menor")
    assert "9.4.3 c" in p.fundamento
    _acordar_y_cumplir(usuarios, p)
    cumple, texto, *_ = verificacion.fuente_verificacion(exp, 2)
    assert cumple and "aprobada por el Comité" in texto


def test_hu_6_1_mfs_prorroga_por_causa_externa_con_adendum(pagada, usuarios, pdf):
    exp = pagada("MFS")
    deleg = delegado_de(usuarios, exp)
    with pytest.raises(PermissionDenied):
        reasignacion.solicitar_prorroga(usuarios["dir_drff"], exp, "Auditoría pospuesta")
    p = reasignacion.solicitar_prorroga(deleg, exp, "La entidad certificadora pospuso la auditoría.", date(2027, 2, 26),
                                        _archivo(), date(2026, 12, 15))
    exp.refresh_from_db()
    assert exp.estado.clave == "prorroga_solicitada" and p.acuse and "R-17" in p.acuse.contenido["nota"]
    with pytest.raises(ValidationError, match="plazo nuevo"):
        reasignacion.resolver_prorroga(usuarios["dir_drff"], p, True, "Procede.")
    reasignacion.resolver_prorroga(usuarios["dir_drff"], p, True, "Causa externa acreditada.", date(2027, 2, 26), _archivo("adendum.pdf"))
    p.refresh_from_db()
    exp.refresh_from_db()
    assert p.autorizada and p.adendum.plazo_nuevo == date(2027, 2, 26) and p.adendum.contrato == exp.contrato
    assert exp.estado.clave == "en_ejecucion" and exp.notificaciones.filter(asunto__contains="prórroga").exists()
    otro = pagada("PS")
    with pytest.raises(ValidationError, match="no prevé prórroga"):
        reasignacion.solicitar_prorroga(delegado_de(usuarios, otro), otro, "x")


# ----------------------------------------------------------------------------- ganchos y pantallas
def test_hu_6_1_un_acuerdo_sin_propuesta_solo_deja_constancia(notificadas, usuarios):
    _, (_, dos, _) = notificadas("CC", cuantas=3, presupuesto=12000)
    s = _sesion(usuarios, dos.ejercicio)
    # Un acuerdo de constancia (sin efecto en los listados) tomado directamente por el Comité (HU-2.4).
    a = dictamen_seguimiento.registrar_acuerdo(usuarios["comite"], s, "caso_fortuito", "Atender el aviso", [dos],
                                               causa="Aviso de la Delegación")
    assert reasignacion.ejecutar_acuerdo in dictamen_seguimiento.RECEPTORES["caso_fortuito"]
    dictamen_seguimiento.cumplir(usuarios["dir_drff"], a)
    dos.refresh_from_db()
    assert dos.estado.clave == "lista_espera" and not Propuesta.objects.exists()


def test_hu_6_1_pestana_pagina_y_bandejas(contratadas, usuarios, client, contrasena):
    _, (exp,) = contratadas("CC")
    s = _desistir(usuarios, exp)
    client.login(username="dir_drff", password=contrasena)
    html = client.get(reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=seguimiento").content.decode()
    assert s.acuse.folio in html and 'data-prueba="proponer-comite"' in html and "HU-6.1" not in html
    assert "Proponer al Comité" in html and "sprint" not in html.lower()
    assert 'data-prueba="panel-solicitudes-por-proponer"' in client.get(reverse("nucleo:bandeja")).content.decode()
    r = client.post(reverse("seguimiento:proponer", args=[exp.folio]), {"tipo": "desistimiento"})
    assert r.status_code == 302 and exp.propuestas_seguimiento.count() == 1
    html = client.get(reverse("seguimiento:pagina")).content.decode()
    assert 'data-prueba="propuestas"' in html and exp.folio in html
    client.login(username="comite", password=contrasena)
    _sesion(usuarios, exp.ejercicio)
    p = exp.propuestas_seguimiento.get()
    html = client.get(reverse("seguimiento:pagina")).content.decode()
    assert 'data-prueba="propuestas-por-llevar"' in html
    sesion = reasignacion.sesiones_para(p).first()
    r = client.post(reverse("seguimiento:llevar_a_sesion", args=[p.pk]), {f"p{p.pk}-sesion": sesion.pk, f"p{p.pk}-aprueba": "si"})
    p.refresh_from_db()
    assert r.status_code == 302 and p.acuerdo and p.estado == "en_sesion"
    client.login(username="del_amecameca", password=contrasena)
    assert client.get(reverse("seguimiento:pagina")).status_code == 403
