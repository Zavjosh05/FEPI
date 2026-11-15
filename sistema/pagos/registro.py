"""Registro del módulo M5 (Pagos) en los puntos de extensión del núcleo.

Cada historia agrega aquí lo suyo (filtros y paneles de bandeja de Administración y Finanzas y de la
Fiduciaria, menú, revisión de plazos, siguiente paso, receptores de acuerdos del Comité), igual que
``dictamen/registro.py``.
"""
from nucleo import extensiones

HISTORIAS = [
    ("HU-5.1", "Solicitud de pago", "solicita cada ministración con el contrato, el oficio y la verificación"),
    ("HU-5.2", "Pago de la ministración", "Administración y Finanzas paga o, en PSAHEM, remite a la Fiduciaria"),
    ("HU-5.3", "Entrega de cheques", "la Fiduciaria emite y envía los cheques; la Delegación los entrega (PSAHEM)"),
]
USOS_DE_PLAZO = ["instruccion_pago_fiduciaria", "cobro_cheque"]


def contexto_pestana(request, exp):
    from .vistas.comun import contexto_pagos

    return contexto_pagos(request, exp)


def registrar():
    if contexto_pestana in [p["contexto"] for p in extensiones.PESTANAS_EXPEDIENTE]:
        return
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "pagos", "nombre": "Pagos",
                                            "plantilla": "pagos/pestana_pagos.html", "contexto": contexto_pestana})
