from django.apps import AppConfig


class RecepcionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "recepcion"
    verbose_name = "M1 · Recepción y expediente"

    def ready(self):
        from nucleo import extensiones

        from .pasos import siguiente_paso

        if siguiente_paso not in extensiones.SIGUIENTES_PASOS:
            extensiones.SIGUIENTES_PASOS.append(siguiente_paso)
