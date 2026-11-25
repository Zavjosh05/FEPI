"""HU-3.1 · Publicación de resultados y notificaciones por conducto de la Delegación.

- ``publicar``: el área responsable del programa publica los listados que el Comité autorizó en su acta
  (CC 9.4.3 fr. III; Convocatoria base quinta). Con las reasignaciones de HU-2.4 (``filas_por_publicar``): quien salió
  por un acuerdo de seguimiento antes de publicar ya no se publica, y quien entró desde la lista de espera se publica
  como persona beneficiaria; si la reasignación llega después de publicar, se publica con el acta de la sesión de
  seguimiento que la acordó (al cerrarla con reasignaciones, el acta autoriza su publicación). Deja la fecha y hora, su acuse, el hito
  ``publicacion_resultados`` de cada solicitud, el cambio de estado de las aprobadas (``aprobada`` →
  ``publicada``) y el aviso del resultado a cada persona por conducto de su Delegación. En PS, además, la
  cita a firma, que la Delegación debe hacer en 5 días hábiles desde la publicación (10.1 inciso h).
- ``enviar_aviso``: cualquier otro aviso a la persona (cita a firma, omisiones por subsanar y devoluciones
  del sprint 3) con ``nucleo.notificaciones``.
- ``registrar_entrega``: la Delegación registra que notificó (fecha, hora, medio y acuse). Al notificar el
  resultado de una persona beneficiaria, el expediente pasa a ``notificada`` (``al_notificar``).
"""
from types import SimpleNamespace

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from dictamen.comun import exigir_programa, exigir_unidad
from dictamen.models import EstadoSesion, MovimientoListado, ResultadoListado, SesionComite, TipoMovimiento, TipoSesion
from nucleo import dias_habiles, notificaciones, plazos
from nucleo.acuses import emitir_acuse
from nucleo.models import (
    Evento, MedioNotificacion, Notificacion, TipoNotificacion, TipoUnidad, expedientes_visibles,
)

from .models import Publicacion, ResultadoPublicado
from nucleo.trazabilidad import registra_usuario

LUGARES_POR_OMISION = ("Página de PROBOSQUE (https://probosque.edomex.gob.mx), Oficinas Centrales y "
                       "Delegaciones Regionales Forestales")
TEXTO_RESULTADO = {
    ResultadoListado.BENEFICIARIA: "Su solicitud fue aprobada: usted es persona beneficiaria",
    ResultadoListado.LISTA_ESPERA: "Su solicitud quedó en la lista de espera",
    ResultadoListado.NO_FACTIBLE: "Su solicitud resultó no factible",
}


def _fmt(valor):
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M:%S h")


class _ConPrograma:
    """Adapta el programa al chequeo de ``exigir_programa`` (que lee ``expediente.programa``)."""

    def __init__(self, programa):
        self.programa = programa


# ----------------------------------------------------------------------------- fecha de la convocatoria
def fecha_limite_publicacion(ejercicio, acta_fecha):
    """(fecha | None, fundamento): la fecha que marca la convocatoria para publicar, si las reglas la traen.

    Las ROP 2026 no fijan días ni fecha para publicar (plazo ``publicacion_resultados`` sin número); si algún
    programa la trae, se usa: una cantidad en días o meses desde el acta, o una fecha límite."""
    plazo = ejercicio.plazo("publicacion_resultados")
    if plazo is None:
        return None, ""
    fundamento = f"{plazo.fundamento} (línea {plazo.linea_rop})" if plazo.linea_rop else plazo.fundamento
    if plazo.cantidad is not None and plazo.unidad in dias_habiles.UNIDADES_CALCULABLES:
        return dias_habiles.calcular_vencimiento(acta_fecha, plazo.cantidad, plazo.unidad), fundamento
    if plazo.fecha_fin:
        return plazo.fecha_fin, fundamento
    return None, fundamento


