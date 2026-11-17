"""Registro del módulo M4 (Ejecución y verificación) en los puntos de extensión del núcleo.

Pestaña «Ejecución» del expediente, menú «Ejecución y verificación», paneles de bandeja, siguiente paso, la sección «Mis
envíos» del portal y las fuentes de soporte de pago que llena cada historia (HU-4.1: ``entregable``), igual que
``contrato/registro.py`` y ``pagos/registro.py``.
"""
from django.urls import reverse

from nucleo import extensiones
from nucleo.models import TipoUnidad

HISTORIAS = [
    ("HU-4.1", "Envío de comprobaciones", "registra cada comprobación (informe, bitácora, solicitud o Plan de auditoría) con su acuse, en la Delegación o desde el portal"),
    ("HU-4.2", "Verificación en campo", "registra el resultado con la superficie verificada y su ajuste, y las incidencias con su tipo y documento, dentro del plazo de entrega"),
    ("HU-4.3", "Evaluación de reportes", "PEG: evaluación por Guardabosque y por periodo, e identifica quién no entregó su reporte"),
]
HISTORIAS_CONSTRUIDAS = {"HU-4.1"}
USOS_DE_PLAZO = ['fecha_limite_conclusion', 'entrega_comprobacion', 'reporte_mensual']


def historias_pendientes():
    return [h for h in HISTORIAS if h[0] not in HISTORIAS_CONSTRUIDAS]


def contexto_pestana(request, exp):
    from .vistas.comun import contexto_ejecucion

    return contexto_ejecucion(request, exp)


def _pestana(exp):
    return reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=ejecucion"


def siguiente_paso(usuario, exp):
    """Siguiente paso de M4 en el expediente."""
    if usuario.tipo_unidad == TipoUnidad.DELEGACION and usuario.unidad_id == exp.delegacion_id:
        pendiente = exp.comprobaciones.filter(medio="portal", revisada_en__isnull=True).order_by("enviada_en").first()
        if pendiente is not None:
            return {"texto": f"Revisar lo recibido por el portal: {pendiente.nombre.lower()}", "url": _pestana(exp),
                    "ayuda": f"Llegó el {pendiente.enviada_en:%d/%m/%Y} con el acuse {pendiente.acuse.folio if pendiente.acuse else ''}."}
    return None


def panel_por_revisar(request):
    from . import comprobaciones

    if request.user.tipo_unidad != TipoUnidad.DELEGACION:
        return None
    pendientes = list(comprobaciones.por_revisar(request.user).order_by("enviada_en")[:50])
    if not pendientes:
        return None
    filas = [{"url": _pestana(c.expediente), "texto": c.expediente.folio,
              "detalle": f"{c.nombre} · {c.enviada_en:%d/%m/%Y %H:%M} h"} for c in pendientes[:6]]
    return {"plantilla": "pagos/_panel.html", "contexto": {
        "clave": "panel-comprobaciones-por-revisar", "titulo": "Comprobaciones recibidas por el portal, por revisar",
        "total": len(pendientes), "filas": filas, "enlace": reverse("ejecucion:comprobaciones"),
        "ayuda": "Ya tienen su acuse con la fecha y la hora del envío; revíselas y márquelas como revisadas.",
        "accion": "Abrir las comprobaciones"}}


def registrar():
    if contexto_pestana in [p["contexto"] for p in extensiones.PESTANAS_EXPEDIENTE]:
        return
    extensiones.PESTANAS_EXPEDIENTE.append({"clave": "ejecucion", "nombre": "Ejecución",
                                            "plantilla": "ejecucion/pestana_ejecucion.html", "contexto": contexto_pestana})
    extensiones.SIGUIENTES_PASOS.append(siguiente_paso)
    extensiones.PANELES_BANDEJA.append(panel_por_revisar)
    T = TipoUnidad
    extensiones.MENU.append({"nombre": "Ejecución", "url": "ejecucion:comprobaciones", "grupo": "Ejecución y verificación",
                             "tipos": [T.DELEGACION, T.DIRECCION, T.JURIDICA]})
    from pagos import solicitudes

    from . import comprobaciones
    from .vistas.portal import seccion_portal

    solicitudes.FUENTES["entregable"] = comprobaciones.fuente_entregable  # HU-4.1: segunda ministración de MFS
    extensiones.SECCIONES_PORTAL.append(seccion_portal)
    extensiones.DEMOS.append(cargar_demo)


def cargar_demo():
    from .demo import cargar_demo as cargar

    return cargar()
