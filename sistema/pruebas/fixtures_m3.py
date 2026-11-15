"""Fixtures del módulo M3 (HU-3.x): solicitudes aprobadas por una sesión del Comité, con acta."""
from datetime import timedelta

import pytest
from django.utils import timezone

from dictamen import aprobacion, juridico, sesiones, tecnico
from dictamen.demo import _validada
from dictamen.models import TipoSesion
from nucleo.models import Ejercicio

from .fixtures_m2 import documento_sesion

__all__ = ["aprobadas", "SOLICITUDES_M3"]

# programa: (usuario Delegación, municipio, predio, persona, modalidad, hectáreas)
SOLICITUDES_M3 = {
    "CC": [("del_amecameca", "Amecameca", "Predio CC Uno", "Beatriz Lara Pineda", "reforestacion", 6),
           ("del_toluca", "Zinacantepec", "Predio CC Dos", "Ramiro Ortega Solís", "reforestacion", 6),
           ("del_valle", "Amanalco", "Predio CC Tres", "Silvia Nava Cruz", "reforestacion", 6)],
    "PS": [("del_amecameca", "Tlalmanalco", "Plantación Los Pinos", "Abel Contreras Vega", "plantacion_forestal_comercial", 4),
           ("del_toluca", "Zinacantepec", "Rancho La Huerta", "Leticia Mora Garduño", "mantenimiento_plantaciones", 2.5)],
    "RHF": [("del_amecameca", "Ozumba", "Barranca Honda", "Rafael Sánchez Ortega", "rfi_modalidad_dos", 3),
            ("del_valle", "Amanalco", "Ojo de Agua", "Guadalupe Reyes Albarrán", "bosques_de_agua", 2)],
    "PSA": [("del_toluca", "Ocoyoacac", "Bosque El Zarco", "Felipe Hernández Ramos", "cuenca_alta", 30),
            ("del_valle", "Villa Victoria", "Monte La Loma", "Josefina Colín Becerril", "cuenca_media_baja", 25)],
}


@pytest.fixture
def aprobadas(catalogos, usuarios):
    """``aprobadas("PS")`` → (sesión, [expedientes]): solicitudes dictaminadas y aprobadas por una sesión de
    aprobación con acta (autoriza la publicación por omisión). Con ``presupuesto`` solo alcanza para el primero;
    el resto va a lista de espera. ``no_factible`` marca al último como no factible."""
    u = usuarios

    def _crear(programa="PS", autoriza=True, presupuesto=None, no_factible=False, cuantas=None):
        ejercicio = Ejercicio.objects.get(programa__clave=programa, anio=2026)
        datos = SOLICITUDES_M3[programa][:cuantas]
        exps = []
        for i, (deleg, municipio, predio, persona, modalidad, ha) in enumerate(datos):
            exp = _validada(u[deleg], u["dir_drff"], ejercicio, municipio, predio, persona, modalidad, ha)
            malo = no_factible and i == len(datos) - 1
            tecnico.dictaminar(u["dir_drff"], exp, "no_factible" if malo else "factible", "Dictamen técnico de prueba.")
            juridico.dictaminar(u["juridica"], exp, "procedente", "Documentación completa.")
            exps.append(exp)
        fecha = timezone.localtime(timezone.now()) - timedelta(hours=2)
        sesion = sesiones.crear_sesion(
            u["comite"], ejercicio, TipoSesion.APROBACION, fecha, "Sala de juntas",
            "Quórum\nListado preliminar\nAprobación de listados\nAutorización de publicación")
        sesiones.agregar_documento(u["comite"], sesion, documento_sesion("preliminar.pdf"), "Listado preliminar")
        sesiones.enviar_convocatoria(u["comite"], sesion, momento=fecha - timedelta(days=21))
        aprobacion.proponer_listados(u["comite"], sesion, presupuesto=presupuesto)
        aprobacion.registrar_acta(u["comite"], sesion, autoriza, "Acta de prueba.", momento=fecha + timedelta(minutes=30))
        sesion.refresh_from_db()
        for e in exps:
            e.refresh_from_db()
        return sesion, exps
    return _crear
