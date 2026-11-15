"""Contexto de la pestaña «Pagos» del expediente. Las historias HU-5.x agregan aquí sus datos."""
from nucleo import montos, plazos

from ..registro import HISTORIAS, USOS_DE_PLAZO


def contexto_pagos(request, exp):
    return {"historias": HISTORIAS, "monto": montos.monto_si_aprobado(exp),
            "vencimientos": list(plazos.vencimientos(exp, USOS_DE_PLAZO).values())}
