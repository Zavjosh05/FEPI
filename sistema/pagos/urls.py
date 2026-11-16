"""Rutas del módulo; cada historia (HU-5.x) agrega las suyas con su vista en vistas/<historia>.py."""
from django.urls import path

from .vistas import pagos, solicitudes

app_name = "pagos"

urlpatterns = [
    # HU-5.1: solicitud de pago
    path("solicitudes/", solicitudes.lista, name="solicitudes"),
    path("expediente/<str:folio>/", solicitudes.expediente, name="expediente"),
    path("oficio/<str:folio>/emitir/", solicitudes.oficio_emitir, name="oficio_emitir"),
    path("oficio/<str:folio>/pdf/", solicitudes.oficio_pdf, name="oficio_pdf"),
    path("comprobante/<str:folio>/subir/", solicitudes.comprobante_subir, name="comprobante_subir"),
    path("comprobante/<str:folio>/<int:pk>/", solicitudes.comprobante, name="comprobante"),
    path("solicitud/<str:folio>/<int:numero>/preparar/", solicitudes.solicitud_preparar, name="solicitud_preparar"),
    path("solicitud/<str:folio>/<int:numero>/enviar/", solicitudes.solicitud_enviar, name="solicitud_enviar"),
    # HU-5.2: pago de la ministración
    path("revision/", pagos.lista, name="pagos"),
    path("solicitud-pago/<int:pk>/revisar/", pagos.revisar, name="revisar"),
    path("solicitud-pago/<int:pk>/pagar/", pagos.pagar, name="pagar"),
    path("solicitud-pago/<int:pk>/remitir/", pagos.remitir, name="remitir"),
]
