"""HU-2.1 · Pantallas del dictamen técnico y del listado preliminar."""
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse

from nucleo.models import Ejercicio, TipoUnidad, expedientes_visibles
from recepcion.models import Poligono

from .. import tecnico
from ..formularios.tecnico import DictamenTecnicoForm
from .comun import expediente_visible, mensajes_error


@login_required
def dictaminar(request, folio):
    exp = expediente_visible(request, folio)
    destino = reverse("recepcion:expediente", args=[folio]) + "?pestana=dictamenes"
    if request.user.tipo_unidad != TipoUnidad.DIRECCION:
        raise PermissionDenied("El dictamen técnico lo emite el área responsable del programa.")
    if hasattr(exp, "dictamen_tecnico") or exp.estado.clave != "validada":
        messages.info(request, "No hay dictamen técnico pendiente para este expediente.")
        return redirect(destino)
    items = tecnico.lista_verificacion(exp.ejercicio)
    form = DictamenTecnicoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        verificacion = {i["clave"]: {"respuesta": request.POST.get(f"v-{i['clave']}", ""),
                                     "nota": request.POST.get(f"n-{i['clave']}", "")} for i in items}
        try:
            d = tecnico.dictaminar(request.user, exp, form.cleaned_data["resultado"], form.cleaned_data["motivo"],
                                   verificacion, form.cleaned_data.get("superficie_factible_ha"),
                                   exigir_revision=True)
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, f"Dictamen técnico {d.get_resultado_display().lower()} registrado (acuse {d.acuse.folio}).")
            return redirect(destino)
    analisis = tecnico.analisis_cartografico(exp)
    return render(request, "dictamen/tecnico/dictaminar.html", {
        "exp": exp, "form": form, "items": items, "analisis": analisis,
        "plazo": tecnico.situacion_plazo(exp), "texto_situacion": tecnico.TEXTO_SITUACION,
        "respuestas": tecnico.RESPUESTAS,
    })


@login_required
def mapa(request, folio):
    exp = expediente_visible(request, folio)
    vigente = exp.poligonos.filter(vigente=True).first()
    elementos = []
    if vigente:
        elementos.append({"type": "Feature", "geometry": json.loads(vigente.geom.geojson),
                          "properties": {"tipo": "vigente", "folio": exp.folio, "superficie_ha": float(vigente.superficie_ha)}})
        for otro in (Poligono.objects.filter(vigente=True, expediente__ejercicio=exp.ejercicio, geom__intersects=vigente.geom)
                     .exclude(expediente=exp).select_related("expediente")):
            elementos.append({"type": "Feature", "geometry": json.loads(otro.geom.geojson),
                              "properties": {"tipo": "traslape", "folio": otro.expediente.folio,
                                             "superficie_ha": float(otro.superficie_ha)}})
    municipio = exp.predio.municipio
    return JsonResponse({
        "poligonos": {"type": "FeatureCollection", "features": elementos},
        "municipio": {"type": "Feature", "geometry": json.loads(municipio.geom.geojson), "properties": {"nombre": municipio.nombre}},
    })


@login_required
def listado(request):
    if request.user.tipo_unidad not in (TipoUnidad.DIRECCION, TipoUnidad.JURIDICA, TipoUnidad.SECRETARIA_COMITE) \
            and not request.user.is_superuser:
        raise PermissionDenied("El listado preliminar es del área responsable, la Unidad Jurídica y el Comité.")
    ejercicios = Ejercicio.objects.filter(reglas_cargadas__isnull=False).select_related("programa")
    ejercicio = ejercicios.filter(pk=request.GET.get("ejercicio") or 0).first() or ejercicios.first()
    filas = tecnico.listado_preliminar(ejercicio, expedientes_visibles(request.user)) if ejercicio else []
    if request.GET.get("formato") == "csv":
        respuesta = HttpResponse(tecnico.listado_csv(filas), content_type="text/csv; charset=utf-8")
        respuesta["Content-Disposition"] = f'attachment; filename="listado_preliminar_{ejercicio}.csv"'.replace(" ", "_")
        return respuesta
    resumen = {k: sum(1 for f in filas if f["resultado"] == k) for k in ("factible", "no_factible", "pendiente")}
    return render(request, "dictamen/tecnico/listado.html",
                  {"filas": filas, "ejercicios": ejercicios, "ejercicio": ejercicio, "resumen": resumen})
