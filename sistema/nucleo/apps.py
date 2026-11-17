from django.apps import AppConfig


class NucleoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "nucleo"
    verbose_name = "Núcleo común"

    def ready(self):
        from . import avisos, extensiones

        if avisos.panel_por_vencer not in extensiones.PANELES_BANDEJA:
            extensiones.PANELES_BANDEJA.insert(0, avisos.panel_por_vencer)
        if avisos.revisar not in extensiones.REVISIONES_PLAZO:
            extensiones.REVISIONES_PLAZO.append(avisos.revisar)
