"""HU-5.1 · Pantallas: oficio de la Delegación, comprobante de la cuenta, solicitud de cada ministración con sus
soportes y su envío a Administración y Finanzas; lista de solicitudes y contexto de la pestaña «Pagos»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nucleo.models import TipoUnidad

from .. import solicitudes
from ..formularios.solicitudes import ComprobanteForm, EnvioForm
from ..models import ComprobanteCuenta, EstadoSolicitud
from .comun import expediente_visible, mensajes_error

TIPOS_QUE_VEN = (TipoUnidad.DELEGACION, TipoUnidad.DIRECCION, TipoUnidad.JURIDICA, TipoUnidad.ADMIN_FINANZAS,
                 TipoUnidad.SECRETARIA_COMITE, TipoUnidad.FIDUCIARIA)


def _destino(folio):
    return reverse("recepcion:expediente", args=[folio]) + "?pestana=pagos"


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


@login_required
def lista(request):
    tipo = request.user.tipo_unidad
    if tipo not in TIPOS_QUE_VEN and not request.user.is_superuser:
        raise PermissionDenied("Las solicitudes de pago las ven las unidades que intervienen en el pago.")
    todas = list(solicitudes.solicitudes_visibles(request.user).order_by("-enviada_en", "-id")[:300])
    return render(request, "pagos/solicitudes/lista.html", {
        "por_emitir": list(solicitudes.sin_oficio(request.user)) if tipo == TipoUnidad.DELEGACION else [],
        "por_solicitar": solicitudes.por_solicitar(request.user) if tipo == TipoUnidad.DIRECCION else [],
        "borradores": [s for s in todas if s.estado == EstadoSolicitud.BORRADOR],
        "devueltas": [s for s in todas if s.estado == EstadoSolicitud.DEVUELTA],
        "en_tramite": [s for s in todas if s.estado in (EstadoSolicitud.ENVIADA, EstadoSolicitud.ACEPTADA,
                                                           EstadoSolicitud.REMITIDA)],
        "pagadas": [s for s in todas if s.estado == EstadoSolicitud.PAGADA],
        "es_delegacion": tipo == TipoUnidad.DELEGACION, "es_area": tipo == TipoUnidad.DIRECCION,
    })


@login_required
def expediente(request, folio):
    expediente_visible(request, folio)
    return redirect(_destino(folio))


@login_required
@require_POST
def oficio_emitir(request, folio):
    exp = expediente_visible(request, folio)
    try:
        oficio = solicitudes.emitir_oficio(request.user, exp)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Oficio {oficio.folio} emitido; acuse {oficio.acuse.folio}.")
    return redirect(_destino(folio))


@login_required
def oficio_pdf(request, folio):
    exp = expediente_visible(request, folio)
    oficio = getattr(exp, "oficio_pago", None)
    if oficio is None or not oficio.archivo:
        raise Http404("La Delegación aún no emite el oficio.")
    return FileResponse(oficio.archivo.open("rb"), filename=f"{oficio.folio}.pdf",
                        as_attachment=request.GET.get("descargar") in ("1", "si", "sí"), content_type="application/pdf")


@login_required
@require_POST
def comprobante_subir(request, folio):
    exp = expediente_visible(request, folio)
    form = ComprobanteForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            solicitudes.adjuntar_comprobante(request.user, exp, form.cleaned_data["archivo"], form.cleaned_data["descripcion"])
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
        else:
            messages.success(request, "Comprobante de la cuenta bancaria guardado.")
    else:
        messages.error(request, "Revise el archivo del comprobante.")
    return redirect(_destino(folio))


@login_required
def comprobante(request, folio, pk):
    exp = expediente_visible(request, folio)
    c = get_object_or_404(ComprobanteCuenta, pk=pk, expediente=exp)
    nombre = c.archivo.name.rsplit("/", 1)[-1]
    extension = nombre.rsplit(".", 1)[-1].lower()
    tipos = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}
    return FileResponse(c.archivo.open("rb"), filename=nombre,
                        as_attachment=request.GET.get("descargar") in ("1", "si", "sí"),
                        content_type=tipos.get(extension, "application/octet-stream"))


@login_required
@require_POST
def solicitud_preparar(request, folio, numero):
    exp = expediente_visible(request, folio)
    try:
        sol = solicitudes.preparar_solicitud(request.user, exp, numero)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Solicitud {sol.folio} lista con su lista de soportes.")
    return redirect(_destino(folio))


@login_required
@require_POST
def solicitud_enviar(request, folio, numero):
    exp = expediente_visible(request, folio)
    form = EnvioForm(request.POST)
    try:
        sol = solicitudes.enviar_solicitud(request.user, exp, numero, form.data.get("observaciones", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Solicitud {sol.folio} enviada a Administración y Finanzas "
                                  f"(acuse {sol.acuse_envio.folio}).")
    return redirect(_destino(folio))


# ----------------------------------------------------------------------------- pestaña «Pagos»
def contexto_solicitudes_exp(request, exp):
    tipo = request.user.tipo_unidad
    filas = solicitudes.ministraciones(exp)
    for fila in filas:
        sol = fila["solicitud"]
        fila["plazo_remision"] = solicitudes.plazo_remision(sol) if sol is not None else None
    firmado = getattr(exp, "firma_contrato", None) is not None
    oficio = getattr(exp, "oficio_pago", None)
    pide_comprobante = any(s["clave"] == "comprobante_cuenta" for s in solicitudes.soportes_requeridos(exp, 1))
    return {
        "oficio": oficio, "ministraciones": filas, "firmado": firmado,
        "puede_emitir_oficio": (tipo == TipoUnidad.DELEGACION and firmado and oficio is None
                                and exp.estado.clave not in ("sin_firma_en_plazo", "recurso_liberado")),
        "es_area": tipo == TipoUnidad.DIRECCION, "pide_comprobante": pide_comprobante,
        "comprobantes": list(exp.comprobantes_cuenta.all()),
        "puede_subir_comprobante": pide_comprobante and tipo in (TipoUnidad.DELEGACION, TipoUnidad.DIRECCION) and firmado,
        "form_comprobante": ComprobanteForm(), "form_envio": EnvioForm(),
        "tipo_pago": solicitudes.nombre_tipo_pago(solicitudes.tipo_pago(exp)),
        "nota_pago": solicitudes.config(exp).get("nota", ""),
    }
