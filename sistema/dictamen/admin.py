from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from . import models


@admin.register(models.DictamenTecnico)
class DictamenTecnicoAdmin(SimpleHistoryAdmin):
    list_display = ["folio", "expediente", "resultado", "dentro_de_plazo", "usuario", "fecha_hora"]
    list_filter = ["resultado"]


@admin.register(models.DictamenJuridico)
class DictamenJuridicoAdmin(SimpleHistoryAdmin):
    list_display = ["folio", "expediente", "resultado", "usuario", "fecha_hora"]
    list_filter = ["resultado"]


@admin.register(models.PersonaIncumplida)
class PersonaIncumplidaAdmin(SimpleHistoryAdmin):
    list_display = ["nombre", "curp", "rfc", "fecha_inscripcion", "activa"]
    list_filter = ["activa"]
    search_fields = ["nombre", "curp", "rfc"]


@admin.register(models.PredioSancionado)
class PredioSancionadoAdmin(SimpleHistoryAdmin):
    list_display = ["descripcion_predio", "tipo", "fecha", "reintegro_realizado", "activo"]


class ResolucionEnLinea(admin.TabularInline):
    model = models.ResolucionSesion
    extra = 0


@admin.register(models.SesionComite)
class SesionComiteAdmin(SimpleHistoryAdmin):
    list_display = ["numero", "tipo", "ejercicio", "fecha_hora", "estado"]
    list_filter = ["tipo", "estado"]
    inlines = [ResolucionEnLinea]


@admin.register(models.Acuerdo)
class AcuerdoAdmin(SimpleHistoryAdmin):
    list_display = ["numero", "tipo", "unidad_responsable", "estado"]
    list_filter = ["tipo", "estado", "unidad_responsable"]


@admin.register(models.RevisionPropiedad)
class RevisionPropiedadAdmin(SimpleHistoryAdmin):
    list_display = ["dictamen", "nombre_documento", "titular_documento", "acreditada"]
    list_filter = ["acreditada", "tipo_documento"]


@admin.register(models.MovimientoListado)
class MovimientoListadoAdmin(SimpleHistoryAdmin):
    list_display = ["acuerdo", "expediente", "movimiento", "lugar_lista_espera", "monto", "usuario", "fecha_hora"]
    list_filter = ["movimiento"]
