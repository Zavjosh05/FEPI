"""Contexto de la pestaña «Contrato» del expediente. Las historias HU-3.x agregan aquí sus datos."""
from nucleo import montos, plazos

from ..registro import HISTORIAS, USOS_DE_PLAZO


def contexto_contrato(request, exp):
    return {"historias": HISTORIAS, "monto": montos.monto_si_aprobado(exp),
            "vencimientos": list(plazos.vencimientos(exp, USOS_DE_PLAZO).values())}
