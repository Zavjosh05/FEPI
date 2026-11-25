"""Calendario de la demostración (G-03, P-03, D-32): fechas verosímiles de la Convocatoria 2026 para cada paso.

La carga de demostración corre con el reloj simulado (``nucleo.reloj``): cada paso ocurre en la fecha que le toca y no en el
instante en que se corre. Hay dos clases de pasos:

* **Los de la recepción y el dictamen** (enero a julio) y lo que ya concluyó (el segundo lote de PS y RHF, con sus firmas de
  octubre; los pagos de septiembre) van fijos en el calendario de su programa (``calendario_convocatoria`` de
  ``reglas/<CLAVE>.json``: recepción del 28-ene al 27-mar; dictaminación hasta el 30-jun en CC y PSAHEM y hasta el 30-abr en PS
  y RHF; aprobación del Comité del 1 al 31-jul en CC y PSAHEM).
* **Los que sirven por estar cerca de «hoy»** (el primer lote de PS y RHF, sus publicaciones, notificaciones y contratos por
  firmar; los vales de planta; las solicitudes de pago, revisiones, remisiones y cheques de octubre y noviembre; las sesiones de
  seguimiento) se escriben en el calendario de referencia, cuya fecha de corte es el 19-nov-2026 (``REFERENCIA``), y se trasladan
  con ``reciente`` a la fecha de corte de la carga: cada uno queda a los mismos días hábiles de ella que en la referencia. Así,
  cargada cualquier día, *Plantación Los Pinos* queda por firmar a un día hábil de vencer, el vale de *Mirador de los Pinos*
  vigente y el cheque de *Loma Verde* por vencer (éste se calcula con su plazo de 3 meses, ``entrega_cheque_por_vencer``).

**Fecha de corte.** Es el «hoy» de la demostración: el momento con el que termina la carga y con el que se señalan lo vencido y
lo por vencer. Por omisión es **el día en que se corre la carga** (``timezone.localdate()``; en las pruebas, el del reloj
simulado), con dos topes para que el calendario de 2026 siga siendo coherente:

* si hoy es anterior al 19-nov-2026 (``CORTE_MINIMO``), se usa el 19-nov: antes no cabrían el segundo lote, sus firmas de octubre
  y sus vales vencidos;
* si hoy es posterior al 31-dic-2026 (``CORTE_MAXIMO``; 2027 en adelante), se usa el 31-dic-2026: el ejercicio de la
  demostración sigue siendo 2026 y no se inventan pasos de 2027; sus plazos se verán vencidos, como los de cualquier expediente
  real del año anterior.

Si hoy es sábado, domingo o inhábil, la fecha de corte es hoy, pero los pasos se cuentan hacia atrás desde el siguiente día hábil
(``ancla``): nada ocurre después de hoy, y ese día hábil la demostración queda como si se hubiera cargado esa mañana.

La variable de entorno ``DEMO_FECHA_CORTE`` (AAAA-MM-DD) fija otra fecha de corte, del 19-nov al 31-dic-2026; las pruebas la
fijan en el 19-nov-2026 para ser deterministas. La fecha de corte se calcula una vez al empezar la carga (``carga``) y no cambia
mientras dura. Una vez cargada, el reloj del sistema es el real: los plazos avanzan día con día, como en cualquier expediente.
"""
import functools
import os
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from . import dias_habiles

REFERENCIA = date(2026, 11, 19)          # fecha de corte del calendario de referencia (y la de las pruebas)
CORTE_MINIMO = REFERENCIA
CORTE_MAXIMO = date(2026, 12, 31)

_cargas = []                             # fechas de corte de las cargas en curso (la última manda)


def _como_fecha(fecha):
    return date.fromisoformat(fecha) if isinstance(fecha, str) else fecha


def corte_para(hoy):
    """La fecha de corte que corresponde a ``hoy``: hoy mismo, sin bajar del 19-nov-2026 ni pasar del 31-dic-2026."""
    return min(max(hoy, CORTE_MINIMO), CORTE_MAXIMO)


