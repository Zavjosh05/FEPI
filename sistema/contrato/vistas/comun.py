"""Vistas y utilidades comunes del módulo M3 y contexto de la pestaña «Contrato» del expediente."""
from django.http import Http404

from nucleo import montos, plazos
from nucleo.models import expedientes_visibles

from ..registro import USOS_DE_PLAZO, historias_pendientes


def mensajes_error(error):
    return error.messages if hasattr(error, "messages") else [str(error)]


def expediente_visible(request, folio):
    exp = expedientes_visibles(request.user).filter(folio=folio).first()
    if exp is None:
        raise Http404("No existe el expediente o no está entre los que atiende su unidad.")
    return exp


def contexto_contrato(request, exp):
    """Cada historia (HU-3.x) suma aquí lo suyo a la pestaña."""
    from .contratos import contexto_contrato_exp
    from .firma import contexto_firma_exp
    from .planta import contexto_planta_exp
    from .publicacion import contexto_publicacion

    contexto = {"historias": historias_pendientes(), "monto": montos.monto_si_aprobado(exp),
                "vencimientos": list(plazos.vencimientos(exp, USOS_DE_PLAZO).values())}
    contexto.update(contexto_publicacion(request, exp))
    contexto.update(contexto_contrato_exp(request, exp))
    contexto.update(contexto_firma_exp(request, exp))
    contexto.update(contexto_planta_exp(request, exp))
    return contexto
