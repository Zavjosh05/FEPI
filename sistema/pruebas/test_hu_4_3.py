"""HU-4.3 · Evaluación de reportes (Guardabosques, PEG): la Delegación revisa los reportes mensuales y los acuses de depósito, la
Dirección de Protección Forestal evalúa por Guardabosque y por periodo y envía la evaluación al CASPEG, que la valida con un acuerdo
de seguimiento (HU-2.4); la ministración pide la evaluación validada."""
from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse

from dictamen import seguimiento, sesiones
from dictamen.models import TipoSesion
from ejecucion import comprobaciones, reportes
from ejecucion.models import EnvioEvaluacion, EvaluacionPeriodo, RevisionReporte
from nucleo import extensiones, reloj
from nucleo.models import Notificacion
from pagos import pagos, solicitudes

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m2 import documento_sesion, fecha_sesion
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m4 import *  # noqa: F401,F403
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db
FIRMA = "2026-06-16 10:00"       # la firma de los Guardabosques (Convocatoria): el primer mes que reportan es junio
JULIO = "2026-07-06 11:00"       # junio ya terminó
SEPTIEMBRE = "2026-09-04 11:00"  # julio y agosto ya terminaron


@pytest.fixture
def dos(contratadas, usuarios):
    """Dos Guardabosques con el contrato firmado el 16-jun: ``a`` (Amecameca) y ``b`` (Amanalco)."""
    with reloj.en(FIRMA):
        _, (a, b) = contratadas("PEG", cuantas=2)
    return a, b


def _reporte(usuarios, exp, periodo, pdf, cuando):
    with reloj.en(cuando):
        return comprobaciones.registrar_envio(delegado_de(usuarios, exp), exp, "reporte_mensual", pdf(f"reporte_{periodo}.pdf"),
                                              periodo=periodo)


def _validar(usuarios, ejercicio, periodo, expedientes, cuando):
    """El CASPEG valida la evaluación del periodo con un acuerdo de su sesión de seguimiento (HU-2.4)."""
    with reloj.en(cuando):
        s = sesiones.crear_sesion(usuarios["comite"], ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(8), "Sala", "Quórum\nValidación")
        sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(), "Evaluación")
        sesiones.enviar_convocatoria(usuarios["comite"], s)
        return seguimiento.registrar_acuerdo(usuarios["comite"], s, "validacion_reportes", f"Se valida la evaluación de {periodo}",
                                             expedientes, periodo=periodo)


def _junio_completo(usuarios, a, b, pdf):
    """Junio: ``a`` entregó y cumple, ``b`` entregó y no cumple; la evaluación se envía al CASPEG el 6-jul."""
    dpf = usuarios["dir_dpf"]
    ra = _reporte(usuarios, a, "2026-06", pdf, "2026-07-02 10:00")
    rb = _reporte(usuarios, b, "2026-06", pdf, "2026-07-02 11:00")
    with reloj.en("2026-07-03 10:00"):
        reportes.revisar(delegado_de(usuarios, a), ra, "revisado")
        reportes.revisar(delegado_de(usuarios, b), rb, "con_observaciones", "El reporte no trae las firmas del núcleo agrario.")
    with reloj.en(JULIO):
        reportes.evaluar_periodo(dpf, a, "2026-06", "cumple")
        reportes.evaluar_periodo(dpf, b, "2026-06", "no_cumple", "Sin las firmas del núcleo agrario.")
        return reportes.enviar_evaluacion(dpf, a.ejercicio, "2026-06")


def test_hu_4_3_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-4.3")
    assert hu["criterios"] == ["Existe la evaluación por Guardabosque y por periodo.", "Queda identificado quién no entregó su reporte."]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M4.3")
    assert set(funcion["necesidades"]) == {"PEG-BEN-01", "PEG-BEN-02", "PEG-DRF-03", "PEG-DPF-05"}
    assert "evalúa los reportes mensuales" in necesidades["PEG-DPF-05"]["texto"] and "CASPEG" in necesidades["PEG-DPF-05"]["texto"]


