"""Núcleo · notificaciones por conducto de la Delegación (S2-02a). Sirven para faltantes (M1) y para lo
que notifiquen M3 a M6 (resultados, cita a firma, omisiones, devoluciones)."""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from nucleo import extensiones, notificaciones
from nucleo.demo import completar_requisitos
from nucleo.models import MedioNotificacion, Notificacion, TipoNotificacion
from recepcion import servicios

pytestmark = pytest.mark.django_db


@pytest.fixture
def con_faltantes(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    completar_requisitos(usuarios["del_amecameca"], exp)
    servicios.enviar_a_direccion(usuarios["del_amecameca"], exp)
    plano = exp.revisiones.get(requisito__clave="CC-REQ-13")
    val = servicios.validar_expediente(usuarios["dir_drff"], exp, [plano.pk])
    exp.refresh_from_db()
    return exp, val


def test_nucleo_notificacion_del_aviso_de_faltantes_vive_en_el_nucleo(con_faltantes, usuarios):
    exp, val = con_faltantes
    notif = val.notificacion
    assert notif.tipo == TipoNotificacion.FALTANTES and notif.expediente == exp
    assert notif.delegacion == exp.delegacion and notif.enviada_por == usuarios["dir_drff"]
    assert notif.unidad_origen == usuarios["dir_drff"].unidad
    assert notif.acuse_envio == val.acuse and notif.enviada_en == val.fecha_hora
    assert not notif.notificada and val.notificado_en is None
    assert exp.eventos.filter(tipo="notificacion_enviada", acuse=val.acuse).exists()
    assert notif in notificaciones.pendientes_de_notificar(exp.delegacion)


def test_nucleo_registrar_notificacion_con_medio_acuse_y_bitacora(con_faltantes, usuarios):
    exp, val = con_faltantes
    acuse = servicios.registrar_notificacion(usuarios["del_amecameca"], val, medio=MedioNotificacion.TELEFONO)
    notif = Notificacion.objects.get(pk=val.notificacion_id)
    assert notif.notificada_en and notif.notificada_por == usuarios["del_amecameca"]
    assert notif.medio == "telefono" and notif.acuse_notificacion == acuse
    assert acuse.tipo == "notificacion_faltantes" and dict(acuse.contenido["renglones"])["Medio"] == "Teléfono"
    assert exp.eventos.filter(tipo="notificacion", acuse=acuse).exists()
    assert notificaciones.ultima_notificada(exp, "faltantes") == notif
    assert notif not in notificaciones.pendientes_de_notificar(exp.delegacion)
    with pytest.raises(ValidationError):
        servicios.registrar_notificacion(usuarios["del_amecameca"], val)


def test_nucleo_solo_la_delegacion_de_la_notificacion_la_registra(con_faltantes, usuarios):
    _, val = con_faltantes
    for nombre in ("dir_drff", "del_toluca", "comite"):
        with pytest.raises(PermissionDenied):
            notificaciones.registrar_notificacion(usuarios[nombre], val.notificacion)


def test_nucleo_fecha_de_notificacion_no_futura_ni_anterior_al_envio(con_faltantes, usuarios):
    _, val = con_faltantes
    deleg = usuarios["del_amecameca"]
    with pytest.raises(ValidationError):
        notificaciones.registrar_notificacion(deleg, val.notificacion, fecha_hora=timezone.now() + timedelta(days=1))
    with pytest.raises(ValidationError):
        notificaciones.registrar_notificacion(deleg, val.notificacion,
                                              fecha_hora=val.notificacion.enviada_en - timedelta(minutes=1))
    with pytest.raises(ValidationError):
        notificaciones.registrar_notificacion(deleg, val.notificacion, medio="paloma")


def test_nucleo_notificacion_general_para_otros_modulos(con_faltantes, usuarios):
    """Una notificación de otro tipo (cita a firma) emite su propio acuse de envío y avisa a los módulos."""
    exp, _ = con_faltantes
    vistas = []
    extensiones.AL_NOTIFICAR.append(vistas.append)
    try:
        notif = notificaciones.emitir_notificacion(exp, TipoNotificacion.CITA_FIRMA, "Cita a firma del contrato",
                                                   usuarios["dir_drff"], renglones=[("Fecha de la cita", "20/04/2026")])
        assert notif.acuse_envio.tipo == "envio_notificacion_cita_firma"
        assert "por conducto de" in notif.acuse_envio.destinatario
        notificaciones.registrar_notificacion(usuarios["del_amecameca"], notif)
    finally:
        extensiones.AL_NOTIFICAR.remove(vistas.append)
    assert vistas == [notif]
    with pytest.raises(ValidationError):
        notificaciones.emitir_notificacion(exp, "inexistente", "x", usuarios["dir_drff"])
    with pytest.raises(PermissionDenied):
        notificaciones.emitir_notificacion(exp, "otro", "x", usuarios["del_toluca"])
