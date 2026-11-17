"""Registro del módulo M4 (Ejecución y verificación) en los puntos de extensión del núcleo.

Hoy solo agrega la pestaña «Ejecución» del expediente, que dice qué historia la llenará y muestra el monto aprobado y los
plazos de la etapa. Cada historia suma aquí lo suyo (filtros y paneles de bandeja, menú, revisión de plazos, siguiente paso,
receptores de acuerdos del Comité y datos de demostración), igual que ``contrato/registro.py`` y ``pagos/registro.py``.
"""
from nucleo import extensiones, montos, plazos

HISTORIAS = [
    ("HU-4.1", "Envío de comprobaciones", "registra cada comprobación (informe, bitácora, solicitud o Plan de auditoría) con su acuse, en la Delegación o desde el portal"),
    ("HU-4.2", "Verificación en campo", "registra el resultado con la superficie verificada y su ajuste, y las incidencias con su tipo y documento, dentro del plazo de entrega"),
    ("HU-4.3", "Evaluación de reportes", "PEG: evaluación por Guardabosque y por periodo, e identifica quién no entregó su reporte"),
]
HISTORIAS_CONSTRUIDAS = set()
USOS_DE_PLAZO = ['fecha_limite_conclusion', 'entrega_comprobacion', 'reporte_mensual']


def historias_pendientes():
    return [h for h in HISTORIAS if h[0] not in HISTORIAS_CONSTRUIDAS]


def contexto_pestana(request, exp):
    """Cada historia suma aquí lo suyo a la pestaña."""
    return {"historias": historias_pendientes(), "monto": montos.monto_si_aprobado(exp),
            "vencimientos": [v for v in plazos.vencimientos(exp, USOS_DE_PLAZO).values() if v is not None]}


def registrar():
    if contexto_pestana in [p["contexto"] for p in extensiones.PESTANAS_EXPEDIENTE]:
        return
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "ejecucion", "nombre": "Ejecución",
                                            "plantilla": "ejecucion/pestana_ejecucion.html", "contexto": contexto_pestana})
    extensiones.DEMOS.append(cargar_demo)


def cargar_demo():
    from .demo import cargar_demo as cargar

    return cargar()
