from django.core.management.base import BaseCommand

from nucleo.catalogos import cargar_reglas_disponibles, cargar_reglas_programa


class Command(BaseCommand):
    help = ("Carga las reglas (requisitos, plazos, formatos, montos) de cada programa-ejercicio desde "
            "reglas/<CLAVE>.json. Sin argumentos carga todos los archivos que existan. Idempotente.")

    def add_arguments(self, parser):
        parser.add_argument("--archivo", help="Ruta de un archivo de reglas en particular.")

    def handle(self, *args, **opciones):
        if opciones.get("archivo"):
            ej = cargar_reglas_programa(opciones["archivo"])
            self.stdout.write(self.style.SUCCESS(f"Reglas cargadas: {ej} ({ej.requisitos.count()} requisitos)."))
            return
        cargados, faltantes = cargar_reglas_disponibles()
        for ej in cargados:
            self.stdout.write(self.style.SUCCESS(
                f"Reglas cargadas: {ej} ({ej.requisitos.count()} requisitos, {ej.plazos.count()} plazos)."))
        if faltantes:
            self.stdout.write(self.style.WARNING("Sin archivo de reglas todavía: " + ", ".join(faltantes)))