# ----------------------------------------------------------------------------- Delegación
def test_hu_4_3_la_delegacion_revisa_reportes_y_acuses_con_su_resultado(dos, usuarios, pdf):
    a, b = dos
    deleg = delegado_de(usuarios, a)
    reporte = _reporte(usuarios, a, "2026-06", pdf, "2026-07-02 10:00")
    with reloj.en("2026-07-02 12:00"):
        acuse = comprobaciones.registrar_envio(deleg, a, "acuse_deposito", pdf("acuse.pdf"), fecha_hecho=date(2026, 7, 1))
    assert set(reportes.por_revisar(deleg)) == {reporte, acuse}
    assert not reportes.por_revisar(delegado_de(usuarios, b)).exists() and not reportes.por_revisar(usuarios["dir_dpf"]).exists()
    with pytest.raises(PermissionDenied):                  # solo la Delegación del expediente
        reportes.revisar(delegado_de(usuarios, b), reporte, "revisado")
    with pytest.raises(PermissionDenied):
        reportes.revisar(usuarios["dir_dpf"], reporte, "revisado")
    with pytest.raises(ValidationError, match="observaciones"):
        reportes.revisar(deleg, reporte, "con_observaciones")
    with pytest.raises(ValidationError, match="observaciones"):
        reportes.revisar(deleg, reporte, "devuelto")
    with reloj.en("2026-07-03 09:00"):
        r1 = reportes.revisar(deleg, reporte, "revisado")
        r2 = reportes.revisar(deleg, acuse, "con_observaciones", "El acuse no trae la fecha de recepción.")
    assert (r1.resultado, r2.resultado) == ("revisado", "con_observaciones") and r1.revisada_por == deleg
    assert not reportes.por_revisar(deleg).exists()
    with pytest.raises(ValidationError, match="ya se revisó"):
        reportes.revisar(deleg, reporte, "revisado")
    reporte.refresh_from_db()
    assert reporte.revisada_en and a.eventos.filter(tipo="reporte_revisado").count() == 2
    with pytest.raises(ValidationError, match="con su resultado"):    # el reporte de PEG no se «marca como revisado»
        comprobaciones.marcar_revisada(deleg, reporte)


def test_hu_4_3_un_reporte_devuelto_se_notifica_y_se_puede_volver_a_enviar(dos, usuarios, pdf):
    a, _ = dos
    deleg = delegado_de(usuarios, a)
    primero = _reporte(usuarios, a, "2026-06", pdf, "2026-07-02 10:00")
    with reloj.en("2026-07-03 10:00"):
        reportes.revisar(deleg, primero, "devuelto", "Falta el Reporte de Integridad Territorial.")
    assert Notificacion.objects.filter(expediente=a, asunto__contains="devuelto").exists()
    with reloj.en("2026-07-05 10:00"):
        # lo devuelto se vuelve a enviar: el nuevo envío del mismo periodo es el que cuenta
        segundo = comprobaciones.registrar_envio(deleg, a, "reporte_mensual", pdf("corregido.pdf"), periodo="2026-06")
    assert reportes.reporte_vigente(a, "2026-06") == segundo
    s = reportes.situacion(a, reportes.periodos(a)[0], date(2026, 7, 6))
    assert s["estado"] == "por_revisar" and s["reporte"] == segundo
    with pytest.raises(ValidationError, match="revisó"):
        reportes.revisar(deleg, primero, "revisado")
    # un reporte devuelto que no se corrige no se evalúa
    with reloj.en("2026-08-05 10:00"):
        julio = comprobaciones.registrar_envio(deleg, a, "reporte_mensual", pdf("julio.pdf"), periodo="2026-07")
        reportes.revisar(deleg, julio, "devuelto", "Ilegible.")
        with pytest.raises(ValidationError, match="Ya se entregó"):          # el de junio, ya corregido, no se duplica
            comprobaciones.registrar_envio(deleg, a, "reporte_mensual", pdf("x.pdf"), periodo="2026-06")
    with reloj.en("2026-08-07 10:00"):
        assert reportes.situacion(a, reportes.periodos(a)[1])["estado"] == "devuelto"
        with pytest.raises(ValidationError, match="devolvió"):
            reportes.evaluar_periodo(usuarios["dir_dpf"], a, "2026-07", "cumple")


