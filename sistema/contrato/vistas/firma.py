"""HU-3.3 · Pantallas: contratos por firmar (Delegación), registro de la firma, contratos sin firma en plazo y
liberación del recurso (área responsable), y el contexto de la pestaña «Contrato»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nucleo.models import TipoUnidad

from .. import firma
from ..formularios.firma import FirmaForm, LiberarForm
from ..models import ElementoFormalizacion, FirmaContrato, SinFirma
from .comun import expediente_visible, mensajes_error

TIPOS_QUE_VEN_FIRMAS = (TipoUnidad.DELEGACION, TipoUnidad.DIRECCION, TipoUnidad.JURIDICA)


def _fila(exp, hoy=None):
    programada, liberacion = firma.fechas_de_firma(exp)
    return {"exp": exp, "programada": programada, "liberacion": liberacion,
            "faltan": firma.dias_que_faltan(liberacion, hoy),
            "faltan_programada": firma.dias_que_faltan(programada, hoy), "contrato": getattr(exp, "contrato", None)}


@login_required
def lista(request):
    if request.user.tipo_unidad not in TIPOS_QUE_VEN_FIRMAS and not request.user.is_superuser:
        raise PermissionDenied("La firma de los contratos la atiende la Delegación y la vigila el área responsable.")
    tipo = request.user.tipo_unidad
    por_firmar = [_fila(e) for e in firma.por_firmar(request.user).order_by("fecha_recepcion")]
    # Primero lo que vence antes (sin fecha al final).
    por_firmar.sort(key=lambda f: (f["faltan"] is None, f["faltan"] if f["faltan"] is not None else 0))
    return render(request, "contrato/firma/lista.html", {
        "por_firmar": por_firmar, "es_delegacion": tipo == TipoUnidad.DELEGACION,
        "es_area": tipo == TipoUnidad.DIRECCION,
        "sin_firma": [{"s": s, "form": LiberarForm(prefix=f"s{s.pk}"), "prefijo": f"s{s.pk}"}
                      for s in firma.sin_firma(request.user)],
        "liberados": firma.sin_firma(request.user, liberados=True)[:50],
        "firmados": firma.firmados(request.user)[:100],
    })


@login_required
def firmar(request, folio):
    exp = expediente_visible(request, folio)
    destino = reverse("recepcion:expediente", args=[folio]) + "?pestana=contrato"
    if request.user.tipo_unidad != TipoUnidad.DELEGACION:
        raise PermissionDenied("La firma del contrato la registra la Delegación.")
    puede = exp.estado.clave == "contrato_en_delegacion"
    puntos, formalizacion = firma.puntos_de_verificacion(exp), firma.formalizacion_propia(exp)
    form = FirmaForm(request.POST or None, request.FILES or None, puntos=puntos, elementos=formalizacion["elementos"])
    if request.method == "POST" and form.is_valid():
        try:
            f = firma.registrar_firma(
                request.user, exp, form.cleaned_data["firmado_en"], form.cleaned_data["firmante"],
                form.cleaned_data["firmante_nombre"], form.cleaned_data["archivo"], form.verificadas(),
                form.datos_elementos(), form.cleaned_data["observaciones"])
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, f"Firma registrada ({f.situacion.lower()}), acuse {f.acuse.folio}. "
                                      "El contrato queda firmado.")
            return redirect(destino)
    programada, liberacion = firma.fechas_de_firma(exp)
    return render(request, "contrato/firma/firmar.html", {
        "exp": exp, "form": form, "puede": puede, "contrato": getattr(exp, "contrato", None),
        "programada": programada, "liberacion": liberacion, "formalizacion": formalizacion,
        "faltan": firma.dias_que_faltan(liberacion), "sin_firma": SinFirma.objects.filter(expediente=exp).first(),
    })


@login_required
@require_POST
def liberar(request, folio):
    exp = expediente_visible(request, folio)
    form = LiberarForm(request.POST, prefix=request.POST.get("prefijo", ""))
    if form.is_valid():
        try:
            firma.liberar_recurso(request.user, exp, form.cleaned_data["motivo"])
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, f"Recurso liberado ({exp.folio}). La reasignación a la lista de espera "
                                      "es por acuerdo del Comité (HU-6.1, lista de espera y sustituciones).")
    else:
        messages.error(request, "Indique el motivo de la liberación del recurso.")
    destino = request.POST.get("volver", "")
    return redirect(destino if destino.startswith("/") and not destino.startswith("//") else reverse("contrato:firmas"))


@login_required
def archivo_firmado(request, folio, clave="contrato"):
    exp = expediente_visible(request, folio)
    f = get_object_or_404(FirmaContrato, expediente=exp)
    if clave == "contrato":
        archivo, nombre = f.archivo, f"{f.contrato.folio}_firmado"
    else:
        e = get_object_or_404(ElementoFormalizacion, firma=f, clave=clave)
        archivo, nombre = e.archivo, f"{f.contrato.folio}_{clave}"
    if not archivo:
        raise Http404("No hay archivo.")
    extension = archivo.name.rsplit(".", 1)[-1].lower()
    tipos = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
    return FileResponse(archivo.open("rb"), filename=f"{nombre}.{extension}",
                        as_attachment=request.GET.get("descargar") in ("1", "si", "sí"),
                        content_type=tipos.get(extension, "application/octet-stream"))


# ----------------------------------------------------------------------------- pestaña «Contrato»
def contexto_firma_exp(request, exp):
    tipo = request.user.tipo_unidad
    f = FirmaContrato.objects.filter(expediente=exp).select_related("acuse", "registrada_por").prefetch_related(
        "elementos").first()
    senal = SinFirma.objects.filter(expediente=exp).select_related("liberado_por", "acuse_liberacion").first()
    contrato = getattr(exp, "contrato", None)
    programada = liberacion = None
    if f is None and contrato is not None and contrato.enviado or exp.estado.clave == "sin_firma_en_plazo":
        programada, liberacion = firma.fechas_de_firma(exp)
    return {
        "firma": f, "sin_firma": senal, "fecha_programada": programada, "fecha_liberacion": liberacion,
        "faltan_firma": firma.dias_que_faltan(liberacion) if liberacion else None,
        "puede_firmar": tipo == TipoUnidad.DELEGACION and exp.estado.clave == "contrato_en_delegacion",
        "puede_liberar": tipo == TipoUnidad.DIRECCION and exp.estado.clave == "sin_firma_en_plazo",
        "formalizacion": firma.formalizacion_propia(exp),
        "form_liberar": LiberarForm(prefix="pestana") if tipo == TipoUnidad.DIRECCION else None,
    }
