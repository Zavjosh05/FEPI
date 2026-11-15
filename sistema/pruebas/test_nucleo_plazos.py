"""Núcleo · plazos con evento de arranque por programa (S2-02b; R-03 y R-12)."""
from datetime import date, datetime, timedelta

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from nucleo import dias_habiles, extensiones, notificaciones, plazos
from nucleo.demo import completar_requisitos
from nucleo.models import Ejercicio, Estado, Evento, Expediente
from recepcion import servicios

pytestmark = pytest.mark.django_db


def _local(anio, mes, dia, hora=10):
    return timezone.make_aware(datetime(anio, mes, dia, hora, 0))


@pytest.fixture
def exp_de(nueva_solicitud):
    """Expediente de CC pasado a otro programa (solo para probar plazos; el tipo de persona no importa)."""
    def _crear(programa="CC", **kw):
        exp = nueva_solicitud(**kw)
        if programa != "CC":
            Expediente.objects.filter(pk=exp.pk).update(ejercicio=Ejercicio.objects.get(programa__clave=programa, anio=2026))
        return Expediente.objects.get(pk=exp.pk)
    return _crear


def _notificar_resultados(exp, usuarios, cuando=None):
    n = notificaciones.emitir_notificacion(exp, "resultados", "Resultados", usuarios["dir_drff"], fecha_hora=cuando)
    notificaciones.registrar_notificacion(usuarios["del_amecameca"], n, fecha_hora=cuando)
    n.refresh_from_db()
    return n


def test_nucleo_eventos_de_la_firma_por_programa():
    """R-03: dos fechas de firma; el evento de cada una sale de datos/sistema.json por programa."""
    esperado = {
        "CC": ("publicacion_resultados", "notificacion_persona"),
        "PS": ("notificacion_persona", "publicacion_resultados"),
        "RHF": ("notificacion_persona", "notificacion_persona"),
        "PSA": ("publicacion_resultados", "publicacion_resultados"),
    }
    for prog, (programada, liberacion) in esperado.items():
        assert plazos.config_uso(prog, "firma_programada")["evento"] == programada
        assert plazos.config_uso(prog, "firma_liberacion")["evento"] == liberacion
        assert plazos.config_uso(prog, "firma_programada")["plazo"] == "firma_contrato"
    assert plazos.config_uso("CC", "cobro_cheque") is None  # es de PSAHEM
    assert "cobro_cheque" in plazos.usos_configurados("PSA") and "cobro_cheque" not in plazos.usos_configurados("CC")
    with pytest.raises(ImproperlyConfigured):
        plazos.config_uso("CC", "uso_que_no_existe")


def test_nucleo_faltantes_en_ventanilla_desde_la_recepcion_con_tope(exp_de):
    """R-12: 5 días hábiles desde la recepción, sin pasar de la fecha límite de recepción (27-mar-2026)."""
    exp = exp_de()
    Expediente.objects.filter(pk=exp.pk).update(fecha_recepcion=_local(2026, 3, 2))
    exp.refresh_from_db()
    v = plazos.vencimiento(exp, "faltantes_ventanilla")
    assert v.evento == "recepcion_solicitud" and v.vencimiento == dias_habiles.sumar_dias_habiles(date(2026, 3, 2), 5)
    assert not v.topado and v.tope == date(2026, 3, 27)
    Expediente.objects.filter(pk=exp.pk).update(fecha_recepcion=_local(2026, 3, 24))
    exp.refresh_from_db()
    v = plazos.vencimiento(exp, "faltantes_ventanilla")
    assert dias_habiles.sumar_dias_habiles(date(2026, 3, 24), 5) > date(2026, 3, 27)
    assert v.topado and v.vencimiento == date(2026, 3, 27) and "sin pasar del 27/03/2026" in v.texto
    assert servicios.plazo_recepcion(exp) == date(2026, 3, 27)


def test_nucleo_recepcion_despues_de_la_fecha_limite_se_senala(exp_de):
    exp = exp_de()  # recibida hoy, fuera del calendario de la Convocatoria 2026
    v = plazos.vencimiento(exp, "faltantes_ventanilla")
    if timezone.localdate() > date(2026, 3, 27):
        assert v.evento_despues_del_tope and not v.topado
    assert v.vencimiento == dias_habiles.sumar_dias_habiles(exp.fecha_recepcion, 5)
    assert "a partir de la recepción" in exp.acuses.get(tipo="recepcion").contenido["nota"]


