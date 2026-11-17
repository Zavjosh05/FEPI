from django.apps import AppConfig


class PortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "portal"
    verbose_name = "Portal de personas beneficiarias"

    def ready(self):
        from nucleo import extensiones

        from . import cuentas

        if cuentas.al_firmar not in extensiones.AL_FIRMAR:
            extensiones.AL_FIRMAR.append(cuentas.al_firmar)
