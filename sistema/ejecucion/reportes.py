"""HU-4.3 · Evaluación de reportes (solo Guardabosques, PEG).

Cada mes el Guardabosque entrega su reporte mensual en la Delegación (HU-4.1). Aquí:

- ``revisar``: la **Delegación** revisa cada reporte mensual y cada acuse de depósito que recibió de los Guardabosques de su
  zona: «revisado», «revisado con observaciones» o «devuelto para corregir» (el Guardabosque lo vuelve a enviar y el nuevo
  envío es el que cuenta). Lo devuelto se notifica a la persona con sus observaciones.
- ``evaluar_periodo``: la **Dirección de Protección Forestal** (Instancia Ejecutora) evalúa por Guardabosque y por periodo, a
  partir de lo que revisó la Delegación: «cumple» o «no cumple» con su motivo. Un periodo ya terminado sin reporte entregado
  queda como «no entregó» automáticamente (``situacion``) y se ve en la tabla por periodo (``tabla_del_periodo``).
- ``enviar_evaluacion``: la Dirección envía la evaluación del periodo al **CASPEG** con fecha, hora y acuse. Por cada
  Guardabosque que no cumplió o no entregó corre ``extensiones.AL_REPORTE_INCUMPLIDO`` (gancho de HU-6.2).
- El CASPEG **valida** la evaluación con un acuerdo de su sesión de seguimiento (HU-2.4, tipo ``validacion_reportes``: no se
  inventa otro) que incluye a los expedientes evaluados y el periodo.
- ``fuente_evaluacion``: soporte ``evaluacion_reportes`` de ``pagos.solicitudes.FUENTES``. La ministración N pide que cada
  periodo que cubre esté evaluado «cumple», enviado al CASPEG y validado por él; quien no cumplió o no entregó queda señalado y
  su ministración no se solicita.
- Qué periodos cubre cada ministración **no lo dicen las ROP** (R-18): ``datos/ejecucion.json`` → ``reportes`` →
  ``meses_por_ministracion`` es un supuesto configurable (cada ministración cubre los meses que van desde la previa, desde el
  mes de la firma) y así se dice en pantalla.

No cambia el estado del expediente: la evaluación es por Guardabosque y por periodo, y el Guardabosque sigue en el ciclo
«pagada» ↔ «ministración solicitada» del programa mientras tiene periodos en distintas etapas; las bandejas de esta historia se
arman con consultas (README, «Evaluación de reportes»).
"""
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from dictamen.comun import exigir_acceso, exigir_programa, exigir_unidad
from nucleo import extensiones, notificaciones
from nucleo.acuses import emitir_acuse
from nucleo.models import Evento, Expediente, TipoUnidad
from nucleo.trazabilidad import registra_usuario

from . import comprobaciones
from .models import (EnvioEvaluacion, EvaluacionPeriodo, ResultadoEvaluacion, ResultadoRevision, RevisionReporte)

SIN_REPORTE, POR_REVISAR, DEVUELTO, POR_EVALUAR = "sin_reporte", "por_revisar", "devuelto", "por_evaluar"
ETIQUETAS = {
    SIN_REPORTE: "El periodo no termina", POR_REVISAR: "Por revisar en la Delegación", DEVUELTO: "Devuelto para corregir",
    POR_EVALUAR: "Por evaluar", ResultadoEvaluacion.CUMPLE: "Cumple", ResultadoEvaluacion.NO_CUMPLE: "No cumple",
    ResultadoEvaluacion.NO_ENTREGO: "No entregó",
}
CLASES = {"cumple": "success", "no_cumple": "danger", "no_entrego": "danger", POR_REVISAR: "warning", POR_EVALUAR: "info",
          DEVUELTO: "warning", SIN_REPORTE: "secondary"}  # color de la insignia (Bootstrap) de cada estado


# ----------------------------------------------------------------------------- datos
def datos_reportes():
    return comprobaciones.datos_ejecucion()["reportes"]


def config(expediente):
    """Lo del programa en ``datos/ejecucion.json`` → ``reportes`` (None si no evalúa reportes: solo PEG)."""
    return datos_reportes()["programas"].get(expediente.programa.clave)