# ----------------------------------------------------------------------------- consultas
def sesiones_publicables(usuario):
    """Sesiones con acta de los programas que atiende la unidad (publicadas o no): las de aprobación y las de seguimiento
    que acordaron reasignaciones (HU-2.4)."""
    qs = SesionComite.objects.filter(
        Q(tipo=TipoSesion.APROBACION) | Q(tipo=TipoSesion.SEGUIMIENTO, autoriza_publicacion=True),
        estado=EstadoSesion.CELEBRADA).select_related("ejercicio__programa", "publicacion")
    if usuario.tipo_unidad == TipoUnidad.DIRECCION:
        return qs.filter(ejercicio__programa__in=usuario.unidad.programas.all())
    return qs  # Jurídica, Secretaría Técnica y administración consultan


def sesiones_por_publicar(usuario):
    return sesiones_publicables(usuario).filter(autoriza_publicacion=True, publicacion__isnull=True)


def sesion_de_expediente(expediente):
    """La sesión con cuya acta se publica: la de aprobación que lo aprobó o, si entró por reasignación (HU-2.4), la de
    aprobación que lo dejó en lista de espera mientras no se publique y, ya publicada, la de seguimiento que lo reasignó."""
    r = (expediente.resoluciones_comite.filter(resultado=ResultadoListado.BENEFICIARIA)
         .select_related("sesion").order_by("-sesion__fecha_hora").first())
    if r is not None:
        return r.sesion
    entrada = (MovimientoListado.objects.filter(expediente=expediente, movimiento=TipoMovimiento.ENTRA)
               .select_related("acuerdo__sesion").order_by("-fecha_hora").first())
    if entrada is None:
        return None
    espera = (expediente.resoluciones_comite.filter(resultado=ResultadoListado.LISTA_ESPERA,
                                                    sesion__estado=EstadoSesion.CELEBRADA)
              .select_related("sesion").order_by("-sesion__fecha_hora").first())
    if espera is not None and not hasattr(espera.sesion, "publicacion"):
        return espera.sesion
    return entrada.acuerdo.sesion


def filas_por_publicar(sesion):
    """Renglones de los listados que se publican con el acta: ``[SimpleNamespace(expediente, resultado, orden, monto,
    reasignada, lugar_espera)]``.

    Sesión de aprobación: sus listados, salvo quien salió por un acuerdo de seguimiento (baja), y con quien entró desde la
    lista de espera (reasignación) como persona beneficiaria. Sesión de seguimiento: las personas que entraron por
    reasignación."""
    if sesion.tipo == TipoSesion.SEGUIMIENTO:
        movs = (MovimientoListado.objects.filter(acuerdo__sesion=sesion, movimiento=TipoMovimiento.ENTRA)
                .select_related("expediente__predio__municipio", "expediente__solicitante", "expediente__estado",
                                "expediente__delegacion").order_by("fecha_hora", "pk"))
        return [SimpleNamespace(expediente=m.expediente, resultado=ResultadoListado.BENEFICIARIA, orden=None,
                                monto=m.monto, reasignada=True, lugar_espera=m.lugar_lista_espera) for m in movs]
    filas = []
    for r in sesion.resoluciones.select_related(
            "expediente__predio__municipio", "expediente__solicitante", "expediente__estado", "expediente__delegacion"):
        estado = r.expediente.estado.clave
        if r.resultado == ResultadoListado.BENEFICIARIA and estado == "baja":
            continue                      # salió por un acuerdo de seguimiento antes de publicar
        if r.resultado == ResultadoListado.LISTA_ESPERA and estado == "aprobada":
            filas.append(SimpleNamespace(expediente=r.expediente, resultado=ResultadoListado.BENEFICIARIA, orden=None,
                                         monto=r.monto, reasignada=True, lugar_espera=r.orden))
            continue
        filas.append(SimpleNamespace(expediente=r.expediente, resultado=r.resultado, orden=r.orden, monto=r.monto,
                                     reasignada=False, lugar_espera=None))
    return filas


