"""HU-5.3 · Entrega de cheques (PSAHEM).

- ``emitir_cheque``: la Fiduciaria emite el cheque de la ministración (70 % o 30 %) de una solicitud remitida: número, importe
  igual al solicitado y fecha de emisión. Uno por persona beneficiaria y ministración.
- ``enviar_a_delegacion``: fecha y hora del envío a la Delegación del expediente, acuse y aviso de pago listo a la persona por
  conducto de la Delegación (ROP PSAHEM 10.1 fr. X: la notificación de los pagos la hacen las Delegaciones).
- ``registrar_entrega``: la Delegación entrega el cheque (fecha y hora, quién recibe, acuse); hito ``entrega_cheque`` del que corren
  los 3 meses para cobrarlo (8.1.7 fr. XVI, líneas 2069 y 2070; R-14). Con la entrega la ministración queda pagada.
- ``registrar_cobro`` y ``revisar_cobros``: el cobro y el aviso (solo aviso: la baja por cheque vencido es del sprint 3) de los
  cheques entregados sin cobro que están por vencer o vencidos.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from dictamen.comun import exigir_acceso, exigir_unidad
from nucleo import plazos
from nucleo.acuses import emitir_acuse
from nucleo.models import Evento, TipoNotificacion, TipoUnidad, expedientes_visibles
from nucleo.notificaciones import emitir_notificacion

from . import pagos
from .models import Cheque, EstadoSolicitud, SolicitudPago
from nucleo.trazabilidad import registra_usuario

USO_COBRO = "cobro_cheque"


def _fmt(v):
    return f"{timezone.localtime(v):%d/%m/%Y %H:%M:%S} h"


def cheques_visibles(usuario):
    return Cheque.objects.filter(expediente__in=expedientes_visibles(usuario)).select_related(
        "expediente__predio__municipio", "expediente__solicitante", "solicitud", "acuse_emision", "acuse_envio",
        "acuse_entrega", "delegacion")


def por_emitir(usuario):
    if usuario.tipo_unidad != TipoUnidad.FIDUCIARIA:
        return []
    return list(SolicitudPago.objects.filter(
        expediente__in=expedientes_visibles(usuario), estado=EstadoSolicitud.REMITIDA, cheque__isnull=True
    ).select_related("expediente__predio__municipio", "expediente__solicitante", "remision").order_by("remision__remitida_en"))


def por_enviar(usuario):
    if usuario.tipo_unidad != TipoUnidad.FIDUCIARIA:
        return []
    return list(cheques_visibles(usuario).filter(enviado_en__isnull=True))


def por_entregar(usuario):
    if usuario.tipo_unidad != TipoUnidad.DELEGACION:
        return []
    return list(cheques_visibles(usuario).filter(enviado_en__isnull=False, entregado_en__isnull=True,
                                                 delegacion=usuario.unidad))


def vencimiento_cobro(cheque):
    """``Vencimiento`` de los 3 meses para cobrar desde la entrega (None si aún no se entrega)."""
    if cheque.entregado_en is None:
        return None
    return plazos.vencimiento(cheque.expediente, USO_COBRO, fecha_evento=cheque.entregado_en)


def por_cobrar(usuario):
    """Cheques entregados sin cobro, con su vencimiento (para avisar de los por vencer o vencidos)."""
    filas = []
    for c in cheques_visibles(usuario).filter(entregado_en__isnull=False, cobrado_en__isnull=True):
        v = vencimiento_cobro(c)
        filas.append({"cheque": c, "vencimiento": v, "estado": v.estado() if v else ""})
    return filas


# ----------------------------------------------------------------------------- emisión
@registra_usuario
def emitir_cheque(usuario, solicitud, numero, importe=None, fecha_emision=None, momento=None):
    exigir_unidad(usuario, TipoUnidad.FIDUCIARIA)
    numero = (numero or "").strip()
    with transaction.atomic():
        solicitud = SolicitudPago.objects.select_related("expediente__solicitante", "expediente__ejercicio__programa").get(
            pk=solicitud.pk)
        exp = solicitud.expediente
        exp.refresh_from_db()
        exigir_acceso(usuario, exp)
        if hasattr(solicitud, "cheque"):
            raise ValidationError("Ya hay un cheque de esta persona beneficiaria para esta ministración: un cheque por "
                                  "persona y ministración.")
        if solicitud.estado != EstadoSolicitud.REMITIDA or not hasattr(solicitud, "remision"):
            raise ValidationError("Solo se emite el cheque de una solicitud que la Secretaría Técnica ya solicitó a la Fiduciaria.")
        if not numero:
            raise ValidationError("Indique el número de cheque.")
        if Cheque.objects.filter(numero=numero).exists():
            raise ValidationError(f"El número de cheque {numero} ya está registrado.")
        importe = solicitud.importe if importe in (None, "") else importe
        if importe != solicitud.importe:
            raise ValidationError(f"El importe del cheque (${importe:,.2f}) debe ser igual al solicitado (${solicitud.importe:,.2f}).")
        hoy = timezone.localdate()
        fecha_emision = fecha_emision or hoy
        if fecha_emision > hoy:
            raise ValidationError("La fecha de emisión no puede ser futura.")
        if fecha_emision < timezone.localtime(solicitud.remision.remitida_en).date():
            raise ValidationError("El cheque no puede emitirse antes de que se solicite el pago a la Fiduciaria.")
        ahora = momento or timezone.now()
        cheque = Cheque(solicitud=solicitud, remision=solicitud.remision, expediente=exp, persona=exp.solicitante,
                        ministracion=solicitud.ministracion, numero=numero, importe=importe, emitido_en=fecha_emision,
                        emitido_por=usuario, registrado_en=ahora, delegacion=exp.delegacion)
        cheque.save()
        cheque.acuse_emision = emitir_acuse(
            exp, "emision_cheque", f"Emisión del cheque {numero}", usuario,
            [("Cheque", numero), ("Persona beneficiaria", exp.solicitante.nombre),
             ("Ministración", f"{solicitud.ministracion} ({solicitud.porcentaje:g} %)"), ("Importe", f"${importe:,.2f}"),
             ("Fecha de emisión", f"{fecha_emision:%d/%m/%Y}"), ("Solicitud", solicitud.folio),
             ("Delegación que lo entrega", exp.delegacion.nombre), ("Registra", usuario.unidad.nombre)],
            destinatario=exp.solicitante.nombre)
        cheque.save(update_fields=["acuse_emision"])
        exp.cambiar_estado("cheque_emitido", usuario, tipo_evento="cheque_emitido", acuse=cheque.acuse_emision,
                           descripcion=f"Cheque {numero} emitido por ${importe:,.2f} (ministración {solicitud.ministracion}).",
                           datos={"cheque": cheque.pk})
    return cheque


# ----------------------------------------------------------------------------- envío
@registra_usuario
def enviar_a_delegacion(usuario, cheque, momento=None):
    exigir_unidad(usuario, TipoUnidad.FIDUCIARIA)
    with transaction.atomic():
        cheque = Cheque.objects.select_related("expediente__solicitante").get(pk=cheque.pk)
        exp = cheque.expediente
        exp.refresh_from_db()
        exigir_acceso(usuario, exp)
        if cheque.enviado:
            raise ValidationError(f"El cheque {cheque.numero} ya se envió a la Delegación.")
        ahora = momento or timezone.now()
        if ahora < cheque.registrado_en:
            raise ValidationError("El envío no puede ser anterior a la emisión del cheque.")
        cheque.enviado_en, cheque.enviado_por = ahora, usuario
        cheque.acuse_envio = emitir_acuse(
            exp, "envio_cheque", f"Envío del cheque {cheque.numero} a la Delegación", usuario,
            [("Cheque", cheque.numero), ("Persona beneficiaria", exp.solicitante.nombre),
             ("Ministración", cheque.ministracion), ("Importe", f"${cheque.importe:,.2f}"),
             ("Delegación", cheque.delegacion.nombre), ("Fecha y hora del envío", _fmt(ahora)),
             ("Envía", usuario.unidad.nombre)], destinatario=cheque.delegacion.nombre)
        cheque.save()
        exp.cambiar_estado("cheque_enviado", usuario, tipo_evento="cheque_enviado", acuse=cheque.acuse_envio,
                           descripcion=f"Cheque {cheque.numero} enviado a {cheque.delegacion.nombre} el "
                                       f"{timezone.localtime(ahora):%d/%m/%Y %H:%M} h.", datos={"cheque": cheque.pk})
        cheque.aviso = emitir_notificacion(
            exp, TipoNotificacion.PAGO, f"Su cheque de la ministración {cheque.ministracion} ya está en la Delegación", usuario,
            acuse_envio=cheque.acuse_envio, delegacion=cheque.delegacion,
            observaciones="Notifique por teléfono, medios electrónicos o visita domiciliaria (ROP PSAHEM 10.1 fr. X). "
                          "Debe cobrarlo en un máximo de 3 meses desde la entrega.", datos={"cheque": cheque.pk})
        cheque.save(update_fields=["aviso"])
    return cheque


# ----------------------------------------------------------------------------- entrega
@registra_usuario
def registrar_entrega(usuario, cheque, recibe_nombre, entregado_en=None, momento=None):
    exigir_unidad(usuario, TipoUnidad.DELEGACION)
    recibe_nombre = (recibe_nombre or "").strip()
    with transaction.atomic():
        cheque = Cheque.objects.select_related("expediente__solicitante", "solicitud", "delegacion").get(pk=cheque.pk)
        exp = cheque.expediente
        exp.refresh_from_db()
        exigir_acceso(usuario, exp)
        if usuario.unidad_id != cheque.delegacion_id:
            raise ValidationError("El cheque corresponde a otra Delegación.")
        if cheque.entregado:
            raise ValidationError(f"El cheque {cheque.numero} ya se entregó.")
        if not cheque.enviado:
            raise ValidationError("El cheque todavía no llega a la Delegación.")
        if not recibe_nombre:
            raise ValidationError("Indique quién recibe el cheque.")
        ahora = momento or timezone.now()
        entregado_en = entregado_en or ahora
        if entregado_en > ahora:
            raise ValidationError("La fecha y la hora de la entrega no pueden ser futuras.")
        if entregado_en < cheque.enviado_en:
            raise ValidationError("La entrega no puede ser anterior al envío del cheque a la Delegación.")
        cheque.entregado_en, cheque.entregado_por, cheque.recibe_nombre = entregado_en, usuario, recibe_nombre
        venc = plazos.vencimiento(exp, USO_COBRO, fecha_evento=entregado_en)
        cheque.vence_cobro = venc.vencimiento if venc else None
        cheque.acuse_entrega = emitir_acuse(
            exp, "entrega_cheque", f"Entrega del cheque {cheque.numero}", usuario,
            [("Cheque", cheque.numero), ("Persona beneficiaria", exp.solicitante.nombre),
             ("Ministración", cheque.ministracion), ("Importe", f"${cheque.importe:,.2f}"),
             ("Recibe", recibe_nombre), ("Fecha y hora de la entrega", _fmt(entregado_en)),
             ("Debe cobrarlo antes del", f"{cheque.vence_cobro:%d/%m/%Y} (3 meses)" if cheque.vence_cobro else "—"),
             ("Entrega", usuario.unidad.nombre)], destinatario=exp.solicitante.nombre)
        cheque.save()
        plazos.registrar_hito(exp, "entrega_cheque", usuario, entregado_en, referencia=cheque.numero,
                              datos={"cheque": cheque.pk, "ministracion": cheque.ministracion})
        cheque.solicitud.estado = EstadoSolicitud.PAGADA
        cheque.solicitud.save(update_fields=["estado"])
        exp.cambiar_estado("cheque_entregado", usuario, tipo_evento="cheque_entregado", acuse=cheque.acuse_entrega,
                           descripcion=f"Cheque {cheque.numero} entregado a {recibe_nombre} el "
                                       f"{timezone.localtime(entregado_en):%d/%m/%Y %H:%M} h.", datos={"cheque": cheque.pk})
    return cheque


# ----------------------------------------------------------------------------- cobro
@registra_usuario
def registrar_cobro(usuario, cheque, fecha_cobro=None):
    exigir_unidad(usuario, TipoUnidad.FIDUCIARIA, TipoUnidad.DELEGACION)
    with transaction.atomic():
        cheque = Cheque.objects.get(pk=cheque.pk)
        exigir_acceso(usuario, cheque.expediente)
        if usuario.tipo_unidad == TipoUnidad.DELEGACION and usuario.unidad_id != cheque.delegacion_id:
            raise ValidationError("El cheque corresponde a otra Delegación.")
        if not cheque.entregado:
            raise ValidationError("El cheque todavía no se entrega a la persona beneficiaria.")
        if cheque.cobrado:
            raise ValidationError("El cheque ya está registrado como cobrado.")
        hoy = timezone.localdate()
        fecha_cobro = fecha_cobro or hoy
        if fecha_cobro > hoy:
            raise ValidationError("La fecha del cobro no puede ser futura.")
        if fecha_cobro < timezone.localtime(cheque.entregado_en).date():
            raise ValidationError("El cobro no puede ser anterior a la entrega del cheque.")
        if cheque.vence_cobro and fecha_cobro > cheque.vence_cobro:
            raise ValidationError(f"El cheque venció el {cheque.vence_cobro:%d/%m/%Y} (3 meses desde la entrega): ya no se "
                                  "cobra; solo se reexpide con causa plenamente justificada (ROP PSAHEM 8.1.7 fr. XVI).")
        cheque.cobrado_en, cheque.cobro_registrado_por = fecha_cobro, usuario
        cheque.save(update_fields=["cobrado_en", "cobro_registrado_por"])
        Evento.registrar(cheque.expediente, usuario, "cheque_cobrado",
                         f"Cheque {cheque.numero} cobrado el {fecha_cobro:%d/%m/%Y}.", datos={"cheque": cheque.pk})
    return cheque


def revisar_cobros(hoy):
    """``manage.py revisar_plazos``: avisa (bitácora, una vez por situación) de los cheques entregados sin cobro que están por
    vencer (5 días hábiles o menos) o vencidos. Solo aviso: la baja por cheque vencido es del sprint 3."""
    avisados = 0
    for c in Cheque.objects.filter(entregado_en__isnull=False, cobrado_en__isnull=True).select_related(
            "expediente__ejercicio__programa"):
        v = vencimiento_cobro(c)
        if v is None or not v.tiene_fecha:
            continue
        estado = {"por vencer": "por_vencer", "vencido": "vencido"}.get(v.estado(hoy))
        if estado is None or c.aviso_cobro == estado:
            continue
        texto = "vence" if estado == "por_vencer" else "venció"
        Evento.registrar(c.expediente, None, f"cheque_{estado}",
                         f"El cheque {c.numero} (ministración {c.ministracion}) {texto} el {v.vencimiento:%d/%m/%Y} sin que se "
                         "registre su cobro.", datos={"cheque": c.pk})
        c.aviso_cobro = estado
        c.save(update_fields=["aviso_cobro"])
        avisados += 1
    return avisados
