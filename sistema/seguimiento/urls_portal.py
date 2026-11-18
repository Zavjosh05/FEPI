"""Rutas de M6 dentro del portal de personas beneficiarias (``/portal/seguimiento/``)."""
from django.urls import path

from .vistas import portal

app_name = "seguimiento_portal"

urlpatterns = [
    path("<str:folio>/enviar/", portal.enviar, name="enviar"),
    path("<str:folio>/archivo/<int:pk>/", portal.archivo, name="archivo"),
]
