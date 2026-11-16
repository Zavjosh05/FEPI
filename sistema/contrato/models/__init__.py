"""Modelos del módulo M3 (Publicación y contrato), **un módulo por historia** para que cada historia traiga su
propia migración:

- ``publicacion.py``  HU-3.1 Publicación y notificaciones
- ``contrato.py``     HU-3.2 Elaboración del contrato
- ``firma.py``        HU-3.3 Firma del contrato
- ``planta.py``       HU-3.4 Entrega de planta

Cada historia crea su archivo, lo importa aquí (``from .publicacion import *``) y genera su migración con
``python manage.py makemigrations contrato -n hu_3_1_publicacion``. Lo que ya da el núcleo y no debe
duplicarse: notificaciones (``nucleo.notificaciones``), plazos y eventos de arranque (``nucleo.plazos``:
registrar ``publicacion_resultados``, ``firma_contrato`` y ``entrega_vale`` como hitos), monto aprobado y
ministraciones (``nucleo.montos``), estados (``datos/flujo_tramite.json``, siempre con
``Expediente.cambiar_estado``) y acuses (``nucleo.acuses.emitir_acuse``).
"""

from .publicacion import Publicacion, ResultadoPublicado  # noqa: E402,F401
from .contratos import (  # noqa: E402,F401
    Adendum, Contrato, EstadoContrato, EstadoVersion, ModeloContrato, TipoModelo, VersionModelo,
)
from .firma import ElementoFormalizacion, FirmaContrato, Firmante, SinFirma  # noqa: E402,F401
from .planta import Especie, RenglonVale, SalidaPlanta, ValePlanta, Vivero  # noqa: E402,F401
