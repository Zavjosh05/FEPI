import mimetypes
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import Acuse, Documento, Estado, Programa, bandeja, expedientes_visibles, puede_ver_expediente


class FormularioEntrarPersonal(AuthenticationForm):
    """La entrada del personal no admite cuentas del portal: las personas beneficiarias entran por /portal/."""

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if hasattr(user, "cuenta_externa"):
            raise ValidationError("Las personas beneficiarias entran por el portal.", code="externo")


class Entrar(auth_views.LoginView):
    template_name = "nucleo/entrar.html"
    redirect_authenticated_user = True
    authentication_form = FormularioEntrarPersonal


def salud(request):
    return HttpResponse("ok", content_type="text/plain")


def inicio(request):
    return redirect("nucleo:bandeja")


@login_required
def ver_bandeja(request):
    """Bandeja de la unidad: expedientes cuyo estado le toca atender (con filtros por HTMX)."""
    alcance = request.GET.get("alcance", "bandeja")
    programa = request.GET.get("programa", "")
    estado = request.GET.get("estado", "")
    q = request.GET.get("q", "").strip()

    def filtrar(qs):
        if programa:
            qs = qs.filter(ejercicio__programa__clave=programa)
        if estado:
            qs = qs.filter(estado__clave=estado)
        if q:
            qs = qs.filter(Q(folio__icontains=q) | Q(predio__nombre__icontains=q) | Q(solicitante__nombre__icontains=q)
                           | Q(predio__municipio__nombre__icontains=q) | Q(predio__folio__icontains=q))
        return qs

    por_atender, todos = filtrar(bandeja(request.user)), filtrar(expedientes_visibles(request.user))
    qs = por_atender if alcance == "bandeja" else todos
    contexto = {
        "expedientes": qs.order_by("estado__orden", "fecha_recepcion")[:300],
        "total": qs.count(),
        "total_por_atender": por_atender.count(),
        "total_todos": todos.count(),
        "programas": Programa.objects.filter(ejercicios__expedientes__in=expedientes_visibles(request.user)).distinct(),
        "estados": Estado.objects.all(),
        "filtros": {"programa": programa, "estado": estado, "q": q, "alcance": alcance},
    }
    from .extensiones import PANELES_BANDEJA

    contexto["paneles"] = [p for p in (f(request) for f in PANELES_BANDEJA) if p]
    if request.headers.get("HX-Request") and request.headers.get("HX-Target") == "tabla-bandeja":
        return render(request, "nucleo/_tabla_bandeja.html", {**contexto, "oob": True})
    if request.user.unidad is None and not request.user.is_superuser:
        messages.warning(request, "Su usuario no tiene unidad asignada; pida al administrador que la registre.")
    return render(request, "nucleo/bandeja.html", contexto)


def _entregar_archivo(archivo, nombre_descarga, adjunto=False):
    """Entrega el archivo (vía Nginx en producción). ``adjunto``: se descarga en vez de abrirse (P-18)."""
    ruta = archivo.name
    if settings.USAR_X_ACCEL:
        respuesta = HttpResponse()
        respuesta["X-Accel-Redirect"] = f"/protegido/{ruta}"
        respuesta["Content-Type"] = mimetypes.guess_type(ruta)[0] or "application/octet-stream"
        respuesta["Content-Disposition"] = f'{"attachment" if adjunto else "inline"}; filename="{nombre_descarga}"'
        return respuesta
    return FileResponse(archivo.open("rb"), filename=nombre_descarga, as_attachment=adjunto)


def _pide_descarga(request):
    return request.GET.get("descargar") in ("1", "si", "sí")


@login_required
def descargar_documento(request, pk):
    doc = get_object_or_404(Documento, pk=pk)
    if not puede_ver_expediente(request.user, doc.expediente):
        raise Http404
    return _entregar_archivo(doc.archivo, Path(doc.archivo.name).name, adjunto=_pide_descarga(request))


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
    return _entregar_archivo(acuse.archivo, f"{acuse.folio}.pdf", adjunto=_pide_descarga(request))
