"""Días hábiles y vencimientos.

Reglas (documentadas en el README):
- Son inhábiles los sábados, los domingos y las fechas del catálogo DiaInhabil (editable en el admin).
- Un plazo en días hábiles empieza a contar el día hábil siguiente al del evento que lo dispara
  (recepción, notificación…): 5 días hábiles desde el lunes vencen el lunes siguiente.
- Un plazo en días naturales, meses o años se cuenta en calendario; si el último día es inhábil,
  el vencimiento pasa al siguiente día hábil.
"""
import calendar
from datetime import date, datetime, timedelta

from django.utils import timezone

UNIDADES_CALCULABLES = {"dias_habiles", "dias_naturales", "meses", "anios"}


def _como_fecha(valor):
    if isinstance(valor, datetime):
        if timezone.is_aware(valor):
            valor = timezone.localtime(valor)
        return valor.date()
    return valor


def dias_inhabiles(desde=None, hasta=None):
    from .models import DiaInhabil

    qs = DiaInhabil.objects.all()
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)
    return set(qs.values_list("fecha", flat=True))


def es_habil(fecha, inhabiles=None):
    fecha = _como_fecha(fecha)
    if fecha.weekday() >= 5:
        return False
    if inhabiles is None:
        inhabiles = dias_inhabiles(fecha, fecha)
    return fecha not in inhabiles


def siguiente_habil(fecha, inhabiles=None, incluir_mismo_dia=True):
    fecha = _como_fecha(fecha)
    if inhabiles is None:
        inhabiles = dias_inhabiles(fecha, fecha + timedelta(days=60))
    if not incluir_mismo_dia:
        fecha += timedelta(days=1)
    while not es_habil(fecha, inhabiles):
        fecha += timedelta(days=1)
    return fecha


def sumar_dias_habiles(inicio, dias):
    """Fecha en que se cumplen ``dias`` días hábiles contados desde el día siguiente a ``inicio``."""
    inicio = _como_fecha(inicio)
    if dias < 0:
        raise ValueError("Los días deben ser positivos.")
    # Margen holgado para traer los inhábiles de una sola consulta.
    inhabiles = dias_inhabiles(inicio, inicio + timedelta(days=dias * 3 + 60))
    fecha = inicio
    contados = 0
    while contados < dias:
        fecha += timedelta(days=1)
        if es_habil(fecha, inhabiles):
            contados += 1
    return fecha


def dias_habiles_entre(inicio, fin):
    """Días hábiles después de ``inicio`` y hasta ``fin`` (inclusive). Negativo si fin < inicio."""
    inicio, fin = _como_fecha(inicio), _como_fecha(fin)
    signo = 1
    if fin < inicio:
        inicio, fin, signo = fin, inicio, -1
    inhabiles = dias_inhabiles(inicio, fin)
    n = 0
    fecha = inicio
    while fecha < fin:
        fecha += timedelta(days=1)
        if es_habil(fecha, inhabiles):
            n += 1
    return n * signo


def sumar_meses(fecha, meses):
    fecha = _como_fecha(fecha)
    mes = fecha.month - 1 + meses
    anio = fecha.year + mes // 12
    mes = mes % 12 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def calcular_vencimiento(inicio, cantidad, unidad):
    """Vencimiento de un plazo (cantidad + unidad) que corre desde ``inicio``."""
    if cantidad is None or unidad not in UNIDADES_CALCULABLES:
        raise ValueError(f"El plazo «{cantidad} {unidad}» no se puede calcular como fecha.")
    if unidad == "dias_habiles":
        return sumar_dias_habiles(inicio, cantidad)
    inicio = _como_fecha(inicio)
    if unidad == "dias_naturales":
        fin = inicio + timedelta(days=cantidad)
    elif unidad == "meses":
        fin = sumar_meses(inicio, cantidad)
    else:
        fin = sumar_meses(inicio, 12 * cantidad)
    return siguiente_habil(fin)


def vencimiento_de_plazo(plazo, inicio):
    """Igual que calcular_vencimiento, con un objeto Plazo del ejercicio."""
    return calcular_vencimiento(inicio, plazo.cantidad, plazo.unidad)
