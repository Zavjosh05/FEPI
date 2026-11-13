from django.core.management import call_command
from django.core.management.base import BaseCommand

from nucleo.demo import CONTRASENA_DEMO, cargar_demo
from nucleo.models import Estado, Municipio


class Command(BaseCommand):
    help = ("Carga usuarios de ejemplo por unidad y solicitudes de demostración de Capturando Carbono 2026 "
            "en distintos estados. Idempotente (no duplica).")

    def handle(self, *args, **opciones):
        if not Municipio.objects.exists() or not Estado.objects.exists():
            call_command("cargar_catalogos")
            call_command("cargar_reglas")
        n = cargar_demo()
        self.stdout.write(self.style.SUCCESS(
            f"Demostración lista: {n} solicitudes nuevas. Contraseña de prueba de los usuarios: {CONTRASENA_DEMO}"))
