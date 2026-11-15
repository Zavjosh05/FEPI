from django.apps import AppConfig


class ContratoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "contrato"
    verbose_name = "M3 · Publicación y contrato"

    def ready(self):
        from . import registro

        registro.registrar()
