"""Modelos del módulo M5 (Pagos), **un módulo por historia** para que cada historia traiga su propia migración:

- ``solicitudes.py``  HU-5.1 Solicitud de pago (oficio de la Delegación, comprobante y solicitud por ministración)
- ``pagos.py``        HU-5.2 Pago de la ministración (revisión, pago o remisión a la Fiduciaria en PSAHEM)
- ``cheques.py``      HU-5.3 Entrega de cheques (PSAHEM)

Cada historia crea su archivo, lo importa aquí y genera su migración con
``python manage.py makemigrations pagos -n hu_5_1_solicitudes``. Lo que ya da el núcleo: el monto y las
ministraciones de cada expediente (``nucleo.montos.monto_aprobado``: número, porcentaje, importe y condición),
los estados de pago por ministración (``datos/flujo_tramite.json``: ministracion_solicitada, pagada,
remitida_fiduciaria, cheque_emitido, cheque_enviado, cheque_entregado), los plazos (``nucleo.plazos``: usos
``instruccion_pago_fiduciaria`` y ``cobro_cheque``, eventos ``solicitud_pago_fiduciaria`` y ``entrega_cheque``
como hitos), las notificaciones y los acuses. Los acuerdos del Comité de instrucción de pago llegan por
``dictamen.seguimiento.RECEPTORES``.
"""
from .solicitudes import ComprobanteCuenta, EstadoSolicitud, OficioPago, SolicitudPago  # noqa: F401
from .pagos import Pago, RemisionFiduciaria, ResultadoRevision, RevisionSolicitud, TipoPagoRegistrado  # noqa: E402,F401
