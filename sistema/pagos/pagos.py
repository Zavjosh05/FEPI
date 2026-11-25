"""HU-5.2 · Pago de la ministración.

- ``revisar_solicitud``: Administración y Finanzas revisa la solicitud del área responsable y la **acepta** (si sus soportes siguen
  completos) o la **devuelve** con observaciones (el expediente vuelve a ``contratada`` y el área la corrige y la reenvía).
- ``registrar_pago``: el pago por transferencia (o depósito al Guardabosque, PEG) con referencia, fecha y un importe igual al
  solicitado; el cheque solo como caso excepcional, con su motivo. Siempre cuelga de una solicitud aceptada y no se paga dos veces la
  misma ministración. Deja acuse, el estado ``pagada`` y el aviso de pago a la persona por conducto de la Delegación.
- ``remitir_a_fiduciaria`` (PSAHEM): quién remite lo deciden las ROP. El pago se solicita a la Fiduciaria **a través de la Secretaría
  Técnica del Comité Técnico**, en un máximo de 5 días hábiles desde que recibe la solicitud del área (10.1 fr. X, líneas 2290 a
  2292); Administración y Finanzas es la responsable de los recursos y de que lo solicitado esté comprobado (10.1 fr. XIV, líneas
  2321 a 2323), así que acepta la solicitud y la Secretaría Técnica la remite. La remisión deja fecha y hora, acuse, el hito
  ``remision_fiduciaria`` y si se hizo dentro del plazo (R-16).
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from dictamen.comun import exigir_acceso, exigir_unidad
from nucleo import montos, plazos
from nucleo.acuses import emitir_acuse
from nucleo.models import Evento, TipoNotificacion, TipoUnidad
from nucleo.notificaciones import emitir_notificacion

from . import solicitudes
from .models import (
    EstadoSolicitud, Pago, RemisionFiduciaria, ResultadoRevision, RevisionSolicitud, SolicitudPago, TipoPagoRegistrado,
)
from nucleo.trazabilidad import registra_usuario

USO_REMISION = "instruccion_pago_fiduciaria"


def es_fiduciaria(expediente):
    """PSAHEM: el pago lo emite la Fiduciaria con cheque (HU-5.3), no Administración y Finanzas."""
    return solicitudes.tipo_pago(expediente) == "cheque_fiduciaria"


def tipos_de_pago(expediente):
    """Formas de pago que puede registrar Administración y Finanzas: la del programa y, siempre, el cheque excepcional."""
    propio = solicitudes.tipo_pago(expediente)
    return [] if es_fiduciaria(expediente) else [propio, TipoPagoRegistrado.CHEQUE_EXCEPCIONAL.value]


def _fmt(valor):
    return f"{timezone.localtime(valor):%d/%m/%Y %H:%M:%S} h"


def _recargar(solicitud):
    s = SolicitudPago.objects.select_related("expediente__ejercicio__programa", "expediente__estado",
                                             "expediente__solicitante").get(pk=solicitud.pk)
    s.expediente.refresh_from_db()
    return s


# ----------------------------------------------------------------------------- consultas
def _visibles(usuario, estado):
    return [s for s in solicitudes.solicitudes_visibles(usuario).filter(estado=estado).order_by("enviada_en", "id")]


def por_revisar(usuario):
    """Solicitudes enviadas que Administración y Finanzas aún no revisa."""
    return _visibles(usuario, EstadoSolicitud.ENVIADA) if usuario.tipo_unidad == TipoUnidad.ADMIN_FINANZAS else []


def por_pagar(usuario):
    """Solicitudes aceptadas que Administración y Finanzas paga (todas menos PSAHEM, que paga la Fiduciaria con cheque)."""
    if usuario.tipo_unidad != TipoUnidad.ADMIN_FINANZAS:
        return []
    return [s for s in _visibles(usuario, EstadoSolicitud.ACEPTADA) if not es_fiduciaria(s.expediente)]


def por_remitir(usuario):
    """PSAHEM: solicitudes aceptadas que la Secretaría Técnica aún no solicita a la Fiduciaria."""
    if usuario.tipo_unidad != TipoUnidad.SECRETARIA_COMITE:
        return []
    return [s for s in _visibles(usuario, EstadoSolicitud.ACEPTADA) if es_fiduciaria(s.expediente)]


def en_revision_psa(usuario):
    """PSAHEM: solicitudes que la Secretaría Técnica recibió del área y Administración y Finanzas aún revisa."""
    if usuario.tipo_unidad != TipoUnidad.SECRETARIA_COMITE:
        return []
    return [s for s in _visibles(usuario, EstadoSolicitud.ENVIADA) if es_fiduciaria(s.expediente)]


# ----------------------------------------------------------------------------- revisión
@registra_usuario
def revisar_solicitud(usuario, solicitud, resultado, observaciones="", momento=None):
    """Administración y Finanzas acepta la solicitud o la devuelve al área responsable con observaciones."""
    exigir_unidad(usuario, TipoUnidad.ADMIN_FINANZAS)
    if resultado not in ResultadoRevision.values:
        raise ValidationError("Indique si la solicitud se acepta o se devuelve.")
    observaciones = (observaciones or "").strip()
    with transaction.atomic():
        solicitud = _recargar(solicitud)
        exp = solicitud.expediente
        exigir_acceso(usuario, exp)
        if solicitud.estado != EstadoSolicitud.ENVIADA:
            raise ValidationError(f"La solicitud {solicitud.folio} está «{solicitud.get_estado_display().lower()}»: "
                                  "solo se revisa una solicitud enviada.")
        if resultado == ResultadoRevision.DEVUELTA and not observaciones:
            raise ValidationError("Al devolver la solicitud indique las observaciones para el área responsable.")
        lista = solicitudes.soportes(exp, solicitud.ministracion)
        faltan = solicitudes.faltantes(lista)
        if resultado == ResultadoRevision.ACEPTADA:
            if faltan:
                raise ValidationError("No se acepta la solicitud: falta " + "; ".join(s["nombre"] for s in faltan)
                                      + ". Devuélvala con observaciones.")
            esperado = next(m for m in montos.monto_aprobado(exp).ministraciones if m.numero == solicitud.ministracion)
            if esperado.importe != solicitud.importe:
                raise ValidationError(f"El importe de la solicitud (${solicitud.importe:,.2f}) no es el de la ministración "
                                      f"aprobada (${esperado.importe:,.2f}): devuélvala.")
        ahora = momento or timezone.now()
        titulo = "aceptada" if resultado == ResultadoRevision.ACEPTADA else "devuelta"
        revision = RevisionSolicitud(solicitud=solicitud, resultado=resultado, envio=solicitud.envios,
                                     observaciones=observaciones, revisada_por=usuario, revisada_en=ahora)
        renglones = [("Solicitud de pago", solicitud.folio), ("Expediente", exp.folio),
                     ("Persona beneficiaria", exp.solicitante.nombre),
                     ("Ministración", f"{solicitud.ministracion} (${solicitud.importe:,.2f})"),
                     ("Resultado de la revisión", ResultadoRevision(resultado).label),
                     ("Fecha y hora", _fmt(ahora)), ("Revisa", usuario.unidad.nombre)]
        if observaciones:
            renglones.append(("Observaciones", observaciones))
        acuse = emitir_acuse(exp, f"revision_solicitud_pago", f"Solicitud de pago {solicitud.folio} {titulo}", usuario,
                             renglones, destinatario=solicitud.enviada_por.unidad.nombre if solicitud.enviada_por else "")
        revision.acuse = acuse
        revision.save()
        if resultado == ResultadoRevision.ACEPTADA:
            solicitud.estado = EstadoSolicitud.ACEPTADA
            solicitud.save(update_fields=["estado"])
            Evento.registrar(exp, usuario, "solicitud_pago_aceptada",
                             f"Solicitud de pago {solicitud.folio} aceptada por Administración y Finanzas.", acuse=acuse,
                             datos={"solicitud": solicitud.pk})
        else:
            solicitud.estado = EstadoSolicitud.DEVUELTA
            solicitud.save(update_fields=["estado"])
            exp.cambiar_estado("contratada", usuario, motivo=observaciones, tipo_evento="solicitud_pago_devuelta",
                               acuse=acuse, descripcion=f"Solicitud de pago {solicitud.folio} devuelta al área responsable: "
                                                        f"{observaciones}", datos={"solicitud": solicitud.pk})
    return revision


# ----------------------------------------------------------------------------- pago
@registra_usuario
def registrar_pago(usuario, solicitud, referencia, fecha_pago, importe=None, tipo=None, motivo_cheque="", momento=None):
    """Administración y Finanzas registra el pago de una solicitud aceptada (transferencia; cheque solo excepcional)."""
    exigir_unidad(usuario, TipoUnidad.ADMIN_FINANZAS)
    referencia, motivo_cheque = (referencia or "").strip(), (motivo_cheque or "").strip()
    with transaction.atomic():
        solicitud = _recargar(solicitud)
        exp = solicitud.expediente
        exigir_acceso(usuario, exp)
        if es_fiduciaria(exp):
            raise ValidationError("En PSAHEM el pago lo emite la Fiduciaria con cheque: la Secretaría Técnica del Comité Técnico "
                                  "se lo solicita y la Delegación lo entrega (HU-5.3).")
        if hasattr(solicitud, "pago"):
            raise ValidationError(f"La ministración {solicitud.ministracion} ya se pagó (pago del "
                                  f"{solicitud.pago.fecha_pago:%d/%m/%Y}): no se paga dos veces.")
        if solicitud.estado != EstadoSolicitud.ACEPTADA:
            raise ValidationError(f"La solicitud {solicitud.folio} está «{solicitud.get_estado_display().lower()}»: "
                                  "solo se paga una solicitud aceptada por Administración y Finanzas.")
        tipo = tipo or solicitudes.tipo_pago(exp)
        if tipo not in tipos_de_pago(exp):
            raise ValidationError("Forma de pago no válida para este programa: "
                                  + ", ".join(solicitudes.nombre_tipo_pago(t) for t in tipos_de_pago(exp)) + ".")
        if tipo == TipoPagoRegistrado.CHEQUE_EXCEPCIONAL and not motivo_cheque:
            raise ValidationError("El cheque es un caso excepcional: indique el motivo.")
        if not referencia:
            raise ValidationError("Indique la referencia del pago (de la transferencia o depósito, o el número de cheque).")
        importe = solicitud.importe if importe in (None, "") else Decimal(importe)
        if importe != solicitud.importe:
            raise ValidationError(f"El importe pagado (${importe:,.2f}) debe ser igual al solicitado (${solicitud.importe:,.2f}).")
        hoy = timezone.localdate()
        if fecha_pago is None:
            raise ValidationError("Indique la fecha del pago.")
        if fecha_pago > hoy:
            raise ValidationError("La fecha del pago no puede ser futura.")
        if fecha_pago < timezone.localtime(solicitud.enviada_en).date():
            raise ValidationError("El pago no puede ser anterior al envío de la solicitud "
                                  f"({timezone.localtime(solicitud.enviada_en):%d/%m/%Y}).")
        ahora = momento or timezone.now()
        pago = Pago(solicitud=solicitud, expediente=exp, ministracion=solicitud.ministracion, importe=importe, tipo=tipo,
                    referencia=referencia, fecha_pago=fecha_pago, motivo_cheque=motivo_cheque, registrado_por=usuario,
                    registrado_en=ahora)
        pago.save()
        renglones = [("Solicitud de pago", solicitud.folio), ("Expediente", exp.folio),
                     ("Persona beneficiaria", exp.solicitante.nombre),
                     ("Ministración", f"{solicitud.ministracion} ({solicitud.porcentaje:g} %)"),
                     ("Importe pagado", f"${importe:,.2f}"), ("Forma de pago", solicitudes.nombre_tipo_pago(tipo)),
                     ("Referencia", referencia), ("Fecha del pago", f"{fecha_pago:%d/%m/%Y}"),
                     ("Registrado", _fmt(ahora)), ("Registra", usuario.unidad.nombre)]
        if motivo_cheque:
            renglones.append(("Motivo del cheque (caso excepcional)", motivo_cheque))
        pago.acuse = emitir_acuse(exp, "pago_ministracion", f"Pago de la ministración {solicitud.ministracion} de {exp.folio}",
                                  usuario, renglones, destinatario=exp.solicitante.nombre)
        pago.save(update_fields=["acuse"])
        solicitud.estado = EstadoSolicitud.PAGADA
        solicitud.save(update_fields=["estado"])
        plazos.registrar_hito(exp, "pago_ministracion", usuario, ahora, referencia=solicitud.folio,
                              datos={"pago": pago.pk, "ministracion": solicitud.ministracion})
        exp.cambiar_estado("pagada", usuario, tipo_evento="pago_ministracion", acuse=pago.acuse,
                           descripcion=f"Ministración {solicitud.ministracion} pagada (${importe:,.2f}, "
                                       f"{solicitudes.nombre_tipo_pago(tipo).lower()}, referencia {referencia}) el "
                                       f"{fecha_pago:%d/%m/%Y}", datos={"pago": pago.pk, "solicitud": solicitud.pk})
        pago.aviso = emitir_notificacion(
            exp, TipoNotificacion.PAGO, f"Pago de su ministración {solicitud.ministracion} ({exp.programa.nombre})", usuario,
            acuse_envio=pago.acuse, observaciones=f"Importe ${importe:,.2f}; {solicitudes.nombre_tipo_pago(tipo).lower()}; "
                                                  f"fecha {fecha_pago:%d/%m/%Y}.", datos={"pago": pago.pk})
        pago.save(update_fields=["aviso"])
    return pago


# ----------------------------------------------------------------------------- PSAHEM: remisión a la Fiduciaria
@registra_usuario
def remitir_a_fiduciaria(usuario, solicitud, oficio="", observaciones="", momento=None):
    """PSAHEM: la Secretaría Técnica del Comité Técnico solicita el pago a la Fiduciaria (fecha y hora, acuse y plazo)."""
    exigir_unidad(usuario, TipoUnidad.SECRETARIA_COMITE)
    with transaction.atomic():
        solicitud = _recargar(solicitud)
        exp = solicitud.expediente
        exigir_acceso(usuario, exp)
        if not es_fiduciaria(exp):
            raise ValidationError(f"{exp.programa.nombre} no paga por la Fiduciaria: solo PSAHEM (ROP PSAHEM 10.1 fr. X).")
        if hasattr(solicitud, "remision"):
            raise ValidationError(f"La ministración {solicitud.ministracion} ya se remitió a la Fiduciaria "
                                  f"el {timezone.localtime(solicitud.remision.remitida_en):%d/%m/%Y}.")
        if solicitud.estado == EstadoSolicitud.ENVIADA:
            raise ValidationError("Administración y Finanzas todavía no acepta la solicitud: no se remite lo que no está comprobado.")
        if solicitud.estado != EstadoSolicitud.ACEPTADA:
            raise ValidationError(f"La solicitud {solicitud.folio} está «{solicitud.get_estado_display().lower()}»: solo se "
                                  "remite una solicitud aceptada por Administración y Finanzas.")
        ahora = momento or timezone.now()
        if ahora < solicitud.enviada_en:
            raise ValidationError("La remisión no puede ser anterior al envío de la solicitud.")
        venc = plazos.vencimiento(exp, USO_REMISION, fecha_evento=solicitud.enviada_en)
        vence = venc.vencimiento if venc is not None else None
        en_plazo = vence is None or timezone.localtime(ahora).date() <= vence
        remision = RemisionFiduciaria(
            solicitud=solicitud, expediente=exp, ministracion=solicitud.ministracion, remitida_por=usuario,
            remitida_en=ahora, recibida_en=solicitud.enviada_en, vence_el=vence, en_plazo=en_plazo,
            oficio=(oficio or "").strip(), observaciones=(observaciones or "").strip())
        remision.save()
        renglones = [("Solicitud de pago", solicitud.folio), ("Expediente", exp.folio),
                     ("Persona beneficiaria", exp.solicitante.nombre),
                     ("Ministración", f"{solicitud.ministracion} ({solicitud.porcentaje:g} %)"),
                     ("Importe", f"${solicitud.importe:,.2f}"),
                     ("Solicitud del área recibida", _fmt(solicitud.enviada_en)),
                     ("Plazo de la Secretaría Técnica", f"5 días hábiles, hasta el {vence:%d/%m/%Y}" if vence else "—"),
                     ("Fecha y hora de la remisión a la Fiduciaria", _fmt(ahora)),
                     ("Situación", "En plazo" if en_plazo else "Fuera de plazo"), ("Remite", usuario.unidad.nombre)]
        if remision.oficio:
            renglones.append(("Oficio", remision.oficio))
        if remision.observaciones:
            renglones.append(("Observaciones", remision.observaciones))
        remision.acuse = emitir_acuse(exp, "remision_fiduciaria", f"Remisión a la Fiduciaria de {solicitud.folio}", usuario,
                                      renglones, destinatario="Fiduciaria del FIPASAHEM",
                                      nota="ROP PSAHEM 10.1 fr. X (líneas 2290 a 2292) y fr. XIV (líneas 2321 a 2323).")
        remision.save(update_fields=["acuse"])
        solicitud.estado = EstadoSolicitud.REMITIDA
        solicitud.save(update_fields=["estado"])
        plazos.registrar_hito(exp, "remision_fiduciaria", usuario, ahora, referencia=solicitud.folio,
                              datos={"remision": remision.pk, "ministracion": solicitud.ministracion, "en_plazo": en_plazo})
        exp.cambiar_estado("remitida_fiduciaria", usuario, tipo_evento="remision_fiduciaria", acuse=remision.acuse,
                           descripcion=f"Pago de la ministración {solicitud.ministracion} solicitado a la Fiduciaria el "
                                       f"{timezone.localtime(ahora):%d/%m/%Y %H:%M} h ({'en plazo' if en_plazo else 'fuera de plazo'}).",
                           datos={"remision": remision.pk, "solicitud": solicitud.pk})
    return remision


def revisar_remisiones(hoy):
    """``manage.py revisar_plazos``: señala (una vez, en la bitácora) las solicitudes de PSAHEM cuyos 5 días hábiles para
    solicitar el pago a la Fiduciaria ya vencieron sin remisión."""
    senaladas = 0
    pendientes = SolicitudPago.objects.filter(
        estado__in=(EstadoSolicitud.ENVIADA, EstadoSolicitud.ACEPTADA), remision__isnull=True).select_related(
        "expediente__ejercicio__programa", "expediente__estado")
    for sol in pendientes:
        if not es_fiduciaria(sol.expediente):
            continue
        venc = solicitudes.plazo_remision(sol)
        if venc is None or not venc.tiene_fecha or hoy <= venc.vencimiento:
            continue
        if Evento.objects.filter(expediente=sol.expediente, tipo="remision_vencida", datos__solicitud=sol.pk).exists():
            continue
        Evento.registrar(sol.expediente, None, "remision_vencida",
                         f"Venció el {venc.vencimiento:%d/%m/%Y} el plazo de 5 días hábiles de la Secretaría Técnica para "
                         f"solicitar a la Fiduciaria el pago de la ministración {sol.ministracion} ({sol.folio}).",
                         datos={"solicitud": sol.pk})
        senaladas += 1
    return senaladas
