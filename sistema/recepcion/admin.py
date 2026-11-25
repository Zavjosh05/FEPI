from django.contrib import admin
from django.contrib.gis.admin import GISModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from .models import ObservacionValidacion, Poligono, RevisionRequisito, Validacion


@admin.register(RevisionRequisito)
class RevisionRequisitoAdmin(SimpleHistoryAdmin):
    list_display = ["expediente", "requisito", "estado", "en_archivo_probosque", "revisado_por", "revisado_en"]
    list_filter = ["estado"]


@admin.register(Poligono)
class PoligonoAdmin(GISModelAdmin, SimpleHistoryAdmin):
    list_display = ["expediente", "superficie_ha", "vigente", "tipo_cambio", "levantado_por", "registrado_en"]
    list_filter = ["vigente", "tipo_cambio"]


@admin.register(Validacion)
class ValidacionAdmin(SimpleHistoryAdmin):
    list_display = ["expediente", "resultado", "fecha_limite", "usuario", "fecha_hora", "notificado_en"]


@admin.register(ObservacionValidacion)
class ObservacionValidacionAdmin(SimpleHistoryAdmin):
    list_display = ["validacion", "revision", "faltante", "origen", "observacion"]
    list_filter = ["faltante", "origen"]
