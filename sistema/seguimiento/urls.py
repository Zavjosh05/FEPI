"""Rutas del módulo M6 (Seguimiento y cierre); cada historia agrega las suyas con su vista en vistas/<historia>.py."""
from django.urls import path

from .vistas import reasignacion

app_name = "seguimiento"

urlpatterns = [
    # HU-6.1: lista de espera y sustituciones
    path("", reasignacion.pagina, name="pagina"),
    path("reasignacion/<int:ejercicio>/proponer/", reasignacion.proponer_reasignacion, name="proponer_reasignacion"),
    path("propuesta/<int:pk>/sesion/", reasignacion.llevar_a_sesion, name="llevar_a_sesion"),
    path("expediente/<str:folio>/solicitud/", reasignacion.registrar_solicitud, name="registrar_solicitud"),
    path("expediente/<str:folio>/proponer/", reasignacion.proponer, name="proponer"),
    path("expediente/<str:folio>/prorroga/", reasignacion.solicitar_prorroga, name="solicitar_prorroga"),
    path("prorroga/<int:pk>/resolver/", reasignacion.resolver_prorroga, name="resolver_prorroga"),
    path("solicitud/<int:pk>/archivo/", reasignacion.archivo_solicitud, name="archivo_solicitud"),
]
