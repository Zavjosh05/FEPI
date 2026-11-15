"""Núcleo · rango de superficie por modalidad (S2-02e: CC general, PS por concepto, PSAHEM por cuenca, RHF sin
máximo)."""
import pytest

from nucleo.models import Ejercicio
from nucleo.reglas import en_rango, rango_superficie

pytestmark = pytest.mark.django_db


def _ej(clave):
    return Ejercicio.objects.get(programa__clave=clave, anio=2026)


def test_nucleo_superficie_general_de_cc(catalogos):
    r = rango_superficie(_ej("CC"), "reforestacion")
    assert (r["minima_ha"], r["maxima_ha"]) == (1, 200) and en_rango(r, 6) and not en_rango(r, 201)


def test_nucleo_superficie_por_concepto_en_ps(catalogos):
    assert rango_superficie(_ej("PS"), "plantacion_forestal_comercial")["minima_ha"] == 1
    r = rango_superficie(_ej("PS"), "mantenimiento_navidenas")
    assert r["minima_ha"] == 0.5 and r["maxima_ha"] is None and en_rango(r, 500)


def test_nucleo_superficie_por_cuenca_y_fsc_en_psahem(catalogos):
    ej = _ej("PSA")
    assert rango_superficie(ej, "cuenca_media_baja")["maxima_ha"] == 300
    assert rango_superficie(ej, "cuenca_alta")["maxima_ha"] == 400
    assert rango_superficie(ej, "cuenca_alta", {"certificacion_FSC"})["maxima_ha"] == 450
    assert not en_rango(rango_superficie(ej, "cuenca_alta"), 19)


def test_nucleo_superficie_sin_maximo_en_rhf(catalogos):
    r = rango_superficie(_ej("RHF"), "bosques_de_agua")
    assert r["maxima_ha"] is None and "no fijan máximo" in r["texto"] and en_rango(r, 1000) and not en_rango(r, 0.4)
