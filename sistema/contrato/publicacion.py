"""HU-3.1 · Publicación de resultados y notificaciones por conducto de la Delegación.

- ``publicar``: el área responsable del programa publica los listados que el Comité autorizó en su acta
  (CC 9.4.3 fr. III; Convocatoria base quinta). Deja la fecha y hora, su acuse, el hito
  ``publicacion_resultados`` de cada solicitud, el cambio de estado de las aprobadas (``aprobada`` →
  ``publicada``) y el aviso del resultado a cada persona por conducto de su Delegación. En PS, además, la
  cita a firma, que la Delegación debe hacer en 5 días hábiles desde la publicación (10.1 inciso h).
- ``enviar_aviso``: cualquier otro aviso a la persona (cita a firma, omisiones por subsanar y devoluciones
  del sprint 3) con ``nucleo.notificaciones``.
- ``registrar_entrega``: la Delegación registra que notificó (fecha, hora, medio y acuse). Al notificar el
  resultado de una persona beneficiaria, el expediente pasa a ``notificada`` (``al_notificar``).
"""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from dictamen.comun import exigir_programa, exigir_unidad
from dictamen.models import EstadoSesion, ResultadoListado, SesionComite, TipoSesion
from nucleo import dias_habiles, notificaciones, plazos
from nucleo.acuses import emitir_acuse
from nucleo.models import (
    Evento, MedioNotificacion, Notificacion, TipoNotificacion, TipoUnidad, expedientes_visibles,
)

from .models import Publicacion, ResultadoPublicado

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
    """Sesiones de aprobación con acta de los programas que atiende la unidad (publicadas o no)."""
    qs = SesionComite.objects.filter(tipo=TipoSesion.APROBACION, estado=EstadoSesion.CELEBRADA).select_related(
        "ejercicio__programa", "publicacion")
    if usuario.tipo_unidad == TipoUnidad.DIRECCION:
        return qs.filter(ejercicio__programa__in=usuario.unidad.programas.all())
    return qs  # Jurídica, Secretaría Técnica y administración consultan


def sesiones_por_publicar(usuario):
    return sesiones_publicables(usuario).filter(autoriza_publicacion=True, publicacion__isnull=True)


def sesion_de_expediente(expediente):
    """La sesión de aprobación que lo aprobó (la última resolución a su favor)."""
    r = (expediente.resoluciones_comite.filter(resultado=ResultadoListado.BENEFICIARIA)
         .select_related("sesion").order_by("-sesion__fecha_hora").first())
    return r.sesion if r else None


def notificaciones_visibles(usuario):
    return (Notificacion.objects.filter(expediente__in=expedientes_visibles(usuario))
            .select_related("expediente__predio__municipio", "expediente__ejercicio__programa", "destinatario",
                            "delegacion", "acuse_envio", "acuse_notificacion", "notificada_por"))


def por_entregar(usuario):
    """Lo que la Delegación del usuario aún debe notificar a las personas."""
    if usuario.tipo_unidad != TipoUnidad.DELEGACION:
        return Notificacion.objects.none()
    return notificaciones_visibles(usuario).filter(delegacion=usuario.unidad, notificada_en__isnull=True)


def vencimiento_de(notificacion):
    """Plazo en que la Delegación debe entregarla (hoy solo la cita a firma de PS), o None."""
    if notificacion.tipo == TipoNotificacion.CITA_FIRMA:
        return plazos.vencimiento(notificacion.expediente, "cita_firma")
    return None


# ----------------------------------------------------------------------------- publicar
def publicar(usuario, sesion, momento=None, lugares=""):
    """Publica los listados de la sesión de aprobación (``Publicacion``). Ver el módulo."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    exigir_programa(usuario, _ConPrograma(sesion.ejercicio.programa))
    if sesion.tipo != TipoSesion.APROBACION:
        raise ValidationError("Solo se publican los listados de una sesión de aprobación.")
    if sesion.estado != EstadoSesion.CELEBRADA or not sesion.acta_fecha:
        raise ValidationError("La sesión no tiene acta: el Comité debe aprobar los listados antes de publicarlos.")
    if not sesion.autoriza_publicacion:
        raise ValidationError("El acta de la sesión no autorizó la publicación de los listados.")
    if Publicacion.objects.filter(sesion=sesion).exists():
        raise ValidationError("Los listados de esta sesión ya se publicaron.")
    ahora = momento or timezone.now()
    if ahora < sesion.acta_fecha:
        raise ValidationError("La publicación no puede ser anterior al acta del Comité.")
    resoluciones = list(sesion.resoluciones.select_related(
        "expediente__predio__municipio", "expediente__solicitante", "expediente__estado", "expediente__delegacion"))
    if not resoluciones:
        raise ValidationError("La sesión no tiene listados que publicar.")
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
        detalle = [{"clave": r.get_resultado_display(),
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
            texto = f"{sesion.numero}: {r.get_resultado_display()} publicada"
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
def enviar_aviso(usuario, expediente, tipo, asunto, observaciones="", renglones=(), datos=None):
    """Aviso a la persona por conducto de la Delegación (cita a firma, omisiones por subsanar, devolución…)."""
    if usuario.tipo_unidad == TipoUnidad.DELEGACION:
        raise PermissionDenied("Los avisos los envía el área responsable; la Delegación los notifica.")
    if not asunto.strip():
        raise ValidationError("El aviso necesita un asunto.")
    return notificaciones.emitir_notificacion(expediente, tipo, asunto.strip(), usuario, renglones=renglones,
                                              observaciones=observaciones, datos=datos)


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
    qs = ResultadoPublicado.objects.filter(publicacion__ejercicio=ejercicio)
    if folio.strip():
        qs = qs.filter(folio__icontains=folio.strip())
    return qs.order_by("resultado", "orden", "folio")
