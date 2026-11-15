"""Rutas del módulo; cada historia (HU-3.x) agrega las suyas con su vista en vistas/<historia>.py."""
from django.urls import path

from .vistas import publicacion

app_name = "contrato"

urlpatterns = [
    # HU-3.1: publicación y notificaciones
    path("publicacion/", publicacion.lista, name="publicaciones"),
    path("publicacion/<int:pk>/", publicacion.detalle, name="publicacion"),
    path("notificaciones/", publicacion.bandeja_notificaciones, name="notificaciones"),
    path("notificaciones/<int:pk>/entregar/", publicacion.entregar, name="notificacion_entregar"),
    # HU-3.1: página pública de resultados (no pide iniciar sesión)
    path("resultados/", publicacion.resultados, name="resultados"),
    path("resultados/<str:clave>/<int:anio>/", publicacion.resultados_programa, name="resultados_programa"),
]
