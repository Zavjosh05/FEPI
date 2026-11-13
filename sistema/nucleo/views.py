import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Acuse, Documento, Estado, Programa, bandeja, expedientes_visibles, puede_ver_expediente


class Entrar(auth_views.LoginView):
    template_name = "nucleo/entrar.html"
    redirect_authenticated_user = True


def salud(request):
    return HttpResponse("ok", content_type="text/plain")


def inicio(request):
    return redirect("nucleo:bandeja")


@login_required
def ver_bandeja(request):
    """Bandeja de la unidad: expedientes cuyo estado le toca atender (con filtros por HTMX)."""
    alcance = request.GET.get("alcance", "bandeja")
    qs = bandeja(request.user) if alcance == "bandeja" else expedientes_visibles(request.user)
    programa = request.GET.get("programa", "")
    estado = request.GET.get("estado", "")
    q = request.GET.get("q", "").strip()
    if programa:
        qs = qs.filter(ejercicio__programa__clave=programa)
    if estado:
        qs = qs.filter(estado__clave=estado)
    if q:
        qs = qs.filter(Q(folio__icontains=q) | Q(predio__nombre__icontains=q) | Q(solicitante__nombre__icontains=q)
                       | Q(predio__municipio__nombre__icontains=q) | Q(predio__folio__icontains=q))
    contexto = {
        "expedientes": qs.order_by("estado__orden", "fecha_recepcion")[:300],
        "total": qs.count(),
        "programas": Programa.objects.filter(ejercicios__expedientes__in=expedientes_visibles(request.user)).distinct(),
        "estados": Estado.objects.all(),
        "filtros": {"programa": programa, "estado": estado, "q": q, "alcance": alcance},
    }
    from .extensiones import PANELES_BANDEJA

    contexto["paneles"] = [p for p in (f(request) for f in PANELES_BANDEJA) if p]
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "tabla-bandeja":
        return render(request, "nucleo/_tabla_bandeja.html", contexto)
    if request.user.unidad is None and not request.user.is_superuser:
        messages.warning(request, "Su usuario no tiene unidad asignada; pida al administrador que la registre.")
    return render(request, "nucleo/bandeja.html", contexto)


def _entregar_archivo(archivo, nombre_descarga):
    ruta = archivo.name
    if settings.USAR_X_ACCEL:
        respuesta = HttpResponse()
        respuesta["X-Accel-Redirect"] = f"/protegido/{ruta}"
        respuesta["Content-Type"] = mimetypes.guess_type(ruta)[0] or "application/octet-stream"
        respuesta["Content-Disposition"] = f'inline; filename="{nombre_descarga}"'
        return respuesta
    return FileResponse(archivo.open("rb"), filename=nombre_descarga, as_attachment=False)


@login_required
def descargar_documento(request, pk):
    doc = get_object_or_404(Documento, pk=pk)
    if not puede_ver_expediente(request.user, doc.expediente):
        raise Http404
    return _entregar_archivo(doc.archivo, Path(doc.archivo.name).name)


@login_required
def descargar_acuse(request, folio):
    acuse = get_object_or_404(Acuse, folio=folio)
    if acuse.expediente_id is None:
        # Acuses de sesiones del Comité: los consulta el personal de PROBOSQUE con unidad asignada.
        permitido = request.user.is_superuser or request.user.unidad_id is not None
    else:
        permitido = puede_ver_expediente(request.user, acuse.expediente)
    if not permitido or not acuse.archivo:
        raise Http404
    return _entregar_archivo(acuse.archivo, f"{acuse.folio}.pdf")
