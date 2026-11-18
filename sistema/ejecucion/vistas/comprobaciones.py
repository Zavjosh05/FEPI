"""HU-4.1 · Pantallas del personal: la Delegación registra la entrega recibida en ventanilla (mismo servicio que el portal)
y revisa lo que llegó por el portal; lista de comprobaciones y contexto de la pestaña «Ejecución»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from nucleo.models import TipoUnidad, expedientes_visibles

from .. import comprobaciones, reportes
from ..formularios.comprobaciones import EnvioForm
from ..models import Comprobacion, Verificacion
from .comun import expediente_visible, mensajes_error, responder_archivo

TIPOS_QUE_VEN = (TipoUnidad.DELEGACION, TipoUnidad.DIRECCION, TipoUnidad.JURIDICA)


def _destino(folio):
    return reverse("recepcion:expediente", args=[folio]) + "?pestana=ejecucion"


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


@login_required
def lista(request):
    tipo = request.user.tipo_unidad
    if tipo not in TIPOS_QUE_VEN and not request.user.is_superuser:
        raise PermissionDenied("Las comprobaciones las ven la Delegación, el área responsable y la Unidad Jurídica.")
    todas = list(comprobaciones.comprobaciones_visibles(request.user).order_by("-enviada_en", "-id")[:300])
    return render(request, "ejecucion/comprobaciones/lista.html", {
        "por_revisar": [c for c in todas if c.por_portal and c.revisada_en is None and not reportes.es_revisable(c)] if tipo == TipoUnidad.DELEGACION else [],
        "todas": todas, "es_delegacion": tipo == TipoUnidad.DELEGACION,
        "por_verificar": list(expedientes_visibles(request.user).filter(estado__clave="comprobacion_enviada").select_related("persona_beneficiaria")
                              .order_by("fecha_recepcion")[:300]),
        "verificaciones": list(Verificacion.objects.filter(expediente__in=expedientes_visibles(request.user))
                               .select_related("expediente", "acuse", "unidad").order_by("-registrada_en")[:300]),
    })


@login_required
@require_POST
def registrar(request, folio):
    exp = expediente_visible(request, folio)
    form = EnvioForm(request.POST, request.FILES, tipos=comprobaciones.tipos_de_envio(exp),
                     periodos=comprobaciones.periodos(exp), ventanilla=True)
    if not form.is_valid():
        messages.error(request, "Revise los datos de la comprobación.")
        return redirect(_destino(folio))
    d = form.cleaned_data
    try:
        c = comprobaciones.registrar_envio(request.user, exp, d["tipo"], d.get("archivo"), d.get("descripcion", ""),
                                           d.get("fecha_hecho"), d.get("periodo", ""), d.get("persona_entrega", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"{c.nombre}: entrega registrada con el acuse {c.acuse.folio}"
                                  + (f" ({c.situacion_plazo})." if c.en_plazo is not None else "."))
    return redirect(_destino(folio))


@login_required
@require_POST
def acceso_prestador(request, folio):
    """La Delegación da acceso al portal al prestador de servicios forestales (RFN): los códigos van en el acuse."""
    from portal import cuentas

    exp = expediente_visible(request, folio)
    try:
        res = cuentas.dar_acceso_prestador(request.user, exp, request.POST.get("nombre", ""), request.POST.get("curp", ""),
                                           request.POST.get("rfn", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        if res["acuse"] is None:
            messages.info(request, "El prestador ya tenía acceso a este expediente con su cuenta activa.")
        else:
            messages.success(request, f"Acceso al portal para el prestador: acuse {res['acuse'].folio} con su usuario (CURP) y el "
                                      "código de primer acceso para entregárselo.")
    return redirect(_destino(folio))


@login_required
@require_POST
def revisada(request, pk):
    c = Comprobacion.objects.filter(pk=pk).select_related("expediente").first()
    if c is None:
        raise Http404
    expediente_visible(request, c.expediente.folio)
    try:
        comprobaciones.marcar_revisada(request.user, c)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"{c.nombre}: revisado.")
    siguiente = request.POST.get("siguiente", "")
    if not url_has_allowed_host_and_scheme(siguiente, allowed_hosts={request.get_host()}):
        siguiente = ""
    return redirect(siguiente or _destino(c.expediente.folio))


@login_required
def archivo(request, pk):
    c = Comprobacion.objects.filter(pk=pk).select_related("expediente").first()
    if c is None or not c.archivo:
        raise Http404("No existe el documento.")
    expediente_visible(request, c.expediente.folio)
    return responder_archivo(request, c.archivo)


def _prestadores(exp):
    from portal.cuentas import prestadores_de

    return prestadores_de(exp)


def contexto_comprobaciones_exp(request, exp):
    es_delegacion = request.user.tipo_unidad == TipoUnidad.DELEGACION and request.user.unidad_id == exp.delegacion_id
    puede, motivo = comprobaciones.puede_enviar(exp)
    tipos = comprobaciones.tipos_de_envio(exp)
    lista = list(exp.comprobaciones.select_related("acuse", "enviada_por", "recibida_por", "revisada_por"))
    for c in lista:
        c.se_revisa_con_resultado = reportes.es_revisable(c)  # HU-4.3: reportes y acuses de PEG
    return {
        "comprobaciones": lista,
        "tipos_envio": tipos, "puede_registrar": es_delegacion and puede and bool(tipos), "motivo_sin_envio": motivo,
        "es_delegacion_exp": es_delegacion,
        "prestadores": list(_prestadores(exp)),
        "form_envio": EnvioForm(tipos=tipos, periodos=comprobaciones.periodos(exp), ventanilla=True),
    }
