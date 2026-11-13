"""Datos de demostración del módulo M2 (idempotente): expedientes en dictamen y dictaminados, una persona en el
Listado de Incumplidas, una sesión de aprobación con acta y una de seguimiento con acuerdos."""
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from nucleo import dias_habiles
from nucleo.demo import _pdf_demo, _solicitud, completar_requisitos, cuadro_en_municipio
from nucleo.models import Ejercicio, Predio, Unidad, Usuario
from recepcion import servicios as recepcion

from . import aprobacion, juridico, seguimiento, sesiones, tecnico
from .models import PersonaIncumplida, PredioSancionado, SesionComite, TipoSesion


def _validada(u_del, u_dir, ejercicio, municipio, predio, persona, modalidad, ha, desplazamiento=(0, 0), **extra):
    exp = _solicitud(u_del, ejercicio, municipio, predio, persona, "fisica", modalidad, str(ha), **extra)
    completar_requisitos(u_del, exp)
    recepcion.registrar_poligono(u_del, exp, cuadro_en_municipio(exp.predio.municipio, ha, desplazamiento), "dibujo",
                                 "delegacion", "Brigada de la Delegación", timezone.localdate() - timedelta(days=5))
    recepcion.enviar_a_direccion(u_del, exp)
    recepcion.validar_expediente(u_dir, exp)
    exp.refresh_from_db()
    return exp


def _existe(ejercicio, nombre):
    return Predio.objects.filter(nombre=nombre, expedientes__ejercicio=ejercicio).first()


