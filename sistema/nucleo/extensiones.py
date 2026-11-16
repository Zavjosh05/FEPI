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
- EVENTOS_PLAZO: ``{evento: fn(expediente, config) -> datetime | None}`` para eventos de arranque de
  plazo que no se registran como ``Hito`` (``nucleo.plazos``). Lo normal es registrar un Hito.
- SUPERFICIE_APROBADA: funciones ``(expediente) -> Decimal | None`` con la superficie que cuenta para el
  monto (``nucleo.montos``); la primera que no dé None gana (M2: la superficie factible del dictamen).
- SIGUIENTES_PASOS: funciones ``(usuario, expediente) -> {"texto", "url", "ayuda"} | None`` con el botón
  del siguiente paso que se muestra en el expediente (``nucleo.pasos``); gana la primera que responda.
- AL_FIRMAR: funciones ``(firma) -> None`` que corren cuando la Delegación registra la firma del contrato
  (HU-3.3); M3.4 las usa para dejar el Vale de Planta entregado antes de la firma en el estado que toca.
- AL_LIBERAR_RECURSO: funciones ``(expediente, usuario) -> None`` que corren cuando el área responsable confirma
  la liberación del recurso de un contrato sin firma en plazo (HU-3.3). Gancho para la reasignación a la lista de
  espera por acuerdo del Comité (sprint 3, flujo alterno D).
"""

FILTROS_BANDEJA = []
PANELES_BANDEJA = []
PESTANAS_EXPEDIENTE = []
MENU = []
REVISIONES_PLAZO = []
DEMOS = []
AL_NOTIFICAR = []
EVENTOS_PLAZO = {}
SUPERFICIE_APROBADA = []
SIGUIENTES_PASOS = []
AL_FIRMAR = []
AL_LIBERAR_RECURSO = []
