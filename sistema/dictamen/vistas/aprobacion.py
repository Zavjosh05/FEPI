"""HU-2.3 · Acciones de la sesión de aprobación: propuesta de listados, ajuste del Comité y acta."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .. import aprobacion
from ..formularios.aprobacion import ActaForm, AjusteForm, PropuestaForm
from ..models import ResolucionSesion, ResultadoListado
from .comun import mensajes_error
from .sesiones import _sesion


def contexto_sesion(request, sesion):
    resoluciones = list(sesion.resoluciones.select_related("expediente__predio", "expediente__solicitante",
                                                           "expediente__dictamen_tecnico"))
    return {
        "plantilla_tipo": "dictamen/aprobacion/_listados.html",
        "listados": [(valor, etiqueta, [x for x in resoluciones if x.resultado == valor])
                     for valor, etiqueta in ResultadoListado.choices],
        "hay_resoluciones": bool(resoluciones), "form_propuesta": PropuestaForm(initial={"presupuesto": sesion.presupuesto}),
        "form_acta": ActaForm(), "monto_ha": aprobacion.monto_por_hectarea(sesion.ejercicio),
        "resultados_listado": ResultadoListado.choices,
    }


def _intentar(request, accion, exito):
    try:
        resultado = accion()
    except (ValidationError, PermissionDenied) as e:
        for m in mensajes_error(e):
            messages.error(request, m)
        return None
    messages.success(request, exito(resultado) if callable(exito) else exito)
    return resultado


@login_required
@require_POST
def proponer(request, pk):
    sesion = _sesion(request, pk)
    form = PropuestaForm(request.POST)
    presupuesto = form.cleaned_data.get("presupuesto") if form.is_valid() else None
    _intentar(request, lambda: aprobacion.proponer_listados(request.user, sesion, presupuesto),
              lambda r: f"Propuesta de listados generada ({len(r)} solicitudes dictaminadas).")
    return redirect("dictamen:sesion", pk)


@login_required
@require_POST
def ajustar(request, pk, resolucion):
    sesion = _sesion(request, pk)
    r = get_object_or_404(ResolucionSesion, pk=resolucion, sesion=sesion)
    form = AjusteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Indique el listado, el lugar y el motivo del ajuste.")
    else:
        d = form.cleaned_data
        _intentar(request, lambda: aprobacion.ajustar(request.user, r, d["resultado"], d.get("orden"), d["motivo"]),
                  f"Ajuste del Comité registrado para {r.expediente.folio}.")
    return redirect("dictamen:sesion", pk)


@login_required
@require_POST
def acta(request, pk):
    sesion = _sesion(request, pk)
    form = ActaForm(request.POST)
    form.is_valid()
    d = form.cleaned_data
    _intentar(request, lambda: aprobacion.registrar_acta(request.user, sesion, d.get("autoriza_publicacion", False),
                                                         d.get("observaciones", "")),
              lambda a: f"Acta registrada (acuse {a.folio}); los expedientes pasaron a sus listados.")
    return redirect("dictamen:sesion", pk)
