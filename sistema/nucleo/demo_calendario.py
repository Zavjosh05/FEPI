"""Calendario de la demostración (G-03, P-03): fechas verosímiles de la Convocatoria 2026 para cada paso.

La carga de demostración corre con el reloj simulado (``nucleo.reloj``): cada paso ocurre en la fecha que le toca en el calendario
de su programa (``calendario_convocatoria`` de ``reglas/<CLAVE>.json``: recepción del 28-ene al 27-mar; dictaminación hasta el 30-jun
en CC y PSAHEM y hasta el 30-abr en PS y RHF; aprobación del Comité del 1 al 31-jul en CC y PSAHEM) y no en el día en que se corre.
Así la carga da lo mismo cualquier día en que se ejecute.

**Fecha de corte.** Es el «hoy» de la demostración: el momento con el que termina la carga y con el que se señalan lo vencido y lo
por vencer (contratos sin firma, remisiones, cheques por vencer). Por omisión es el 19-nov-2026 y se cambia con la variable de
entorno ``DEMO_FECHA_CORTE`` (AAAA-MM-DD). Los casos «en plazo» y «por vencer» se arman hacia atrás desde la fecha de corte
(por ejemplo, el cheque por vencer se entregó 88 días antes), y los vencidos por el calendario del programa. Una vez cargada, el
reloj del sistema es el real: los plazos de una demostración vieja se ven como vencidos, como en cualquier expediente real.
"""
import os
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from . import dias_habiles

CORTE_POR_OMISION = date(2026, 11, 19)


def fecha_corte():
    """Fecha de corte de la demostración (``DEMO_FECHA_CORTE`` o el 19-nov-2026)."""
    valor = os.environ.get("DEMO_FECHA_CORTE", "").strip()
    return date.fromisoformat(valor) if valor else CORTE_POR_OMISION


def cuando(fecha, hora=10, minuto=0):
    """Momento (con zona horaria de México) de una fecha: ``cuando("2026-03-09", 11, 30)``."""
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    return timezone.make_aware(datetime.combine(fecha, time(hora, minuto)))


def habil(fecha, n=0):
    """El día hábil que está ``n`` días hábiles después de ``fecha`` (``n=0``: ``fecha`` si es hábil, o el siguiente hábil).
    Los días hábiles cuentan sábados, domingos y el catálogo de días inhábiles como no laborables."""
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    if n == 0:
        return dias_habiles.siguiente_habil(fecha)
    return dias_habiles.sumar_dias_habiles(fecha, n)


def antes_del_corte(dias):
    """Fecha ``dias`` días naturales antes de la fecha de corte."""
    return fecha_corte() - timedelta(days=dias)


def habil_antes(fecha, n):
    """El día hábil que está ``n`` días hábiles antes de ``fecha``."""
    if isinstance(fecha, str):
        fecha = date.fromisoformat(fecha)
    contados = 0
    while contados < n:
        fecha -= timedelta(days=1)
        if dias_habiles.es_habil(fecha):
            contados += 1
    return fecha
