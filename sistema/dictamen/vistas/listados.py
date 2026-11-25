"""Pantallas de Candidatos y de Beneficiarios (dos vistas separadas, con exportación a CSV)."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import render

from nucleo.models import Ejercicio, TipoUnidad, expedientes_visibles

from .. import listados

CONSULTAN = (TipoUnidad.DELEGACION, TipoUnidad.DIRECCION, TipoUnidad.JURIDICA, TipoUnidad.SECRETARIA_COMITE)


def _ejercicio(request):
    if request.user.tipo_unidad not in CONSULTAN and not request.user.is_superuser:
        raise PermissionDenied("Los listados de candidatos y beneficiarios los consultan la Delegación, el área "
                               "responsable, la Unidad Jurídica y el Comité.")
    ejercicios = Ejercicio.objects.filter(reglas_cargadas__isnull=False).select_related("programa")
    ejercicio = ejercicios.filter(pk=request.GET.get("ejercicio") or 0).first() or ejercicios.first()
    return ejercicios, ejercicio


def _csv(contenido, nombre):
    respuesta = HttpResponse(contenido, content_type="text/csv; charset=utf-8")
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre}.csv"'.replace(" ", "_")
    return respuesta


@login_required
def candidatos(request):
    ejercicios, ejercicio = _ejercicio(request)
    situacion = request.GET.get("situacion", "")
    if situacion not in listados.SITUACIONES_CANDIDATO:
        situacion = ""
    visibles = expedientes_visibles(request.user)
    filas = listados.candidatos(ejercicio, visibles, situacion) if ejercicio else []
    if request.GET.get("formato") == "csv":
        return _csv(listados.csv_de(filas, listados.COLUMNAS_CANDIDATOS), f"candidatos_{ejercicio}")
    todas = listados.candidatos(ejercicio, visibles) if ejercicio else []
    conteo = {k: sum(1 for f in todas if f["situacion"] == k) for k in listados.SITUACIONES_CANDIDATO}
    return render(request, "dictamen/listados/candidatos.html", {
        "ejercicios": ejercicios, "ejercicio": ejercicio, "filas": filas, "situacion": situacion,
        "situaciones": [(k, v[1], conteo[k]) for k, v in listados.SITUACIONES_CANDIDATO.items()], "total": len(todas),
    })


@login_required
def beneficiarios(request):
    ejercicios, ejercicio = _ejercicio(request)
    vigentes, bajas = listados.beneficiarios(ejercicio, expedientes_visibles(request.user)) if ejercicio else ([], [])
    if request.GET.get("formato") == "csv":
        return _csv(listados.csv_de(vigentes, listados.COLUMNAS_BENEFICIARIOS), f"beneficiarios_{ejercicio}")
    return render(request, "dictamen/listados/beneficiarios.html", {
        "ejercicios": ejercicios, "ejercicio": ejercicio, "vigentes": vigentes, "bajas": bajas,
        "totales": listados.totales(vigentes),
    })
