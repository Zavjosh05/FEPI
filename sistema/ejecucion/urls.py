"""Rutas del módulo M4 (Ejecución y verificación); cada historia agrega las suyas con su vista en vistas/<historia>.py."""
from django.urls import path

from .vistas import comprobaciones, reportes, verificacion

app_name = "ejecucion"

urlpatterns = [
    # HU-4.1: envío de comprobaciones (entrega en ventanilla y lo recibido por el portal)
    path("comprobaciones/", comprobaciones.lista, name="comprobaciones"),
    path("comprobacion/<str:folio>/registrar/", comprobaciones.registrar, name="registrar"),
    path("comprobacion/<int:pk>/revisada/", comprobaciones.revisada, name="revisada"),
    path("comprobacion/<int:pk>/archivo/", comprobaciones.archivo, name="archivo"),
    path("comprobacion/<str:folio>/prestador/", comprobaciones.acceso_prestador, name="acceso_prestador"),
    # HU-4.2: verificación en campo
    path("verificacion/<str:folio>/registrar/", verificacion.registrar, name="verificar"),
    path("verificacion/<str:folio>/devolver/", verificacion.devolver, name="devolver"),
    path("verificacion/<str:folio>/concluir/", verificacion.concluir, name="concluir"),
    path("verificacion/<int:pk>/archivo/", verificacion.archivo, name="verificacion_archivo"),
    path("incidencia/<int:pk>/archivo/", verificacion.archivo_incidencia, name="incidencia_archivo"),
    # HU-4.3: evaluación de reportes (Guardabosques)
    path("reportes/", reportes.pagina, name="reportes"),
    path("reportes/revision/<int:pk>/", reportes.revisar, name="revisar_reporte"),
    path("reportes/evaluar/<str:folio>/<str:periodo>/", reportes.evaluar, name="evaluar_reporte"),
    path("reportes/<int:ejercicio>/<str:periodo>/enviar/", reportes.enviar, name="enviar_evaluacion"),
]