def es_revisable(comprobacion):
    """El reporte mensual y el acuse de depósito de un programa que los evalúa."""
    cfg = config(comprobacion.expediente)
    return cfg is not None and comprobacion.tipo in cfg["tipos_revisables"]


def _fecha(texto):
    return date.fromisoformat(texto)


def periodos(expediente):
    """Periodos que debe reportar el Guardabosque: los del ejercicio desde el mes de la firma de su contrato."""
    firma = getattr(expediente, "firma_contrato", None)
    if config(expediente) is None or firma is None:
        return []
    desde = timezone.localtime(firma.firmado_en).date()
    return [p for p in comprobaciones.periodos(expediente) if _fecha(p["fin"]) >= desde]


def periodos_de_ministracion(expediente, numero):
    """Supuesto configurable (R-18): periodos que cubre la ministración ``numero``, contados desde el primero que se reporta."""
    cfg = config(expediente)
    if cfg is None:
        return []
    meses, inicio = cfg["meses_por_ministracion"], 0
    for n in range(1, int(numero)):
        if meses.get(str(n)) is None:
            return []
        inicio += meses[str(n)]
    if str(numero) not in meses:
        return []
    cantidad = meses[str(numero)]
    return periodos(expediente)[inicio:None if cantidad is None else inicio + cantidad]


def ministracion_de_periodo(expediente, clave):
    for n in sorted(int(k) for k in (config(expediente) or {}).get("meses_por_ministracion", {})):
        if any(p["clave"] == clave for p in periodos_de_ministracion(expediente, n)):
            return n
    return None


# ----------------------------------------------------------------------------- situación de un Guardabosque en un periodo
def reporte_vigente(expediente, periodo):
    """El reporte más reciente del periodo (el que cuenta si el anterior se devolvió)."""
    cfg = config(expediente)
    return expediente.comprobaciones.filter(tipo=cfg["tipo_reporte"], periodo=periodo).order_by("-enviada_en", "-id").first()


def revision_vigente(comprobacion):
    return comprobacion.revisiones.order_by("-revisada_en", "-id").first() if comprobacion else None


def hay_envio_vigente(expediente, tipo, periodo):
    """HU-4.1: ¿ya hay un envío de ese periodo que cuente? Uno devuelto para corregir se puede volver a enviar."""
    c = expediente.comprobaciones.filter(tipo=tipo, periodo=periodo).order_by("-enviada_en", "-id").first()
    if c is None:
        return False
    r = revision_vigente(c)
    return not (r is not None and r.resultado == ResultadoRevision.DEVUELTO)


def validacion(expediente, evaluacion):
    """El acuerdo del CASPEG (HU-2.4) que validó esta evaluación, si ya la validó."""
    from dictamen.models import Acuerdo

    if evaluacion is None or evaluacion.envio_id is None:
        return None
    return (Acuerdo.objects.filter(tipo="validacion_reportes", periodo=evaluacion.periodo, expedientes=expediente,
                                   registrado__gte=evaluacion.envio.enviado_en).order_by("registrado", "pk").first())


def situacion(expediente, periodo, hoy=None):
    """``{"periodo", "estado", "etiqueta", "reporte", "revision", "evaluacion", "envio", "validacion", "automatico"}`` del
    Guardabosque en el periodo (``periodo``: renglón de ``periodos_reportes``)."""
    hoy = hoy or timezone.localdate()
    clave = periodo["clave"]
    ev = expediente.evaluaciones_periodo.filter(periodo=clave).select_related("envio__acuse", "comprobacion").first()
    c = reporte_vigente(expediente, clave)
    rev = revision_vigente(c)
    automatico = False
    if ev is not None:
        estado = ev.resultado
    elif c is None:
        automatico = _fecha(periodo["fin"]) < hoy
        estado = ResultadoEvaluacion.NO_ENTREGO if automatico else SIN_REPORTE
    elif rev is None:
        estado = POR_REVISAR
    elif rev.resultado == ResultadoRevision.DEVUELTO:
        estado = DEVUELTO
    else:
        estado = POR_EVALUAR
    return {"periodo": periodo, "estado": str(estado), "etiqueta": ETIQUETAS[estado], "clase": CLASES[str(estado)], "reporte": c, "revision": rev,
            "evaluacion": ev, "envio": ev.envio if ev else None, "validacion": validacion(expediente, ev),
            "automatico": automatico or bool(ev and ev.automatica), "ministracion": ministracion_de_periodo(expediente, clave)}


