"""HU-4.1 · Pantallas del personal: la Delegación registra la entrega recibida en ventanilla (mismo servicio que el portal)
y revisa lo que llegó por el portal; lista de comprobaciones y contexto de la pestaña «Ejecución»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from nucleo.models import TipoUnidad

from .. import comprobaciones
from ..formularios.comprobaciones import EnvioForm
from ..models import Comprobacion
from .comun import expediente_visible, mensajes_error, responder_archivo

TIPOS_QUE_VEN = (TipoUnidad.DELEGACION, TipoUnidad.DIRECCION, TipoUnidad.JURIDICA)


def _destino(folio):
    return reverse("recepcion:expediente", args=[folio]) + "?pestana=ejecucion"


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


@login_required
def lista(request):
    tipo = request.user.tipo_unidad
    if tipo not in TIPOS_QUE_VEN and not request.user.is_superuser:
        raise PermissionDenied("Las comprobaciones las ven la Delegación, el área responsable y la Unidad Jurídica.")
    todas = list(comprobaciones.comprobaciones_visibles(request.user).order_by("-enviada_en", "-id")[:300])
    return render(request, "ejecucion/comprobaciones/lista.html", {
        "por_revisar": [c for c in todas if c.por_portal and c.revisada_en is None] if tipo == TipoUnidad.DELEGACION else [],
        "todas": todas, "es_delegacion": tipo == TipoUnidad.DELEGACION,
    })


@login_required
@require_POST
def registrar(request, folio):
    exp = expediente_visible(request, folio)
    form = EnvioForm(request.POST, request.FILES, tipos=comprobaciones.tipos_de_envio(exp),
                     periodos=comprobaciones.periodos(exp), ventanilla=True)
    if not form.is_valid():
        messages.error(request, "Revise los datos de la comprobación.")
        return redirect(_destino(folio))
    d = form.cleaned_data
    try:
        c = comprobaciones.registrar_envio(request.user, exp, d["tipo"], d.get("archivo"), d.get("descripcion", ""),
                                           d.get("fecha_hecho"), d.get("periodo", ""), d.get("persona_entrega", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"{c.nombre}: entrega registrada con el acuse {c.acuse.folio}"
                                  + (f" ({c.situacion_plazo})." if c.en_plazo is not None else "."))
    return redirect(_destino(folio))


@login_required
@require_POST
def revisada(request, pk):
    c = Comprobacion.objects.filter(pk=pk).select_related("expediente").first()
    if c is None:
        raise Http404
    expediente_visible(request, c.expediente.folio)
    try:
        comprobaciones.marcar_revisada(request.user, c)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"{c.nombre}: revisado.")
    siguiente = request.POST.get("siguiente", "")
    if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        siguiente = ""
    return redirect(siguiente or _destino(c.expediente.folio))


@login_required
def archivo(request, pk):
    c = Comprobacion.objects.filter(pk=pk).select_related("expediente").first()
    if c is None or not c.archivo:
        raise Http404("No existe el documento.")
    expediente_visible(request, c.expediente.folio)
    return responder_archivo(request, c.archivo)


def contexto_comprobaciones_exp(request, exp):
    es_delegacion = request.user.tipo_unidad == TipoUnidad.DELEGACION and request.user.unidad_id == exp.delegacion_id
    puede, motivo = comprobaciones.puede_enviar(exp)
    tipos = comprobaciones.tipos_de_envio(exp)
    return {
        "comprobaciones": list(exp.comprobaciones.select_related("acuse", "enviada_por", "recibida_por", "revisada_por")),
        "tipos_envio": tipos, "puede_registrar": es_delegacion and puede and bool(tipos), "motivo_sin_envio": motivo,
        "es_delegacion_exp": es_delegacion,
        "form_envio": EnvioForm(tipos=tipos, periodos=comprobaciones.periodos(exp), ventanilla=True),
    }