# ----------------------------------------------------------------------------- criterio 1
def test_hu_4_3_existe_la_evaluacion_por_guardabosque_y_por_periodo(dos, usuarios, pdf):
    """Criterio 1."""
    a, b = dos
    dpf = usuarios["dir_dpf"]
    ra = _reporte(usuarios, a, "2026-06", pdf, "2026-07-02 10:00")
    rb = _reporte(usuarios, b, "2026-06", pdf, "2026-07-02 11:00")
    with reloj.en("2026-07-03 10:00"):
        with pytest.raises(ValidationError, match="no revisa"):           # primero revisa la Delegación
            reportes.evaluar_periodo(dpf, a, "2026-06", "cumple")
        reportes.revisar(delegado_de(usuarios, a), ra, "revisado")
        reportes.revisar(delegado_de(usuarios, b), rb, "revisado")
        with pytest.raises(PermissionDenied):                              # la Delegación no evalúa
            reportes.evaluar_periodo(delegado_de(usuarios, a), a, "2026-06", "cumple")
        with pytest.raises(ValidationError, match="motivo"):
            reportes.evaluar_periodo(dpf, b, "2026-06", "no_cumple")
        with pytest.raises(ValidationError, match="sistema"):              # «no entregó» lo pone el sistema
            reportes.evaluar_periodo(dpf, b, "2026-06", "no_entrego")
        with pytest.raises(ValidationError, match="desde el mes de la firma"):
            reportes.evaluar_periodo(dpf, a, "2026-05", "cumple")
        ea = reportes.evaluar_periodo(dpf, a, "2026-06", "cumple")
        eb = reportes.evaluar_periodo(dpf, b, "2026-06", "no_cumple", "Sin las firmas del núcleo agrario.")
        eb2 = reportes.evaluar_periodo(dpf, b, "2026-06", "no_cumple", "Sin firmas ni evidencia fotográfica.")  # se corrige antes del envío
    assert eb2.pk == eb.pk and EvaluacionPeriodo.objects.filter(periodo="2026-06").count() == 2
    assert (ea.resultado, ea.comprobacion) == ("cumple", ra) and ea.evaluada_por == dpf and ea.unidad == dpf.unidad
    assert not ea.senalado and eb.senalado
    filas = {f["expediente"].pk: f for f in reportes.tabla_del_periodo(a.ejercicio, "2026-06", dpf, date(2026, 7, 4))}
    assert filas[a.pk]["estado"] == "cumple" and filas[b.pk]["estado"] == "no_cumple"
    assert reportes.resumen(filas.values()) == [{"estado": "cumple", "etiqueta": "Cumple", "clase": "success", "n": 1},
                                                {"estado": "no_cumple", "etiqueta": "No cumple", "clase": "danger", "n": 1}]
    assert a.eventos.filter(tipo="reporte_evaluado").exists()


def test_hu_4_3_la_evaluacion_es_por_periodo_y_cada_guardabosque_reporta_desde_el_mes_de_su_firma(contratadas, usuarios):
    with reloj.en("2026-08-03 10:00"):
        _, (exp,) = contratadas("PEG")
    claves = [p["clave"] for p in reportes.periodos(exp)]
    assert claves[0] == "2026-08" and claves[-1] == "2026-12" and len(claves) == 5     # 2026-01 a 2026-07 no se le piden
    assert len(comprobaciones.periodos(exp)) == 12                                    # el ejercicio tiene los 12 meses derivados
    with reloj.en("2026-08-20 10:00"):
        assert [f["periodo"]["clave"] for f in reportes.historial(exp)] == ["2026-08"]  # solo los que ya empezaron