def historial(expediente, hoy=None):
    """Una fila por periodo que debe reportar el Guardabosque (los que ya empezaron), con su situación."""
    hoy = hoy or timezone.localdate()
    return [situacion(expediente, p, hoy) for p in periodos(expediente) if _fecha(p["inicio"]) <= hoy]


# ----------------------------------------------------------------------------- consultas
def _activos(qs):
    from .comprobaciones import datos_ejecucion

    return qs.exclude(estado__final=True).exclude(estado__clave__in=datos_ejecucion()["estados_sin_envios"])


def guardabosques(ejercicio, usuario=None):
    """Expedientes con contrato firmado y apoyo vigente de un ejercicio que evalúa reportes (los que ve ``usuario``)."""
    from nucleo.models import expedientes_visibles

    base = expedientes_visibles(usuario) if usuario is not None else Expediente.objects.all()
    qs = base.filter(ejercicio=ejercicio, firma_contrato__isnull=False)
    return _activos(qs).select_related("solicitante", "persona_beneficiaria", "delegacion", "estado", "ejercicio__programa").order_by("folio")


def periodo_del_ejercicio(ejercicio, clave):
    return next((p for p in (ejercicio.datos or {}).get("periodos_reportes", []) if isinstance(p, dict) and p["clave"] == clave), None)


def ejercicios_que_evaluan(usuario):
    """Ejercicios de los programas que evalúan reportes y que atiende la unidad del usuario."""
    from nucleo.models import Ejercicio

    claves = list(datos_reportes()["programas"])
    qs = Ejercicio.objects.filter(programa__clave__in=claves, reglas_cargadas__isnull=False).select_related("programa")
    unidad = getattr(usuario, "unidad", None)
    if usuario.tipo_unidad == TipoUnidad.DIRECCION and unidad is not None:
        qs = qs.filter(programa__in=unidad.programas.all())
    return qs.order_by("-anio")


def tabla_del_periodo(ejercicio, clave, usuario=None, hoy=None):
    """Guardabosques × estado del periodo: ``[{"expediente", **situacion}]`` (los que deben reportarlo)."""
    hoy = hoy or timezone.localdate()
    filas = []
    for exp in guardabosques(ejercicio, usuario):
        p = next((p for p in periodos(exp) if p["clave"] == clave), None)
        if p is not None and _fecha(p["inicio"]) <= hoy:
            filas.append({"expediente": exp, **situacion(exp, p, hoy)})
    return filas


def resumen(filas):
    """``[{"estado", "etiqueta", "clase", "n"}]`` con cuántos Guardabosques hay en cada estado del periodo."""
    cuenta = {}
    for f in filas:
        cuenta.setdefault(f["estado"], {"estado": f["estado"], "etiqueta": f["etiqueta"], "clase": f["clase"], "n": 0})["n"] += 1
    return list(cuenta.values())


def por_revisar(usuario):
    """Delegación: reportes y acuses de depósito de los Guardabosques de su zona que todavía no revisa."""
    if usuario.tipo_unidad != TipoUnidad.DELEGACION:
        return comprobaciones.Comprobacion.objects.none()
    tipos = sorted({t for c in datos_reportes()["programas"].values() for t in c["tipos_revisables"]})
    claves = list(datos_reportes()["programas"])
    return (comprobaciones.comprobaciones_visibles(usuario).filter(tipo__in=tipos, expediente__ejercicio__programa__clave__in=claves,
                                                                  revisiones__isnull=True)
            .exclude(expediente__estado__final=True).order_by("enviada_en"))


