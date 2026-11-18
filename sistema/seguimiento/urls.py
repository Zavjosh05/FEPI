"""Rutas del módulo M6 (Seguimiento y cierre); cada historia agrega las suyas con su vista en vistas/<historia>.py."""
from django.urls import path

from .vistas import cierre, incumplimientos, reasignacion

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
    # HU-6.2: incumplimientos y reintegros
    path("incumplimientos/", incumplimientos.pagina, name="incumplimientos"),
    path("expediente/<str:folio>/omision/", incumplimientos.avisar, name="avisar_omision"),
    path("omision/<int:pk>/subsanada/", incumplimientos.subsanar, name="subsanar"),
    path("senalamiento/<int:pk>/confirmar/", incumplimientos.confirmar, name="confirmar"),
    path("requerimiento/<int:pk>/emitir/", incumplimientos.emitir, name="emitir_requerimiento"),
    path("requerimiento/<int:pk>/deposito/", incumplimientos.comprobar, name="comprobar_deposito"),
    path("requerimiento/<int:pk>/comprobante/", incumplimientos.archivo_deposito, name="archivo_deposito"),
    path("cuentas/", incumplimientos.registrar_cuenta, name="registrar_cuenta"),
    # HU-6.3: cierre del ejercicio, padrón e informe anual
    path("cierre/", cierre.pagina, name="cierre"),
    path("cierre/<int:pk>/", cierre.detalle, name="cierre_detalle"),
    path("cierre/<int:pk>/resultados.csv", cierre.resultados_csv, name="resultados_csv"),
    path("cierre/<int:pk>/cerrar/", cierre.cerrar_listos, name="cerrar_listos"),
    path("cierre/<int:pk>/padron/", cierre.publicar_padron, name="publicar_padron"),
    path("cierre/<int:pk>/informe/", cierre.enviar_informe, name="enviar_informe"),
    path("cierre/<int:pk>/informe/archivo/", cierre.informe_archivo, name="informe_archivo"),
    path("cierre/<int:pk>/informe/recepcion/", cierre.recepcion_informe, name="recepcion_informe"),
    path("expediente/<str:folio>/cerrar/", cierre.cerrar_expediente, name="cerrar_expediente"),
]