# ----------------------------------------------------------------------------- criterio 2
def test_hu_4_3_queda_identificado_quien_no_entrego_su_reporte(dos, usuarios, pdf, monkeypatch):
    """Criterio 2: el periodo sin reporte entregado queda «no entregó» en automático, visible en la tabla por periodo."""
    a, b = dos
    dpf = usuarios["dir_dpf"]
    señalados = []
    monkeypatch.setattr(extensiones, "AL_REPORTE_INCUMPLIDO", [señalados.append])
    ra = _reporte(usuarios, a, "2026-06", pdf, "2026-07-02 10:00")
    periodo = reportes.periodos(a)[0]
    # durante el periodo todavía no se le puede exigir; al terminar, no entregó
    assert reportes.situacion(b, periodo, date(2026, 6, 20))["estado"] == "sin_reporte"
    s = reportes.situacion(b, periodo, date(2026, 7, 1))
    assert s["estado"] == "no_entrego" and s["automatico"] and s["etiqueta"] == "No entregó" and s["reporte"] is None
    with reloj.en("2026-07-03 10:00"):
        reportes.revisar(delegado_de(usuarios, a), ra, "revisado")
        reportes.evaluar_periodo(dpf, a, "2026-06", "cumple")
        with pytest.raises(ValidationError, match="No hay reporte"):       # no se «evalúa» lo que no se entregó
            reportes.evaluar_periodo(dpf, b, "2026-06", "cumple")
    with reloj.en(JULIO):
        filas = {f["expediente"].pk: f for f in reportes.tabla_del_periodo(a.ejercicio, "2026-06", dpf)}
        assert filas[b.pk]["estado"] == "no_entrego" and filas[a.pk]["estado"] == "cumple"
        envio = reportes.enviar_evaluacion(dpf, a.ejercicio, "2026-06")
    e_b = EvaluacionPeriodo.objects.get(expediente=b, periodo="2026-06")
    assert e_b.resultado == "no_entrego" and e_b.automatica and e_b.senalado and e_b.envio == envio
    assert (envio.cumplen, envio.no_cumplen, envio.no_entregaron) == (1, 0, 1)
    assert señalados == [e_b]                                              # el gancho de HU-6.2 solo corre por quien no cumplió
    assert reportes.periodos_senalados(b) == [e_b] and reportes.periodos_senalados(a) == []
    assert b.eventos.filter(tipo="evaluacion_enviada").exists()


# ----------------------------------------------------------------------------- envío al CASPEG
def test_hu_4_3_la_evaluacion_del_periodo_se_envia_al_caspeg_con_fecha_hora_y_acuse(dos, usuarios, pdf):
    a, b = dos
    dpf = usuarios["dir_dpf"]
    ra = _reporte(usuarios, a, "2026-06", pdf, "2026-07-02 10:00")
    with reloj.en("2026-06-25 10:00"), pytest.raises(ValidationError, match="todavía no termina"):
        reportes.enviar_evaluacion(dpf, a.ejercicio, "2026-06")
    with reloj.en(JULIO):
        with pytest.raises(ValidationError, match="por revisar o evaluar"):   # a todavía no está revisado
            reportes.enviar_evaluacion(dpf, a.ejercicio, "2026-06")
        reportes.revisar(delegado_de(usuarios, a), ra, "revisado")
        with pytest.raises(ValidationError, match="por revisar o evaluar"):   # y falta evaluarlo
            reportes.enviar_evaluacion(dpf, a.ejercicio, "2026-06")
        reportes.evaluar_periodo(dpf, a, "2026-06", "cumple")
        for quien in (delegado_de(usuarios, a), usuarios["comite"], usuarios["finanzas"]):
            with pytest.raises(PermissionDenied):
                reportes.enviar_evaluacion(quien, a.ejercicio, "2026-06")
        with pytest.raises(PermissionDenied):                                # otra Dirección no es la Instancia Ejecutora
            reportes.enviar_evaluacion(usuarios["dir_drff"], a.ejercicio, "2026-06")
        envio = reportes.enviar_evaluacion(dpf, a.ejercicio, "2026-06")
        with pytest.raises(ValidationError, match="No hay evaluaciones por enviar"):
            reportes.enviar_evaluacion(dpf, a.ejercicio, "2026-06")
        with pytest.raises(ValidationError, match="ya se envió"):
            reportes.evaluar_periodo(dpf, a, "2026-06", "no_cumple", "Cambio de opinión")
    assert envio.enviado_en.date() == date(2026, 7, 6) and envio.enviado_por == dpf and envio.unidad == dpf.unidad
    renglones = dict(envio.acuse.contenido["renglones"])
    assert envio.acuse.tipo == "evaluacion_reportes" and envio.acuse.expediente is None and envio.acuse.archivo
    assert renglones["Periodo evaluado"] == "Junio 2026" and "06/07/2026" in renglones["Fecha y hora del envío"]
    assert renglones["Guardabosques"].startswith("2: 1 cumplen, 0 no cumplen y 1 no entregaron")
    assert {d["clave"] for d in envio.acuse.contenido["detalle"]} == {a.folio, b.folio}
    assert EnvioEvaluacion.objects.filter(ejercicio=a.ejercicio, periodo="2026-06").count() == 1


