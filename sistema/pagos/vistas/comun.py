"""Vistas y utilidades comunes del módulo M5 y contexto de la pestaña «Pagos» del expediente."""
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


def contexto_pagos(request, exp):
    """Cada historia (HU-5.x) suma aquí lo suyo a la pestaña."""
    from .pagos import contexto_pagos_exp
    from .solicitudes import contexto_solicitudes_exp

    contexto = {"historias": historias_pendientes(), "monto": montos.monto_si_aprobado(exp),
                "vencimientos": list(plazos.vencimientos(exp, USOS_DE_PLAZO).values())}
    contexto.update(contexto_solicitudes_exp(request, exp))
    contexto_pagos_exp(request, exp, contexto)
    return contexto
