"""HU-4.2 · Pantallas: resultado de la verificación en campo con sus incidencias, devolución de la comprobación,
conclusión de las actividades y contexto de la pestaña «Ejecución»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from nucleo import plazos
from nucleo.models import TipoUnidad

from .. import verificacion
from ..formularios.verificacion import DevolucionForm, VerificacionForm
from ..models import Incidencia, Verificacion
from .comun import expediente_visible, mensajes_error, responder_archivo


def _destino(folio):
    return reverse("recepcion:expediente", args=[folio]) + "?pestana=ejecucion"


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


def _form(exp, *args):
    cfg = verificacion.config(exp) or {}
    return VerificacionForm(*args, documentos=verificacion.documentos(exp), incidencias=verificacion.tipos_incidencia(exp),
                            superficie=bool(cfg.get("superficie")), sobrevivencia=bool(cfg.get("sobrevivencia")))


@login_required
@require_POST
def registrar(request, folio):
    exp = expediente_visible(request, folio)
    form = _form(exp, request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Revise los datos de la verificación.")
        return redirect(_destino(folio))
    d = form.cleaned_data
    try:
        v = verificacion.registrar_verificacion(
            request.user, exp, d["tipo_documento"], d.get("archivo"), d.get("fecha_visita"), d.get("superficie_verificada"),
            d.get("sobrevivencia"), d.get("observaciones", ""), form.incidencias())
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Verificación registrada ({v.get_resultado_display().lower()}, entrega {v.situacion_plazo}) "
                                  f"con el acuse {v.acuse.folio}.")
    return redirect(_destino(folio))


@login_required
@require_POST
def devolver(request, folio):
    exp = expediente_visible(request, folio)
    form = DevolucionForm(request.POST)
    try:
        verificacion.devolver_comprobacion(request.user, exp, form.data.get("motivo", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, "Comprobación devuelta; la Delegación notifica las observaciones a la persona.")
    return redirect(_destino(folio))


@login_required
@require_POST
def concluir(request, folio):
    exp = expediente_visible(request, folio)
    try:
        verificacion.dar_por_concluida(request.user, exp)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, "Actividades concluidas.")
    return redirect(_destino(folio))


@login_required
def archivo(request, pk):
    v = Verificacion.objects.filter(pk=pk).select_related("expediente").first()
    if v is None:
        raise Http404
    expediente_visible(request, v.expediente.folio)
    return responder_archivo(request, v.archivo)


@login_required
def archivo_incidencia(request, pk):
    i = Incidencia.objects.filter(pk=pk).select_related("expediente").first()
    if i is None:
        raise Http404
    expediente_visible(request, i.expediente.folio)
    return responder_archivo(request, i.archivo)


def contexto_verificacion_exp(request, exp):
    cfg = verificacion.config(exp)
    if cfg is None:
        return {"verificacion_aplica": False}
    puede, motivo = verificacion.puede_registrar(request.user, exp)
    es_area = request.user.tipo_unidad == TipoUnidad.DIRECCION
    lista = list(exp.verificaciones.select_related("acuse", "registrada_por", "unidad").prefetch_related("incidencias"))
    return {
        "verificacion_aplica": True, "verificaciones": lista, "config_verificacion": cfg,
        "puede_verificar": puede, "motivo_sin_verificar": motivo, "form_verificacion": _form(exp) if puede else None,
        "sobrevivencia_minima": verificacion.sobrevivencia_minima(exp),
        "puede_devolver": es_area and exp.estado.clave == "comprobacion_enviada", "form_devolucion": DevolucionForm(),
        "puede_concluir": es_area and exp.estado.clave == "verificada" and lista
                          and lista[0].resultado != "incumplimiento" and not verificacion.ministraciones_pendientes(exp),
        "plazo_entrega": plazos.vencimiento(exp, "entrega_comprobacion"),
    }