def notificaciones_visibles(usuario):
    return (Notificacion.objects.filter(expediente__in=expedientes_visibles(usuario))
            .select_related("expediente__predio__municipio", "expediente__ejercicio__programa", "destinatario",
                            "delegacion", "acuse_envio", "acuse_notificacion", "notificada_por"))


def por_entregar(usuario):
    """Lo que la Delegación del usuario aún debe notificar a las personas."""
    if usuario.tipo_unidad != TipoUnidad.DELEGACION:
        return Notificacion.objects.none()
    return notificaciones_visibles(usuario).filter(delegacion=usuario.unidad, notificada_en__isnull=True)


def vencimientos_de(notificaciones):
    """``{pk: Vencimiento}`` de las notificaciones que tienen plazo (hoy la cita a firma de PS), con una sola consulta de
    los hitos de publicación en lugar de una por renglón."""
    citas = [n for n in notificaciones if n.tipo == TipoNotificacion.CITA_FIRMA]
    if not citas:
        return {}
    from nucleo.models import Hito

    publicaciones = {}
    for h in Hito.objects.filter(clave="publicacion_resultados", expediente_id__in={n.expediente_id for n in citas})             .order_by("fecha_hora", "id"):
        publicaciones[h.expediente_id] = h.fecha_hora            # el más reciente de cada expediente
    return {n.pk: plazos.vencimiento(n.expediente, "cita_firma", fecha_evento=publicaciones.get(n.expediente_id)) if
            n.expediente_id in publicaciones else vencimiento_de(n) for n in citas}


def vencimiento_de(notificacion):
    """Plazo en que la Delegación debe entregarla (hoy solo la cita a firma de PS), o None."""
    if notificacion.tipo == TipoNotificacion.CITA_FIRMA:
        return plazos.vencimiento(notificacion.expediente, "cita_firma")
    return None


