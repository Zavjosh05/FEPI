"""Pantallas comunes de las sesiones del Comité: lista, alta, detalle, documentos y convocatoria."""
from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from nucleo.models import TipoUnidad
from nucleo.views import _entregar_archivo

from .. import sesiones as servicio
from ..formularios.sesiones import DocumentoSesionForm, SesionForm
from ..models import SesionComite, TipoSesion
from .comun import mensajes_error

CONSULTAN = (TipoUnidad.SECRETARIA_COMITE, TipoUnidad.DIRECCION, TipoUnidad.JURIDICA)


def _consulta(request):
    if request.user.tipo_unidad not in CONSULTAN and not request.user.is_superuser:
        raise PermissionDenied("Las sesiones las consulta el Comité, el área responsable y la Unidad Jurídica.")


def _sesion(request, pk):
    _consulta(request)
    return get_object_or_404(SesionComite.objects.select_related("ejercicio__programa"), pk=pk)


@login_required
def lista(request):
    _consulta(request)
    return render(request, "dictamen/sesiones/lista.html", {
        "sesiones": SesionComite.objects.select_related("ejercicio__programa"),
        "puede_crear": request.user.tipo_unidad == TipoUnidad.SECRETARIA_COMITE,
    })


@login_required
def nueva(request):
    if request.user.tipo_unidad != TipoUnidad.SECRETARIA_COMITE:
        raise PermissionDenied("La Secretaría Técnica prepara las sesiones.")
    form = SesionForm(request.POST or None, initial={"tipo": request.GET.get("tipo", TipoSesion.APROBACION),
                                                     "ejercicio": request.GET.get("ejercicio")})
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        try:
            sesion = servicio.crear_sesion(request.user, d["ejercicio"], d["tipo"], d["fecha_hora"], d["lugar"],
                                           d["orden_del_dia"], d["caracter"])
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, f"Sesión {sesion.numero} creada. Adjunte los documentos y envíe la convocatoria.")
            return redirect("dictamen:sesion", sesion.pk)
    return render(request, "dictamen/sesiones/nueva.html", {"form": form})


@login_required
def detalle(request, pk):
    sesion = _sesion(request, pk)
    es_st = request.user.tipo_unidad == TipoUnidad.SECRETARIA_COMITE
    texto_plazo, limite = servicio.anticipacion_requerida(sesion)
    contexto = {
        "sesion": sesion, "es_st": es_st, "documentos": sesion.documentos.all(),
        "form_documento": DocumentoSesionForm(), "texto_plazo": texto_plazo, "limite_convocatoria": limite,
    }
    # Lo propio de cada tipo de sesión vive en la vista de su historia (HU-2.3 o HU-2.4).
    if sesion.tipo == TipoSesion.APROBACION:
        from .aprobacion import contexto_sesion
    else:
        from .seguimiento import contexto_sesion
    contexto.update(contexto_sesion(request, sesion))
    return render(request, "dictamen/sesiones/detalle.html", contexto)


@login_required
@require_POST
def documento(request, pk):
    sesion = _sesion(request, pk)
    form = DocumentoSesionForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            servicio.agregar_documento(request.user, sesion, form.cleaned_data["archivo"], form.cleaned_data["nombre"])
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, "Documento agregado a la sesión.")
    else:
        messages.error(request, "Elija el archivo del documento.")
    return redirect("dictamen:sesion", pk)


@login_required
def descargar_documento(request, pk, doc):
    sesion = _sesion(request, pk)
    documento = sesion.documentos.filter(pk=doc).first()
    if documento is None:
        raise Http404
    return _entregar_archivo(documento.archivo, Path(documento.archivo.name).name)


@login_required
@require_POST
def convocar(request, pk):
    sesion = _sesion(request, pk)
    try:
        acuse = servicio.enviar_convocatoria(request.user, sesion)
    except (ValidationError, PermissionDenied) as e:
        for m in mensajes_error(e):
            messages.error(request, m)
    else:
        messages.success(request, f"Convocatoria enviada. Acuse {acuse.folio}.")
    return redirect("dictamen:sesion", pk)
