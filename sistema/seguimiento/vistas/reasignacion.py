"""HU-6.1 · Pantallas: lista de espera y recurso liberado, propuestas al Comité y su acuerdo, solicitudes de sustitución y
desistimiento (Delegación), prórroga por causa externa (MFS) y la parte de la pestaña «Seguimiento» del expediente."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from dictamen.models import SesionComite
from ejecucion.vistas.comun import expediente_visible, mensajes_error, responder_archivo
from nucleo.models import Ejercicio, TipoUnidad

from .. import reasignacion
from ..formularios.reasignacion import (AcuerdoPropuestaForm, PropuestaForm, ProrrogaForm, ReasignacionForm,
                                        ResolucionProrrogaForm, SolicitudForm)
from ..models import Propuesta, Prorroga, SolicitudPersona


def _destino(folio):
    return reverse("recepcion:expediente", args=[folio]) + "?pestana=seguimiento"


def _errores(request, e):
    for m in mensajes_error(e):
        messages.error(request, m)


# ----------------------------------------------------------------------------- página del módulo
@login_required
def pagina(request):
    u = request.user
    if u.tipo_unidad not in (TipoUnidad.DIRECCION, TipoUnidad.SECRETARIA_COMITE, TipoUnidad.JURIDICA) and not u.is_superuser:
        raise PermissionDenied("Esta pantalla es del área responsable, la Secretaría Técnica y la Unidad Jurídica.")
    propuestas = list(reasignacion.propuestas_visibles(u)[:100])
    por_llevar = []
    if u.tipo_unidad == TipoUnidad.SECRETARIA_COMITE:
        for p in propuestas:
            if p.estado == "enviada":
                sesiones = list(reasignacion.sesiones_para(p))
                por_llevar.append({"propuesta": p, "sesiones": sesiones,
                                   "form": AcuerdoPropuestaForm(sesiones=sesiones, prefix=f"p{p.pk}")})
    return render(request, "seguimiento/reasignacion/pagina.html", {
        "ejercicios": reasignacion.ejercicios_con_lista(u), "propuestas": propuestas, "por_llevar": por_llevar,
        "solicitudes": list(reasignacion.solicitudes_visibles(u).order_by("-presentada_en")[:100]),
        "es_area": u.tipo_unidad == TipoUnidad.DIRECCION, "form_reasignacion": ReasignacionForm(),
    })


@login_required
@require_POST
def proponer_reasignacion(request, ejercicio):
    ej = get_object_or_404(Ejercicio, pk=ejercicio)
    form = ReasignacionForm(request.POST)
    form.is_valid()
    try:
        p = reasignacion.proponer_reasignacion(request.user, ej, form.cleaned_data.get("observaciones", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Propuesta de reasignación enviada a la Secretaría Técnica con el acuse {p.acuse.folio}.")
    return redirect("seguimiento:pagina")


@login_required
@require_POST
def llevar_a_sesion(request, pk):
    p = get_object_or_404(Propuesta, pk=pk)
    sesiones = list(reasignacion.sesiones_para(p))
    form = AcuerdoPropuestaForm(request.POST, sesiones=sesiones, prefix=f"p{p.pk}")
    if not form.is_valid():
        messages.error(request, "Elija la sesión de seguimiento (convocada) y lo que acordó el Comité.")
        return redirect("seguimiento:pagina")
    d = form.cleaned_data
    try:
        a = reasignacion.llevar_a_sesion(request.user, p, SesionComite.objects.get(pk=d["sesion"]), d["aprueba"] == "si",
                                         d.get("descripcion", ""))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Acuerdo {a.numero} registrado; queda pendiente en la bandeja de {a.unidad_responsable}, "
                                  "que al cumplirlo lo ejecuta.")
    return redirect("seguimiento:pagina")


# ----------------------------------------------------------------------------- expediente
@login_required
@require_POST
def registrar_solicitud(request, folio):
    exp = expediente_visible(request, folio)
    form = SolicitudForm(request.POST, request.FILES, tipos=reasignacion.tipos_solicitud(exp),
                         puntos=reasignacion.puntos_firma(exp))
    if not form.is_valid():
        messages.error(request, "Revise los datos de la solicitud.")
        return redirect(_destino(folio))
    d = form.cleaned_data
    try:
        s = reasignacion.registrar_solicitud(request.user, exp, d["tipo"], d.get("archivo"), d.get("persona_presenta", ""),
                                             d.get("motivo", ""), d.get("fecha_hecho"), form.segunda(), d.get("causa", ""),
                                             d.get("firmas", []))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Registrado: {s.nombre.lower()}, con el acuse {s.acuse.folio}"
                                  + (f" ({s.situacion_plazo})." if s.en_plazo is not None else "."))
    return redirect(_destino(folio))


@login_required
@require_POST
def proponer(request, folio):
    exp = expediente_visible(request, folio)
    form = PropuestaForm(request.POST, tipos=reasignacion.tipos_propuesta(exp),
                         resoluciones=reasignacion.datos_seguimiento()["propuestas"]["resoluciones_caso_fortuito"],
                         bases=reasignacion.datos_seguimiento()["incumplimientos"]["reintegro"]["bases"])
    if not form.is_valid():
        messages.error(request, "Elija la propuesta.")
        return redirect(_destino(folio))
    d = form.cleaned_data
    try:
        p = reasignacion.proponer(request.user, exp, d["tipo"], d.get("descripcion", ""), d.get("resolucion", ""),
                                  base=d.get("base") or "ministrado")
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Propuesta enviada a la Secretaría Técnica con el acuse {p.acuse.folio}.")
    return redirect(_destino(folio))


@login_required
@require_POST
def solicitar_prorroga(request, folio):
    exp = expediente_visible(request, folio)
    form = ProrrogaForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Describa la causa externa.")
        return redirect(_destino(folio))
    d = form.cleaned_data
    try:
        p = reasignacion.solicitar_prorroga(request.user, exp, d["causa"], d.get("plazo_solicitado"), d.get("archivo"),
                                            d.get("plazo_original"))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, f"Solicitud de prórroga registrada con el acuse {p.acuse.folio}.")
    return redirect(_destino(folio))


@login_required
@require_POST
def resolver_prorroga(request, pk):
    p = get_object_or_404(Prorroga, pk=pk)
    expediente_visible(request, p.expediente.folio)
    form = ResolucionProrrogaForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Escriba el motivo de la resolución.")
        return redirect(_destino(p.expediente.folio))
    d = form.cleaned_data
    try:
        reasignacion.resolver_prorroga(request.user, p, d["autorizada"] == "si", d["motivo"], d.get("plazo_nuevo"),
                                       d.get("archivo"))
    except (ValidationError, PermissionDenied) as e:
        _errores(request, e)
    else:
        messages.success(request, "Prórroga resuelta; la Delegación notifica la resolución.")
    return redirect(_destino(p.expediente.folio))


@login_required
def archivo_solicitud(request, pk):
    s = SolicitudPersona.objects.filter(pk=pk).select_related("expediente").first()
    if s is None or not s.archivo:
        raise Http404
    expediente_visible(request, s.expediente.folio)
    return responder_archivo(request, s.archivo)


def contexto_reasignacion_exp(request, exp):
    u = request.user
    es_deleg = u.tipo_unidad == TipoUnidad.DELEGACION and u.unidad_id == exp.delegacion_id
    es_area = u.tipo_unidad == TipoUnidad.DIRECCION and u.unidad.programas.filter(pk=exp.programa.pk).exists()
    tipos = reasignacion.tipos_solicitud(exp)
    puede_solicitar = es_deleg and bool(tipos) and reasignacion.puede_solicitar(exp)[0]
    tipos_prop = reasignacion.tipos_propuesta(exp) if es_area else []
    resoluciones = reasignacion.datos_seguimiento()["propuestas"]["resoluciones_caso_fortuito"]
    cfg_prorroga = reasignacion.config_prorroga(exp)
    prorrogas = list(exp.prorrogas.select_related("acuse", "acuse_resolucion", "adendum")) if cfg_prorroga else []
    pendiente = next((p for p in prorrogas if p.autorizada is None), None)
    return {
        "solicitudes_seg": list(exp.solicitudes_seguimiento.select_related("acuse", "segunda_persona", "propuesta")),
        "tipos_solicitud": tipos, "puede_solicitar": puede_solicitar,
        "form_solicitud": SolicitudForm(tipos=tipos, puntos=reasignacion.puntos_firma(exp)) if puede_solicitar else None,
        "propuestas_exp": list(exp.propuestas_seguimiento.select_related("acuse", "acuerdo__sesion")),
        "recursos_exp": list(exp.recursos_liberados.all()),
        "form_propuesta": PropuestaForm(tipos=tipos_prop, resoluciones=resoluciones,
                                        bases=reasignacion.datos_seguimiento()["incumplimientos"]["reintegro"]["bases"])
        if tipos_prop else None,
        "hay_caso_fortuito": any(t == "caso_fortuito" for t, _ in tipos_prop),
        "hay_cancelacion": any(t in ("cancelacion", "baja_cheque", "baja_reportes") for t, _ in tipos_prop),
        "por_ministrar": reasignacion.por_ministrar(exp) if es_area and tipos_prop else None,
        "ministrado": reasignacion.ministrado(exp) if es_area and tipos_prop else None,
        "prorroga": cfg_prorroga, "prorrogas": prorrogas,
        "puede_pedir_prorroga": bool(cfg_prorroga) and es_deleg and exp.estado.clave in ("en_ejecucion", "pagada")
                                and pendiente is None,
        "form_prorroga": ProrrogaForm(), "prorroga_pendiente": pendiente if es_area else None,
        "form_resolucion_prorroga": ResolucionProrrogaForm(),
    }