def fecha_corte():
    """Fecha de corte de la demostración: la de la carga en curso; fuera de una carga, ``DEMO_FECHA_CORTE`` o la de hoy (con
    los topes de ``corte_para``)."""
    if _cargas:
        return _cargas[-1]
    valor = os.environ.get("DEMO_FECHA_CORTE", "").strip()
    if valor:
        fecha = date.fromisoformat(valor)
        if not CORTE_MINIMO <= fecha <= CORTE_MAXIMO:
            raise ValueError(f"DEMO_FECHA_CORTE={valor}: la fecha de corte de la demostración va del "
                             f"{CORTE_MINIMO:%d/%m/%Y} al {CORTE_MAXIMO:%d/%m/%Y} (ejercicio 2026).")
        return fecha
    return corte_para(timezone.localdate())


@contextmanager
def carga():
    """Fija la fecha de corte mientras dura la carga (se calcula una sola vez, al entrar). Se puede anidar: dentro de otra
    carga se conserva la de afuera."""
    _cargas.append(fecha_corte())
    try:
        yield _cargas[-1]
    finally:
        _cargas.pop()


def con_corte(funcion):
    """Decorador para las funciones ``cargar_demo``: corren dentro de ``carga()``."""
    @functools.wraps(funcion)
    def envoltura(*args, **kwargs):
        with carga():
            return funcion(*args, **kwargs)
    return envoltura


def ancla():
    """El día hábil desde el que se cuentan los pasos recientes: la fecha de corte o, si es inhábil, el siguiente hábil."""
    return dias_habiles.siguiente_habil(fecha_corte())


def cuando(fecha, hora=10, minuto=0):
    """Momento (con zona horaria de México) de una fecha: ``cuando("2026-03-09", 11, 30)``."""
    return timezone.make_aware(datetime.combine(_como_fecha(fecha), time(hora, minuto)))


def habil(fecha, n=0):
    """El día hábil que está ``n`` días hábiles después de ``fecha`` (``n=0``: ``fecha`` si es hábil, o el siguiente hábil).
    Los días hábiles cuentan sábados, domingos y el catálogo de días inhábiles como no laborables."""
    fecha = _como_fecha(fecha)
    if n == 0:
        return dias_habiles.siguiente_habil(fecha)
    return dias_habiles.sumar_dias_habiles(fecha, n)


def antes_del_corte(dias):
    """Fecha ``dias`` días naturales antes de la fecha de corte."""
    return fecha_corte() - timedelta(days=dias)


def habil_antes(fecha, n):
    """El día hábil que está ``n`` días hábiles antes de ``fecha``."""
    fecha = _como_fecha(fecha)
    contados = 0
    while contados < n:
        fecha -= timedelta(days=1)
        if dias_habiles.es_habil(fecha):
            contados += 1
    return fecha


def trasladar(fecha, de, a):
    """``fecha`` (un día hábil) llevada de la referencia ``de`` a ``a`` (días hábiles los dos): queda a los mismos días hábiles
    de ``a`` que estaba de ``de``, antes o después."""
    fecha, de = _como_fecha(fecha), _como_fecha(de)
    n = dias_habiles.dias_habiles_entre(fecha, de)        # positivo si ``fecha`` es anterior a ``de``
    return habil_antes(a, n) if n > 0 else habil(a, -n)


def reciente(fecha):
    """Una fecha del calendario de referencia (corte el 19-nov-2026) llevada a la fecha de corte de la carga: queda a los mismos
    días hábiles de ella. El 19-nov es la fecha de corte misma; con la fecha de corte de referencia, cada fecha queda igual."""
    fecha = _como_fecha(fecha)
    if fecha == REFERENCIA:
        return fecha_corte()
    return trasladar(fecha, REFERENCIA, ancla())


def entrega_cheque_por_vencer(dias_para_vencer=2, meses=3):
    """Día hábil de entrega de un cheque cuyo plazo de cobro (``meses`` desde la entrega; si el último día es inhábil, el
    siguiente hábil) vence a ``dias_para_vencer`` días hábiles del ancla o un poco antes: el día más tardío que no pase de ahí.
    Con el corte de referencia da el 21-ago-2026 (vence el lunes 23-nov)."""
    objetivo = habil(ancla(), dias_para_vencer)
    entrega = habil(dias_habiles.sumar_meses(objetivo, -meses))
    while dias_habiles.siguiente_habil(dias_habiles.sumar_meses(entrega, meses)) > objetivo:
        entrega = habil_antes(entrega, 1)
    return entrega
