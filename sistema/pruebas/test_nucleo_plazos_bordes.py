"""Núcleo · bordes de cada plazo que el sistema calcula (G-03): el último momento válido y el primero inválido, con el reloj
simulado, y que un fin de semana o un día inhábil en medio muevan el vencimiento. Inhábiles de 2026 usados aquí: 2-feb,
2-mar, 16-mar, 2 y 3-abr, 1-may, 16-sep, 2 y 16-nov (datos/dias_inhabiles_2026.json)."""
from datetime import date, datetime, time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from contrato import firma, planta
from dictamen import sesiones, tecnico
from dictamen.demo import _validada
from dictamen.models import TipoSesion
from nucleo import plazos, reloj
from nucleo.demo import archivo_demo
from pagos import pagos, solicitudes

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m2 import documento_sesion
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m5 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db
D = date.fromisoformat


def cuando_(texto):
    return timezone.make_aware(datetime.fromisoformat(texto))


def borde(v, esperado):
    """El vencimiento es ``esperado``: ese día todavía vale y al siguiente ya venció."""
    assert v.vencimiento == D(esperado), f"{v.uso}: {v.vencimiento} y no {esperado}"
    assert v.estado(v.vencimiento) != "vencido"
    assert v.estado(v.vencimiento + timedelta(days=1)) == "vencido"
    return v


# ----------------------------------------------------------------------------- faltantes en ventanilla (5 días hábiles, con tope)
@pytest.mark.parametrize("recepcion, vence, topado, despues", [
    ("2026-03-09 10:00", "2026-03-17", False, False),   # lunes: el sábado, el domingo y el lunes 16 (inhábil) en medio
    ("2026-02-27 17:00", "2026-03-09", False, False),   # viernes, y el 2-mar es inhábil
    ("2026-03-24 12:00", "2026-03-27", True, False),    # 5 días hábiles pasarían del 27-mar: se topa a la fecha límite
    ("2026-03-27 23:30", "2026-03-27", True, False),    # el último día de la recepción: vence ese mismo día
    ("2026-03-30 09:00", "2026-04-08", False, True),    # recibida después del tope: no se topa; hay Jueves y Viernes Santo
])
def test_nucleo_borde_faltantes_en_ventanilla(nueva_solicitud, recepcion, vence, topado, despues):
    with reloj.en(recepcion):
        exp = nueva_solicitud()
    v = plazos.vencimiento(exp, "faltantes_ventanilla")
    assert v.tope == D("2026-03-27") and v.topado is topado and v.evento_despues_del_tope is despues
    borde(v, vence)


def test_nucleo_borde_faltantes_avisados_por_la_direccion(nueva_solicitud):
    exp = nueva_solicitud()
    borde(plazos.vencimiento(exp, "faltantes_direccion", fecha_evento=cuando_("2026-04-01 11:00")), "2026-04-10")  # Jueves y Viernes Santo
    borde(plazos.vencimiento(exp, "faltantes_direccion", fecha_evento=cuando_("2026-05-08 16:00")), "2026-05-15")  # viernes: fin de semana
    borde(plazos.vencimiento(exp, "faltantes_direccion", fecha_evento=cuando_("2026-04-24 16:00")), "2026-05-04")  # el 1-may es inhábil


# ----------------------------------------------------------------------------- firma del contrato: las dos fechas
def test_nucleo_borde_firma_cc_programada_desde_la_publicacion_y_liberacion_desde_la_notificacion(nueva_solicitud):
    exp = nueva_solicitud()                                       # CC
    programada = plazos.vencimiento(exp, "firma_programada", fecha_evento=cuando_("2026-06-01 10:00"))
    liberacion = plazos.vencimiento(exp, "firma_liberacion", fecha_evento=cuando_("2026-06-03 10:00"))
    assert (programada.evento, liberacion.evento) == ("publicacion_resultados", "notificacion_persona")
    borde(programada, "2026-06-15")
    borde(liberacion, "2026-06-17")                                # la de liberación es posterior


def test_nucleo_borde_firma_ps_van_al_reves_programada_desde_la_notificacion_y_liberacion_desde_la_publicacion(aprobadas):
    _, (exp,) = aprobadas("PS", cuantas=1)
    programada = plazos.vencimiento(exp, "firma_programada", fecha_evento=cuando_("2026-06-03 10:00"))
    liberacion = plazos.vencimiento(exp, "firma_liberacion", fecha_evento=cuando_("2026-06-01 10:00"))
    assert (programada.evento, liberacion.evento) == ("notificacion_persona", "publicacion_resultados")
    borde(programada, "2026-06-17")
    borde(liberacion, "2026-06-15")                                # la de liberación puede caer antes (R-13)