def periodos_por_evaluar(usuario):
    """Dirección: periodos ya terminados con evaluaciones por hacer o por enviar al CASPEG. ``[{"ejercicio", "periodo",
    "pendientes", "por_enviar"}]``."""
    hoy = timezone.localdate()
    salida = []
    for ej in ejercicios_que_evaluan(usuario):
        for p in (ej.datos or {}).get("periodos_reportes", []):
            if not isinstance(p, dict) or _fecha(p["fin"]) >= hoy:
                continue
            filas = tabla_del_periodo(ej, p["clave"], usuario, hoy)
            sin_enviar = [f for f in filas if f["envio"] is None]
            if not sin_enviar:
                continue
            pendientes = [f for f in sin_enviar if f["estado"] in (POR_REVISAR, POR_EVALUAR)]
            salida.append({"ejercicio": ej, "periodo": p, "pendientes": len(pendientes), "por_enviar": len(sin_enviar) - len(pendientes)})
    return salida


def envios_por_validar(ejercicio=None):
    """CASPEG: evaluaciones enviadas cuyo periodo aún no valida un acuerdo para algún expediente. ``[(envio, [evaluaciones])]``."""
    envios = EnvioEvaluacion.objects.select_related("ejercicio__programa", "acuse")
    if ejercicio is not None:
        envios = envios.filter(ejercicio=ejercicio)
    pendientes = []
    for envio in envios:
        sin = [e for e in envio.evaluaciones.select_related("expediente__persona_beneficiaria", "expediente__solicitante") if validacion(e.expediente, e) is None]
        if sin:
            pendientes.append((envio, sin))
    return pendientes


# ----------------------------------------------------------------------------- revisión de la Delegación
@registra_usuario
def revisar(usuario, comprobacion, resultado, observaciones="", momento=None):
    """La Delegación del expediente revisa un reporte mensual o un acuse de depósito recibido (portal o ventanilla)."""
    exp = comprobacion.expediente
    if not es_revisable(comprobacion):
        raise ValidationError("Solo se revisan los reportes mensuales y los acuses de depósito de los Guardabosques.")
    if usuario.tipo_unidad != TipoUnidad.DELEGACION or usuario.unidad_id != exp.delegacion_id:
        raise PermissionDenied("Revisa el reporte la Delegación del expediente.")
    if resultado not in ResultadoRevision.values:
        raise ValidationError("Indique el resultado de la revisión.")
    observaciones = (observaciones or "").strip()
    if resultado != ResultadoRevision.REVISADO and not observaciones:
        raise ValidationError("Escriba las observaciones: qué se debe corregir o qué se observó.")
    if comprobacion.revisiones.exists():
        raise ValidationError("Este envío ya se revisó.")
    if comprobacion.periodo:
        vigente = reporte_vigente(exp, comprobacion.periodo)
        if vigente is None or vigente.pk != comprobacion.pk:
            raise ValidationError("Hay un envío más reciente de ese periodo: es el que se revisa.")
        if exp.evaluaciones_periodo.filter(periodo=comprobacion.periodo).exists():
            raise ValidationError("El periodo ya se evaluó: no se revisa de nuevo.")
    ahora = momento or timezone.now()
    nombre = comprobacion.nombre + (f" de {_nombre(exp, comprobacion.periodo)}" if comprobacion.periodo else "")
    with transaction.atomic():
        r = RevisionReporte.objects.create(comprobacion=comprobacion, expediente=exp, periodo=comprobacion.periodo,
                                           resultado=resultado, observaciones=observaciones, revisada_por=usuario,
                                           unidad=usuario.unidad, revisada_en=ahora)
        if comprobacion.revisada_en is None:
            comprobacion.revisada_por, comprobacion.revisada_en = usuario, ahora
            comprobacion.save(update_fields=["revisada_por", "revisada_en"])
        Evento.registrar(exp, usuario, "reporte_revisado",
                         f"{nombre}: {r.get_resultado_display().lower()} por {usuario.unidad.nombre}."
                         + (f" {observaciones}" if observaciones else ""), datos={"comprobacion": comprobacion.pk, "revision": r.pk})
        if resultado == ResultadoRevision.DEVUELTO:
            notificaciones.emitir_notificacion(
                exp, "otro", f"{nombre} devuelto para corregir", usuario, observaciones=observaciones,
                destinatario=exp.beneficiaria, renglones=[("Observaciones", observaciones),
                                                         ("Qué hacer", "Corrija el reporte y envíelo de nuevo por el portal o en la Delegación.")])
    return r


