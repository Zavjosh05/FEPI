from django.apps import AppConfig


class NucleoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nucleo"
    verbose_name = "Núcleo común"

    def ready(self):
        from . import extensiones, trazabilidad

        if trazabilidad.fuentes_nucleo not in extensiones.TRAZABILIDAD:
            extensiones.TRAZABILIDAD.insert(0, trazabilidad.fuentes_nucleo)
