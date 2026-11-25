"""Prepara dos casos de Plantaciones Sustentables con fechas de hoy para la secuencia de prueba del sprint 2.

La demostración se carga con un calendario simulado cuya fecha de corte es el 19-nov-2026: sus plazos de firma ya vencieron
cuando se prueba después, y no deja nada de PS por publicar ni nadie en la Lista de espera. Este script agrega, con los mismos
servicios que usa la interfaz y **con la fecha y la hora de hoy**, lo que la secuencia necesita:

* **Caso 1, «aprobada y por publicar»** (escenarios B y C): *Plantación Cumbres* (Ozumba, Delegación Amecameca, 4 ha de
  plantación forestal comercial), dictaminada y aprobada por una sesión del Comité cuya acta autoriza la publicación. La
  Dirección la publica en la secuencia y sus plazos corren desde ese momento.
* **Caso 2, «baja y reasignación con contrato»** (escenario F): una segunda sesión de aprobación con dos solicitudes y recurso
  para una sola. *Vereda Alta* (Temoaya, Delegación Toluca) es persona beneficiaria, ya publicada y notificada, con su contrato
  **enviado a la Delegación** y sin firmar; *Cañada Honda* (Ozumba) es la **primera de la Lista de espera**. Además queda una
  **sesión de seguimiento** de PS, ya convocada y con fecha de hace unas horas, sin acuerdos y sin cerrar, para que la
  Secretaría Técnica registre la baja y la reasignación y la cierre.

Se corre una vez, con el sistema levantado y la demostración cargada, desde la carpeta `sistema/`:

    docker compose -p probosque_s2 exec -T web python manage.py shell < ../datos_prueba/sprint_2/preparar_casos_ps.py

Es idempotente: si *Plantación Cumbres* ya existe, no hace nada. Todos los nombres son inventados.
"""
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.utils import timezone

from contrato import contratos, publicacion
from contrato.demo import _delegacion
from dictamen import aprobacion, juridico, sesiones, tecnico
from dictamen.demo import _validada, propiedad_en_regla
from dictamen.models import TipoSesion
from nucleo import montos
from nucleo.demo import _pdf_demo
from nucleo.models import Ejercicio, Expediente, Usuario


def _sesion_de_aprobacion(u, ejercicio, presupuesto=None):
    """Sesión de aprobación celebrada hace dos horas, con su acta (autoriza publicar)."""
    st = u["comite"]
    fecha = timezone.localtime(timezone.now()) - timedelta(hours=2)
    sesion = sesiones.crear_sesion(st, ejercicio, TipoSesion.APROBACION, fecha, "Sala de juntas de PROBOSQUE, Metepec",
                                   "Quórum\nListado preliminar\nAprobación de listados\nAutorización de publicación")
    sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo("Listado preliminar PS"), name="preliminar.pdf"),
                               "Listado preliminar")
    sesiones.enviar_convocatoria(st, sesion, momento=fecha - timedelta(days=21))
    aprobacion.proponer_listados(st, sesion, presupuesto=presupuesto)
    aprobacion.registrar_acta(st, sesion, True, "Se aprueban los listados por unanimidad.", momento=fecha + timedelta(minutes=30))
    sesion.refresh_from_db()
    return sesion


def _dictaminada(u, ejercicio, fila):
    usuario, municipio, predio, persona, modalidad, ha = fila
    exp = _validada(u[usuario], u["dir_drff"], ejercicio, municipio, predio, persona, modalidad, ha)
    tecnico.dictaminar(u["dir_drff"], exp, "factible", "Cumple los criterios técnicos de elegibilidad de las reglas.")
    juridico.dictaminar(u["juridica"], exp, "procedente", "Documentación legal completa y vigente.",
                        propiedad=propiedad_en_regla(exp))
    return exp


def preparar():
    u = {x.username: x for x in Usuario.objects.all()}
    st, drff = u["comite"], u["dir_drff"]
    ejercicio = Ejercicio.objects.filter(programa__clave="PS", reglas_cargadas__isnull=False).order_by("-anio").first()
    if ejercicio is None:
        return "No hay reglas de Plantaciones Sustentables: ¿se cargó la demostración?"
    if Expediente.objects.filter(ejercicio=ejercicio, predio__nombre="Plantación Cumbres").exists():
        return "Ya estaba preparado (Plantación Cumbres existe)."

    # Caso 1: aprobada, sin publicar.
    cumbres = _dictaminada(u, ejercicio, ("del_amecameca", "Ozumba", "Plantación Cumbres", "Joaquín Villegas Ponce",
                                          "plantacion_forestal_comercial", 4))
    s1 = _sesion_de_aprobacion(u, ejercicio)

    # Caso 2: dos solicitudes y recurso para una; la primera se publica, se notifica y recibe su contrato.
    vereda = _dictaminada(u, ejercicio, ("del_toluca", "Temoaya", "Vereda Alta", "Marcelo Ibarra Téllez",
                                         "plantacion_forestal_comercial", 3))
    honda = _dictaminada(u, ejercicio, ("del_amecameca", "Ozumba", "Cañada Honda", "Silvia Barrera Núñez",
                                        "plantacion_forestal_comercial", 3))
    superficie = vereda.dictamen_tecnico.superficie_factible_ha or vereda.superficie_solicitada_ha
    s2 = _sesion_de_aprobacion(u, ejercicio, presupuesto=montos.monto_aprobado(vereda, superficie).total)
    publicacion.publicar(drff, s2)
    vereda.refresh_from_db()
    publicacion.registrar_entrega(_delegacion(u, vereda), vereda.notificaciones.get(tipo="resultados"), "personal",
                                  observaciones="Entregado (datos de prueba del sprint 2).")
    vereda.refresh_from_db()
    contrato = contratos.elaborar_contrato(drff, vereda, contratos.modelos_elegibles(vereda)[0])
    contratos.enviar_a_delegacion(drff, contrato)

    # Sesión de seguimiento ya convocada, con fecha de hace unas horas: se pueden registrar acuerdos y cerrarla.
    fecha = timezone.localtime(timezone.now()) - timedelta(hours=1)
    seg = sesiones.crear_sesion(st, ejercicio, TipoSesion.SEGUIMIENTO, fecha, "Sala de juntas de PROBOSQUE, Metepec",
                                "Lista de asistencia y declaración de quórum\nSeguimiento de casos del ejercicio\nAsuntos generales")
    sesiones.agregar_documento(st, seg, ContentFile(_pdf_demo("Casos para seguimiento PS"), name="casos_ps.pdf"),
                               "Casos para seguimiento")
    sesiones.enviar_convocatoria(st, seg, momento=fecha - timedelta(days=14))
    for e in (cumbres, vereda, honda):
        e.refresh_from_db()
    return (f"Listo. Caso 1: {cumbres.folio} Plantación Cumbres ({cumbres.estado}), sesión {s1.numero} por publicar. "
            f"Caso 2: {vereda.folio} Vereda Alta ({vereda.estado}), {honda.folio} Cañada Honda ({honda.estado}), "
            f"sesión de seguimiento {seg.numero} por cerrar.")


print(preparar())
