from django.apps import AppConfig


class EjecucionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ejecucion"
    verbose_name = "M4 · Ejecución y verificación"

    def ready(self):
        from . import registro

        registro.registrar()
