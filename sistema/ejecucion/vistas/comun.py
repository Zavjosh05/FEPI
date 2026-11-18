"""Vistas y utilidades comunes del módulo M4 y contexto de la pestaña «Ejecución» del expediente."""
from django.http import FileResponse, Http404

from nucleo import montos, plazos
from nucleo.models import expedientes_visibles

TIPOS_ARCHIVO = {"pdf": "application/pdf", "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png"}


def mensajes_error(error):
    return error.messages if hasattr(error, "messages") else [str(error)]


def expediente_visible(request, folio):
    exp = expedientes_visibles(request.user).filter(folio=folio).first()
    if exp is None:
        raise Http404("No existe el expediente o no está entre los que atiende su unidad.")
    return exp


def responder_archivo(request, campo):
    nombre = campo.name.rsplit("/", 1)[-1]
    return FileResponse(campo.open("rb"), filename=nombre, as_attachment=request.GET.get("descargar") in ("1", "si", "sí"),
                        content_type=TIPOS_ARCHIVO.get(nombre.rsplit(".", 1)[-1].lower(), "application/octet-stream"))


def contexto_ejecucion(request, exp):
    """Cada historia (HU-4.x) suma aquí lo suyo a la pestaña."""
    from ..registro import USOS_DE_PLAZO, historias_pendientes
    from .comprobaciones import contexto_comprobaciones_exp
    from .reportes import contexto_reportes_exp
    from .verificacion import contexto_verificacion_exp

    contexto = {"historias": historias_pendientes(), "monto": montos.monto_si_aprobado(exp),
                "vencimientos": [v for v in plazos.vencimientos(exp, USOS_DE_PLAZO).values() if v is not None]}
    contexto.update(contexto_comprobaciones_exp(request, exp))
    contexto.update(contexto_verificacion_exp(request, exp))
    contexto.update(contexto_reportes_exp(request, exp))
    return contexto
