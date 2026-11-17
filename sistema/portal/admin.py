from django.contrib import admin

from .models import AccesoExpediente, CodigoConsulta, CuentaExterna


@admin.register(CuentaExterna)
class CuentaExternaAdmin(admin.ModelAdmin):
    list_display = ["usuario", "persona", "creada_en", "activada_en"]
    exclude = ["codigo_hash"]
    readonly_fields = ["usuario", "persona", "creada_en", "creada_por", "codigo_emitido_en", "activada_en"]


@admin.register(AccesoExpediente)
class AccesoExpedienteAdmin(admin.ModelAdmin):
    list_display = ["cuenta", "expediente", "rol", "otorgado_en"]


@admin.register(CodigoConsulta)
class CodigoConsultaAdmin(admin.ModelAdmin):
    list_display = ["expediente", "creado_en"]
    exclude = ["codigo_hash"]