# ----------------------------------------------------------------------------- validación del CASPEG y pago
def test_hu_4_3_el_caspeg_valida_la_evaluacion_y_la_ministracion_pide_esa_validacion(dos, usuarios, pdf):
    a, b = dos
    with reloj.en(JULIO):
        fuente = solicitudes.FUENTES["evaluacion_reportes"]
    assert fuente is reportes.fuente_evaluacion                               # HU-4.3 reemplaza la fuente de HU-2.4
    ok, detalle, *_ = fuente(a, 1)
    assert not ok and "no entregó" in detalle and "falta enviar" in detalle.replace("todavía falta enviar", "falta enviar")
    _junio_completo(usuarios, a, b, pdf)
    ok, detalle, *_ = fuente(a, 1)
    assert not ok and "falta su validación" in detalle                         # enviada al CASPEG, sin acuerdo
    ac = _validar(usuarios, a.ejercicio, "2026-06", [a, b], "2026-07-07 11:00")
    ok, detalle, referencia, url = fuente(a, 1)
    assert ok and "Junio 2026" in detalle and referencia == ac.numero and url
    # un acuerdo de otro periodo, o que no incluye al Guardabosque, no valida
    ok, detalle, *_ = fuente(b, 1)
    assert not ok and "no cumple" in detalle and "señalado" in detalle and "firmas" in detalle
    assert reportes.validacion(a, EvaluacionPeriodo.objects.get(expediente=a)) == ac
    # la ministración 2 cubre julio y agosto (supuesto) y todavía no hay nada
    ok, detalle, *_ = fuente(a, 2)
    assert not ok and "Julio 2026" in detalle and "Agosto 2026" in detalle
    # el acuerdo del CASPEG es el de HU-2.4, no uno nuevo
    assert ac.tipo == "validacion_reportes" and seguimiento.tipo_acuerdo("validacion_reportes")["unidad"] == "DPF"


def test_hu_4_3_la_validacion_no_cuenta_si_es_anterior_al_envio_o_de_otro_periodo(dos, usuarios, pdf):
    a, b = dos
    _validar(usuarios, a.ejercicio, "2026-06", [a], "2026-07-02 11:00")      # antes de que se envíe la evaluación
    _junio_completo(usuarios, a, b, pdf)
    assert not solicitudes.FUENTES["evaluacion_reportes"](a, 1)[0]
    _validar(usuarios, a.ejercicio, "2026-07", [a], "2026-07-08 11:00")      # de otro periodo
    assert not solicitudes.FUENTES["evaluacion_reportes"](a, 1)[0]
    _validar(usuarios, a.ejercicio, "2026-06", [b], "2026-07-09 11:00")      # incluye a otro expediente
    assert not solicitudes.FUENTES["evaluacion_reportes"](a, 1)[0]
    _validar(usuarios, a.ejercicio, "2026-06", [a], "2026-07-10 11:00")
    assert solicitudes.FUENTES["evaluacion_reportes"](a, 1)[0]


