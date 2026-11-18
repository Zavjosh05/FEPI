"""Rutas públicas de M6 (``/padron/``): el padrón de personas beneficiarias, sin iniciar sesión (HU-6.3)."""
from django.urls import path

from .vistas import padron

app_name = "padron"

urlpatterns = [
    path("", padron.indice, name="indice"),
    path("<str:clave>/<int:anio>/", padron.programa, name="programa"),
    path("<str:clave>/<int:anio>/padron.csv", padron.archivo_csv, name="csv"),
]
