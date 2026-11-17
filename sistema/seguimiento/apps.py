from django.apps import AppConfig


class SeguimientoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "seguimiento"
    verbose_name = "M6 · Seguimiento y cierre"

    def ready(self):
        from . import registro

        registro.registrar()
