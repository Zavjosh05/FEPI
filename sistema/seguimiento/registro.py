"""Registro del módulo M6 (Seguimiento y cierre) en los puntos de extensión del núcleo.

Hoy solo agrega la pestaña «Seguimiento» del expediente, que dice qué historia la llenará y muestra el monto aprobado y los
plazos de la etapa. Cada historia suma aquí lo suyo (filtros y paneles de bandeja, menú, revisión de plazos, siguiente paso,
receptores de acuerdos del Comité y datos de demostración), igual que ``contrato/registro.py`` y ``pagos/registro.py``.
"""
from nucleo import extensiones, montos, plazos

HISTORIAS = [
    ("HU-6.1", "Lista de espera y sustituciones", "propone la reasignación del recurso liberado en el orden de la lista de espera y registra sustituciones y desistimientos con su acuse"),
    ("HU-6.2", "Incumplimientos y reintegros", "registra cada omisión con su plazo, el caso fortuito, la cancelación, el requerimiento de devolución con monto y cuenta, el reintegro y el Listado de Incumplidas"),
    ("HU-6.3", "Cierre del ejercicio", "cuadra los resultados finales con las verificaciones y los pagos, publica el padrón y registra el envío del informe al Comité"),
]
HISTORIAS_CONSTRUIDAS = set()
USOS_DE_PLAZO = ['aviso_caso_fortuito', 'interes_segunda_beneficiaria', 'subsanar_omisiones']


def historias_pendientes():
    return [h for h in HISTORIAS if h[0] not in HISTORIAS_CONSTRUIDAS]


def contexto_pestana(request, exp):
    """Cada historia suma aquí lo suyo a la pestaña."""
    return {"historias": historias_pendientes(), "monto": montos.monto_si_aprobado(exp),
            "vencimientos": [v for v in plazos.vencimientos(exp, USOS_DE_PLAZO).values() if v is not None]}


def registrar():
    if contexto_pestana in [p["contexto"] for p in extensiones.PESTANAS_EXPEDIENTE]:
        return
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "seguimiento", "nombre": "Seguimiento",
                                            "plantilla": "seguimiento/pestana_seguimiento.html", "contexto": contexto_pestana})
