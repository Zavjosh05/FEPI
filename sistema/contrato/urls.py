"""Rutas del módulo; cada historia (HU-3.x) agrega las suyas con su vista en vistas/<historia>.py."""
from django.urls import path

from .vistas import contratos, firma, planta, publicacion

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
    # HU-3.3: firma del contrato
    path("firmas/", firma.lista, name="firmas"),
    path("contratos/<str:folio>/firmar/", firma.firmar, name="firmar"),
    path("contratos/<str:folio>/liberar/", firma.liberar, name="liberar"),
    path("contratos/<str:folio>/firmado/<str:clave>/", firma.archivo_firmado, name="firma_archivo"),
    # HU-3.4: entrega de planta
    path("vales/", planta.lista, name="vales"),
    path("vales/emitir/<str:folio>/", planta.emitir, name="vale_emitir"),
    path("vales/<str:folio>/", planta.detalle, name="vale"),
    path("vales/<str:folio>/pdf/", planta.pdf, name="vale_pdf"),
    path("vales/<str:folio>/carta/", planta.carta, name="vale_carta"),
    path("vales/<str:folio>/salida/", planta.salida, name="vale_salida"),
    path("vivero/", planta.vivero, name="vivero"),
]
