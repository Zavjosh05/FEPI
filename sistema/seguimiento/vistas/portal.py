"""HU-6.1 · Desistimiento y sustitución desde el portal de personas beneficiarias (mismo servicio que la Delegación).
Las rutas cuelgan de ``/portal/seguimiento/`` para que ``SoloPortalMiddleware`` las deje pasar. La consulta sin cuenta ve las
solicitudes y sus acuses, pero no envía."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from ejecucion.vistas.comun import mensajes_error, responder_archivo
from portal import cuentas
from portal.views import _expediente_permitido

from .. import reasignacion
from ..formularios.reasignacion import SolicitudForm


@require_POST
def enviar(request, folio):
    if not cuentas.es_externo(request.user):
        raise PermissionDenied("Para enviar entre con su cuenta del portal (o preséntelo en la Delegación).")
    exp = cuentas.expedientes_de(request.user).filter(folio=folio).first()
    if exp is None:
        raise Http404("No existe el expediente o no es suyo.")
    form = SolicitudForm(request.POST, request.FILES, tipos=reasignacion.tipos_solicitud(exp),
                         puntos=reasignacion.puntos_firma(exp), portal=True)
    if form.is_valid():
        d = form.cleaned_data
        try:
            s = reasignacion.registrar_solicitud(request.user, exp, d["tipo"], d.get("archivo"), "", d.get("motivo", ""),
                                                 d.get("fecha_hecho"), form.segunda(), d.get("causa", ""), d.get("firmas", []))
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, f"Enviado: {s.nombre.lower()}, con el acuse {s.acuse.folio}.")
    else:
        messages.error(request, "Revise los datos de la solicitud.")
    return redirect("portal:expediente", folio)


def archivo(request, folio, pk):
    exp = _expediente_permitido(request, folio)
    s = exp.solicitudes_seguimiento.filter(pk=pk).first()
    if s is None or not s.archivo:
        raise Http404("No existe el documento.")
    return responder_archivo(request, s.archivo)


def seccion_portal(request, exp, con_cuenta):
    """Sección «Desistimiento o sustitución» del expediente en el portal (``extensiones.SECCIONES_PORTAL``)."""
    tipos = [t for t in reasignacion.tipos_solicitud(exp) if t.get("portal")]
    if not tipos or getattr(exp, "firma_contrato", None) is None and exp.estado.clave not in reasignacion.ESTADOS_SOLICITUD:
        return None
    puede, motivo = reasignacion.puede_solicitar(exp)
    return {"plantilla": "seguimiento/reasignacion/_portal.html", "contexto": {
        "solicitudes_seg": list(exp.solicitudes_seguimiento.select_related("acuse")), "tipos_solicitud": tipos,
        "puede_solicitar": con_cuenta and puede, "motivo_sin_solicitud": motivo, "con_cuenta": con_cuenta,
        "form_solicitud": SolicitudForm(tipos=tipos, puntos=reasignacion.puntos_firma(exp), portal=True)
        if con_cuenta and puede else None,
    }}