def _nombre(expediente, clave):
    p = next((p for p in comprobaciones.periodos(expediente) if p["clave"] == clave), None)
    return (p or {}).get("nombre", clave)


# ----------------------------------------------------------------------------- evaluación de la Dirección
def puede_evaluar(usuario, expediente):
    if config(expediente) is None:
        return False
    return usuario.tipo_unidad == TipoUnidad.DIRECCION and usuario.unidad.programas.filter(pk=expediente.programa.pk).exists()


@registra_usuario
def evaluar_periodo(usuario, expediente, periodo, resultado, motivo="", momento=None):
    """«Cumple» o «no cumple» (con su motivo) de un Guardabosque en un periodo con reporte revisado por la Delegación.
    Se puede cambiar mientras la evaluación del periodo no se envía al CASPEG."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    exigir_acceso(usuario, expediente)
    exigir_programa(usuario, expediente)
    if config(expediente) is None:
        raise ValidationError(f"{expediente.programa.nombre} no evalúa reportes mensuales.")
    p = next((p for p in periodos(expediente) if p["clave"] == periodo), None)
    if p is None:
        raise ValidationError("Ese periodo no lo reporta este Guardabosque (se reporta desde el mes de la firma).")
    if resultado == ResultadoEvaluacion.NO_ENTREGO:
        raise ValidationError("«No entregó» lo pone el sistema cuando termina el periodo sin reporte.")
    if resultado not in (ResultadoEvaluacion.CUMPLE, ResultadoEvaluacion.NO_CUMPLE):
        raise ValidationError("Indique si cumple o no cumple.")
    motivo = (motivo or "").strip()
    if resultado == ResultadoEvaluacion.NO_CUMPLE and not motivo:
        raise ValidationError("Escriba el motivo por el que no cumple.")
    s = situacion(expediente, p)
    if s["envio"] is not None:
        raise ValidationError("La evaluación del periodo ya se envió al CASPEG: no se cambia.")
    if s["reporte"] is None:
        raise ValidationError(f"No hay reporte de {p['nombre']}: queda como «no entregó» al terminar el periodo; no se evalúa.")
    if s["revision"] is None:
        raise ValidationError("La Delegación todavía no revisa el reporte de este periodo.")
    if s["revision"].resultado == ResultadoRevision.DEVUELTO:
        raise ValidationError("El reporte se devolvió para corregir: se evalúa cuando el Guardabosque lo envíe de nuevo.")
    ahora = momento or timezone.now()
    with transaction.atomic():
        e, _ = EvaluacionPeriodo.objects.update_or_create(
            expediente=expediente, periodo=periodo,
            defaults=dict(nombre_periodo=p["nombre"], resultado=resultado, motivo=motivo, comprobacion=s["reporte"],
                          automatica=False, evaluada_por=usuario, unidad=usuario.unidad, evaluada_en=ahora))
        Evento.registrar(expediente, usuario, "reporte_evaluado",
                         f"Evaluación de {p['nombre']}: {e.get_resultado_display().lower()}"
                         + (f" ({motivo})" if motivo else "") + f" por {usuario.unidad.nombre}.",
                         datos={"evaluacion": e.pk, "periodo": periodo})
    return e


@registra_usuario
def enviar_evaluacion(usuario, ejercicio, periodo, momento=None, expedientes=None):
    """Envía al CASPEG la evaluación del periodo con fecha, hora y acuse. Pone «no entregó» a quien no tiene reporte (o lo
    tiene devuelto sin corregir) y no se envía mientras haya reportes por revisar o por evaluar. Lo ya enviado no se vuelve a
    enviar. ``expedientes`` (solo servicios, pruebas y demostración) limita el envío a esos Guardabosques."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    if not usuario.unidad.programas.filter(pk=ejercicio.programa_id).exists():
        raise PermissionDenied("Su Dirección no es Instancia Ejecutora de este programa.")
    if ejercicio.programa.clave not in datos_reportes()["programas"]:
        raise ValidationError(f"{ejercicio.programa.nombre} no evalúa reportes mensuales.")
    p = periodo_del_ejercicio(ejercicio, periodo)
    if p is None:
        raise ValidationError("Ese no es un periodo de reportes del programa.")
    ahora = momento or timezone.now()
    hoy = timezone.localtime(ahora).date()
    if _fecha(p["fin"]) >= hoy:
        raise ValidationError(f"{p['nombre']} todavía no termina: la evaluación se envía al CASPEG cuando ya se sabe quién "
                              "entregó su reporte.")
    filas = [f for f in tabla_del_periodo(ejercicio, periodo, usuario, hoy) if f["envio"] is None
             and (expedientes is None or f["expediente"].pk in {e.pk for e in expedientes})]
    pendientes = [f for f in filas if f["estado"] in (POR_REVISAR, POR_EVALUAR)]
    if pendientes:
        folios = ", ".join(f["expediente"].folio for f in pendientes[:5]) + ("…" if len(pendientes) > 5 else "")
        raise ValidationError(f"Faltan {len(pendientes)} Guardabosque(s) por revisar o evaluar antes de enviar el periodo: {folios}.")
    if not filas:
        raise ValidationError("No hay evaluaciones por enviar de este periodo.")
    with transaction.atomic():
        envio = EnvioEvaluacion.objects.create(ejercicio=ejercicio, periodo=periodo, nombre_periodo=p["nombre"],
                                               enviado_por=usuario, unidad=usuario.unidad, enviado_en=ahora)
        evaluaciones = []
        for f in filas:
            exp = f["expediente"]
            if f["evaluacion"] is not None:
                e = f["evaluacion"]
            else:
                devuelto = f["estado"] == DEVUELTO
                e = EvaluacionPeriodo.objects.create(
                    expediente=exp, periodo=periodo, nombre_periodo=p["nombre"], resultado=ResultadoEvaluacion.NO_ENTREGO,
                    motivo=("El reporte se devolvió para corregir y no se volvió a enviar." if devuelto
                            else "No hay reporte del periodo."), comprobacion=f["reporte"], automatica=True, evaluada_en=ahora)
            e.envio = envio
            e.save(update_fields=["envio"])
            evaluaciones.append(e)
        envio.cumplen = sum(e.resultado == ResultadoEvaluacion.CUMPLE for e in evaluaciones)
        envio.no_cumplen = sum(e.resultado == ResultadoEvaluacion.NO_CUMPLE for e in evaluaciones)
        envio.no_entregaron = sum(e.resultado == ResultadoEvaluacion.NO_ENTREGO for e in evaluaciones)
        envio.acuse = _acuse(envio, evaluaciones, usuario, ahora)
        envio.save()
        for e in evaluaciones:
            Evento.registrar(e.expediente, usuario, "evaluacion_enviada",
                             f"Evaluación de {p['nombre']} ({e.get_resultado_display().lower()}) enviada al CASPEG para su validación; "
                             f"acuse {envio.acuse.folio}.", acuse=envio.acuse, datos={"evaluacion": e.pk, "envio": envio.pk})
        for e in evaluaciones:
            if e.senalado:
                for funcion in extensiones.AL_REPORTE_INCUMPLIDO:
                    funcion(e)
    return envio


