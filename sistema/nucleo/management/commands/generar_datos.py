import time

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from nucleo import generador
from nucleo.models import Estado, Municipio


class Command(BaseCommand):
    help = ("Genera solicitudes de prueba con los servicios del sistema (herramienta aparte: no corre al levantar el sitio). "
            "La misma semilla da los mismos datos. Ejemplo: manage.py generar_datos --programa CC --n 200 --semilla 7")

    def add_arguments(self, parser):
        parser.add_argument("--programa", required=True, help="CC, PS, RHF, PSA o «todos».")
        parser.add_argument("--n", type=int, default=100, help="Solicitudes por programa (por omisión 100).")
        parser.add_argument("--semilla", type=int, default=1)
        parser.add_argument("--pdf-real", action="store_true", help="Renderiza los PDF con WeasyPrint (4 a 8 s por documento).")

    def handle(self, *args, programa, n, semilla, pdf_real, **opciones):
        programa = programa.upper()
        claves = list(generador.PROGRAMAS) if programa == "TODOS" else [programa]
        if any(c not in generador.PROGRAMAS for c in claves):
            raise CommandError(f"Programa desconocido: use {', '.join(generador.PROGRAMAS)} o todos.")
        if not Municipio.objects.exists() or not Estado.objects.exists():
            call_command("cargar_catalogos")
        call_command("cargar_reglas")
        from nucleo.demo import crear_usuarios

        crear_usuarios()
        from contrato import planta  # noqa: F401  (el catálogo de especies y viveros lo carga la demostración)

        for clave in claves:
            inicio = time.monotonic()
            creadas = generador.generar(clave, n, semilla, pdf_real, escribir=lambda t: self.stdout.write(t))
            segundos = time.monotonic() - inicio
            self.stdout.write(self.style.SUCCESS(
                f"{clave}: {creadas} solicitudes en {segundos:.0f} s ({segundos / max(creadas, 1):.2f} s por solicitud)."))
