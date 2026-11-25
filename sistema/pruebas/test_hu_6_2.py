"""HU-6.2 · Incumplimientos y reintegros: cada omisión con su plazo; cancelación por acuerdo con su requerimiento de devolución
(monto y cuenta) y la inscripción en el Listado de Personas Beneficiarias Incumplidas; comprobación del depósito; bajas
pendientes (cheque vencido, reportes de Guardabosques, faltantes vencidos), siempre confirmadas por una persona (P-08)."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from dictamen import seguimiento as dictamen_seguimiento
from dictamen.models import MovimientoListado, PersonaIncumplida
from ejecucion import comprobaciones, verificacion
from nucleo import extensiones, plazos, reloj
from nucleo.models import Evento, Hito, Programa
from seguimiento import incumplimientos, reasignacion
from seguimiento.models import Senalamiento

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de, direccion_de
from .fixtures_m4 import *  # noqa: F401,F403
from .fixtures_m5 import *  # noqa: F401,F403
from .test_hu_6_1 import _acordar_y_cumplir, _archivo, _desistir, _sesion

pytestmark = pytest.mark.django_db


def _cumplir(usuarios, propuesta, aprueba=True):
    """La Secretaría Técnica lleva la propuesta a sesión y la unidad responsable del acuerdo lo cumple."""
    s = _sesion(usuarios, propuesta.ejercicio)
    acuerdo = reasignacion.llevar_a_sesion(usuarios["comite"], propuesta, s, aprueba)
    quien = next(u for u in usuarios.values() if u.unidad_id == acuerdo.unidad_responsable_id)
    dictamen_seguimiento.cumplir(quien, acuerdo, "Cumplido.")
    return acuerdo


def _cuenta(usuarios, clave="CC"):
    return incumplimientos.registrar_cuenta(usuarios["finanzas"], Programa.objects.get(clave=clave), "PROBOSQUE",
                                            "Banco de prueba", "CUENTA-PRUEBA-0001", "REF-REINTEGRO")


def _con_omision_vencida(pagada, usuarios, programa="CC"):
    with reloj.en("2026-09-01 10:00"):
        exp = pagada(programa)
        aviso = incumplimientos.avisar_omision(direccion_de(usuarios, exp.ejercicio), exp, "No entregó la evidencia de los trabajos.",
                                               date(2026, 9, 15))
    return exp, aviso


def test_hu_6_2_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-6.2")
    assert "trazabilidad" in hu["criterios"][-1]
    assert hu["criterios"][:-1] == ["Cada omisión tiene su plazo para corregirse.",
                               "Un apoyo cancelado tiene su requerimiento de devolución con el monto y la cuenta para el depósito.",
                               "La persona con apoyo cancelado está en el Listado de Personas Beneficiarias Incumplidas."]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M6.2")
    assert {"CC-ARP-07", "CC-UJ-03", "CC-AF-02", "PS-UJ-03", "PSA-AF-02"} <= set(funcion["necesidades"])
    assert "planta no establecida" in necesidades["PS-UJ-03"]["texto"] and "Fiduciaria" in necesidades["PSA-AF-02"]["texto"]


# ----------------------------------------------------------------------------- criterio 1
def test_hu_6_2_cada_omision_tiene_su_plazo_para_corregirse(pagada, usuarios):
    with reloj.en("2026-09-01 10:00"):
        exp = pagada("CC")
        drff = usuarios["dir_drff"]
        with pytest.raises(ValidationError, match="plazo"):
            incumplimientos.avisar_omision(drff, exp, "Falta la evidencia.", None)
        with pytest.raises(ValidationError, match="posterior al aviso"):
            incumplimientos.avisar_omision(drff, exp, "Falta la evidencia.", date(2026, 9, 1))
        with pytest.raises(PermissionDenied):
            incumplimientos.avisar_omision(delegado_de(usuarios, exp), exp, "Falta la evidencia.", date(2026, 9, 15))
        aviso = incumplimientos.avisar_omision(drff, exp, "Falta la evidencia fotográfica.", date(2026, 9, 15),
                                               "8.1.8.1, fr. I: No realizar las actividades comprometidas")
    exp.refresh_from_db()
    assert exp.estado.clave == "omisiones_por_subsanar" and aviso.vence == date(2026, 9, 15)
    v = plazos.vencimiento(exp, "subsanar_omisiones")
    assert v.vencimiento == date(2026, 9, 15) and v.decision_propia
    assert Hito.objects.get(expediente=exp, clave="aviso_omision").datos["vence"] == "2026-09-15"
    renglones = dict(aviso.acuse.contenido["renglones"])
    assert renglones["Fecha límite para subsanar"].startswith("15/09/2026") and "no fijan días" in aviso.acuse.contenido["nota"]
    assert aviso.notificacion.tipo == "omision" and aviso.notificacion.delegacion == exp.delegacion
    with reloj.en("2026-09-10 10:00"):
        incumplimientos.dar_por_subsanadas(drff, aviso, "Entregó la evidencia el 9-sep.")
    exp.refresh_from_db()
    assert exp.estado.clave == "pagada" and aviso.situacion() == "subsanada"


def test_hu_6_2_al_vencer_sin_subsanar_el_sistema_senala_y_una_persona_propone(pagada, usuarios, client, contrasena):
    exp, aviso = _con_omision_vencida(pagada, usuarios)
    assert incumplimientos.revisar(date(2026, 9, 15)) == 0           # el último día todavía está en plazo
    assert incumplimientos.revisar(date(2026, 9, 16)) == 1
    assert incumplimientos.revisar(date(2026, 9, 17)) == 0           # una sola vez
    assert incumplimientos.revisar in extensiones.REVISIONES_PLAZO
    s = Senalamiento.objects.get(expediente=exp, tipo="omision_vencida")
    exp.refresh_from_db()
    assert exp.estado.clave == "omisiones_por_subsanar" and not exp.propuestas_seguimiento.exists()   # P-08: nada se ejecuta solo
    assert exp.eventos.filter(tipo="senalamiento_omision_vencida", usuario=None).exists()
    client.login(username="dir_drff", password=contrasena)
    assert 'data-prueba="panel-senalamientos"' in client.get(reverse("nucleo:bandeja")).content.decode()
    r = client.post(reverse("seguimiento:confirmar", args=[s.pk]))
    assert r.status_code == 302
    s.refresh_from_db()
    assert s.atendido_por == usuarios["dir_drff"] and s.propuesta.tipo == "cancelacion"
    assert "Listado de Personas Beneficiarias Incumplidas" in s.propuesta.descripcion


# ----------------------------------------------------------------------------- criterios 2 y 3
def test_hu_6_2_cancelacion_con_requerimiento_monto_cuenta_listado_y_reintegro(pagada, usuarios):
    exp, aviso = _con_omision_vencida(pagada, usuarios)                   # CC 6 ha: $8,400 ministrados
    incumplimientos.revisar(date(2026, 9, 16))
    s = Senalamiento.objects.get(expediente=exp)
    incumplimientos.confirmar(usuarios["dir_drff"], s)
    p = Senalamiento.objects.get(pk=s.pk).propuesta
    acuerdo = _cumplir(usuarios, p)
    assert acuerdo.tipo == "cancelacion" and acuerdo.unidad_responsable.clave == "UJ"
    exp.refresh_from_db()
    assert exp.estado.clave == "cancelada"
    # Criterio 3: inscripción automática en el Listado con el acuerdo como fundamento (y el cotejo de HU-2.2 la encuentra).
    inscrita = PersonaIncumplida.objects.get(persona=exp.beneficiaria)
    assert inscrita.activa and acuerdo.numero in inscrita.acuerdo and inscrita.registrado_por == usuarios["juridica"]
    assert exp.eventos.filter(tipo="inscripcion_incumplidas").exists()
    assert MovimientoListado.objects.get(expediente=exp, origen="cancelacion", movimiento="sale").monto == Decimal("3600.00")
    req = exp.requerimientos.get()
    assert req.estado == "por_emitir" and req.monto_total == Decimal("8400.00") and req.acuerdo == acuerdo
    with pytest.raises(ValidationError, match="cuenta para los reintegros"):
        incumplimientos.emitir_requerimiento(usuarios["juridica"], req)
    with pytest.raises(PermissionDenied):
        _cuenta({"finanzas": usuarios["juridica"]})
    cuenta = _cuenta(usuarios)
    with pytest.raises(ValidationError, match="no piden el valor de la planta"):
        incumplimientos.emitir_requerimiento(usuarios["juridica"], req, plantas=10, precio_planta="5", fuente_precio="x")
    incumplimientos.emitir_requerimiento(usuarios["juridica"], req)
    req.refresh_from_db()
    exp.refresh_from_db()
    # Criterio 2: el requerimiento tiene el monto y la cuenta para el depósito, y lo notifica la Delegación.
    assert req.estado == "emitido" and req.cuenta == cuenta and exp.estado.clave == "en_devolucion"
    renglones = dict(req.acuse.contenido["renglones"])
    assert renglones["Monto por devolver"] == "$8,400.00" and "CUENTA-PRUEBA-0001" in renglones["Cuenta para el depósito"]
    assert req.notificacion.tipo == "devolucion" and req.notificacion.delegacion == exp.delegacion
    af = usuarios["finanzas"]
    with pytest.raises(ValidationError, match="no coincide"):
        incumplimientos.comprobar_deposito(af, req, timezone.localdate(), "8000", "DEP-1", _archivo("deposito.pdf"))
    incumplimientos.comprobar_deposito(af, req, timezone.localdate(), "8400", "DEP-1", _archivo("deposito.pdf"))
    exp.refresh_from_db()
    req.refresh_from_db()
    assert exp.estado.clave == "reintegrada" and req.estado == "depositado" and req.acuse_deposito
    assert MovimientoListado.objects.get(expediente=exp, origen="reintegro", movimiento="libera").monto == Decimal("8400.00")


def test_hu_6_2_el_requerimiento_suma_el_valor_de_la_planta_no_establecida_en_ps(pagada, usuarios):
    exp = pagada("PS")
    assert incumplimientos.planta_aplica(exp) and "8.1.9" in incumplimientos.fundamento_planta(exp)
    p = reasignacion.proponer(usuarios["dir_drff"], exp, "cancelacion", "Planta no establecida en el polígono.")
    _cumplir(usuarios, p)
    _cuenta(usuarios, "PS")
    req = exp.requerimientos.get()
    with pytest.raises(ValidationError, match="precio por planta"):
        incumplimientos.emitir_requerimiento(usuarios["juridica"], req, plantas=300)
    incumplimientos.emitir_requerimiento(usuarios["juridica"], req, plantas=300, precio_planta="6.50",
                                         fuente_precio="Listado de precios de la Secretaría de Finanzas 2026")
    req.refresh_from_db()
    assert req.monto_planta == Decimal("1950.00") and req.monto_total == req.monto_base + Decimal("1950.00")
    assert "300 plantas" in dict(req.acuse.contenido["renglones"])["Valor de la planta no establecida"]


def test_hu_6_2_lo_ministrado_de_mas_por_la_verificacion_y_la_incidencia_de_incumplimiento(pagada, usuarios):
    exp = pagada("CC")                                                    # 6 ha: $8,400 pagados
    deleg = delegado_de(usuarios, exp)
    comprobaciones.registrar_envio(deleg, exp, "aviso_termino", fecha_hecho=timezone.localdate() - timedelta(days=1))
    verificacion.registrar_verificacion(deleg, exp, "informe_final_firmado", _archivo(), timezone.localdate(), "3",
                                        incidencias=[{"tipo": "incumplimiento", "descripcion": "Solo se trabajaron 3 ha.",
                                                      "archivo": _archivo("acta.pdf")}])
    v = verificacion.vigente(exp)
    assert v.excedente_ministrado == Decimal("2400.00")                  # $8,400 − 3 ha × $2,000
    s = Senalamiento.objects.get(expediente=exp, tipo="incidencia")     # AL_INCIDENCIA
    assert incumplimientos.al_incidencia in extensiones.AL_INCIDENCIA
    with pytest.raises(ValidationError, match="formulario"):
        incumplimientos.confirmar(usuarios["dir_drff"], s)
    incumplimientos.avisar_omision(usuarios["dir_drff"], exp, "Concluir las 3 ha restantes.", timezone.localdate() + timedelta(days=20),
                                   incidencia=v.incidencias.get())
    s.refresh_from_db()
    assert s.atendido_en and v.incidencias.get().atendida_en
    p = reasignacion.proponer(usuarios["dir_drff"], exp, "cancelacion", base="excedente")
    assert p.datos["por_devolver"] == "2400.00"
    _cumplir(usuarios, p)
    assert exp.requerimientos.get().monto_total == Decimal("2400.00")


def test_hu_6_2_la_cuenta_de_psahem_es_configurable_y_la_duda_se_dice(entregado, usuarios):
    cfg = incumplimientos.config_cuenta(Programa.objects.get(clave="PSA"))
    assert cfg["titular"].startswith("Fiduciaria") and "R-14" in cfg["duda"]
    assert incumplimientos.config_cuenta(Programa.objects.get(clave="CC"))["titular"] == "PROBOSQUE"
    c = incumplimientos.registrar_cuenta(usuarios["finanzas"], Programa.objects.get(clave="PSA"), "Fiduciaria del FIPASAHEM",
                                         "Banco de prueba", "CUENTA-FIDUCIARIA-01")
    otra = incumplimientos.registrar_cuenta(usuarios["finanzas"], Programa.objects.get(clave="PSA"), "PROBOSQUE", "Banco",
                                            "CUENTA-02")
    c.refresh_from_db()
    assert not c.vigente and incumplimientos.cuenta_vigente(Programa.objects.get(clave="PSA")) == otra


# ----------------------------------------------------------------------------- bajas pendientes
def test_hu_6_2_baja_por_cheque_vencido_sin_cobrar(entregado, usuarios):
    exp, cheque = entregado()
    type(cheque).objects.filter(pk=cheque.pk).update(entregado_en=timezone.now() - timedelta(days=120))
    assert incumplimientos.revisar(timezone.localdate()) == 1
    s = Senalamiento.objects.get(expediente=exp, tipo="cheque_vencido")
    assert "fr. VII" in s.fundamento and incumplimientos.ministrado_efectivo(exp) == 0
    exp.refresh_from_db()
    assert exp.estado.clave == "cheque_entregado"                       # no se da de baja solo
    incumplimientos.confirmar(usuarios["dir_drff"], s)
    s.refresh_from_db()
    _cumplir(usuarios, s.propuesta)
    exp.refresh_from_db()
    assert exp.estado.clave == "cancelada" and PersonaIncumplida.objects.filter(persona=exp.beneficiaria).exists()
    assert exp.requerimientos.get().estado == "sin_monto"                # el cheque no se cobró: nada por devolver


def test_hu_6_2_guardabosque_que_no_entrega_suspension_y_baja(peg_contratado, usuarios, monkeypatch):
    exp = peg_contratado()
    from ejecucion import reportes

    malas = []
    monkeypatch.setattr(reportes, "periodos_senalados", lambda e: list(malas))
    for i, mes in enumerate(("2026-07", "2026-08", "2026-09"), 1):
        ev = SimpleNamespace(expediente=exp, periodo=mes, nombre_periodo=mes, resultado="no_entrego",
                             get_resultado_display=lambda: "No entregó")
        malas.append(ev)
        incumplimientos.al_reporte_incumplido(ev)
        if i < 3:
            assert Senalamiento.objects.filter(expediente=exp, tipo="reportes_incumplidos").count() == i
    baja = Senalamiento.objects.get(expediente=exp, tipo="baja_reportes")
    assert "8.1.9.2 f" in baja.fundamento and incumplimientos.al_reporte_incumplido in extensiones.AL_REPORTE_INCUMPLIDO
    sus = Senalamiento.objects.filter(expediente=exp, tipo="reportes_incumplidos").first()
    incumplimientos.confirmar(usuarios["dir_dpf"], sus)
    sus.refresh_from_db()
    assert sus.propuesta.tipo == "suspension"
    _cumplir(usuarios, sus.propuesta)
    exp.refresh_from_db()
    assert exp.estado.clave == "suspendida"
    incumplimientos.confirmar(usuarios["dir_dpf"], baja)
    baja.refresh_from_db()
    _cumplir(usuarios, baja.propuesta)
    exp.refresh_from_db()
    assert exp.estado.clave == "cancelada" and PersonaIncumplida.objects.get(persona=exp.beneficiaria).nombre == "Margarito Sánchez Ruiz"
    assert MovimientoListado.objects.filter(expediente=exp, movimiento="sale").exists()   # su lugar queda para la lista de espera


def test_hu_6_2_levantar_la_suspension_regresa_al_estado_previo(pagada, usuarios):
    exp = pagada("RHF")
    p = reasignacion.proponer(usuarios["dir_drff"], exp, "suspension")
    _cumplir(usuarios, p)
    exp.refresh_from_db()
    assert exp.estado.clave == "suspendida"
    p2 = reasignacion.proponer(usuarios["dir_drff"], exp, "levantar_suspension")
    _cumplir(usuarios, p2)
    exp.refresh_from_db()
    assert exp.estado.clave == "pagada"


def test_hu_6_2_desecho_por_faltantes_vencidos_lo_confirma_una_persona(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    Evento.registrar(exp, None, "plazo_vencido", "Venció el 27/03/2026 el plazo para completar la documentación desde la recepción.")
    assert incumplimientos.revisar(timezone.localdate()) == 1
    s = Senalamiento.objects.get(expediente=exp, tipo="faltantes_vencidos")
    exp.refresh_from_db()
    assert exp.estado.clave == "recibida"
    with pytest.raises(PermissionDenied):
        incumplimientos.confirmar(usuarios["del_toluca"], s)
    incumplimientos.confirmar(usuarios["del_amecameca"], s)
    exp.refresh_from_db()
    ev = exp.eventos.get(estado_destino__clave="desechada")
    assert exp.estado.clave == "desechada" and ev.usuario == usuarios["del_amecameca"] and "se tendrá por desechada" in ev.motivo


def test_hu_6_2_el_desistimiento_con_ministraciones_genera_el_requerimiento_sin_inscribir(pagada, usuarios):
    exp = pagada("PS")
    _desistir(usuarios, exp)
    _acordar_y_cumplir(usuarios, reasignacion.proponer(usuarios["dir_drff"], exp, "desistimiento"))
    exp.refresh_from_db()
    req = exp.requerimientos.get()
    assert exp.estado.clave == "cancelada" and req.monto_base == reasignacion.ministrado(exp)
    assert not PersonaIncumplida.objects.filter(persona=exp.beneficiaria).exists()
    _cuenta(usuarios, "PS")
    incumplimientos.emitir_requerimiento(usuarios["juridica"], req)
    req.refresh_from_db()
    assert "10 días hábiles" in req.plazo_texto                          # PS: desistimiento_reintegro


def test_hu_6_2_pantallas_de_juridica_y_finanzas(pagada, usuarios, client, contrasena):
    exp = pagada("CC")
    p = reasignacion.proponer(usuarios["dir_drff"], exp, "cancelacion")
    _cumplir(usuarios, p)
    client.login(username="juridica", password=contrasena)
    assert 'data-prueba="panel-requerimientos"' in client.get(reverse("nucleo:bandeja")).content.decode()
    html = client.get(reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=seguimiento").content.decode()
    assert 'id="form-requerimiento"' in html and 'data-prueba="inscripcion-listado"' in html and "HU-6.2" not in html
    client.login(username="finanzas", password=contrasena)
    cc = Programa.objects.get(clave="CC")
    r = client.post(reverse("seguimiento:registrar_cuenta"), {"programa": cc.pk, "titular": "PROBOSQUE", "banco": "Banco",
                                                              "cuenta": "CUENTA-PRUEBA-9"})
    assert r.status_code == 302 and incumplimientos.cuenta_vigente(cc).cuenta == "CUENTA-PRUEBA-9"
    html = client.get(reverse("seguimiento:incumplimientos")).content.decode()
    assert "CUENTA-PRUEBA-9" in html and 'id="form-cuenta"' in html
    client.login(username="juridica", password=contrasena)
    client.post(reverse("seguimiento:emitir_requerimiento", args=[exp.requerimientos.get().pk]), {"plantas": "0"})
    exp.refresh_from_db()
    assert exp.estado.clave == "en_devolucion"
    client.login(username="finanzas", password=contrasena)
    html = client.get(reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=seguimiento").content.decode()
    assert 'id="form-deposito"' in html and "Comprobar el depósito del reintegro" in html


def _filas_de(exp, registro):
    from nucleo.trazabilidad import historial_expediente

    return [f for f in historial_expediente(exp) if f["registro"] == registro]


# ----------------------------------------------------------------------------- criterio 4: trazabilidad
def test_hu_6_2_trazabilidad_del_aviso_el_senalamiento_y_el_requerimiento(pagada, usuarios):
    """Criterio 4: el aviso de omisiones, el señalamiento que confirma una persona y el requerimiento quedan en el
    historial; el señalamiento atendido es un cambio del mismo registro (antes se actualizaba sin dejar rastro)."""
    exp, aviso = _con_omision_vencida(pagada, usuarios)
    drff = usuarios["dir_drff"]
    assert aviso.history.get(history_type="+").history_user == drff
    incumplimientos.revisar(date(2026, 9, 16))
    s = Senalamiento.objects.get(expediente=exp)
    assert s.history.get(history_type="+").history_user is None                     # lo registra el sistema
    incumplimientos.confirmar(drff, s)
    _cumplir(usuarios, Senalamiento.objects.get(pk=s.pk).propuesta)
    s.refresh_from_db()
    assert s.atendido_en is not None
    atendido = s.history.filter(history_type="~", atendido_en__isnull=False).first()
    assert atendido is not None and atendido.history_user == drff                   # quien lo confirmó
    assert exp.requerimientos.get().history.filter(history_type="+").exists()
    assert any(f["usuario"] == drff for f in _filas_de(exp, "Aviso de omisiones"))
    assert len(_filas_de(exp, "Señalamiento del sistema")) >= 2 and _filas_de(exp, "Requerimiento de devolución")
