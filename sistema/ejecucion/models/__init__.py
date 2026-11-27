"""Modelos del módulo M4 (Ejecución y verificación), **un módulo por historia** para que cada historia traiga su propia migración:

- ``comprobaciones.py``  HU-4.1 Envío de comprobaciones
- ``verificacion.py``  HU-4.2 Verificación en campo
- ``reportes.py``  HU-4.3 Evaluación de reportes

Cada historia crea su archivo, lo importa aquí y genera su migración con
``python manage.py makemigrations ejecucion -n hu_4_1_comprobaciones``. Hechos: HU-4.1 (``Comprobacion``), HU-4.2 (``Verificacion``, ``Incidencia``) y HU-4.3 (``RevisionReporte``,
``EvaluacionPeriodo``, ``EnvioEvaluacion``).

Ganchos que ya existen y que estas historias llenan (no hay que tocar el núcleo):

- ``pagos.solicitudes.FUENTES``: HU-4.1 reemplaza ``"entregable"`` (MFS: Bitácora o autorización en ETF; solicitud o Plan
  de auditoría en FSC), HU-4.2 ``"verificacion_campo"`` (CC, PS, RHF, PSAHEM) y HU-4.3 ``"evaluacion_reportes"`` (PEG: la evaluación
  del periodo validada por el CASPEG). Con la función nueva la segunda ministración deja de estar bloqueada.
- Estados (``datos/flujo_tramite.json``): ``en_ejecucion``, ``comprobacion_enviada``, ``verificada``, ``concluida`` y, en
  PEG, ``reporte_entregado`` y ``reportes_evaluados``. Cambiarlos solo con ``Expediente.cambiar_estado``.
- Plazos (``nucleo.plazos.vencimiento``): ``entrega_comprobacion`` (R-04: plazo de ENTREGA del informe o del documento de
  verificación, desde la fecha límite de conclusión), ``fecha_limite_conclusion`` y ``reporte_mensual`` (PEG); los avisa
  ``nucleo.avisos`` (panel «Por vencer»).
- Portal: ``portal.models.AccesoExpediente`` dice qué expedientes ve cada persona (y si es el prestador con RFN): las
  comprobaciones que lleguen por el portal se registran con el mismo servicio que las de la Delegación.
- Superficie verificada: ``extensiones.SUPERFICIE_APROBADA`` admite una función que dé la superficie verificada para que
  ``nucleo.montos`` ajuste la segunda ministración.
"""
from .comprobaciones import Comprobacion, MedioEnvio  # noqa: E402,F401
from .verificacion import Incidencia, ResultadoVerificacion, Verificacion  # noqa: E402,F401
from .reportes import (EnvioEvaluacion, EvaluacionPeriodo, ResultadoEvaluacion, ResultadoRevision,  # noqa: E402,F401
                       RevisionReporte)
