"""Registro del módulo M5 (Pagos) en los puntos de extensión del núcleo.

Cada historia agrega aquí lo suyo (filtros y paneles de bandeja de Delegación, área responsable, Administración y Finanzas y
Fiduciaria, menú, revisión de plazos, siguiente paso, receptores de acuerdos del Comité), igual que ``contrato/registro.py``.
"""
from django.urls import reverse

from nucleo import extensiones
from nucleo.models import TipoUnidad

HISTORIAS = [
    ("HU-5.1", "Solicitud de pago", "solicita cada ministración con el contrato, el oficio y la verificación"),
    ("HU-5.2", "Pago de la ministración", "Administración y Finanzas paga o, en PSAHEM, remite a la Fiduciaria"),
    ("HU-5.3", "Entrega de cheques", "la Fiduciaria emite y envía los cheques; la Delegación los entrega (PSAHEM)"),
]
HISTORIAS_CONSTRUIDAS = {"HU-5.1"}
USOS_DE_PLAZO = ["instruccion_pago_fiduciaria", "cobro_cheque"]


def historias_pendientes():
    return [h for h in HISTORIAS if h[0] not in HISTORIAS_CONSTRUIDAS]


def contexto_pestana(request, exp):
    from .vistas.comun import contexto_pagos

    return contexto_pagos(request, exp)


def _pestana(exp):
    return reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=pagos"


def siguiente_paso(usuario, exp):
    """Siguiente paso de M5 en el expediente."""
    from . import solicitudes

    estado, tipo = exp.estado.clave, usuario.tipo_unidad
    firmado = getattr(exp, "firma_contrato", None) is not None
    if tipo == TipoUnidad.DELEGACION and firmado and getattr(exp, "oficio_pago", None) is None and estado not in (
            "sin_firma_en_plazo", "recurso_liberado"):
        return {"texto": "Emitir el oficio de solicitud de pago", "url": _pestana(exp),
                "ayuda": "El contrato ya está firmado: el oficio de la Delegación es soporte de la solicitud de pago."}
    if tipo == TipoUnidad.DIRECCION and estado in solicitudes.ESTADOS_PARA_SOLICITAR:
        fila = solicitudes.siguiente_por_solicitar(exp)
        if fila is not None and fila["puede"]:
            return {"texto": f"Solicitar la ministración {fila['numero']}", "url": _pestana(exp),
                    "ayuda": ("Falta " + ", ".join(s["nombre"].lower() for s in fila["faltan"]) + "."
                              if fila["faltan"] else "Soportes completos: se puede enviar a Administración y Finanzas.")}
    return None


def panel_oficios_por_emitir(request):
    from . import solicitudes

    if request.user.tipo_unidad != TipoUnidad.DELEGACION:
        return None
    pendientes = list(solicitudes.sin_oficio(request.user))
    if not pendientes:
        return None
    filas = [{"url": reverse("pagos:expediente", args=[e.folio]), "texto": e.folio,
              "detalle": f"{e.solicitante.nombre} · {e.predio.nombre}"} for e in pendientes[:6]]
    return {"plantilla": "pagos/_panel.html", "contexto": {
        "clave": "panel-oficios-por-emitir", "titulo": "Contratos firmados por emitir el oficio de solicitud de pago",
        "total": len(pendientes), "filas": filas, "enlace": reverse("pagos:solicitudes"),
        "accion": "Abrir las solicitudes de pago"}}


def panel_por_solicitar(request):
    from . import solicitudes

    if request.user.tipo_unidad != TipoUnidad.DIRECCION:
        return None
    pendientes = solicitudes.por_solicitar(request.user)
    if not pendientes:
        return None
    filas = [{"url": reverse("pagos:expediente", args=[f["exp"].folio]), "texto": f["exp"].folio,
              "detalle": f"{f['exp'].solicitante.nombre} · ministración {f['fila']['numero']}"
                         + (" (devuelta)" if f["fila"]["solicitud"] and f["fila"]["solicitud"].estado == "devuelta" else "")
                         + (" · faltan soportes" if f["fila"]["faltan"] else " · soportes completos")}
             for f in pendientes[:6]]
    return {"plantilla": "pagos/_panel.html", "contexto": {
        "clave": "panel-por-solicitar", "titulo": "Ministraciones por solicitar", "total": len(pendientes), "filas": filas,
        "enlace": reverse("pagos:solicitudes"), "accion": "Abrir las solicitudes de pago"}}


def registrar():
    if contexto_pestana in [p["contexto"] for p in extensiones.PESTANAS_EXPEDIENTE]:
        return
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "pagos", "nombre": "Pagos",
                                            "plantilla": "pagos/pestana_pagos.html", "contexto": contexto_pestana})
    extensiones.SIGUIENTES_PASOS.append(siguiente_paso)
    extensiones.PANELES_BANDEJA.extend([panel_oficios_por_emitir, panel_por_solicitar])
    T = TipoUnidad
    extensiones.MENU.append({"nombre": "Pagos", "url": "pagos:solicitudes",
                             "tipos": [T.DELEGACION, T.DIRECCION, T.JURIDICA, T.ADMIN_FINANZAS]})
    extensiones.DEMOS.append(cargar_demo)


def cargar_demo():
    from .demo import cargar_demo as cargar

    return cargar()