def test_hu_4_3_la_ministracion_se_paga_a_quien_cumplio_y_no_a_quien_no_cumplio_o_no_entrego(dos, usuarios, pdf):
    a, b = dos
    dpf, finanzas = usuarios["dir_dpf"], usuarios["finanzas"]
    for exp in (a, b):
        solicitudes.adjuntar_comprobante(delegado_de(usuarios, exp), exp, pdf("cuenta.pdf"))
    _junio_completo(usuarios, a, b, pdf)
    _validar(usuarios, a.ejercicio, "2026-06", [a, b], "2026-07-07 11:00")
    with reloj.en("2026-07-08 10:00"):
        sol = solicitudes.enviar_solicitud(dpf, a, 1)                          # cumplió: se solicita
        pagos.revisar_solicitud(finanzas, sol, "aceptada")
        sol.refresh_from_db()
        pagos.registrar_pago(finanzas, sol, "DEP-0001", date(2026, 7, 8))
        with pytest.raises(ValidationError, match="no cumple"):                # no cumplió: queda señalado y no se solicita
            solicitudes.enviar_solicitud(dpf, b, 1)
    # julio: a cumple y b no entregó; agosto: a cumple y b no entregó: la ministración 2 es de a
    ra = _reporte(usuarios, a, "2026-07", pdf, "2026-08-04 10:00")
    rb = _reporte(usuarios, b, "2026-07", pdf, "2026-08-04 11:00")
    with reloj.en("2026-08-05 10:00"):
        reportes.revisar(delegado_de(usuarios, a), ra, "revisado")
        reportes.revisar(delegado_de(usuarios, b), rb, "revisado")
    with reloj.en("2026-08-06 10:00"):
        for exp in (a, b):
            reportes.evaluar_periodo(dpf, exp, "2026-07", "cumple")
        reportes.enviar_evaluacion(dpf, a.ejercicio, "2026-07")
    ra8 = _reporte(usuarios, a, "2026-08", pdf, "2026-09-02 10:00")            # b no entrega agosto
    with reloj.en("2026-09-03 10:00"):
        reportes.revisar(delegado_de(usuarios, a), ra8, "revisado")
    with reloj.en(SEPTIEMBRE):
        reportes.evaluar_periodo(dpf, a, "2026-08", "cumple")
        envio = reportes.enviar_evaluacion(dpf, a.ejercicio, "2026-08")
    assert (envio.cumplen, envio.no_entregaron) == (1, 1)
    _validar(usuarios, a.ejercicio, "2026-07", [a, b], "2026-09-10 11:00")
    _validar(usuarios, a.ejercicio, "2026-08", [a, b], "2026-09-10 12:00")
    with reloj.en("2026-09-11 10:00"):
        sol2 = solicitudes.enviar_solicitud(dpf, a, 2)
        assert {s["clave"]: s["cumple"] for s in solicitudes.soportes(a, 2)}["evaluacion_reportes"]
        pagos.revisar_solicitud(finanzas, sol2, "aceptada")
        sol2.refresh_from_db()
        pagos.registrar_pago(finanzas, sol2, "DEP-0002", date(2026, 9, 11))
    segunda_b = {s["clave"]: s for s in solicitudes.soportes(b, 2)}["evaluacion_reportes"]
    assert not segunda_b["cumple"] and "Agosto 2026: no entregó su reporte" in segunda_b["detalle"]
    assert sorted(a.solicitudes_pago.filter(estado="pagada").values_list("ministracion", flat=True)) == [1, 2]
    assert [e.nombre_periodo for e in reportes.periodos_senalados(b)] == ["Junio 2026", "Agosto 2026"]


def test_hu_4_3_que_periodos_cubre_cada_ministracion_es_un_supuesto_configurable(dos, monkeypatch):
    a, _ = dos
    cubre = {n: [p["clave"] for p in reportes.periodos_de_ministracion(a, n)] for n in (1, 2, 3, 4)}
    assert cubre == {1: ["2026-06"], 2: ["2026-07", "2026-08"], 3: ["2026-09", "2026-10"], 4: ["2026-11", "2026-12"]}
    assert reportes.periodos_de_ministracion(a, 5) == [] and reportes.ministracion_de_periodo(a, "2026-09") == 3
    cfg = reportes.config(a)
    assert "supuesto" in cfg["supuesto_correspondencia"].lower() and "R-18" in cfg["supuesto_correspondencia"]
    monkeypatch.setitem(cfg["meses_por_ministracion"], "1", 2)                # configurable en datos/ejecucion.json
    monkeypatch.setitem(cfg["meses_por_ministracion"], "2", 1)
    assert [p["clave"] for p in reportes.periodos_de_ministracion(a, 1)] == ["2026-06", "2026-07"]
    assert [p["clave"] for p in reportes.periodos_de_ministracion(a, 2)] == ["2026-08"]


def test_hu_4_3_solo_los_guardabosques_tienen_evaluacion_de_reportes(contratadas, usuarios):
    with reloj.en(FIRMA):
        _, (cc,) = contratadas("CC")
    assert reportes.config(cc) is None and reportes.periodos(cc) == [] and reportes.historial(cc) == []
    with pytest.raises(ValidationError, match="no evalúa"):
        reportes.evaluar_periodo(usuarios["dir_drff"], cc, "2026-06", "cumple")