# ----------------------------------------------------------------------------- publicar
@registra_usuario
def publicar(usuario, sesion, momento=None, lugares=""):
    """Publica los listados de la sesión de aprobación (``Publicacion``). Ver el módulo."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    exigir_programa(usuario, _ConPrograma(sesion.ejercicio.programa))
    if sesion.tipo not in (TipoSesion.APROBACION, TipoSesion.SEGUIMIENTO):
        raise ValidationError("Solo se publican los listados de una sesión de aprobación o las reasignaciones de una de "
                              "seguimiento.")
    if sesion.estado != EstadoSesion.CELEBRADA or not sesion.acta_fecha:
        raise ValidationError("La sesión no tiene acta: el Comité debe aprobar los listados antes de publicarlos.")
    if not sesion.autoriza_publicacion:
        raise ValidationError("El acta de la sesión no autorizó la publicación de los listados."
                              if sesion.tipo == TipoSesion.APROBACION else
                              "La sesión de seguimiento no acordó reasignaciones que publicar.")
    if Publicacion.objects.filter(sesion=sesion).exists():
        raise ValidationError("Los listados de esta sesión ya se publicaron.")
    ahora = momento or timezone.now()
    if ahora < sesion.acta_fecha:
        raise ValidationError("La publicación no puede ser anterior al acta del Comité.")
    resoluciones = filas_por_publicar(sesion)
    if not resoluciones:
        raise ValidationError("La sesión no tiene listados que publicar.")
    if sesion.tipo == TipoSesion.SEGUIMIENTO:
        resoluciones = [r for r in resoluciones if r.expediente.estado.clave == "aprobada"]
        if not resoluciones:
            raise ValidationError("Las personas que entraron por reasignación en esta sesión ya no siguen aprobadas.")
    for r in resoluciones:
        if r.resultado == ResultadoListado.BENEFICIARIA and r.expediente.estado.clave != "aprobada":
            raise ValidationError(f"{r.expediente.folio} está «{r.expediente.estado}»; solo se publica una "
                                  "solicitud aprobada.")
    limite, fundamento = fecha_limite_publicacion(sesion.ejercicio, sesion.acta_fecha)
    dentro = None if limite is None else timezone.localtime(ahora).date() <= limite
    lugares = lugares.strip() or LUGARES_POR_OMISION
    orden = {ResultadoListado.BENEFICIARIA: 0, ResultadoListado.LISTA_ESPERA: 1, ResultadoListado.NO_FACTIBLE: 2}
    resoluciones.sort(key=lambda r: (orden[r.resultado], r.orden or 0, r.expediente.folio))
    with transaction.atomic():
        detalle = [{"clave": ResultadoListado(r.resultado).label + (" (reasignación)" if r.reasignada else ""),
                    "texto": f"{r.expediente.folio} · {r.expediente.predio.nombre} · {r.expediente.predio.municipio.nombre}"
                             + (f" · {r.expediente.solicitante.nombre}" if r.resultado == ResultadoListado.BENEFICIARIA else ""),
                    "estado": str(r.orden) if r.orden else "—"} for r in resoluciones]
        cuenta = {k: sum(r.resultado == k for r in resoluciones) for k in orden}
        if limite is None:
            texto_fecha = "Sin fecha en las reglas (las ROP no fijan fecha ni días para publicar)"
        else:
            texto_fecha = f"{limite:%d/%m/%Y}: " + ("dentro de la fecha" if dentro else "fuera de la fecha")
        acuse = emitir_acuse(
            None, "publicacion_resultados", f"Publicación de resultados de la sesión {sesion.numero}", usuario,
            [("Programa", f"{sesion.ejercicio.programa.nombre} {sesion.ejercicio.anio}"),
             ("Sesión del Comité", f"{sesion.numero} (acta del {_fmt(sesion.acta_fecha)})"),
             ("Fecha y hora de la publicación", _fmt(ahora)), ("Publicada en", lugares),
             ("Fecha de la convocatoria", texto_fecha),
             ("Personas beneficiarias", str(cuenta[ResultadoListado.BENEFICIARIA])),
             ("Lista de espera", str(cuenta[ResultadoListado.LISTA_ESPERA])),
             ("No factibles", str(cuenta[ResultadoListado.NO_FACTIBLE])),
             ("Publica", usuario.unidad.nombre)],
            destinatario="Público en general", referencia=f"Sesión {sesion.numero}", detalle=detalle,
            encabezado_detalle=["Listado", "Solicitud", "Lugar"],
        )
        pub = Publicacion.objects.create(
            sesion=sesion, ejercicio=sesion.ejercicio, publicada_en=ahora, publicada_por=usuario, acuse=acuse,
            lugares=lugares, fecha_limite=limite, dentro_de_fecha=dentro, fundamento_fecha=fundamento)
        for r in resoluciones:
            exp = r.expediente
            ResultadoPublicado.objects.create(
                publicacion=pub, expediente=exp, resultado=r.resultado, orden=r.orden, folio=exp.folio,
                predio=exp.predio.nombre, municipio=exp.predio.municipio.nombre,
                persona=exp.solicitante.nombre if r.resultado == ResultadoListado.BENEFICIARIA else "")
            plazos.registrar_hito(exp, "publicacion_resultados", usuario, ahora, referencia=f"Sesión {sesion.numero}",
                                  datos={"publicacion": pub.pk, "resultado": r.resultado})
            texto = f"{sesion.numero}: {ResultadoListado(r.resultado).label} publicada" + (
                " (entró por reasignación desde la lista de espera)" if r.reasignada else "")
            if r.resultado == ResultadoListado.BENEFICIARIA:
                exp.cambiar_estado("publicada", usuario, tipo_evento="publicacion_resultados", acuse=acuse,
                                   descripcion=texto, datos={"publicacion": pub.pk})
            else:
                Evento.registrar(exp, usuario, "publicacion_resultados", texto, acuse=acuse,
                                 datos={"publicacion": pub.pk})
            _avisos_de_resultado(usuario, pub, r, ahora)
    return pub


def _avisos_de_resultado(usuario, pub, resolucion, ahora):
    exp = resolucion.expediente
    texto = TEXTO_RESULTADO[resolucion.resultado]
    if resolucion.reasignada:
        texto += " por reasignación del recurso liberado (acuerdo del Comité)"
    if resolucion.resultado == ResultadoListado.LISTA_ESPERA and resolucion.orden:
        texto += f", lugar {resolucion.orden}"
    renglones = [("Solicitud", f"{exp.folio} · {exp.predio.nombre}, {exp.predio.municipio.nombre}"),
                 ("Resultado", texto)]
    if resolucion.resultado == ResultadoListado.BENEFICIARIA:
        firma = plazos.vencimiento(exp, "firma_programada")
        if firma is not None:
            renglones.append(("Firma del contrato", firma.texto))
    notificaciones.emitir_notificacion(
        exp, TipoNotificacion.RESULTADOS, f"Resultado de su solicitud {exp.folio}", usuario, renglones=renglones,
        fecha_hora=ahora, datos={"publicacion": pub.pk, "resultado": resolucion.resultado})
    if resolucion.resultado == ResultadoListado.BENEFICIARIA:
        cita = plazos.vencimiento(exp, "cita_firma")
        if cita is not None:  # PS: la Delegación notifica y cita en 5 días hábiles desde la publicación
            notificaciones.emitir_notificacion(
                exp, TipoNotificacion.CITA_FIRMA, f"Cita a la firma del Contrato de Adhesión ({exp.folio})", usuario,
                renglones=[("Plazo de la Delegación para citar", cita.texto)], fecha_hora=ahora,
                datos={"publicacion": pub.pk})


# ----------------------------------------------------------------------------- avisos y entrega
@registra_usuario
def enviar_aviso(usuario, expediente, tipo, asunto, observaciones="", renglones=(), datos=None):
    """Aviso a la persona por conducto de la Delegación (cita a firma, omisiones por subsanar, devolución…)."""
    if usuario.tipo_unidad == TipoUnidad.DELEGACION:
        raise PermissionDenied("Los avisos los envía el área responsable; la Delegación los notifica.")
    if not asunto.strip():
        raise ValidationError("El aviso necesita un asunto.")
    return notificaciones.emitir_notificacion(expediente, tipo, asunto.strip(), usuario, renglones=renglones,
                                              observaciones=observaciones, datos=datos)


@registra_usuario
def registrar_entrega(usuario, notificacion, medio=MedioNotificacion.PERSONAL, fecha_hora=None, observaciones=""):
    """La Delegación registra que notificó a la persona (fecha, hora, medio) y se emite su acuse."""
    return notificaciones.registrar_notificacion(usuario, notificacion, medio, fecha_hora=fecha_hora,
                                                 observaciones=observaciones)


def al_notificar(notificacion):
    """Notificado el resultado de una persona beneficiaria, el expediente pasa a ``notificada``."""
    exp = notificacion.expediente
    exp.refresh_from_db()
    if notificacion.tipo == TipoNotificacion.RESULTADOS and exp.estado.clave == "publicada":
        exp.cambiar_estado("notificada", notificacion.notificada_por, acuse=notificacion.acuse_notificacion,
                           descripcion="Persona beneficiaria notificada del resultado",
                           datos={"notificacion": notificacion.pk})


# ----------------------------------------------------------------------------- página pública
def publicaciones_publicas():
    return Publicacion.objects.select_related("ejercicio__programa", "sesion").order_by("-publicada_en")


def renglones_publicos(ejercicio, folio=""):
    """Lo publicado del ejercicio; de una solicitud publicada más de una vez (lista de espera y luego reasignación) queda
    su publicación más reciente."""
    qs = ResultadoPublicado.objects.filter(publicacion__ejercicio=ejercicio)
    if folio.strip():
        qs = qs.filter(folio__icontains=folio.strip())
    ultimos = {}
    for r in qs.order_by("publicacion__publicada_en", "pk"):
        ultimos[r.expediente_id] = r.pk
    return qs.filter(pk__in=ultimos.values()).order_by("resultado", "orden", "folio")
