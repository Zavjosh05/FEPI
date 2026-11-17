"""HU-4.1 · Envío de comprobaciones desde el portal de personas beneficiarias (mismo servicio que la ventanilla).
Las rutas cuelgan de ``/portal/envios/`` para que ``SoloPortalMiddleware`` las deje pasar. Con la consulta sin cuenta
(folio + código) se ven los envíos y sus acuses, pero no se envía: el acuse lleva el nombre de quien envía."""
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from portal import cuentas
from portal.views import _expediente_permitido

from .. import comprobaciones
from ..formularios.comprobaciones import EnvioForm
from .comun import mensajes_error, responder_archivo


@require_POST
def enviar(request, folio):
    if not cuentas.es_externo(request.user):
        raise PermissionDenied("Para enviar entre con su cuenta del portal (o entréguelo en la Delegación).")
    exp = cuentas.expedientes_de(request.user).filter(folio=folio).first()
    if exp is None:
        raise Http404("No existe el expediente o no es suyo.")
    form = EnvioForm(request.POST, request.FILES, tipos=comprobaciones.tipos_de_envio(exp),
                     periodos=comprobaciones.periodos(exp))
    if form.is_valid():
        d = form.cleaned_data
        try:
            c = comprobaciones.registrar_envio(request.user, exp, d["tipo"], d.get("archivo"), d.get("descripcion", ""),
                                               d.get("fecha_hecho"), d.get("periodo", ""))
        except (ValidationError, PermissionDenied) as e:
            for m in mensajes_error(e):
                messages.error(request, m)
        else:
            messages.success(request, f"Envío registrado: {c.nombre}, con el acuse {c.acuse.folio}"
                                      + (f" ({c.situacion_plazo})." if c.en_plazo is not None else "."))
    else:
        messages.error(request, "Revise los datos del envío.")
    return redirect("portal:expediente", folio)


def archivo(request, folio, pk):
    exp = _expediente_permitido(request, folio)
    c = exp.comprobaciones.filter(pk=pk).first()
    if c is None or not c.archivo:
        raise Http404("No existe el documento.")
    return responder_archivo(request, c.archivo)


def seccion_portal(request, exp, con_cuenta):
    """Sección «Mis envíos» de la pantalla del expediente en el portal (``extensiones.SECCIONES_PORTAL``)."""
    tipos = comprobaciones.tipos_de_envio(exp)
    if not tipos:
        return None
    puede, motivo = comprobaciones.puede_enviar(exp)
    return {"plantilla": "ejecucion/comprobaciones/_portal.html", "contexto": {
        "comprobaciones": list(exp.comprobaciones.select_related("acuse")), "tipos_envio": tipos,
        "puede_enviar": con_cuenta and puede, "motivo_sin_envio": motivo, "con_cuenta": con_cuenta,
        "form_envio": EnvioForm(tipos=tipos, periodos=comprobaciones.periodos(exp)) if con_cuenta and puede else None,
    }}
