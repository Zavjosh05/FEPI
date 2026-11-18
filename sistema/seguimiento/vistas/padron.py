"""HU-6.3 · Página pública del padrón de personas beneficiarias (sin iniciar sesión), igual que la de resultados de HU-3.1."""
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from nucleo.models import Ejercicio

from .. import cierre

LIMITE_PUBLICO = 300


def indice(request):
    return render(request, "seguimiento/cierre/padron_indice.html", {"publicaciones": cierre.padrones_publicos()})


def _ejercicio_publicado(clave, anio):
    ejercicio = get_object_or_404(Ejercicio.objects.select_related("programa"), programa__clave=clave.upper(), anio=anio)
    publicacion = cierre.padron_publicado(ejercicio)
    if publicacion is None:
        raise Http404("Este programa aún no publica su padrón.")
    return ejercicio, publicacion


def programa(request, clave, anio):
    ejercicio, publicacion = _ejercicio_publicado(clave, anio)
    p = cierre.padron(ejercicio)
    buscar = request.GET.get("folio", "").strip().lower()
    filas = [f for f in p["filas"] if not buscar or buscar in str(f.get("folio", "")).lower()]
    return render(request, "seguimiento/cierre/padron_programa.html", {
        "ejercicio": ejercicio, "publicacion": publicacion, "padron": p, "filas": filas[:LIMITE_PUBLICO],
        "recortadas": max(len(filas) - LIMITE_PUBLICO, 0), "folio": buscar, "ahora": timezone.localtime()})


def archivo_csv(request, clave, anio):
    ejercicio, _ = _ejercicio_publicado(clave, anio)
    respuesta = HttpResponse(cierre.padron_csv(ejercicio), content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="padron_{ejercicio.programa.clave}_{ejercicio.anio}.csv"'
    return respuesta
