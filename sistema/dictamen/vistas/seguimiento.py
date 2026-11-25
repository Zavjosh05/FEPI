"""HU-2.4 · Reasignaciones e incidentes: acuerdos de las sesiones de seguimiento y su cumplimiento por el área responsable."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .. import seguimiento
from ..formularios.seguimiento import AcuerdoForm
from ..models import Acuerdo
from .comun import mensajes_error
from .sesiones import _sesion


def contexto_sesion(request, sesion):
    tipos = seguimiento.tipos_acuerdo(sesion.ejercicio.programa)
    return {
        "plantilla_tipo": "dictamen/seguimiento/_acuerdos.html",
        "acuerdos": sesion.acuerdos.select_related("unidad_responsable").prefetch_related("expedientes", "movimientos__expediente"),
        "form_acuerdo": AcuerdoForm(sesion=sesion, tipos=tipos), "tipos_acuerdo": {t["clave"]: t for t in tipos},
        "lista_espera": seguimiento.lista_de_espera(sesion.ejercicio),
        "recurso_liberado": seguimiento.recurso_liberado(sesion.ejercicio),
        "movimientos": seguimiento.movimientos_del_ejercicio(sesion.ejercicio)
                       .select_related("acuerdo", "expediente__solicitante", "usuario"),
    }


@login_required
@require_POST
def acuerdo(request, pk):
    sesion = _sesion(request, pk)
    form = AcuerdoForm(request.POST, sesion=sesion, tipos=seguimiento.tipos_acuerdo(sesion.ejercicio.programa))
    if not form.is_valid():
        for campo, errores in form.errors.items():
            for e in errores:
                messages.error(request, f"{form.fields[campo].label if campo in form.fields else ''}: {e}")
        return redirect("dictamen:sesion", pk)
    d = form.cleaned_data
    try:
        a = seguimiento.registrar_acuerdo(request.user, sesion, d["tipo"], d["descripcion"], d["expedientes"],
                                          d.get("unidad_responsable"), d.get("ministracion"), d.get("periodo", ""),
                                          causa=d.get("causa", ""))
    except (ValidationError, PermissionDenied) as e:
        for m in mensajes_error(e):
            messages.error(request, m)
    else:
        cambios = ""
        if a.movimientos.exists():
            salen = a.movimientos.filter(movimiento="sale").count()
            entran = a.movimientos.filter(movimiento="entra").count()
            cambios = f" Listados: {salen} sale{'n' if salen != 1 else ''} y {entran} entra{'n' if entran != 1 else ''}."
        messages.success(request, f"Acuerdo {a.numero} registrado; queda pendiente en la bandeja de {a.unidad_responsable}.{cambios}")
    return redirect("dictamen:sesion", pk)


@login_required
@require_POST
def cerrar(request, pk):
    sesion = _sesion(request, pk)
    try:
        seguimiento.cerrar_sesion(request.user, sesion, request.POST.get("observaciones", ""))
    except (ValidationError, PermissionDenied) as e:
        for m in mensajes_error(e):
            messages.error(request, m)
    else:
        messages.success(request, "Sesión de seguimiento cerrada.")
    return redirect("dictamen:sesion", pk)


@login_required
@require_POST
def cumplir(request, pk):
    a = get_object_or_404(Acuerdo, pk=pk)
    try:
        seguimiento.cumplir(request.user, a, request.POST.get("observaciones", ""))
    except (ValidationError, PermissionDenied) as e:
        for m in mensajes_error(e):
            messages.error(request, m)
    else:
        messages.success(request, f"Acuerdo {a.numero} marcado como cumplido.")
    return redirect(request.POST.get("siguiente") or "nucleo:bandeja")
