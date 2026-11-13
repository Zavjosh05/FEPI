from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

app_name = "nucleo"

urlpatterns = [
    path("", views.inicio, name="inicio"),
    path("entrar/", views.Entrar.as_view(), name="entrar"),
    path("salir/", auth_views.LogoutView.as_view(), name="salir"),
    path("bandeja/", views.ver_bandeja, name="bandeja"),
    path("documentos/<int:pk>/", views.descargar_documento, name="documento"),
    path("acuses/<str:folio>/", views.descargar_acuse, name="acuse"),
    path("salud/", views.salud, name="salud"),
]
