"""Registro del módulo M3 (Publicación y contrato) en los puntos de extensión del núcleo.

Cada historia agrega aquí lo suyo (filtros y paneles de bandeja, menú, revisión de plazos, siguiente paso,
receptores de notificación y datos de demostración), igual que ``dictamen/registro.py``.
"""
from nucleo import extensiones

HISTORIAS = [
    ("HU-3.1", "Publicación y notificaciones", "publica los listados y envía los avisos por conducto de la Delegación"),
    ("HU-3.2", "Elaboración del contrato", "elabora el contrato sobre el modelo validado por la Unidad Jurídica"),
    ("HU-3.3", "Firma del contrato", "cita a la persona, recaba su firma y señala lo que no se firmó en plazo"),
    ("HU-3.4", "Entrega de planta", "valida el Vale de Planta y registra la salida por especie y cantidad"),
]
USOS_DE_PLAZO = ["cita_firma", "firma_programada", "firma_liberacion", "ptrfi_actualizado", "recoger_planta"]


def contexto_pestana(request, exp):
    from .vistas.comun import contexto_contrato

    return contexto_contrato(request, exp)


def siguiente_paso(usuario, exp):
    """Mientras HU-3.1 no exista, lo aprobado lleva a la pestaña que dice qué sigue (P-17)."""
    from django.urls import reverse

    from nucleo.models import TipoUnidad

    if exp.estado.clave == "aprobada" and usuario.tipo_unidad == TipoUnidad.DIRECCION:
        return {"texto": "Ver lo que sigue: publicación y contrato",
                "url": reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=contrato",
                "ayuda": "La publicación de resultados la construye HU-3.1."}
    return None


def registrar():
    if contexto_pestana in [p["contexto"] for p in extensiones.PESTANAS_EXPEDIENTE]:
        return
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "contrato", "nombre": "Contrato",
                                            "plantilla": "contrato/pestana_contrato.html", "contexto": contexto_pestana})
    extensiones.SIGUIENTES_PASOS.append(siguiente_paso)
    extensiones.DEMOS.append(cargar_demo)


def cargar_demo():
    from .demo import cargar_demo as cargar

    return cargar()
