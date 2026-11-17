"""Rutas del módulo M4 (Ejecución y verificación); cada historia agrega las suyas con su vista en vistas/<historia>.py."""
from django.urls import path

from .vistas import comprobaciones

app_name = "ejecucion"

urlpatterns = [
    # HU-4.1: envío de comprobaciones (entrega en ventanilla y lo recibido por el portal)
    path("comprobaciones/", comprobaciones.lista, name="comprobaciones"),
    path("comprobacion/<str:folio>/registrar/", comprobaciones.registrar, name="registrar"),
    path("comprobacion/<int:pk>/revisada/", comprobaciones.revisada, name="revisada"),
    path("comprobacion/<int:pk>/archivo/", comprobaciones.archivo, name="archivo"),
]
