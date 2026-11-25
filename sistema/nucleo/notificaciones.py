"""Notificaciones a la persona por conducto de la Delegación (servicio general del núcleo).

Sirve igual para el aviso de faltantes (M1), los resultados y la cita a firma (M3), las omisiones y
las devoluciones (M5, M6). Cada notificación tiene dos momentos con fecha, hora y acuse:

1. ``emitir_notificacion``: la unidad que decide (Dirección, Secretaría Técnica, Unidad Jurídica…)
   la envía a la Delegación. El acuse del envío puede ser el del propio documento (por ejemplo, el
   aviso de faltantes) o uno que se emite aquí.
2. ``registrar_notificacion``: la Delegación registra que notificó a la persona, con el medio; se
   emite el acuse de la notificación. Los plazos que corren «desde la notificación» usan esa fecha.

Ambos escriben la bitácora del expediente. ``extensiones.AL_NOTIFICAR`` recibe la notificación ya
registrada, para que un módulo reaccione sin que el núcleo lo conozca.
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from . import extensiones
from .acuses import emitir_acuse
from .models import (
    Evento, MedioNotificacion, Notificacion, TipoNotificacion, TipoUnidad, puede_ver_expediente,
)


def _fmt(valor):
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M:%S h")


def emitir_notificacion(expediente, tipo, asunto, usuario, acuse_envio=None, renglones=(), detalle=None,
                        delegacion=None, destinatario=None, observaciones="", datos=None, fecha_hora=None,
                        titulo_acuse=None):
    """Crea la notificación (momento del envío a la Delegación) y escribe la bitácora.

    Si no se pasa ``acuse_envio`` se emite uno («Envío de notificación a la Delegación»).
    """
    if tipo not in TipoNotificacion.values:
        raise ValidationError(f"Tipo de notificación no reconocido: {tipo}.")
    if not puede_ver_expediente(usuario, expediente):
        raise PermissionDenied("El expediente no pertenece a su unidad.")
    delegacion = delegacion or expediente.delegacion
    destinatario = destinatario or expediente.solicitante
    ahora = fecha_hora or timezone.now()
    with transaction.atomic():
        if acuse_envio is None:
            acuse_envio = emitir_acuse(
                expediente, f"envio_notificacion_{tipo}", titulo_acuse or f"Envío a la Delegación: {asunto}", usuario,
                [("Asunto", asunto), ("Envía", getattr(usuario.unidad, "nombre", "—")),
                 ("Notifica", delegacion.nombre), ("Fecha y hora del envío", _fmt(ahora)), *renglones],
                destinatario=f"{destinatario.nombre}, por conducto de {delegacion.nombre}", detalle=detalle,
            )
        notif = Notificacion.objects.create(
            expediente=expediente, tipo=tipo, asunto=asunto[:250], destinatario=destinatario, enviada_por=usuario,
            unidad_origen=getattr(usuario, "unidad", None), delegacion=delegacion, enviada_en=ahora,
            acuse_envio=acuse_envio, observaciones=observaciones, datos=datos or {},
        )
        Evento.registrar(expediente, usuario, "notificacion_enviada",
                         f"{asunto}: enviada a {delegacion.nombre} para notificar a la persona.",
                         acuse=acuse_envio, datos={"notificacion": notif.pk, "tipo": tipo})
    return notif


def puede_notificar(usuario, notificacion):
    return (usuario.tipo_unidad == TipoUnidad.DELEGACION and usuario.unidad_id == notificacion.delegacion_id
            and notificacion.notificada_en is None)


def registrar_notificacion(usuario, notificacion, medio=MedioNotificacion.PERSONAL, fecha_hora=None,
                           titulo_acuse=None, renglones=(), detalle=None, descripcion=None, observaciones="",
                           encabezado_detalle=None):
    """La Delegación registra que notificó a la persona; emite el acuse de la notificación.

    ``fecha_hora`` permite registrar una notificación hecha antes (no futura ni anterior al envío).
    """
    exp = notificacion.expediente
    if usuario.tipo_unidad != TipoUnidad.DELEGACION:
        raise PermissionDenied(f"Esta acción le corresponde a: {TipoUnidad.DELEGACION.label}.")
    if usuario.unidad_id != notificacion.delegacion_id or not puede_ver_expediente(usuario, exp):
        raise PermissionDenied("La notificación corresponde a otra Delegación.")
    if notificacion.notificada_en:
        raise ValidationError("La notificación ya se registró.")
    if medio not in MedioNotificacion.values:
        raise ValidationError("Medio de notificación no reconocido.")
    ahora = timezone.now()
    cuando = fecha_hora or ahora
    if cuando > ahora:
        raise ValidationError("La fecha de la notificación no puede ser futura.")
    if cuando < notificacion.enviada_en:
        raise ValidationError("La notificación no puede ser anterior a su envío a la Delegación.")
    with transaction.atomic():
        acuse = emitir_acuse(
            exp, f"notificacion_{notificacion.tipo}", titulo_acuse or f"Acuse de notificación: {notificacion.asunto}",
            usuario,
            [("Aviso", notificacion.acuse_envio.folio if notificacion.acuse_envio else "—"),
             ("Fecha y hora de la notificación", _fmt(cuando)),
             ("Medio", MedioNotificacion(medio).label), *renglones],
            destinatario=notificacion.destinatario.nombre if notificacion.destinatario else exp.solicitante.nombre,
            detalle=detalle, encabezado_detalle=encabezado_detalle,
        )
        notificacion.notificada_en = cuando
        notificacion.notificada_por = usuario
        notificacion.medio = medio
        notificacion.acuse_notificacion = acuse
        if observaciones:
            notificacion.observaciones = (notificacion.observaciones + "\n" + observaciones).strip()
        notificacion.save(update_fields=["notificada_en", "notificada_por", "medio", "acuse_notificacion",
                                         "observaciones"])
        Evento.registrar(exp, usuario, "notificacion",
                         descripcion or f"{notificacion.asunto}: notificada a la persona.", acuse=acuse,
                         datos={"notificacion": notificacion.pk, "tipo": notificacion.tipo, "medio": medio})
        for reaccion in extensiones.AL_NOTIFICAR:
            reaccion(notificacion)
    return acuse


def pendientes_de_notificar(delegacion, tipo=None):
    """Notificaciones que la Delegación aún no registra como hechas."""
    qs = Notificacion.objects.filter(delegacion=delegacion, notificada_en__isnull=True).select_related("expediente")
    if tipo:
        qs = qs.filter(tipo=tipo)
    return qs


def ultima_notificada(expediente, tipo):
    """La notificación más reciente de ese tipo que ya se hizo a la persona (o None)."""
    return expediente.notificaciones.filter(tipo=tipo, notificada_en__isnull=False).order_by("-notificada_en").first()
