"""HU-3.4 · Pantallas: vales de planta (Delegación y área responsable), bandeja del vivero con la validación y las
salidas, el vale en PDF y el contexto de la pestaña «Contrato»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from nucleo.models import TipoUnidad

from .. import planta
from ..formularios.planta import SalidaForm, ValeForm
from ..models import ValePlanta
from .comun import expediente_visible, mensajes_error

TIPOS_QUE_VEN_VALES = (TipoUnidad.DELEGACION, TipoUnidad.DIRECCION, TipoUnidad.JURIDICA, TipoUnidad.VIVERO)


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


def _vale(request, folio):
    return get_object_or_404(planta.vales_visibles(request.user), folio=folio)


@login_required
def lista(request):
    tipo = request.user.tipo_unidad
    if tipo not in TIPOS_QUE_VEN_VALES and not request.user.is_superuser:
        raise PermissionDenied("Los vales de planta los entrega la Delegación y los surte el vivero.")
    if tipo == TipoUnidad.VIVERO:
        return redirect("contrato:vivero")
    vales = list(planta.vales_visibles(request.user))
    return render(request, "contrato/planta/lista.html", {
        "por_entregar": planta.por_entregar_vale(request.user) if tipo == TipoUnidad.DELEGACION else [],
        "por_reponer": [v for v in vales if v.situacion() == "vencido"],
        "vales": vales[:200], "es_delegacion": tipo == TipoUnidad.DELEGACION,
    })


@login_required
def emitir(request, folio):
    exp = expediente_visible(request, folio)
    if request.user.tipo_unidad != TipoUnidad.DELEGACION:
        raise PermissionDenied("El Vale de Planta lo entrega la Delegación.")
    destino = reverse("recepcion:expediente", args=[folio]) + "?pestana=contrato"
    situacion = planta.situacion_para_emitir(exp)
    form = ValeForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            vale = planta.emitir_vale(
                request.user, exp, form.cleaned_data["vivero"], form.renglones(), form.cleaned_data["carta_compromiso"],
                form.cleaned_data["motivo_ajuste"], form.cleaned_data["planta_disponible"],
                form.cleaned_data["fecha_hora"])
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
        else:
            messages.success(request, f"Vale {vale.folio} entregado (acuse {vale.acuse.folio}); vigente hasta el "
                                      f"{vale.vence_el:%d/%m/%Y}." if vale.vence_el else f"Vale {vale.folio} entregado.")
            return redirect("contrato:vale", vale.folio)
    prop = planta.propuesta(exp)
    cfg = planta.config_vale(exp) or {}
    return render(request, "contrato/planta/emitir.html", {
        "exp": exp, "form": form, "situacion": situacion, "propuesta": prop, "cfg": cfg, "destino": destino,
        "vigencia": planta.plazos.vencimiento(exp, "recoger_planta", fecha_evento=timezone.now()),
        "anticipado": exp.estado.clave in planta.ESTADOS_ANTICIPADOS,
        "reposicion": situacion["tipo"] == "reposicion", "repone": situacion["repone"],
        "sin_catalogo": not form.especies or not form.fields["vivero"].queryset.exists(),
    })


@login_required
def detalle(request, folio):
    vale = _vale(request, folio)
    tipo = request.user.tipo_unidad
    exp = vale.expediente
    situacion = vale.situacion()
    cfg = planta.config_vale(exp) or {}
    return render(request, "contrato/planta/vale.html", {
        "vale": vale, "exp": exp, "situacion": situacion, "salidas": vale.salidas.select_related("renglon__especie", "acuse"),
        "es_vivero": tipo == TipoUnidad.VIVERO, "form_salida": SalidaForm(vale=vale),
        "puede_salida": tipo == TipoUnidad.VIVERO and situacion == "vigente" and vale.total_pendiente > 0,
        "puede_reponer": tipo == TipoUnidad.DELEGACION and situacion == "vencido" and cfg.get("reposicion"),
        "sin_reposicion": situacion == "vencido" and not cfg.get("reposicion"), "cfg": cfg,
    })


@login_required
@require_POST
def salida(request, folio):
    vale = _vale(request, folio)
    form = SalidaForm(request.POST, vale=vale)
    if form.is_valid():
        try:
            s = planta.registrar_salida(request.user, vale, form.cleaned_data["especie"], form.cleaned_data["cantidad"],
                                        form.cleaned_data["fecha_hora"], form.cleaned_data["observaciones"])
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
        else:
            msg = f"Salida registrada: {s.especie.nombre} × {s.cantidad} (acuse {s.acuse.folio})."
            vale.expediente.refresh_from_db()
            if vale.expediente.estado.clave == "planta_entregada":      # P-28: avisa el nuevo estado al surtirse
                msg += f" El vale quedó surtido y la solicitud pasó a «{vale.expediente.estado.nombre}»."
            messages.success(request, msg)
    else:
        messages.error(request, "Indique la especie y una cantidad mayor que cero.")
    return redirect("contrato:vale", vale.folio)


@login_required
def vivero(request):
    if request.user.tipo_unidad != TipoUnidad.VIVERO and not request.user.is_superuser:
        raise PermissionDenied("Esta bandeja es del personal del vivero.")
    folio = (request.GET.get("folio") or "").strip().upper()
    encontrado = mensaje = None
    if folio:
        encontrado = planta.vales_visibles(request.user).filter(folio=folio).first()
        if encontrado is None:
            mensaje = f"No hay un vale {folio} para este vivero."
        else:
            try:
                if request.user.tipo_unidad == TipoUnidad.VIVERO:
                    planta.validar_vale(request.user, encontrado)
            except ValidationError as e:
                mensaje = " ".join(mensajes_error(e))
            else:
                return redirect("contrato:vale", encontrado.folio)
    vales = list(planta.vales_visibles(request.user))
    return render(request, "contrato/planta/vivero.html", {
        "por_surtir": [v for v in vales if v.vigente() and v.total_pendiente > 0],
        "otros": [v for v in vales if not (v.vigente() and v.total_pendiente > 0)][:100],
        "folio": folio, "mensaje": mensaje, "encontrado": encontrado,
    })


@login_required
def pdf(request, folio):
    vale = _vale(request, folio)
    if not vale.archivo:
        raise Http404("El vale no tiene PDF.")
    return FileResponse(vale.archivo.open("rb"), filename=f"{vale.folio}.pdf",
                        as_attachment=request.GET.get("descargar") in ("1", "si", "sí"), content_type="application/pdf")


@login_required
def carta(request, folio):
    vale = _vale(request, folio)
    if not vale.carta_compromiso:
        raise Http404("El vale no tiene carta compromiso.")
    extension = vale.carta_compromiso.name.rsplit(".", 1)[-1].lower()
    tipos = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
    return FileResponse(vale.carta_compromiso.open("rb"), filename=f"{vale.folio}_carta_compromiso.{extension}",
                        content_type=tipos.get(extension, "application/octet-stream"))


# ----------------------------------------------------------------------------- pestaña «Contrato»
def contexto_planta_exp(request, exp):
    tipo = request.user.tipo_unidad
    aplica, razon = planta.aplica(exp)
    vales = list(ValePlanta.objects.filter(expediente=exp).select_related("vivero", "acuse", "repone").prefetch_related(
        "renglones__especie", "renglones__salidas", "reposiciones", "salidas__renglon__especie", "salidas__acuse"))
    if tipo == TipoUnidad.VIVERO:
        vales = [v for v in vales if v.vivero.unidad_id == request.user.unidad_id]
    situacion = planta.situacion_para_emitir(exp) if aplica else {"puede": False, "motivo": razon, "tipo": "", "repone": None}
    return {
        "aplica_vale": aplica, "razon_sin_vale": razon, "vales": [{"v": v, "situacion": v.situacion()} for v in vales],
        "puede_emitir_vale": tipo == TipoUnidad.DELEGACION and situacion["puede"],
        "tipo_emision": situacion["tipo"], "motivo_sin_emitir": situacion["motivo"],
        "vigencia_vale": planta.plazos.vencimiento(exp, "recoger_planta", fecha_evento=timezone.now())
        if aplica and not vales else None,
    }
