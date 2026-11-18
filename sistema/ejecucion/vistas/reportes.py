"""HU-4.3 · Pantallas de la evaluación de reportes: bandeja de la Delegación, tabla por periodo de la Dirección de Protección
Forestal con su envío al CASPEG, lo enviado al CASPEG y el contexto de la pestaña «Ejecución» del expediente."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from nucleo.models import Ejercicio, TipoUnidad

from .. import reportes
from ..formularios.reportes import EvaluacionForm, RevisionForm
from ..models import Comprobacion, EnvioEvaluacion
from .comun import expediente_visible, mensajes_error

TIPOS_QUE_VEN = (TipoUnidad.DELEGACION, TipoUnidad.DIRECCION, TipoUnidad.SECRETARIA_COMITE)


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


def _siguiente(request, por_omision):
    siguiente = request.POST.get("siguiente", "")
    return siguiente if siguiente and url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}) else por_omision


def _pagina(ejercicio=None, periodo=None):
    url = reverse("ejecucion:reportes")
    return url + (f"?ejercicio={ejercicio}" if ejercicio else "") + (f"&periodo={periodo}" if ejercicio and periodo else "")


def _pestana(folio):
    return reverse("recepcion:expediente", args=[folio]) + "?pestana=ejecucion"


@login_required
def pagina(request):
    tipo = request.user.tipo_unidad
    if tipo not in TIPOS_QUE_VEN and not request.user.is_superuser:
        raise PermissionDenied("La evaluación de reportes la ven la Delegación, la Dirección de Protección Forestal y el CASPEG.")
    ejercicios = list(reportes.ejercicios_que_evaluan(request.user))
    ejercicio = next((e for e in ejercicios if str(e.pk) == request.GET.get("ejercicio")), None) or (ejercicios[0] if ejercicios else None)
    contexto = {"ejercicios": ejercicios, "ejercicio": ejercicio, "tipo": tipo, "es_delegacion": tipo == TipoUnidad.DELEGACION,
                "es_direccion": tipo == TipoUnidad.DIRECCION, "es_comite": tipo == TipoUnidad.SECRETARIA_COMITE,
                "datos": reportes.datos_reportes(), "form_revision": RevisionForm(), "form_evaluacion": EvaluacionForm()}
    if ejercicio is None:
        return render(request, "ejecucion/reportes/pagina.html", contexto)
    cfg = reportes.datos_reportes()["programas"][ejercicio.programa.clave]
    hoy = timezone.localdate()
    todos = [p for p in (ejercicio.datos or {}).get("periodos_reportes", []) if isinstance(p, dict) and reportes._fecha(p["inicio"]) <= hoy]
    clave = request.GET.get("periodo")
    periodo = next((p for p in todos if p["clave"] == clave), None)
    if periodo is None and todos:
        terminados = [p for p in todos if reportes._fecha(p["fin"]) < hoy]
        periodo = (terminados or todos)[-1]
    contexto.update({"cfg": cfg, "periodos": todos, "periodo": periodo,
                     "periodo_terminado": bool(periodo and reportes._fecha(periodo["fin"]) < hoy)})
    if periodo is not None and tipo != TipoUnidad.SECRETARIA_COMITE:
        filas = reportes.tabla_del_periodo(ejercicio, periodo["clave"], request.user, hoy)
        sin_enviar = [f for f in filas if f["envio"] is None]
        pendientes = [f for f in sin_enviar if f["estado"] in (reportes.POR_REVISAR, reportes.POR_EVALUAR)]
        contexto.update({"filas": filas, "resumen": reportes.resumen(filas), "pendientes": pendientes, "por_enviar": len(sin_enviar),
                         "puede_enviar": tipo == TipoUnidad.DIRECCION and contexto["periodo_terminado"] and bool(sin_enviar)
                                         and not pendientes})
    if periodo is not None and tipo != TipoUnidad.SECRETARIA_COMITE:
        columnas = [p for p in todos if p["clave"]]
        contexto["columnas"] = columnas
        contexto["matriz"] = [{"expediente": exp, "celdas": [reportes.situacion(exp, p, hoy) if p["clave"] in {x["clave"] for x in reportes.periodos(exp)} else None
                                                              for p in columnas]} for exp in reportes.guardabosques(ejercicio, request.user)]
    if tipo == TipoUnidad.DELEGACION:
        contexto["por_revisar"] = list(reportes.por_revisar(request.user)[:200])
    if tipo in (TipoUnidad.DIRECCION, TipoUnidad.SECRETARIA_COMITE) or request.user.is_superuser:
        envios = list(EnvioEvaluacion.objects.filter(ejercicio=ejercicio).select_related("acuse", "enviado_por")
                      .prefetch_related("evaluaciones__expediente__persona_beneficiaria"))
        por_validar = {envio.pk: lista for envio, lista in reportes.envios_por_validar(ejercicio)}
        contexto["envios"] = [{"envio": e, "por_validar": por_validar.get(e.pk, []), "evaluaciones": list(e.evaluaciones.all())}
                              for e in envios]
    return render(request, "ejecucion/reportes/pagina.html", contexto)


@login_required
@require_POST
def revisar(request, pk):
    c = get_object_or_404(Comprobacion.objects.select_related("expediente"), pk=pk)
    expediente_visible(request, c.expediente.folio)
    form = RevisionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Indique el resultado de la revisión.")
    else:
        try:
            r = reportes.revisar(request.user, c, form.cleaned_data["resultado"], form.cleaned_data["observaciones"])
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
        else:
            messages.success(request, f"{c.expediente.folio} · {c.nombre}{' ' + c.periodo if c.periodo else ''}: "
                                      f"{r.get_resultado_display().lower()}"
                                      + (" y notificado a la persona para que lo corrija." if r.resultado == "devuelto" else "."))
    return redirect(_siguiente(request, _pestana(c.expediente.folio)))


@login_required
@require_POST
def evaluar(request, folio, periodo):
    exp = expediente_visible(request, folio)
    form = EvaluacionForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Indique si cumple o no cumple.")
    else:
        try:
            e = reportes.evaluar_periodo(request.user, exp, periodo, form.cleaned_data["resultado"], form.cleaned_data["motivo"])
        except (ValidationError, PermissionDenied) as err:
            _errores(request, err)
        else:
            messages.success(request, f"{exp.folio} · {e.nombre_periodo}: {e.get_resultado_display().lower()}.")
    return redirect(_siguiente(request, _pestana(folio)))


@login_required
@require_POST
def enviar(request, ejercicio, periodo):
    ej = get_object_or_404(Ejercicio.objects.select_related("programa"), pk=ejercicio)
    try:
        envio = reportes.enviar_evaluacion(request.user, ej, periodo)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Evaluación de {envio.nombre_periodo} enviada al CASPEG el "
                                  f"{timezone.localtime(envio.enviado_en):%d/%m/%Y a las %H:%M} h, con el acuse {envio.acuse.folio} "
                                  f"({envio.cumplen} cumplen, {envio.no_cumplen} no cumplen, {envio.no_entregaron} no entregaron).")
    return redirect(_pagina(ejercicio, periodo))


def contexto_reportes_exp(request, exp):
    cfg = reportes.config(exp)
    if cfg is None:
        return {"reportes_aplica": False}
    usuario = request.user
    es_delegacion = usuario.tipo_unidad == TipoUnidad.DELEGACION and usuario.unidad_id == exp.delegacion_id
    pendientes = list(reportes.por_revisar(usuario).filter(expediente=exp)) if es_delegacion else []
    return {
        "reportes_aplica": True, "cfg_reportes": cfg, "historial_reportes": reportes.historial(exp),
        "revisiones_pendientes": pendientes, "puede_evaluar_reportes": reportes.puede_evaluar(usuario, exp),
        "form_revision": RevisionForm(), "form_evaluacion": EvaluacionForm(),
        "senalados_reportes": reportes.periodos_senalados(exp), "pagina_reportes": reverse("ejecucion:reportes"),
    }
