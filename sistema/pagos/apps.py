from django.apps import AppConfig


class PagosConfig(AppConfig):
    """Base de datos completa desde el sprint 1: esta app trae solo sus modelos (tablas); sus pantallas y servicios
    llegan con las historias de su sprint."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "pagos"
    verbose_name = "M5 · Pagos"
