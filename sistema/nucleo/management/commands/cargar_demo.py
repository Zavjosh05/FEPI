from django.core.management import call_command
from django.core.management.base import BaseCommand

from nucleo import demo_calendario
from nucleo.demo import CONTRASENA_DEMO, cargar_demo
from nucleo.models import Ejercicio, Estado, Municipio


class Command(BaseCommand):
    help = ("Carga usuarios de ejemplo por unidad, solicitudes de demostración de Capturando Carbono 2026 en "
            "distintos estados y solicitudes aprobadas de PS, RHF y PSAHEM. Idempotente (no duplica).")

    def handle(self, *args, **opciones):
        if not Municipio.objects.exists() or not Estado.objects.exists():
            call_command("cargar_catalogos")
        # Las reglas de los programas que tengan archivo (CC, PS, RHF y PSAHEM) deben estar cargadas.
        if Ejercicio.objects.filter(programa__clave__in=["CC", "PS", "RHF", "PSA"], reglas_cargadas__isnull=True).exists():
            call_command("cargar_reglas")
        from nucleo.extensiones import DEMOS

        # Una sola fecha de corte para toda la carga: por omisión el día de hoy (D-32; ver nucleo/demo_calendario.py).
        with demo_calendario.carga() as corte:
            n = cargar_demo()
            for demo in DEMOS:
                n += demo()
        self.stdout.write(self.style.SUCCESS(
            f"Demostración lista: {n} solicitudes nuevas (fecha de corte {corte:%d/%m/%Y}). "
            f"Contraseña de prueba de los usuarios: {CONTRASENA_DEMO}"))
