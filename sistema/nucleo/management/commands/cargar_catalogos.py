from django.core.management.base import BaseCommand

from nucleo.catalogos import cargar_catalogos


class Command(BaseCommand):
    help = ("Carga programas, unidades, Delegaciones con sus municipios, estados y transiciones, "
            "grupos y días inhábiles (reglas/catalogos.json y datos/*.json). Idempotente.")

    def handle(self, *args, **opciones):
        r = cargar_catalogos()
        self.stdout.write(self.style.SUCCESS(
            f"Catálogos cargados: {r['municipios']} municipios, {r['asignados']} asignados a una Delegación, "
            f"{r['dias_inhabiles']} días inhábiles."
        ))