def test_nucleo_borde_firma_ps_el_servicio_recibe_el_ultimo_dia_y_rechaza_el_siguiente(en_delegacion, usuarios):
    with reloj.en("2026-06-01 10:00", tic=1):
        _, (ultimo, siguiente) = en_delegacion("PS", cuantas=2)   # publicadas y notificadas el 1-jun: liberación el 15-jun
    for exp, momento, ok in ((ultimo, "2026-06-15 23:30", True), (siguiente, "2026-06-16 00:10", False)):
        with reloj.en(momento):
            verificados = [p["clave"] for p in firma.puntos_de_verificacion(exp)]
            argumentos = (delegado_de(usuarios, exp), exp, None, "persona", exp.solicitante.nombre, archivo_demo("f.pdf"),
                          verificados)
            if ok:
                f = firma.registrar_firma(*argumentos)
                assert f.dentro_de_plazo and f.fecha_liberacion == D("2026-06-15")
            else:
                with pytest.raises(ValidationError, match="vencimiento para liberar el recurso fue el 15/06/2026"):
                    firma.registrar_firma(*argumentos)


def test_nucleo_borde_firma_revisar_plazos_senala_solo_despues_del_vencimiento(notificadas):
    with reloj.en("2026-06-01 10:00"):
        notificadas("PS", cuantas=1)
    assert firma.revisar_firmas(D("2026-06-15")) == 0              # el último día todavía vale
    assert firma.revisar_firmas(D("2026-06-16")) == 1


# ----------------------------------------------------------------------------- cita a firma (PS), vales y pagos
def test_nucleo_borde_cita_a_firma_de_ps(aprobadas):
    _, (exp,) = aprobadas("PS", cuantas=1)
    borde(plazos.vencimiento(exp, "cita_firma", fecha_evento=cuando_("2026-06-01 10:00")), "2026-06-08")
    borde(plazos.vencimiento(exp, "cita_firma", fecha_evento=cuando_("2026-06-05 18:00")), "2026-06-12")  # viernes
    borde(plazos.vencimiento(exp, "cita_firma", fecha_evento=cuando_("2026-09-11 10:00")), "2026-09-21")  # el 16-sep es inhábil


def test_nucleo_borde_vale_de_ps_30_dias_naturales(aprobadas):
    _, (exp,) = aprobadas("PS", cuantas=1)
    borde(plazos.vencimiento(exp, "recoger_planta", fecha_evento=cuando_("2026-09-01 10:00")), "2026-10-01")
    borde(plazos.vencimiento(exp, "recoger_planta", fecha_evento=cuando_("2026-09-10 10:00")), "2026-10-12")  # el 10-oct es sábado


def test_nucleo_borde_vale_de_ps_el_servicio_entrega_planta_el_ultimo_dia_y_no_el_siguiente(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    with reloj.en("2026-08-20 10:00", tic=1):
        _, (exp,) = contratadas("PS")
    with reloj.en("2026-09-01 10:00"):
        vale = planta.emitir_vale(delegado_de(usuarios, exp), exp, vivero, [(esp["Pino patula"], 4400)])
    assert vale.vence_el == D("2026-10-01")
    with reloj.en("2026-10-01 23:00"):
        planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 100)
    with reloj.en("2026-10-02 00:05"):
        with pytest.raises(ValidationError, match="venció el 01/10/2026"):
            planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 100)


def test_nucleo_borde_vale_de_rhf_15_dias_habiles(aprobadas):
    _, (exp,) = aprobadas("RHF", cuantas=1)
    borde(plazos.vencimiento(exp, "recoger_planta", fecha_evento=cuando_("2026-09-07 10:00")), "2026-09-29")  # el 16-sep es inhábil
    borde(plazos.vencimiento(exp, "recoger_planta", fecha_evento=cuando_("2026-10-02 10:00")), "2026-10-23")  # viernes: fines de semana


def test_nucleo_borde_instruccion_de_pago_a_la_fiduciaria_5_dias_habiles(aprobadas):
    _, (exp,) = aprobadas("PSA", cuantas=1)
    borde(plazos.vencimiento(exp, "instruccion_pago_fiduciaria", fecha_evento=cuando_("2026-08-28 10:00")), "2026-09-04")
    borde(plazos.vencimiento(exp, "instruccion_pago_fiduciaria", fecha_evento=cuando_("2026-09-14 10:00")), "2026-09-22")  # 16-sep


@pytest.mark.parametrize("dia, hora, en_plazo", [("2026-09-04", "23:30", True), ("2026-09-05", "00:10", False)])
def test_nucleo_borde_remision_a_la_fiduciaria_el_servicio_marca_en_plazo_y_fuera_de_plazo(aceptada, usuarios, dia, hora, en_plazo):
    with reloj.en("2026-08-28 10:00", tic=1):
        exp, sol = aceptada("PSA")                                # enviada a Administración y Finanzas el viernes 28-ago
    assert solicitudes.plazo_remision(sol).vencimiento == D("2026-09-04")
    with reloj.en(f"{dia} {hora}"):
        r = pagos.remitir_a_fiduciaria(usuarios["comite"], sol)
    assert r.en_plazo is en_plazo and r.vence_el == D("2026-09-04")


