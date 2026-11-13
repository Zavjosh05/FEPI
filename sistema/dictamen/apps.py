from django.apps import AppConfig


class DictamenConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "dictamen"
    verbose_name = "M2 · Dictamen y Comité"

    def ready(self):
        from . import registro

        registro.registrar()
