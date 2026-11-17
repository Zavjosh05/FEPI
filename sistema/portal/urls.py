from django.urls import path

from . import views

app_name = "portal"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", views.entrar, name="entrar"),
    path("primer-acceso/", views.primer_acceso, name="primer_acceso"),
    path("consulta/", views.consulta, name="consulta"),
    path("expediente/<str:folio>/", views.expediente, name="expediente"),
    path("expediente/<str:folio>/acuse/<str:acuse_folio>/", views.acuse, name="acuse"),
    path("salir/", views.salir, name="salir"),
]
