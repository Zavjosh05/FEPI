"""Rutas del módulo; cada historia (HU-3.x) agrega las suyas con su vista en vistas/<historia>.py."""
from django.urls import path

from .vistas import contratos, publicacion

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
    # HU-3.2: elaboración del contrato
    path("modelos/", contratos.modelos, name="modelos"),
    path("modelos/<int:pk>/", contratos.modelo, name="modelo"),
    path("modelos/<int:pk>/version/", contratos.modelo_version, name="modelo_version"),
    path("modelos/<int:pk>/revisar/", contratos.modelo_revisar, name="modelo_revisar"),
    path("contratos/", contratos.lista, name="contratos"),
    path("contratos/<str:folio>/elaborar/", contratos.elaborar, name="elaborar"),
    path("contratos/<str:folio>/enviar/", contratos.enviar, name="enviar"),
    path("contratos/<str:folio>/pdf/", contratos.pdf, name="contrato_pdf"),
]
