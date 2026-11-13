from django.urls import path

from . import views

app_name = "recepcion"

urlpatterns = [
    path("registrar/", views.registrar, name="registrar"),
    path("registrar/delegacion/", views.delegacion_de_municipio, name="delegacion_municipio"),
    path("expediente/<str:folio>/", views.expediente, name="expediente"),
    path("expediente/<str:folio>/requisito/<int:pk>/", views.revisar_requisito, name="revisar_requisito"),
    path("expediente/<str:folio>/envio/", views.panel_envio, name="panel_envio"),
    path("expediente/<str:folio>/enviar/", views.enviar, name="enviar"),
    path("expediente/<str:folio>/estado/", views.cambiar_con_motivo, name="cambiar_estado"),
    path("expediente/<str:folio>/poligono/", views.registrar_poligono, name="poligono"),
    path("expediente/<str:folio>/poligonos.json", views.poligonos_geojson, name="poligonos_geojson"),
    path("expediente/<str:folio>/poligono/<int:pk>/archivo/", views.archivo_poligono, name="archivo_poligono"),
    path("expediente/<str:folio>/validar/", views.validar, name="validar"),
    path("expediente/<str:folio>/notificar/", views.notificar, name="notificar"),
]