def _acuse(envio, evaluaciones, usuario, ahora):
    cfg = datos_reportes()["programas"][envio.ejercicio.programa.clave]
    renglones = [
        ("Programa", f"{envio.ejercicio.programa.nombre} {envio.ejercicio.anio}"), ("Periodo evaluado", envio.nombre_periodo),
        ("Fecha y hora del envío", f"{timezone.localtime(ahora):%d/%m/%Y %H:%M:%S} h"),
        ("Envía", f"{usuario.get_full_name() or usuario.username}, {usuario.unidad.nombre}"),
        ("Guardabosques", f"{envio.total}: {envio.cumplen} cumplen, {envio.no_cumplen} no cumplen y {envio.no_entregaron} no entregaron"),
        ("Fundamento", cfg["fundamento_validacion"]),
    ]
    detalle = [{"clave": e.expediente.folio, "texto": f"{e.expediente.beneficiaria.nombre}" + (f": {e.motivo}" if e.motivo else ""),
                "estado": e.get_resultado_display()} for e in evaluaciones]
    return emitir_acuse(None, "evaluacion_reportes", f"Evaluación de reportes de {envio.nombre_periodo} para el CASPEG", usuario,
                        renglones, destinatario="CASPEG (Secretaría Técnica)", detalle=detalle,
                        nota="El CASPEG valida la evaluación con un acuerdo de su sesión de seguimiento; quien no cumplió o no "
                             "entregó queda señalado para el seguimiento de incumplimientos.",
                        referencia=f"evaluacion-{envio.ejercicio.programa.clave}-{envio.periodo}",
                        encabezado_detalle=["Solicitud", "Guardabosque y motivo", "Resultado"])