@pytest.mark.parametrize("entrega, vence", [
    ("2026-11-30 10:00", "2027-03-01"),    # fin de mes: 30-nov + 3 meses = 28-feb (no hay 30-feb), domingo → lunes 1-mar
    ("2026-08-31 10:00", "2026-11-30"),    # 31-ago + 3 meses = 30-nov
    ("2026-05-29 10:00", "2026-08-31"),
    ("2026-11-20 10:00", "2027-02-22"),    # 20-feb-2027 es sábado
    ("2026-08-02 10:00", "2026-11-03"),    # 2-ago + 3 meses = 2-nov, inhábil (Día de Muertos): pasa al 3-nov
])
def test_nucleo_borde_cobro_del_cheque_3_meses_desde_la_entrega(aprobadas, entrega, vence):
    _, (exp,) = aprobadas("PSA", cuantas=1)
    borde(plazos.vencimiento(exp, "cobro_cheque", fecha_evento=cuando_(entrega)), vence)


def test_nucleo_borde_cobro_del_cheque_por_vencer_a_5_dias_habiles(aprobadas):
    _, (exp,) = aprobadas("PSA", cuantas=1)
    v = plazos.vencimiento(exp, "cobro_cheque", fecha_evento=cuando_("2026-08-24 10:00"))      # vence el 24-nov
    assert v.vencimiento == D("2026-11-24")
    assert v.estado(D("2026-11-16")) == "en plazo" and v.estado(D("2026-11-17")) == "por vencer"   # 16-nov inhábil
    assert v.estado(D("2026-11-24")) == "por vencer" and v.estado(D("2026-11-25")) == "vencido"


# ----------------------------------------------------------------------------- Comité y dictaminación
@pytest.mark.parametrize("sesion, ultimo", [
    ("2026-07-15 11:00", "2026-07-10"),    # miércoles: 14, 13 y 10 son los tres días hábiles anteriores (fin de semana en medio)
    ("2026-11-17 11:00", "2026-11-11"),    # martes: el lunes 16 es inhábil y hay fin de semana
])
def test_nucleo_borde_convocatoria_del_comite_3_dias_habiles_de_anticipacion(cc, usuarios, sesion, ultimo):
    comite = usuarios["comite"]

    def nueva():
        s = sesiones.crear_sesion(comite, cc, TipoSesion.APROBACION, cuando_(sesion), "Sala", "Quórum\nListado")
        sesiones.agregar_documento(comite, s, documento_sesion(), "Listado")
        return s

    ses = nueva()
    _, limite = sesiones.anticipacion_requerida(ses)
    assert timezone.localtime(limite).date() == D(ultimo) and timezone.localtime(limite).time() == time(23, 59, 59)
    with reloj.en(f"{ultimo} 23:59:00"):
        sesiones.enviar_convocatoria(comite, ses)                    # el último momento válido
    otra = nueva()
    with reloj.en(f"{D(ultimo) + timedelta(days=1)} 00:01:00"):      # el primero inválido
        with pytest.raises(ValidationError, match="La convocatoria debe enviarse con"):
            sesiones.enviar_convocatoria(comite, otra)


def test_nucleo_borde_dictaminacion_en_cc_hasta_el_30_de_junio(cc, usuarios):
    with reloj.en("2026-03-03 10:00", tic=1):
        a = _validada(usuarios["del_amecameca"], usuarios["dir_drff"], cc, "Amecameca", "Predio Borde Uno", "Persona Uno",
                      "reforestacion", 5)
        b = _validada(usuarios["del_amecameca"], usuarios["dir_drff"], cc, "Ozumba", "Predio Borde Dos", "Persona Dos",
                      "reforestacion", 5, desplazamiento=(2000, 2000))
    assert tecnico.situacion_plazo(a, D("2026-06-30"))["situacion"] == "por_vencer"      # el último día todavía vale
    assert tecnico.situacion_plazo(a, D("2026-07-01"))["situacion"] == "vencido"
    with reloj.en("2026-06-30 23:00"):
        tecnico.dictaminar(usuarios["dir_drff"], a, "factible", "En su último día.")
    with reloj.en("2026-07-01 00:10"):
        tecnico.dictaminar(usuarios["dir_drff"], b, "factible", "Un día tarde.")
    a.refresh_from_db()
    b.refresh_from_db()
    assert tecnico.situacion_plazo(a)["situacion"] == "cumplido"
    assert tecnico.situacion_plazo(b)["situacion"] == "fuera_de_plazo"
