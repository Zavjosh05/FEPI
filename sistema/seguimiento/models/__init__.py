"""Modelos del módulo M6 (Seguimiento y cierre), **un módulo por historia** para que cada historia traiga su propia migración:

- ``reasignacion.py``  HU-6.1 Lista de espera y sustituciones (``Propuesta``, ``SolicitudPersona``,
  ``Prorroga``)
- ``incumplimientos.py``  HU-6.2 Incumplimientos y reintegros (``AvisoOmision``, ``Senalamiento``, ``CuentaReintegro``,
  ``Requerimiento``)
- ``cierre.py``  HU-6.3 Cierre del ejercicio (``CierreExpediente``, ``PadronPublicacion``, ``InformeAnual``)

Cada historia crea su archivo, lo importa aquí y genera su migración con
``python manage.py makemigrations seguimiento -n hu_6_1_reasignacion``. Hechos: HU-6.1, HU-6.2 y HU-6.3. ``Propuesta`` (propuesta del área
responsable al Comité, ligada al acuerdo que la resuelve) es común: HU-6.2 suma sus tipos.

Ganchos que ya existen y que estas historias llenan (no hay que tocar el núcleo):

- Acuerdos del Comité: ``dictamen.seguimiento.RECEPTORES`` (tipo de acuerdo -> funciones): reasignación y sustitución
  (HU-6.1), caso fortuito, suspensión, cancelación, baja y reintegro (HU-6.2). ``extensiones.AL_LIBERAR_RECURSO`` corre al
  liberar el recurso de un contrato sin firma (HU-6.1 propone la reasignación).
- Estados: ``caso_fortuito`` (D), ``suspendida``, ``omisiones_por_subsanar``, ``cancelada``, ``en_devolucion``,
  ``reintegrada`` (E), ``sustitucion`` (F), ``prorroga_solicitada`` (G, solo MFS; el modelo ``contrato.Adendum`` ya
  existe) y ``ejercicio_cerrado``.
- Plazos: ``aviso_caso_fortuito`` (hito ``siniestro``), ``interes_segunda_beneficiaria`` (hito ``fallecimiento_titular``)
  y ``subsanar_omisiones`` (hito ``aviso_omision`` con ``datos["vence"]``, el plazo que fija el área); se registran con
  ``nucleo.plazos.registrar_hito`` y los avisa ``nucleo.avisos``.
- Notificaciones de omisión y devolución: ``nucleo.notificaciones`` (tipos ``omision`` y ``devolucion``).
- Listado de Personas Beneficiarias Incumplidas: el catálogo de HU-2.2 (``dictamen``).
"""
from .reasignacion import (EstadoPropuesta, MedioSolicitud, Propuesta, Prorroga,  # noqa: E402,F401
                           SolicitudPersona)
from .incumplimientos import (AvisoOmision, CuentaReintegro, EstadoRequerimiento, Requerimiento,  # noqa: E402,F401
                              Senalamiento)
from .cierre import CierreExpediente, InformeAnual, PadronPublicacion  # noqa: E402,F401