# ----------------------------------------------------------------------------- soporte del pago
def fuente_evaluacion(expediente, numero):
    """Soporte «evaluacion_reportes» de ``pagos.solicitudes.FUENTES``: cada periodo que cubre la ministración, evaluado
    «cumple», enviado al CASPEG y validado por él."""
    cubiertos = periodos_de_ministracion(expediente, numero)
    if config(expediente) is None or not cubiertos:
        return (False, f"Para la ministración {numero} no hay periodos de reportes que evaluar (supuesto: cada ministración "
                       "cubre los meses desde la previa, a partir de la firma).", "", "")
    hoy = timezone.localdate()
    faltas, acuerdos = [], []
    for p in cubiertos:
        s = situacion(expediente, p, hoy)
        nombre = p["nombre"]
        if s["estado"] in (ResultadoEvaluacion.NO_CUMPLE, ResultadoEvaluacion.NO_ENTREGO):
            motivo = s["evaluacion"].motivo if s["evaluacion"] and s["evaluacion"].motivo else ""
            if s["estado"] == ResultadoEvaluacion.NO_ENTREGO and not s["evaluacion"]:
                faltas.append(f"{nombre}: no entregó su reporte (todavía falta enviar la evaluación del periodo al CASPEG); queda "
                              "señalado para el seguimiento de incumplimientos")
            elif s["estado"] == ResultadoEvaluacion.NO_ENTREGO:
                faltas.append(f"{nombre}: no entregó su reporte; queda señalado para el seguimiento de incumplimientos")
            else:
                faltas.append(f"{nombre}: no cumple" + (f" ({motivo})" if motivo else "")
                              + "; queda señalado para el seguimiento de incumplimientos")
        elif s["envio"] is None:
            faltas.append(f"{nombre}: falta la evaluación de la Dirección de Protección Forestal enviada al CASPEG "
                          f"({s['etiqueta'].lower()})")
        elif s["validacion"] is None:
            faltas.append(f"{nombre}: evaluada y enviada al CASPEG el {timezone.localtime(s['envio'].enviado_en):%d/%m/%Y}; "
                          "falta su validación con un acuerdo de seguimiento")
        else:
            acuerdos.append(s["validacion"].numero)
    if faltas:
        return False, "No se puede solicitar con la evaluación de reportes: " + "; ".join(faltas) + ".", "", ""
    nombres = ", ".join(p["nombre"] for p in cubiertos)
    return (True, f"Cumple en {nombres}; evaluación validada por el CASPEG (acuerdo {', '.join(sorted(set(acuerdos)))}).",
            ", ".join(sorted(set(acuerdos))), reverse("ejecucion:reportes"))


def periodos_senalados(expediente):
    """Periodos con evaluación enviada en que no cumplió o no entregó (lo que HU-6.2 atiende)."""
    return list(expediente.evaluaciones_periodo.filter(envio__isnull=False).exclude(resultado=ResultadoEvaluacion.CUMPLE)
                .order_by("periodo"))