@transaction.atomic
def cargar_demo():
    ejercicio = Ejercicio.objects.filter(programa__clave="CC", reglas_cargadas__isnull=False).order_by("-anio").first()
    if ejercicio is None or SesionComite.objects.filter(ejercicio=ejercicio).exists():
        return 0
    u = {x.username: x for x in Usuario.objects.all()}
    d_ame, d_tol, d_val = u["del_amecameca"], u["del_toluca"], u["del_valle"]
    drff, uj, st = u["dir_drff"], u["juridica"], u["comite"]
    creadas = 0

    # Catálogos de la Unidad Jurídica
    incumplida, _ = PersonaIncumplida.objects.get_or_create(
        curp="BANR600101HMCTXG09", defaults={
            "nombre": "Rogelio Bautista Núñez", "programa": "Capturando Carbono 2024",
            "motivo": "No realizó las actividades comprometidas ni reintegró el recurso (8.1.8.1 fr. I).",
            "acuerdo": "CAS-CC/02.ORD/007/2025", "fecha_inscripcion": timezone.localdate() - timedelta(days=300),
            "registrado_por": uj})
    PredioSancionado.objects.get_or_create(
        descripcion_predio="Predio El Zacatonal, Ixtapan del Oro", defaults={
            "tipo": "procedimiento", "descripcion": "Procedimiento administrativo por aprovechamiento sin autorización.",
            "autoridad": "PROFEPA, Delegación Estado de México", "registrado_por": uj})

    # Expedientes validados que pasan por el dictamen
    agua_blanca = Predio.objects.filter(nombre="Predio Agua Blanca").first()
    agua_blanca = agua_blanca.expedientes.filter(ejercicio=ejercicio).first() if agua_blanca else None
    encinos = _validada(d_ame, drff, ejercicio, "Juchitepec", "Los Encinos del Monte", "Ernestina Flores Medina",
                        "reforestacion", 9, curp="FOME720815MMCLDR01")
    joya = _validada(d_ame, drff, ejercicio, "Juchitepec", "La Joya Alta", "Pablo Juárez Santana", "reforestacion", 5,
                     desplazamiento=(180, 120))
    ocotal = _validada(d_tol, drff, ejercicio, "Ocoyoacac", "El Ocotal", "Gerardo Mejía Ortiz", "plantacion_maderable", 15)
    cruz = _validada(d_val, drff, ejercicio, "Villa de Allende", "Cerro de la Cruz", "Rogelio Bautista Núñez",
                     "reforestacion", 11, curp="BANR600101HMCTXG09")
    trojes = _validada(d_val, drff, ejercicio, "Villa Victoria", "Las Trojes", "Martina Colín Reyes", "reforestacion", 20)
    creadas += 5

    tecnico.dictaminar(drff, encinos, "factible", "Reforestación de 6 años con densidad de 72 %; cumple los criterios de 8.1.1.1.")
    for exp, motivo in [(joya, "Reforestación de 5 años; el traslape con Los Encinos del Monte se ajustó en campo."),
                        (cruz, "Reforestación de 7 años con densidad suficiente."),
                        (trojes, "Reforestación en zona alta de cuenca; densidad de 68 %.")]:
        tecnico.dictaminar(drff, exp, "factible", motivo)
    juridico.dictaminar(uj, joya, "procedente", "Documentación legal completa y vigente.")
    juridico.dictaminar(uj, trojes, "procedente", "Escritura pública y CURP vigentes.")
    juridico.dictaminar(uj, cruz, "no_procedente", "El titular está en el Listado de Personas Beneficiarias Incumplidas.")
    if agua_blanca is not None and agua_blanca.estado.clave == "validada":
        tecnico.dictaminar(drff, agua_blanca, "factible", "Refrendo: concluyó las actividades del ejercicio anterior.")
        juridico.dictaminar(uj, agua_blanca, "procedente", "Refrendo con documentación vigente; nuevo dictamen jurídico (10.1 fr. IV).")

    # Sesión de aprobación con acta
    fecha = timezone.localtime(timezone.now()).replace(hour=11, minute=0, second=0, microsecond=0)
    fecha = timezone.make_aware(datetime.combine(dias_habiles.sumar_dias_habiles(fecha, 5), fecha.time()))
    sesion = sesiones.crear_sesion(
        st, ejercicio, TipoSesion.APROBACION, fecha, "Sala de juntas de PROBOSQUE, Metepec (y videoconferencia)",
        "Lista de asistencia y declaración de quórum\nLectura y aprobación del orden del día\n"
        "Presentación del listado preliminar de solicitudes factibles y no factibles\n"
        "Aprobación de la Lista de Personas Beneficiarias, la Lista de espera y la Lista de solicitudes No factibles\n"
        "Autorización de la publicación de resultados\nAsuntos generales")
    sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo("Listado preliminar CC 2026"), name="listado_preliminar.pdf"),
                               "Listado preliminar de solicitudes")
    sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo("Dictamenes tecnicos y juridicos"), name="dictamenes.pdf"),
                               "Dictámenes técnicos y jurídicos")
    sesiones.enviar_convocatoria(st, sesion)
    aprobacion.proponer_listados(st, sesion, Decimal("57000"))
    aprobacion.registrar_acta(st, sesion, True, "Se aprueban los listados por unanimidad.")

    # Expediente dictaminado después de la sesión (queda en la bandeja de la Secretaría Técnica)
    potrero = _validada(d_ame, drff, ejercicio, "Tenango del Aire", "Potrero Viejo", "Sergio Ayala Pineda", "reforestacion", 4)
    tecnico.dictaminar(drff, potrero, "factible", "Reforestación de 4 años; cumple la densidad mínima.")
    juridico.dictaminar(uj, potrero, "procedente", "Documentación legal vigente.")
    creadas += 1

    # Sesión de seguimiento con acuerdos
    fecha2 = timezone.make_aware(datetime.combine(dias_habiles.sumar_dias_habiles(fecha, 10), fecha.time()))
    seg = sesiones.crear_sesion(st, ejercicio, TipoSesion.SEGUIMIENTO, fecha2, "Sala de juntas de PROBOSQUE, Metepec",
                                "Lista de asistencia y declaración de quórum\nSeguimiento de casos del ejercicio\nAsuntos generales")
    sesiones.agregar_documento(st, seg, ContentFile(_pdf_demo("Casos para seguimiento"), name="casos.pdf"), "Casos para seguimiento")
    sesiones.enviar_convocatoria(st, seg)
    drff_unidad = Unidad.objects.get(clave="DRFF")
    if agua_blanca is not None:
        seguimiento.registrar_acuerdo(st, seg, "caso_fortuito", "Atender el aviso de incendio en la parte baja del predio "
                                      "y ajustar la propuesta FO-PB-520-B con la Delegación.", [agua_blanca], drff_unidad)
    reasignado = seguimiento.registrar_acuerdo(
        st, seg, "reasignacion", "Reasignar el recurso liberado por desistimiento a la primera solicitud de la lista de espera.",
        [trojes], drff_unidad)
    seguimiento.cumplir(drff, reasignado, "Se notificó por conducto de la Delegación Amecameca.")
    seguimiento.registrar_acuerdo(st, seg, "otro", "Revisar con la Unidad Jurídica la situación del titular del Cerro de la Cruz.",
                                  [cruz], Unidad.objects.get(clave="UJ"))
    return creadas
