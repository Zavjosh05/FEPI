"""HU-5.3 · Pantallas: cheques por emitir y por enviar (Fiduciaria), por entregar (Delegación), cobro y cheques por vencer; contexto
de la pestaña «Pagos»."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nucleo.models import TipoUnidad

from .. import cheques, solicitudes
from ..formularios.cheques import CobroForm, EmisionForm, EntregaChequeForm
from ..models import Cheque
from .comun import mensajes_error

TIPOS_QUE_VEN = (TipoUnidad.FIDUCIARIA, TipoUnidad.DELEGACION, TipoUnidad.ADMIN_FINANZAS, TipoUnidad.DIRECCION,
                 TipoUnidad.SECRETARIA_COMITE, TipoUnidad.JURIDICA)


def _destino(exp):
    return reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=pagos"


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


@login_required
def lista(request):
    if request.user.tipo_unidad not in TIPOS_QUE_VEN and not request.user.is_superuser:
        raise PermissionDenied("Los cheques los atienden la Fiduciaria y las Delegaciones.")
    return render(request, "pagos/cheques/lista.html", {
        "por_emitir": cheques.por_emitir(request.user), "por_enviar": cheques.por_enviar(request.user),
        "por_entregar": cheques.por_entregar(request.user), "por_cobrar": cheques.por_cobrar(request.user),
        "cheques": list(cheques.cheques_visibles(request.user)[:200]),
    })


@login_required
@require_POST
def emitir(request, pk):
    sol = get_object_or_404(solicitudes.solicitudes_visibles(request.user), pk=pk)
    form = EmisionForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        try:
            c = cheques.emitir_cheque(request.user, sol, d["numero"], d["importe"], d["fecha_emision"])
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
        else:
            messages.success(request, f"Cheque {c.numero} emitido (acuse {c.acuse_emision.folio}).")
    else:
        for campo, errores in form.errors.items():
            messages.error(request, f"{form.fields[campo].label}: {' '.join(errores)}")
    return redirect(_destino(sol.expediente))


def _cheque(request, pk):
    return get_object_or_404(cheques.cheques_visibles(request.user), pk=pk)


@login_required
@require_POST
def enviar(request, pk):
    c = _cheque(request, pk)
    try:
        c = cheques.enviar_a_delegacion(request.user, c)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Cheque {c.numero} enviado a {c.delegacion.nombre} (acuse {c.acuse_envio.folio}).")
    return redirect(_destino(c.expediente))


@login_required
@require_POST
def entregar(request, pk):
    c = _cheque(request, pk)
    form = EntregaChequeForm(request.POST)
    if form.is_valid():
        try:
            c = cheques.registrar_entrega(request.user, c, form.cleaned_data["recibe_nombre"], form.cleaned_data["entregado_en"])
        except (ValidationError, PermissionDenied) as e:
            _errores(request, e)
        else:
            messages.success(request, f"Entrega del cheque {c.numero} registrada (acuse {c.acuse_entrega.folio}).")
    else:
        for campo, errores in form.errors.items():
            messages.error(request, f"{form.fields[campo].label}: {' '.join(errores)}")
    return redirect(_destino(c.expediente))


@login_required
@require_POST
def cobro(request, pk):
    c = _cheque(request, pk)
    form = CobroForm(request.POST)
    try:
        c = cheques.registrar_cobro(request.user, c, form.cleaned_data.get("fecha_cobro") if form.is_valid() else None)
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Cobro del cheque {c.numero} registrado.")
    return redirect(_destino(c.expediente))


# ----------------------------------------------------------------------------- pestaña «Pagos»
def contexto_cheques_exp(request, exp, contexto):
    tipo = request.user.tipo_unidad
    for fila in contexto["ministraciones"]:
        sol = fila["solicitud"]
        c = getattr(sol, "cheque", None) if sol is not None else None
        fila.update({"cheque": c, "vence_cobro": cheques.vencimiento_cobro(c) if c else None, "puede_emitir": False,
                     "puede_enviar": False, "puede_entregar": False, "puede_cobrar": False})
        if sol is not None and sol.estado == "remitida" and c is None and tipo == TipoUnidad.FIDUCIARIA:
            fila["puede_emitir"] = True
            fila["form_emision"] = EmisionForm(importe=sol.importe)
        if c is not None:
            fila["puede_enviar"] = tipo == TipoUnidad.FIDUCIARIA and not c.enviado
            fila["puede_entregar"] = (tipo == TipoUnidad.DELEGACION and c.enviado and not c.entregado
                                      and request.user.unidad_id == c.delegacion_id)
            fila["puede_cobrar"] = (c.entregado and not c.cobrado and (
                tipo == TipoUnidad.FIDUCIARIA or (tipo == TipoUnidad.DELEGACION and request.user.unidad_id == c.delegacion_id)))
            if fila["puede_entregar"]:
                fila["form_entrega"] = EntregaChequeForm()
            if fila["puede_cobrar"]:
                fila["form_cobro"] = CobroForm()
    return contexto
