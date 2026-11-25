"""Puntos de extensión del núcleo. Las apps de cada módulo (dictamen, contrato, pagos…) se registran
aquí en su ``AppConfig.ready()`` para sumar lo suyo sin que el núcleo dependa de ellas.

- FILTROS_BANDEJA: funciones ``(usuario, queryset) -> queryset`` que afinan la bandeja de una unidad
  (por ejemplo, quitar de la bandeja de la Dirección lo que ya dictaminó).
- PANELES_BANDEJA: funciones ``(request) -> dict | None`` con ``plantilla`` y ``contexto`` de un
  panel extra en la bandeja (por ejemplo, acuerdos del Comité pendientes de cumplir).
- PESTANAS_EXPEDIENTE: dicts ``{"clave", "nombre", "plantilla", "contexto": fn(request, exp)}``
  que se agregan a la página del expediente.
- MENU: dicts ``{"nombre", "url", "grupo", "tipos": [tipos de unidad] | None}`` para la barra superior. ``grupo`` es el
  módulo (uno de ``GRUPOS_MENU``) bajo el que se despliega el enlace; sin grupo, el enlace va suelto. ``estricto`` impide que el superusuario sin unidad lo vea. Cada unidad ve solo
  los grupos y enlaces que le tocan; un grupo con un solo enlace para esa unidad se muestra como enlace simple.
- GRUPOS_MENU: orden de los grupos del menú.
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
- EXTRAS_BANDEJA: funciones ``(usuario) -> Q | None`` que suman a «por atender» expedientes que la unidad debe atender
  aunque su estado esté asignado a otra unidad (PSAHEM: la solicitud aceptada que la Secretaría Técnica debe remitir, P-26).
- SECCIONES_PORTAL: funciones ``(request, expediente, con_cuenta) -> {"plantilla", "contexto"} | None`` con una sección más
  de la pantalla del expediente en el portal de personas beneficiarias (HU-4.1: los envíos a la Delegación).
- AJUSTES_MONTO: funciones ``(expediente, monto) -> MontoAprobado | None`` que ajustan el monto del expediente
  (``nucleo.montos.monto_aprobado`` sin superficie ni condiciones explícitas). HU-4.2: la ministración que depende de la
  verificación se paga por lo verificado donde las reglas lo dicen.
- AL_INCIDENCIA: funciones ``(incidencia) -> None`` que corren al registrar una incidencia de la verificación en campo
  (HU-4.2); HU-6.2 conecta aquí el seguimiento de los incumplimientos.
- AL_REPORTE_INCUMPLIDO: funciones ``(evaluacion) -> None`` que corren, al enviar al CASPEG la evaluación de un periodo, por cada
  Guardabosque que no cumplió o no entregó su reporte (``ejecucion.models.EvaluacionPeriodo``; HU-4.3). HU-6.2 conecta aquí el
  seguimiento (suspensión por ministración o baja por tres reportes no presentados, PEG 8.1.9.1 a y 8.1.9.2 f).
- TRAZABILIDAD: funciones ``(expediente) -> [(etiqueta, historial)]`` con el historial (django-simple-history) de los
  registros del expediente que guarda cada módulo; la pestaña «Trazabilidad» los junta (``nucleo.trazabilidad``).
"""

FILTROS_BANDEJA = []
EXTRAS_BANDEJA = []
PANELES_BANDEJA = []
PESTANAS_EXPEDIENTE = []
GRUPOS_MENU = ["Recepción", "Dictamen y Comité", "Listados", "Publicación y contrato", "Pagos", "Ejecución y verificación",
               "Seguimiento y cierre"]
MENU = [{"nombre": "Registrar solicitud", "url": "recepcion:registrar", "grupo": "Recepción", "tipos": ["delegacion"],
         "estricto": True}]
REVISIONES_PLAZO = []
DEMOS = []
AL_NOTIFICAR = []
EVENTOS_PLAZO = {}
SUPERFICIE_APROBADA = []
SIGUIENTES_PASOS = []
AL_FIRMAR = []
AL_LIBERAR_RECURSO = []
SECCIONES_PORTAL = []
AJUSTES_MONTO = []
AL_INCIDENCIA = []
AL_REPORTE_INCUMPLIDO = []
TRAZABILIDAD = []
