"""Datos de demostración para las historias de M3 y M5 (idempotente): dos solicitudes aprobadas de PS, de RHF y
de PSAHEM, cada programa con su sesión de aprobación y su acta. Todo con los servicios de M1, M2 y M3, igual
que la interfaz. Las de CC aprobadas las deja ``dictamen/demo.py``.

HU-3.1: PS y RHF ya publicaron sus resultados (a distintas horas); en PS la Delegación notificó el resultado
y la cita de la primera solicitud, y en RHF solo el resultado; lo demás queda por notificar. PSAHEM y CC
quedan con el acta que autoriza publicar, para mostrar la pantalla de publicación."""
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from contrato import publicacion
from contrato.models import Publicacion
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
        aprobacion.registrar_acta(st, sesion, True, "Se aprueban los listados por unanimidad.",
                                  momento=fecha + timedelta(minutes=30))
    creadas += _publicaciones(u)
    return creadas


def _despues(base, minutos):
    """Un momento posterior a ``base`` (nunca en el futuro)."""
    return max(base, min(base + timedelta(minutes=minutos), timezone.now()))


def _publicaciones(u):
    """HU-3.1: publica PS y RHF con la demostración de avisos a distintas horas (idempotente)."""
    hechas = 0
    drff = u["dir_drff"]
    for clave, entregas in (("PS", ("resultados", "cita_firma")), ("RHF", ("resultados",))):
        sesion = (SesionComite.objects.filter(ejercicio__programa__clave=clave, tipo=TipoSesion.APROBACION,
                                              estado="celebrada", autoriza_publicacion=True, publicacion__isnull=True)
                  .order_by("-fecha_hora").first())
        if sesion is None:
            continue
        pub = publicacion.publicar(drff, sesion, momento=_despues(sesion.acta_fecha, 30))
        primera = pub.renglones.order_by("folio").first().expediente
        for minutos, tipo in zip((20, 40), entregas):
            n = primera.notificaciones.get(tipo=tipo)
            publicacion.registrar_entrega(
                _delegacion(u, primera), n, "personal" if tipo == "resultados" else "telefono",
                fecha_hora=_despues(pub.publicada_en, minutos), observaciones="Entregado (demostración).")
        hechas += 1
    return hechas


def _delegacion(u, expediente):
    return next(x for x in u.values() if x.unidad_id == expediente.delegacion_id)
