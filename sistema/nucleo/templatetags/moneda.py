"""Filtro de plantilla para montos en pesos con separador de miles: ``{{ monto|moneda }}`` -> ``$20,500.00``."""
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()


def formato_moneda(valor):
    """«$20,500.00» (dos decimales, coma de miles); vacío o no numérico = «—»."""
    if valor in (None, ""):
        return "—"
    try:
        numero = Decimal(str(valor))
    except InvalidOperation:
        return "—"
    signo = "-" if numero < 0 else ""
    return f"{signo}${abs(numero):,.2f}"


@register.filter(name="moneda")
def moneda(valor):
    return formato_moneda(valor)