# ----------------------------------------------------------------------------- pantallas
def test_hu_4_3_pantallas_de_la_delegacion_la_direccion_y_el_caspeg(dos, usuarios, pdf, client, contrasena):
    a, b = dos
    deleg_a, dpf, comite = delegado_de(usuarios, a), usuarios["dir_dpf"], usuarios["comite"]
    ra = _reporte(usuarios, a, "2026-06", pdf, "2026-07-02 10:00")
    url = reverse("ejecucion:reportes")
    # Delegación: su bandeja trae el reporte por revisar y su tabla por periodo
    client.login(username=deleg_a.username, password=contrasena)
    html = client.get(reverse("nucleo:bandeja")).content.decode()
    assert 'data-prueba="panel-reportes-por-revisar"' in html and a.folio in html
    html = client.get(url + "?periodo=2026-06").content.decode()
    assert 'data-prueba="por-revisar"' in html and 'data-prueba="supuestos"' in html and "supuesto" in html.lower()
    assert "Registrar la revisión" in html and b.folio not in html.split('data-prueba="tabla-periodo"')[1]
    r = client.post(reverse("ejecucion:revisar_reporte", args=[ra.pk]), {"resultado": "revisado"}, follow=True)
    assert "revisado" in r.content.decode().lower() and RevisionReporte.objects.filter(comprobacion=ra).count() == 1
    client.post(reverse("ejecucion:revisar_reporte", args=[ra.pk]), {"resultado": "revisado"}, follow=True)
    assert RevisionReporte.objects.filter(comprobacion=ra).count() == 1               # ya se revisó: no se duplica
    assert 'data-estado="por_evaluar"' in client.get(url + "?periodo=2026-06").content.decode()
    # Dirección: tabla por periodo y evaluación desde la pantalla
    client.logout()
    client.login(username=dpf.username, password=contrasena)
    html = client.get(url + "?periodo=2026-06").content.decode()
    assert f'data-folio="{a.folio}" data-estado="por_evaluar"' in html and f'data-folio="{b.folio}" data-estado="no_entrego"' in html
    assert 'data-prueba="matriz-periodos"' in html and "Enviar la evaluación de Junio 2026 al CASPEG" in html
    with reloj.en(JULIO):
        client.post(reverse("ejecucion:evaluar_reporte", args=[a.folio, "2026-06"]), {"resultado": "cumple", "motivo": ""})
        html = client.post(reverse("ejecucion:enviar_evaluacion", args=[a.ejercicio.pk, "2026-06"]), follow=True).content.decode()
    assert "enviada al CASPEG" in html and EnvioEvaluacion.objects.count() == 1
    html = client.get(reverse("nucleo:bandeja")).content.decode()
    pestana = client.get(reverse("recepcion:expediente", args=[b.folio]) + "?pestana=ejecucion").content.decode()
    assert 'data-prueba="senalado-reportes"' in pestana and "No entregó" in pestana and 'data-prueba="historial-reportes"' in pestana
    # CASPEG: ve lo enviado y lo que falta validar; la Jurídica no entra
    client.logout()
    client.login(username=comite.username, password=contrasena)
    assert 'data-prueba="panel-evaluaciones-por-validar"' in client.get(reverse("nucleo:bandeja")).content.decode()
    html = client.get(url).content.decode()
    assert 'data-prueba="enviados-al-caspeg"' in html and a.folio in html and "Por validar" in html
    client.logout()
    client.login(username=usuarios["juridica"].username, password=contrasena)
    assert client.get(url).status_code == 403


def test_hu_4_3_el_guardabosque_ve_en_su_portal_la_revision_de_la_delegacion(dos, usuarios, cuenta_portal, client, pdf):
    a, _ = dos
    with reloj.en(FIRMA):
        persona = cuenta_portal(a)
    with reloj.en("2026-07-02 10:00"):
        c = comprobaciones.registrar_envio(persona, a, "reporte_mensual", pdf("junio.pdf"), periodo="2026-06")
    with reloj.en("2026-07-03 10:00"):
        reportes.revisar(delegado_de(usuarios, a), c, "devuelto", "Falta la firma del núcleo agrario.")
    client.login(username=persona.username, password=CONTRASENA_PORTAL)
    html = client.get(reverse("portal:expediente", args=[a.folio])).content.decode()
    assert 'data-prueba="revision-delegacion"' in html and "Devuelto para corregir" in html and "Falta la firma del núcleo agrario." in html
    with reloj.en("2026-07-04 10:00"):                                         # lo corrige y lo vuelve a enviar por el portal
        r = client.post(reverse("ejecucion_portal:enviar", args=[a.folio]),
                        {"tipo": "reporte_mensual", "periodo": "2026-06", "archivo": pdf("corregido.pdf")}, follow=True)
    assert a.comprobaciones.filter(tipo="reporte_mensual", periodo="2026-06").count() == 2, r.content.decode()[:500]
