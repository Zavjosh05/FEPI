"""HU-5.2 · Pantallas: solicitudes por revisar y por pagar (Administración y Finanzas), por remitir a la Fiduciaria (Secretaría
Técnica) y las acciones sobre cada solicitud; contexto de la pestaña «Pagos»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nucleo.models import TipoUnidad

from .. import pagos, solicitudes
from ..formularios.pagos import PagoForm, RemisionForm, RevisionForm
from ..models import EstadoSolicitud, Pago, RemisionFiduciaria
from .comun import mensajes_error

TIPOS_QUE_VEN = (TipoUnidad.ADMIN_FINANZAS, TipoUnidad.SECRETARIA_COMITE, TipoUnidad.DIRECCION, TipoUnidad.JURIDICA,
                 TipoUnidad.FIDUCIARIA)


def _destino(solicitud):
    return reverse("recepcion:expediente", args=[solicitud.expediente.folio]) + "?pestana=pagos"


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


def _solicitud(request, pk):
    return get_object_or_404(solicitudes.solicitudes_visibles(request.user), pk=pk)


@login_required
def lista(request):
    tipo = request.user.tipo_unidad
    if tipo not in TIPOS_QUE_VEN and not request.user.is_superuser:
        raise PermissionDenied("El pago de las ministraciones lo atiende Administración y Finanzas.")
    visibles = solicitudes.solicitudes_visibles(request.user)
    return render(request, "pagos/pagos/lista.html", {
        "por_revisar": pagos.por_revisar(request.user), "por_pagar": pagos.por_pagar(request.user),
        "por_remitir": pagos.por_remitir(request.user), "en_revision_psa": pagos.en_revision_psa(request.user),
        "aceptadas_psa": [s for s in visibles.filter(estado=EstadoSolicitud.ACEPTADA) if pagos.es_fiduciaria(s.expediente)]
        if tipo == TipoUnidad.ADMIN_FINANZAS else [],
        "devueltas": list(visibles.filter(estado=EstadoSolicitud.DEVUELTA)[:50]),
        "pagos": list(Pago.objects.filter(solicitud__in=visibles).select_related(
            "expediente__solicitante", "expediente__predio", "solicitud", "acuse")[:100]),
        "remisiones": list(RemisionFiduciaria.objects.filter(solicitud__in=visibles).select_related(
            "expediente__solicitante", "expediente__predio", "solicitud", "acuse")[:100]),
        "es_af": tipo == TipoUnidad.ADMIN_FINANZAS, "es_st": tipo == TipoUnidad.SECRETARIA_COMITE,
    })


@login_required
@require_POST
def revisar(request, pk):
    sol = _solicitud(request, pk)
    resultado = request.POST.get("resultado", "")
    form = RevisionForm(request.POST)
    try:
        pagos.revisar_solicitud(request.user, sol, resultado, form.data.get("observaciones", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        if resultado == "aceptada":
            messages.success(request, f"Solicitud {sol.folio} aceptada.")
        else:
            messages.success(request, f"Solicitud {sol.folio} devuelta al área responsable con sus observaciones.")
    return redirect(_destino(sol))


@login_required
@require_POST
def pagar(request, pk):
    sol = _solicitud(request, pk)
    form = PagoForm(request.POST, tipos=pagos.tipos_de_pago(sol.expediente) or ["transferencia"])
    if form.is_valid():
        d = form.cleaned_data
        try:
            pago = pagos.registrar_pago(request.user, sol, d["referencia"], d["fecha_pago"], d["importe"], d["tipo"],
                                        d["motivo_cheque"])
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
        else:
            messages.success(request, f"Pago de la ministración {pago.ministracion} registrado (acuse {pago.acuse.folio}); "
                                      "la Delegación avisará a la persona beneficiaria.")
    else:
        for campo, errores in form.errors.items():
            messages.error(request, f"{form.fields[campo].label}: {' '.join(errores)}")
    return redirect(_destino(sol))


@login_required
@require_POST
def remitir(request, pk):
    sol = _solicitud(request, pk)
    form = RemisionForm(request.POST)
    try:
        r = pagos.remitir_a_fiduciaria(request.user, sol, form.data.get("oficio", ""), form.data.get("observaciones", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Pago solicitado a la Fiduciaria ({'en plazo' if r.en_plazo else 'fuera de plazo'}); "
                                  f"acuse {r.acuse.folio}.")
    return redirect(_destino(sol))


# ----------------------------------------------------------------------------- pestaña «Pagos»
def contexto_pagos_exp(request, exp, contexto):
    """Suma a cada ministración de la pestaña su revisión, su pago o su remisión y las acciones que puede hacer la unidad."""
    tipo = request.user.tipo_unidad
    fiduciaria = pagos.es_fiduciaria(exp)
    tipos = pagos.tipos_de_pago(exp)
    nombres = {t: solicitudes.nombre_tipo_pago(t) for t in tipos}
    for fila in contexto["ministraciones"]:
        sol = fila["solicitud"]
        fila.update({"revisiones": [], "pago": None, "remision": None, "puede_revisar": False, "puede_pagar": False,
                     "puede_remitir": False, "espera_remision": False})
        if sol is None:
            continue
        fila["revisiones"] = list(sol.revisiones.select_related("revisada_por", "acuse"))
        fila["pago"] = getattr(sol, "pago", None)
        fila["remision"] = getattr(sol, "remision", None)
        enviada, aceptada = sol.estado == EstadoSolicitud.ENVIADA, sol.estado == EstadoSolicitud.ACEPTADA
        fila["puede_revisar"] = tipo == TipoUnidad.ADMIN_FINANZAS and enviada
        fila["puede_pagar"] = tipo == TipoUnidad.ADMIN_FINANZAS and aceptada and not fiduciaria
        fila["puede_remitir"] = tipo == TipoUnidad.SECRETARIA_COMITE and aceptada and fiduciaria
        fila["espera_remision"] = aceptada and fiduciaria and not fila["puede_remitir"]
        if fila["puede_revisar"]:
            fila["form_revision"] = RevisionForm()
        if fila["puede_pagar"]:
            fila["form_pago"] = PagoForm(tipos=tipos, nombres=nombres, importe=sol.importe)
        if fila["puede_remitir"]:
            fila["form_remision"] = RemisionForm()
    contexto["es_af"] = tipo == TipoUnidad.ADMIN_FINANZAS
    return contexto
