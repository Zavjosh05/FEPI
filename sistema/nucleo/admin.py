from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.gis.admin import GISModelAdmin
from simple_history.admin import SimpleHistoryAdmin

from . import models


@admin.register(models.Usuario)
class UsuarioAdmin(UserAdmin):
    list_display = ["username", "first_name", "last_name", "unidad", "is_active"]
    list_filter = ["unidad__tipo", "unidad", "is_active"]
    fieldsets = UserAdmin.fieldsets + (("PROBOSQUE", {"fields": ["unidad", "cargo"]}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("PROBOSQUE", {"fields": ["unidad", "cargo"]}),)


class MunicipioEnLinea(admin.TabularInline):
    model = models.Municipio
    fields = ["clave", "nombre"]
    readonly_fields = ["clave", "nombre"]
    extra = 0
    can_delete = False
    show_change_link = True


@admin.register(models.Unidad)
class UnidadAdmin(admin.ModelAdmin):
    list_display = ["nombre", "clave", "tipo", "sede", "asignacion_confirmada"]
    list_filter = ["tipo", "asignacion_confirmada"]
    search_fields = ["nombre", "clave"]
    filter_horizontal = ["programas"]
    inlines = [MunicipioEnLinea]


@admin.register(models.Municipio)
class MunicipioAdmin(GISModelAdmin):
    list_display = ["nombre", "clave", "delegacion"]
    list_filter = ["delegacion"]
    list_editable = ["delegacion"]
    search_fields = ["nombre"]


@admin.register(models.DiaInhabil)
class DiaInhabilAdmin(admin.ModelAdmin):
    list_display = ["fecha", "descripcion", "fuente"]
    date_hierarchy = "fecha"


class RequisitoEnLinea(admin.TabularInline):
    model = models.Requisito
    fields = ["clave", "texto", "aplica_en_refrendo", "es_documento_legal", "opcional", "condicion"]
    extra = 0


class PlazoEnLinea(admin.TabularInline):
    model = models.Plazo
    fields = ["clave", "cantidad", "unidad", "fundamento"]
    extra = 0


@admin.register(models.Programa)
class ProgramaAdmin(admin.ModelAdmin):
    list_display = ["clave", "nombre", "usa_poligono"]


@admin.register(models.Ejercicio)
class EjercicioAdmin(admin.ModelAdmin):
    list_display = ["programa", "anio", "vigente", "reglas_cargadas", "archivo_reglas"]
    inlines = [PlazoEnLinea, RequisitoEnLinea]
    readonly_fields = ["reglas_cargadas", "datos"]


@admin.register(models.Requisito)
class RequisitoAdmin(admin.ModelAdmin):
    list_display = ["clave", "ejercicio", "titulo", "aplica_en_refrendo", "es_documento_legal", "opcional"]
    list_filter = ["ejercicio", "es_documento_legal", "aplica_en_refrendo"]
    filter_horizontal = ["tipos_persona", "modalidades"]
    search_fields = ["clave", "texto"]


@admin.register(models.Plazo)
class PlazoAdmin(admin.ModelAdmin):
    list_display = ["clave", "ejercicio", "cantidad", "unidad", "fundamento"]
    list_filter = ["ejercicio", "unidad"]


for m in [models.TipoPersona, models.Modalidad, models.Formato, models.MontoApoyo, models.Ministracion]:
    admin.site.register(m)


@admin.register(models.Estado)
class EstadoAdmin(admin.ModelAdmin):
    list_display = ["clave", "nombre", "tipo_unidad_bandeja", "flujo_alterno", "final", "orden"]


@admin.register(models.Transicion)
class TransicionAdmin(admin.ModelAdmin):
    list_display = ["origen", "destino", "tipo_unidad", "accion", "programa", "requiere_motivo"]
    list_filter = ["tipo_unidad", "programa"]


@admin.register(models.Persona)
class PersonaAdmin(SimpleHistoryAdmin):
    list_display = ["nombre", "tipo", "curp", "rfn"]
    search_fields = ["nombre", "curp", "rfn"]


@admin.register(models.Predio)
class PredioAdmin(SimpleHistoryAdmin):
    list_display = ["folio", "nombre", "municipio", "titular"]
    search_fields = ["folio", "nombre"]


@admin.register(models.Expediente)
class ExpedienteAdmin(SimpleHistoryAdmin):
    list_display = ["folio", "ejercicio", "predio", "estado", "delegacion", "fecha_recepcion"]
    list_filter = ["ejercicio", "estado", "delegacion"]
    search_fields = ["folio", "predio__nombre", "solicitante__nombre"]
    readonly_fields = ["estado"]  # el estado solo cambia con Expediente.cambiar_estado


@admin.register(models.Acuse)
class AcuseAdmin(admin.ModelAdmin):
    list_display = ["folio", "titulo", "expediente", "fecha_hora", "emitido_por"]
    search_fields = ["folio", "expediente__folio"]


@admin.register(models.Evento)
class EventoAdmin(admin.ModelAdmin):
    list_display = ["fecha_hora", "expediente", "tipo", "usuario", "descripcion"]
    list_filter = ["tipo"]


@admin.register(models.Notificacion)
class NotificacionAdmin(SimpleHistoryAdmin):
    list_display = ["expediente", "tipo", "asunto", "delegacion", "enviada_en", "notificada_en", "medio"]
    list_filter = ["tipo", "medio", "delegacion"]
    search_fields = ["expediente__folio", "asunto"]
