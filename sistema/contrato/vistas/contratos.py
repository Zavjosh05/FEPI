"""HU-3.2 · Pantallas: modelos de contrato (área responsable y Unidad Jurídica), elaboración y envío del contrato
(área responsable) y el contexto de la pestaña «Contrato»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nucleo import montos
from nucleo.models import Ejercicio, TipoUnidad

from .. import contratos
from ..formularios.contratos import ElaborarForm, ModeloForm, RevisionForm, TextoModeloForm
from ..models import Contrato, EstadoVersion, ModeloContrato, TipoModelo
from .comun import expediente_visible, mensajes_error

TIPOS_QUE_VEN_MODELOS = (TipoUnidad.DIRECCION, TipoUnidad.JURIDICA)


def _exigir_modelos(request):
    if request.user.tipo_unidad not in TIPOS_QUE_VEN_MODELOS and not request.user.is_superuser:
        raise PermissionDenied("Los modelos de contrato los registra el área responsable y los valida la Unidad Jurídica.")


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


def _programas(request):
    return request.user.unidad.programas.all() if request.user.tipo_unidad == TipoUnidad.DIRECCION else None


# ----------------------------------------------------------------------------- modelos
@login_required
def modelos(request):
    _exigir_modelos(request)
    es_area = request.user.tipo_unidad == TipoUnidad.DIRECCION
    form = ModeloForm(request.POST or None, programas=_programas(request))
    if request.method == "POST":
        try:
            if request.POST.get("accion") == "base":
                ejercicio = form.fields["ejercicio"].queryset.get(pk=request.POST.get("ejercicio"))
                m = contratos.crear_plantilla_base(request.user, ejercicio, request.POST.get("tipo"))
                messages.success(request, "Plantilla base creada: queda marcada como borrador y por validar.")
                return redirect("contrato:modelo", m.pk)
            if form.is_valid():
                m = contratos.registrar_modelo(request.user, **form.cleaned_data)
                messages.success(request, "Modelo registrado: la Unidad Jurídica debe validarlo antes de usarlo.")
                return redirect("contrato:modelo", m.pk)
        except (ValidationError, PermissionDenied, Ejercicio.DoesNotExist) as e:
            _errores(request, e)
    lista = [{"m": m, "v": m.vigente} for m in contratos.modelos_visibles(request.user)]
    return render(request, "contrato/contratos/modelos.html", {
        "modelos": lista, "form": form, "es_area": es_area, "campos": contratos.CAMPOS,
        "tipos": TipoModelo.choices, "ejercicios": form.fields["ejercicio"].queryset if es_area else [],
        "por_validar": sum(x["v"].estado == EstadoVersion.PENDIENTE for x in lista),
    })


@login_required
def modelo(request, pk):
    _exigir_modelos(request)
    m = get_object_or_404(contratos.modelos_visibles(request.user), pk=pk)
    vigente = m.vigente
    es_area = request.user.tipo_unidad == TipoUnidad.DIRECCION
    es_uj = request.user.tipo_unidad == TipoUnidad.JURIDICA
    return render(request, "contrato/contratos/modelo.html", {
        "m": m, "vigente": vigente, "versiones": m.versiones.select_related("creada_por", "revisada_por"),
        "form_texto": TextoModeloForm(initial={"texto": vigente.texto}), "form_revision": RevisionForm(),
        "puede_modificar": es_area, "puede_revisar": es_uj and vigente.estado == EstadoVersion.PENDIENTE,
        "campos": contratos.CAMPOS,
    })


@login_required
@require_POST
def modelo_version(request, pk):
    m = get_object_or_404(contratos.modelos_visibles(request.user), pk=pk)
    form = TextoModeloForm(request.POST)
    if form.is_valid():
        try:
            v = contratos.modificar_modelo(request.user, m, form.cleaned_data["texto"])
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
        else:
            messages.success(request, f"Versión {v.numero} registrada: queda por validar por la Unidad Jurídica.")
    return redirect("contrato:modelo", m.pk)


@login_required
@require_POST
def modelo_revisar(request, pk):
    m = get_object_or_404(contratos.modelos_visibles(request.user), pk=pk)
    form = RevisionForm(request.POST)
    if form.is_valid():
        try:
            if form.cleaned_data["decision"] == "validar":
                v = contratos.validar_version(request.user, m.vigente, form.cleaned_data["observaciones"])
                messages.success(request, f"Versión {v.numero} validada por la Unidad Jurídica.")
            else:
                v = contratos.devolver_version(request.user, m.vigente, form.cleaned_data["observaciones"])
                messages.success(request, f"Versión {v.numero} devuelta con observaciones.")
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
    else:
        messages.error(request, "Elija si valida o devuelve el modelo.")
    return redirect("contrato:modelo", m.pk)


# ----------------------------------------------------------------------------- contratos
@login_required
def lista(request):
    if request.user.tipo_unidad not in (TipoUnidad.DIRECCION, TipoUnidad.JURIDICA) and not request.user.is_superuser:
        raise PermissionDenied("Los contratos los elabora el área responsable del programa.")
    return render(request, "contrato/contratos/lista.html", {
        "por_elaborar": contratos.por_elaborar(request.user).order_by("fecha_recepcion"),
        "por_enviar": contratos.por_enviar(request.user).select_related("contrato"),
        "enviados": contratos.contratos_visibles(request.user).filter(estado="enviado").order_by("-enviado_en")[:100],
        "es_area": request.user.tipo_unidad == TipoUnidad.DIRECCION,
    })


@login_required
def elaborar(request, folio):
    exp = expediente_visible(request, folio)
    destino = reverse("recepcion:expediente", args=[folio]) + "?pestana=contrato"
    if request.user.tipo_unidad != TipoUnidad.DIRECCION:
        raise PermissionDenied("El contrato lo elabora el área responsable del programa.")
    contrato = getattr(exp, "contrato", None)
    elegibles = contratos.modelos_elegibles(exp)
    form = ElaborarForm(request.POST or None, modelos=elegibles)
    if request.method == "POST" and form.is_valid():
        try:
            c = contratos.elaborar_contrato(request.user, exp, form.cleaned_data["modelo"])
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
        else:
            messages.success(request, f"Contrato {c.folio} elaborado. Revise el PDF y envíelo a la Delegación.")
            return redirect(destino)
    return render(request, "contrato/contratos/elaborar.html", {
        "exp": exp, "form": form, "contrato": contrato, "elegibles": elegibles,
        "tipo": TipoModelo(contratos.tipo_requerido(exp)).label,
        "todos": ModeloContrato.objects.filter(ejercicio=exp.ejercicio, tipo=contratos.tipo_requerido(exp)),
        "puede_elaborar": (contrato is None and exp.estado.clave == "notificada")
        or (contrato is not None and not contrato.enviado),
        "monto": montos.monto_aprobado(exp),
    })


@login_required
@require_POST
def enviar(request, folio):
    exp = expediente_visible(request, folio)
    contrato = get_object_or_404(Contrato, expediente=exp)
    try:
        acuse = contratos.enviar_a_delegacion(request.user, contrato)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Contrato enviado a {exp.delegacion.nombre} (acuse {acuse.folio}).")
    return redirect(reverse("recepcion:expediente", args=[folio]) + "?pestana=contrato")


@login_required
def pdf(request, folio):
    exp = expediente_visible(request, folio)
    contrato = get_object_or_404(Contrato, expediente=exp)
    if request.user.tipo_unidad == TipoUnidad.DELEGACION and not contrato.enviado:
        raise Http404("El contrato todavía no se envía a la Delegación.")
    return FileResponse(contrato.archivo.open("rb"), filename=f"{contrato.folio}.pdf",
                        as_attachment=request.GET.get("descargar") in ("1", "si", "sí"), content_type="application/pdf")


# ----------------------------------------------------------------------------- pestaña «Contrato»
def contexto_contrato_exp(request, exp):
    contrato = Contrato.objects.filter(expediente=exp).select_related("version_modelo__modelo", "acuse_envio").first()
    tipo = request.user.tipo_unidad
    ve_pdf = contrato is not None and (tipo != TipoUnidad.DELEGACION or contrato.enviado)
    return {
        "contrato": contrato, "puede_ver_pdf": ve_pdf,
        "puede_elaborar_contrato": tipo == TipoUnidad.DIRECCION and (
            (contrato is None and exp.estado.clave == "notificada") or (contrato is not None and not contrato.enviado)),
        "puede_enviar_contrato": tipo == TipoUnidad.DIRECCION and contrato is not None and not contrato.enviado
        and exp.estado.clave == "contrato_elaborado",
        "tipo_modelo": TipoModelo(contratos.tipo_requerido(exp)).label if tipo != TipoUnidad.DELEGACION else "",
    }
