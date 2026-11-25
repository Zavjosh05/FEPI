"""Puntos de extensión del núcleo. Las apps de cada módulo (dictamen, contrato, pagos…) se registran
aquí en su ``AppConfig.ready()`` para sumar lo suyo sin que el núcleo dependa de ellas.

- FILTROS_BANDEJA: funciones ``(usuario, queryset) -> queryset`` que afinan la bandeja de una unidad
  (por ejemplo, quitar de la bandeja de la Dirección lo que ya dictaminó).
- PANELES_BANDEJA: funciones ``(request) -> dict | None`` con ``plantilla`` y ``contexto`` de un
  panel extra en la bandeja (por ejemplo, acuerdos del Comité pendientes de cumplir).
- PESTANAS_EXPEDIENTE: dicts ``{"clave", "nombre", "plantilla", "contexto": fn(request, exp)}``
  que se agregan a la página del expediente.
- MENU: dicts ``{"nombre", "url", "tipos": [tipos de unidad] | None, "grupo": opcional}`` para la barra superior;
  las opciones con el mismo «grupo» se juntan en un menú desplegable.
- REVISIONES_PLAZO: funciones ``(fecha) -> int`` que corre ``manage.py revisar_plazos``.
- DEMOS: funciones ``() -> int`` que agregan datos de demostración (``manage.py cargar_demo``).
- TRAZABILIDAD: funciones ``(expediente) -> [(etiqueta, historial)]`` con el historial (django-simple-history) de los
  registros del expediente que guarda cada módulo; la pestaña «Trazabilidad» los junta (``nucleo.trazabilidad``).
"""

FILTROS_BANDEJA = []
PANELES_BANDEJA = []
PESTANAS_EXPEDIENTE = []
MENU = []
REVISIONES_PLAZO = []
DEMOS = []
TRAZABILIDAD = []
