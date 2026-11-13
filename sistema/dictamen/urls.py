from django.urls import path

from .vistas import aprobacion, juridico, seguimiento, sesiones, tecnico

app_name = "dictamen"

urlpatterns = [
    # HU-2.1
    path("tecnico/<str:folio>/", tecnico.dictaminar, name="tecnico"),
    path("tecnico/<str:folio>/mapa.json", tecnico.mapa, name="tecnico_mapa"),
    path("listado/", tecnico.listado, name="listado"),
    # HU-2.2
    path("juridico/<str:folio>/", juridico.dictaminar, name="juridico"),
    path("incumplidas/", juridico.incumplidas, name="incumplidas"),
    path("incumplidas/<str:catalogo>/<int:pk>/baja/", juridico.baja, name="incumplida_baja"),
    # Sesiones (comunes a HU-2.3 y HU-2.4)
    path("sesiones/", sesiones.lista, name="sesiones"),
    path("sesiones/nueva/", sesiones.nueva, name="sesion_nueva"),
    path("sesiones/<int:pk>/", sesiones.detalle, name="sesion"),
    path("sesiones/<int:pk>/documento/", sesiones.documento, name="sesion_documento"),
    path("sesiones/<int:pk>/documento/<int:doc>/", sesiones.descargar_documento, name="sesion_documento_archivo"),
    path("sesiones/<int:pk>/convocar/", sesiones.convocar, name="sesion_convocar"),
    # HU-2.3
    path("sesiones/<int:pk>/proponer/", aprobacion.proponer, name="sesion_proponer"),
    path("sesiones/<int:pk>/ajustar/<int:resolucion>/", aprobacion.ajustar, name="sesion_ajustar"),
    path("sesiones/<int:pk>/acta/", aprobacion.acta, name="sesion_acta"),
    # HU-2.4
    path("sesiones/<int:pk>/acuerdo/", seguimiento.acuerdo, name="sesion_acuerdo"),
    path("sesiones/<int:pk>/cerrar/", seguimiento.cerrar, name="sesion_cerrar"),
    path("acuerdos/<int:pk>/cumplir/", seguimiento.cumplir, name="acuerdo_cumplir"),
]
