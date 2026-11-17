from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "PROBOSQUE · Administración de catálogos"
admin.site.site_title = "PROBOSQUE"
admin.site.index_title = "Catálogos y reglas"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("recepcion/", include("recepcion.urls")),
    path("dictamen/", include("dictamen.urls")),
    path("contrato/", include("contrato.urls")),
    path("pagos/", include("pagos.urls")),
    path("ejecucion/", include("ejecucion.urls")),
    path("seguimiento/", include("seguimiento.urls")),
    path("portal/envios/", include("ejecucion.urls_portal")),  # HU-4.1: envíos desde el portal
    path("portal/", include("portal.urls")),
    path("", include("nucleo.urls")),
]
