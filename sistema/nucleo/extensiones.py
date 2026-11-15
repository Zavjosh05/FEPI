"""Puntos de extensión del núcleo. Las apps de cada módulo (dictamen, contrato, pagos…) se registran
aquí en su ``AppConfig.ready()`` para sumar lo suyo sin que el núcleo dependa de ellas.

- FILTROS_BANDEJA: funciones ``(usuario, queryset) -> queryset`` que afinan la bandeja de una unidad
  (por ejemplo, quitar de la bandeja de la Dirección lo que ya dictaminó).
- PANELES_BANDEJA: funciones ``(request) -> dict | None`` con ``plantilla`` y ``contexto`` de un
  panel extra en la bandeja (por ejemplo, acuerdos del Comité pendientes de cumplir).
- PESTANAS_EXPEDIENTE: dicts ``{"clave", "nombre", "plantilla", "contexto": fn(request, exp)}``
  que se agregan a la página del expediente.
- MENU: dicts ``{"nombre", "url", "tipos": [tipos de unidad] | None}`` para la barra superior.
- REVISIONES_PLAZO: funciones ``(fecha) -> int`` que corre ``manage.py revisar_plazos``.
- DEMOS: funciones ``() -> int`` que agregan datos de demostración (``manage.py cargar_demo``).
- AL_NOTIFICAR: funciones ``(notificacion) -> None`` que corren cuando la Delegación registra que
  notificó a la persona (``nucleo.notificaciones.registrar_notificacion``).
"""

FILTROS_BANDEJA = []
PANELES_BANDEJA = []
PESTANAS_EXPEDIENTE = []
MENU = []
REVISIONES_PLAZO = []
DEMOS = []
AL_NOTIFICAR = []
