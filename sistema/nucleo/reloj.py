"""Reloj simulado para los datos de demostración, el generador y las pruebas (G-03).

``with reloj.en("2026-03-02 10:30"): ...`` hace que **todo** el sistema vea ese momento como «ahora» mientras dure el bloque:
``timezone.now()`` y ``timezone.localdate()``, los ``auto_now`` y ``auto_now_add``, los ``default=timezone.now`` de los
modelos (acuses, bitácora, historiales), los folios con año, los plazos y los vencimientos. Al salir se restaura el reloj
real. Sin dependencias: sustituye ``django.utils.timezone.now`` y los valores por omisión de los campos que lo usan.

* El reloj queda **detenido** en el momento dado; ``r.avanzar(minutes=5)`` o ``r.ir_a(otro_momento)`` lo mueven.
  Con ``tic`` (segundos), cada lectura avanza ese tanto, útil para que los renglones de una carga tengan horas distintas.
* Se puede anidar: al salir de un bloque vuelve el momento del bloque que lo contiene.
* Un momento sin zona horaria se toma en la hora del centro de México (``settings.TIME_ZONE``).
* La interfaz y los servicios no lo usan ni cambian: sin ningún bloque activo, ``timezone.now`` es el de Django.
* No es seguro entre hilos: es para cargas, generadores y pruebas, no para el servidor.

``datetime.now()`` y ``date.today()`` no se simulan; el sistema no los usa (todo pasa por ``django.utils.timezone``).
"""
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta

from django.apps import apps
from django.utils import timezone

_AHORA_REAL = timezone.now          # la función original de Django (la que traen los campos como valor por omisión)
_pila = []                          # relojes activos; el último manda


class Reloj:
    """Un momento simulado que se puede mover mientras dura el bloque."""

    def __init__(self, momento, tic=0):
        self.momento = momento
        self.tic = timedelta(seconds=tic)

    def ahora(self):
        actual = self.momento
        self.momento = actual + self.tic
        return actual

    def ir_a(self, momento):
        self.momento = _como_momento(momento)
        return self.momento

    def avanzar(self, **delta):
        """Mueve el reloj hacia adelante (``days``, ``hours``, ``minutes``…)."""
        self.momento += timedelta(**delta)
        return self.momento


def _como_momento(valor):
    """datetime (con o sin zona), date (a las 10:00 locales) o texto ISO («2026-03-02», «2026-03-02 10:30»)."""
    if isinstance(valor, str):
        valor = datetime.fromisoformat(valor)
    if isinstance(valor, datetime):
        return timezone.make_aware(valor) if timezone.is_naive(valor) else valor
    if isinstance(valor, date):
        return timezone.make_aware(datetime.combine(valor, time(10, 0)))
    raise TypeError(f"No es un momento: {valor!r}")


def _ahora_simulado():
    return _pila[-1].ahora() if _pila else _AHORA_REAL()


def _poner_valores_por_omision(funcion):
    """Los campos con ``default=timezone.now`` guardan la función original: se cambia por la que consulta el reloj."""
    for modelo in apps.get_models(include_auto_created=True):
        for campo in modelo._meta.local_fields:
            if campo.default in (_AHORA_REAL, _ahora_simulado):
                campo.default = funcion
                campo.__dict__.pop("_get_default", None)       # Django guarda en caché el valor por omisión


def _instalar():
    timezone.now = _ahora_simulado
    _poner_valores_por_omision(_ahora_simulado)


def _desinstalar():
    timezone.now = _AHORA_REAL
    _poner_valores_por_omision(_AHORA_REAL)


@contextmanager
def en(momento, tic=0):
    """``with reloj.en("2026-03-02 10:30") as r: ...`` — todo el sistema ve ese momento como «ahora»."""
    reloj = Reloj(_como_momento(momento), tic)
    if not _pila:
        _instalar()
    _pila.append(reloj)
    try:
        yield reloj
    finally:
        _pila.pop()
        if not _pila:
            _desinstalar()


def activo():
    """True mientras haya un bloque ``en(...)`` abierto."""
    return bool(_pila)
