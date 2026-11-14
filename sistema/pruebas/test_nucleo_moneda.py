"""Filtro de plantilla `moneda`: pesos con separador de miles."""
from decimal import Decimal

from django.template import Context, Template

from nucleo.templatetags.moneda import formato_moneda


def test_nucleo_moneda_separador_de_miles_y_dos_decimales():
    assert formato_moneda(Decimal("20500")) == "$20,500.00"
    assert formato_moneda(Decimal("1234567.891")) == "$1,234,567.89"
    assert formato_moneda(2000) == "$2,000.00"
    assert formato_moneda("57000") == "$57,000.00"
    assert formato_moneda(Decimal("0")) == "$0.00"
    assert formato_moneda(Decimal("-1500.5")) == "-$1,500.50"
    assert formato_moneda(None) == "—" and formato_moneda("abc") == "—"


def test_nucleo_moneda_como_filtro_de_plantilla():
    html = Template("{% load moneda %}{{ monto|moneda }}").render(Context({"monto": Decimal("20500.00")}))
    assert html == "$20,500.00"
