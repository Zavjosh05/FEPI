"""Datos de demostración para las historias de M3 y M5 (idempotente): dos solicitudes aprobadas de PS, de RHF y
de PSAHEM, cada programa con su sesión de aprobación y su acta. Todo con los servicios de M1 y M2, igual
que la interfaz. Las de CC aprobadas las deja ``dictamen/demo.py``."""
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from dictamen import aprobacion, juridico, sesiones, tecnico
from dictamen.demo import _validada
from dictamen.models import SesionComite, TipoSesion
from nucleo.demo import _pdf_demo
from nucleo.models import Ejercicio, Usuario

# programa: [(usuario de la Delegación, municipio, predio, persona, modalidad, hectáreas)]
SOLICITUDES = {
    "PS": [("del_amecameca", "Tlalmanalco", "Plantación Los Pinos", "Abel Contreras Vega", "plantacion_forestal_comercial", 4),
           ("del_toluca", "Zinacantepec", "Rancho La Huerta", "Leticia Mora Garduño", "mantenimiento_plantaciones", 2.5)],
    "RHF": [("del_amecameca", "Ozumba", "Barranca Honda", "Rafael Sánchez Ortega", "rfi_modalidad_dos", 3),
            ("del_valle", "Amanalco", "Ojo de Agua", "Guadalupe Reyes Albarrán", "bosques_de_agua", 2)],
    "PSA": [("del_toluca", "Ocoyoacac", "Bosque El Zarco", "Felipe Hernández Ramos", "cuenca_alta", 30),
            ("del_valle", "Villa Victoria", "Monte La Loma", "Josefina Colín Becerril", "cuenca_media_baja", 25)],
}


@transaction.atomic
def cargar_demo():
    u = {x.username: x for x in Usuario.objects.all()}
    drff, uj, st = u["dir_drff"], u["juridica"], u["comite"]
    creadas = 0
    for clave, solicitudes in SOLICITUDES.items():
        ejercicio = Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()
        if ejercicio is None or SesionComite.objects.filter(ejercicio=ejercicio).exists():
            continue
        for usuario, municipio, predio, persona, modalidad, ha in solicitudes:
            exp = _validada(u[usuario], drff, ejercicio, municipio, predio, persona, modalidad, ha)
            tecnico.dictaminar(drff, exp, "factible", "Cumple los criterios técnicos de elegibilidad de las reglas.")
            juridico.dictaminar(uj, exp, "procedente", "Documentación legal completa y vigente.")
            creadas += 1
        fecha = timezone.localtime(timezone.now()) - timedelta(hours=2)
        sesion = sesiones.crear_sesion(
            st, ejercicio, TipoSesion.APROBACION, fecha, "Sala de juntas de PROBOSQUE, Metepec",
            "Lista de asistencia y declaración de quórum\nPresentación del listado preliminar\n"
            "Aprobación de los listados\nAutorización de la publicación de resultados")
        sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo(f"Listado preliminar {clave} 2026"),
                                                           name="listado_preliminar.pdf"), "Listado preliminar")
        sesiones.enviar_convocatoria(st, sesion, momento=fecha - timedelta(days=21))
        aprobacion.proponer_listados(st, sesion)
        aprobacion.registrar_acta(st, sesion, True, "Se aprueban los listados por unanimidad.")
    return creadas