def test_nucleo_faltantes_de_la_direccion_desde_el_aviso(exp_de, usuarios):
    exp = exp_de()
    completar_requisitos(usuarios["del_amecameca"], exp)
    servicios.enviar_a_direccion(usuarios["del_amecameca"], exp)
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    val = servicios.validar_expediente(usuarios["dir_drff"], exp, [plano.pk])
    v = plazos.vencimiento(exp, "faltantes_direccion")
    assert v.evento == "aviso_direccion" and v.decision_propia
    assert v.fecha_evento == val.notificacion.enviada_en and v.vencimiento == val.fecha_limite


def test_nucleo_firma_sin_fecha_hasta_que_ocurre_el_evento_cc(exp_de, usuarios):
    exp = exp_de()
    prog, lib = plazos.vencimiento(exp, "firma_programada"), plazos.vencimiento(exp, "firma_liberacion")
    assert not prog.tiene_fecha and not lib.tiene_fecha
    assert prog.estado() == plazos.SIN_FECHA and plazos.SIN_FECHA in prog.texto
    # M3 registra la publicación como hito; el servicio no cambia.
    publicacion = _local(2026, 8, 3)
    plazos.registrar_hito(exp, "publicacion_resultados", usuarios["comite"], fecha_hora=publicacion)
    prog, lib = plazos.vencimiento(exp, "firma_programada"), plazos.vencimiento(exp, "firma_liberacion")
    assert prog.vencimiento == dias_habiles.sumar_dias_habiles(publicacion, 10) and not lib.tiene_fecha
    # La liberación del recurso corre desde la notificación con acuse.
    notif = _notificar_resultados(exp, usuarios)
    lib = plazos.vencimiento(exp, "firma_liberacion")
    assert lib.fecha_evento == notif.notificada_en
    assert lib.vencimiento == dias_habiles.sumar_dias_habiles(notif.notificada_en, 10)
    assert set(plazos.vencimientos(exp)) >= {"faltantes_ventanilla", "firma_programada", "firma_liberacion"}


def test_nucleo_firma_en_ps_al_reves_que_en_cc(exp_de, usuarios):
    exp = exp_de("PS")
    publicacion = timezone.now() - timedelta(days=20)
    plazos.registrar_hito(exp, "publicacion_resultados", fecha_hora=publicacion)
    assert plazos.vencimiento(exp, "firma_liberacion").vencimiento == dias_habiles.sumar_dias_habiles(publicacion, 10)
    assert not plazos.vencimiento(exp, "firma_programada").tiene_fecha
    assert plazos.vencimiento(exp, "cita_firma").vencimiento == dias_habiles.sumar_dias_habiles(publicacion, 5)
    notif = _notificar_resultados(exp, usuarios)
    assert plazos.vencimiento(exp, "firma_programada").vencimiento == dias_habiles.sumar_dias_habiles(
        notif.notificada_en, 10)


def test_nucleo_reasignadas_cuentan_desde_su_notificacion_y_topan_en_septiembre(exp_de, usuarios):
    exp = exp_de()
    Evento.registrar(exp, usuarios["comite"], "cambio_estado", "Reasignación",
                     estado_origen=Estado.objects.get(clave="lista_espera"), estado_destino=Estado.objects.get(clave="aprobada"))
    Expediente.objects.filter(pk=exp.pk).update(fecha_recepcion=_local(2026, 3, 2))
    exp.refresh_from_db()
    plazos.registrar_hito(exp, "publicacion_resultados", fecha_hora=_local(2026, 8, 3))
    _notificar_resultados(exp, usuarios, cuando=_local(2026, 9, 25))
    prog = plazos.vencimiento(exp, "firma_programada")
    assert prog.evento == "notificacion_persona"  # no la publicación
    assert prog.topado and prog.vencimiento == date(2026, 9, 30)
    assert plazos.vencimiento(exp, "firma_liberacion").vencimiento == date(2026, 9, 30)


def test_nucleo_dias_sin_precisar_y_eventos_de_otros_modulos(exp_de):
    exp = exp_de("PS")
    entrega = _local(2026, 5, 4)
    plazos.registrar_hito(exp, "entrega_vale", fecha_hora=entrega)
    v = plazos.vencimiento(exp, "recoger_planta")  # «30 días» sin decir si son hábiles: naturales (R-13)
    assert v.vencimiento == dias_habiles.calcular_vencimiento(entrega, 30, "dias_naturales")
    psa = exp_de("PSA")
    cheque = _local(2026, 6, 1)
    extensiones.EVENTOS_PLAZO["entrega_cheque"] = lambda e, c: cheque
    try:
        v = plazos.vencimiento(psa, "cobro_cheque")
    finally:
        del extensiones.EVENTOS_PLAZO["entrega_cheque"]
    assert v.vencimiento == dias_habiles.calcular_vencimiento(cheque, 3, "meses") and v.decision_propia
    assert plazos.vencimiento(exp, "cobro_cheque") is None
