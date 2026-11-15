"""Siguiente paso del trámite para la unidad que mira el expediente (P-13).

Cada módulo registra en ``extensiones.SIGUIENTES_PASOS`` funciones ``(usuario, expediente) -> dict | None``
con ``{"texto", "url", "ayuda"?}``; gana la primera que responda. El expediente y la bandeja muestran el
botón; así una pantalla nueva (M3, M5…) no tiene que tocar las de M1.
"""
from . import extensiones


def siguiente_paso(usuario, expediente):
    for funcion in extensiones.SIGUIENTES_PASOS:
        paso = funcion(usuario, expediente)
        if paso:
            return paso
    return None
