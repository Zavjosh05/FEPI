"""Datos de demostración del módulo M2 (idempotente): expedientes en dictamen y dictaminados, una persona en el
Listado de Incumplidas, una sesión de aprobación con acta y una de seguimiento con acuerdos. Cada dictamen expide su documento
en PDF y el jurídico revisa la propiedad del predio; en la sesión de seguimiento La Joya Alta desiste y su recurso se reasigna a
Las Trojes, la primera de la lista de espera (HU-2.4).

Todo ocurre en las fechas del calendario de la Convocatoria de CC 2026 (reloj simulado, ``nucleo/reloj.py``): solicitudes del 3 al
24 de marzo (recepción hasta el 27-mar), validación en el plazo de la ventanilla, dictámenes en abril y mayo (la fecha límite es el
30-jun) y la sesión de aprobación del Comité el 14-jul (aprobación del 1 al 31-jul). Hay casos fuera de plazo a propósito: El Ocotal
nunca tuvo dictamen técnico (venció el 30-jun; el jurídico no acredita la posesión) y Potrero Viejo se dictaminó el 15-jul, después de la fecha límite. La sesión de seguimiento se
convocó con anticipación y se celebra después de la fecha de corte (``nucleo/demo_calendario.py``)."""
from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from nucleo import reloj
from nucleo.demo import _pdf_demo, _solicitud, completar_requisitos, cuadro_en_municipio
from nucleo.demo_calendario import cuando, habil, habil_antes
from nucleo.models import Ejercicio, Predio, Unidad, Usuario
from recepcion import servicios as recepcion

from . import aprobacion, juridico, seguimiento, sesiones, tecnico
from .models import PersonaIncumplida, PredioSancionado, SesionComite, TipoSesion


def paso(fecha, hora=10, minuto=0):
    """Reloj simulado en la fecha (un tic de 2 s por lectura, para que cada renglón tenga su segundo)."""
    return reloj.en(cuando(fecha, hora, minuto), tic=2)


def _validada(u_del, u_dir, ejercicio, municipio, predio, persona, modalidad, ha, desplazamiento=(0, 0), registro=None, **extra):
    """Solicitud registrada, con requisitos, polígono, enviada a la Dirección y validada. Con ``registro`` (fecha del registro)
    cada paso ocurre en su día del calendario: polígono al día hábil siguiente, envío a los 2 y validación a los 5 días hábiles;
    sin ella, todo ocurre «ahora» (fixtures de pruebas)."""
    if registro is None:
        exp = _solicitud(u_del, ejercicio, municipio, predio, persona, "fisica", modalidad, str(ha), **extra)
        completar_requisitos(u_del, exp)
        recepcion.registrar_poligono(u_del, exp, cuadro_en_municipio(exp.predio.municipio, ha, desplazamiento), "dibujo",
                                     "delegacion", "Brigada de la Delegación", timezone.localdate() - timedelta(days=5))
        recepcion.enviar_a_direccion(u_del, exp)
        recepcion.validar_expediente(u_dir, exp)
        exp.refresh_from_db()
        return exp
    registro = habil(registro)
    with paso(registro, 9):
        exp = _solicitud(u_del, ejercicio, municipio, predio, persona, "fisica", modalidad, str(ha), **extra)
        completar_requisitos(u_del, exp)
    with paso(habil(registro, 1), 12):
        recepcion.registrar_poligono(u_del, exp, cuadro_en_municipio(exp.predio.municipio, ha, desplazamiento), "dibujo",
                                     "delegacion", "Brigada de la Delegación", timezone.localdate() - timedelta(days=1))
    with paso(habil(registro, 2), 10):
        recepcion.enviar_a_direccion(u_del, exp)
    with paso(habil(registro, 5), 11):
        recepcion.validar_expediente(u_dir, exp)
    exp.refresh_from_db()
    return exp


def sesion_aprobacion(st, ejercicio, fecha, documentos, observaciones="Se aprueban los listados por unanimidad.",
                      presupuesto=None, puntos=None, lugar="Sala de juntas de PROBOSQUE, Metepec"):
    """Sesión de aprobación del Comité con su ciclo completo en las fechas del calendario: se crea y se agregan los
    documentos una semana antes, se convoca con 5 días hábiles de anticipación (las reglas piden 3), se propone el listado un día
    hábil antes y el acta se registra el día de la sesión, a las 13:00 (la sesión es a las 11:00). Devuelve la sesión con acta."""
    fecha_sesion = habil(fecha)
    puntos = puntos or ["Lista de asistencia y declaración de quórum", "Presentación del listado preliminar",
                        "Aprobación de los listados", "Autorización de la publicación de resultados"]
    with paso(habil_antes(fecha_sesion, 7), 12):
        sesion = sesiones.crear_sesion(st, ejercicio, TipoSesion.APROBACION, cuando(fecha_sesion, 11), lugar, "\n".join(puntos))
        for nombre in documentos:
            sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo(f"{nombre} {ejercicio.programa.clave} {ejercicio.anio}"),
                                                               name=f"{nombre.lower().replace(' ', '_')}.pdf"), nombre)
    with paso(habil_antes(fecha_sesion, 5), 10):
        sesiones.enviar_convocatoria(st, sesion)
    with paso(habil_antes(fecha_sesion, 1), 16):
        if presupuesto is None:
            aprobacion.proponer_listados(st, sesion)
        else:
            aprobacion.proponer_listados(st, sesion, presupuesto)
    with paso(fecha_sesion, 13):
        aprobacion.registrar_acta(st, sesion, True, observaciones)
    sesion.refresh_from_db()
    return sesion


def propiedad_en_regla(expediente, **cambios):
    """Revisión de la propiedad de demostración y de prueba: escritura pública a nombre del titular que ampara el predio."""
    from .juridico import superficie_a_acreditar

    superficie = superficie_a_acreditar(expediente) or Decimal("10")
    datos = {"tipo_documento": "escritura", "numero_documento": f"Escritura {1000 + expediente.pk}",
             "fecha_documento": timezone.localdate() - timedelta(days=3650), "titular_documento": expediente.solicitante.nombre,
             "titular_coincide": True, "superficie_documento_ha": (Decimal(superficie) * Decimal("1.25")).quantize(Decimal("0.0001")),
             "vigente_hasta": None, "sin_conflicto": True, "observaciones": ""}
    datos.update(cambios)
    return datos


def verificacion_revisada(expediente, respuesta="si"):
    """Lista de verificación de demostración con todos los criterios revisados (como la deja la pantalla)."""
    return {i["clave"]: {"respuesta": respuesta} for i in tecnico.lista_verificacion(expediente.ejercicio, expediente.modalidad)
            if not i.get("informativo")}


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
    with paso("2026-02-03", 12):
        PersonaIncumplida.objects.get_or_create(
            curp="BANR600101HMCTXG09", defaults={
                "nombre": "Rogelio Bautista Núñez", "programa": "Capturando Carbono 2024",
                "motivo": "No realizó las actividades comprometidas ni reintegró el recurso (8.1.8.1 fr. I).",
                "acuerdo": "CAS-CC/02.ORD/007/2025", "fecha_inscripcion": timezone.localdate() - timedelta(days=300),
                "registrado_por": uj})
        PredioSancionado.objects.get_or_create(
            descripcion_predio="Predio El Zacatonal, Ixtapan del Oro", defaults={
                "tipo": "procedimiento", "descripcion": "Procedimiento administrativo por aprovechamiento sin autorización.",
                "autoridad": "PROFEPA, Delegación Estado de México", "registrado_por": uj})

    # Expedientes que se registran en marzo y la Dirección valida en el plazo de la ventanilla (recepción hasta el 27-mar)
    agua_blanca = Predio.objects.filter(nombre="Predio Agua Blanca").first()
    agua_blanca = agua_blanca.expedientes.filter(ejercicio=ejercicio).first() if agua_blanca else None
    encinos = _validada(d_ame, drff, ejercicio, "Juchitepec", "Los Encinos del Monte", "Ernestina Flores Medina",
                        "reforestacion", 9, curp="FOME720815MMCLDR01", registro="2026-03-03")
    joya = _validada(d_ame, drff, ejercicio, "Juchitepec", "La Joya Alta", "Pablo Juárez Santana", "reforestacion", 5,
                     desplazamiento=(180, 120), registro="2026-03-04")
    ocotal = _validada(d_tol, drff, ejercicio, "Ocoyoacac", "El Ocotal", "Gerardo Mejía Ortiz", "plantacion_maderable", 15,
                       registro="2026-03-05")
    cruz = _validada(d_val, drff, ejercicio, "Villa de Allende", "Cerro de la Cruz", "Rogelio Bautista Núñez",
                     "reforestacion", 11, curp="BANR600101HMCTXG09", registro="2026-03-09")
    trojes = _validada(d_val, drff, ejercicio, "Villa Victoria", "Las Trojes", "Martina Colín Reyes", "reforestacion", 4.5,
                       registro="2026-03-10")
    creadas += 5

    # Dictámenes de abril y mayo, antes de la fecha límite (30-jun); a El Ocotal nunca se le hizo (dictamen vencido a propósito)
    with paso("2026-04-14", 10):
        tecnico.dictaminar(drff, encinos, "factible", "Reforestación de 6 años con densidad de 72 %; cumple los criterios de 8.1.1.1.",
                           verificacion_revisada(encinos))
    for dia, exp, motivo in [("2026-04-15", joya, "Reforestación de 5 años; el traslape con Los Encinos del Monte se ajustó en campo."),
                             ("2026-04-16", cruz, "Reforestación de 7 años con densidad suficiente."),
                             ("2026-04-17", trojes, "Reforestación en zona alta de cuenca; densidad de 68 %.")]:
        with paso(dia, 10):
            tecnico.dictaminar(drff, exp, "factible", motivo, verificacion_revisada(exp))
    with paso("2026-05-05", 10):
        juridico.dictaminar(uj, joya, "procedente", "Documentación legal completa y vigente; se acredita la propiedad.",
                            propiedad=propiedad_en_regla(joya, tipo_documento="certificado_parcelario",
                                                         numero_documento="Certificado parcelario 000123456"))
    with paso("2026-05-06", 10):
        juridico.dictaminar(uj, trojes, "procedente", "Escritura pública y CURP vigentes; la escritura ampara el predio.",
                            propiedad=propiedad_en_regla(trojes))
    with paso("2026-05-07", 10):
        juridico.dictaminar(uj, cruz, "no_procedente", "El titular está en el Listado de Personas Beneficiarias Incumplidas.",
                            propiedad=propiedad_en_regla(cruz))
    # Propiedad no acreditada: la constancia de posesión venció (sin dictamen técnico, El Ocotal sigue con su plazo vencido).
    with paso("2026-05-08", 10):
        juridico.dictaminar(uj, ocotal, "no_procedente",
                            "No se acredita la legal posesión: la constancia de posesión venció y no ampara toda la superficie.",
                            propiedad=propiedad_en_regla(ocotal, tipo_documento="constancia_posesion",
                                                         numero_documento="Constancia 45/2024 del Comisariado Ejidal",
                                                         superficie_documento_ha=Decimal("10"),
                                                         vigente_hasta=timezone.localdate() - timedelta(days=40)))
    if agua_blanca is not None and agua_blanca.estado.clave == "validada":
        with paso("2026-04-20", 10):
            tecnico.dictaminar(drff, agua_blanca, "factible", "Refrendo: concluyó las actividades del ejercicio anterior.",
                               verificacion_revisada(agua_blanca))
        with paso("2026-04-21", 10):
            juridico.dictaminar(uj, agua_blanca, "procedente", "Refrendo con documentación vigente; nuevo dictamen jurídico (10.1 fr. IV).",
                                propiedad=propiedad_en_regla(agua_blanca))

    # Sesión de aprobación del Comité (aprobación del 1 al 31-jul): el 14-jul, con acta
    sesion_aprobacion(st, ejercicio, "2026-07-14", ["Listado preliminar de solicitudes", "Dictámenes técnicos y jurídicos"],
                      presupuesto=Decimal("26000"), puntos=[
                          "Lista de asistencia y declaración de quórum", "Lectura y aprobación del orden del día",
                          "Presentación del listado preliminar de solicitudes factibles y no factibles",
                          "Aprobación de la Lista de Personas Beneficiarias, la Lista de espera y la Lista de solicitudes No factibles",
                          "Autorización de la publicación de resultados", "Asuntos generales"])

    # Expediente que se dictamina después de la sesión y de la fecha límite (fuera de plazo, a propósito); queda en la bandeja
    # de la Secretaría Técnica
    potrero = _validada(d_ame, drff, ejercicio, "Tenango del Aire", "Potrero Viejo", "Sergio Ayala Pineda", "reforestacion", 4,
                        registro="2026-03-24")
    with paso("2026-07-15", 15):
        tecnico.dictaminar(drff, potrero, "factible", "Reforestación de 4 años; cumple la densidad mínima.",
                           verificacion_revisada(potrero))
    with paso("2026-07-16", 10):
        juridico.dictaminar(uj, potrero, "procedente", "Documentación legal vigente.", propiedad=propiedad_en_regla(potrero))
    creadas += 1

    # Sesión de seguimiento con acuerdos: se convoca en noviembre y se celebra después de la fecha de corte
    fecha_seg = habil("2026-11-24")
    with paso("2026-11-09", 12):
        seg = sesiones.crear_sesion(st, ejercicio, TipoSesion.SEGUIMIENTO, cuando(fecha_seg, 11),
                                    "Sala de juntas de PROBOSQUE, Metepec",
                                    "Lista de asistencia y declaración de quórum\nSeguimiento de casos del ejercicio\nAsuntos generales")
        sesiones.agregar_documento(st, seg, ContentFile(_pdf_demo("Casos para seguimiento"), name="casos.pdf"), "Casos para seguimiento")
    with paso("2026-11-10", 10):
        sesiones.enviar_convocatoria(st, seg)
    drff_unidad = Unidad.objects.get(clave="DRFF")
    with paso("2026-11-11", 10):
        if agua_blanca is not None:
            seguimiento.registrar_acuerdo(st, seg, "caso_fortuito", "Atender el aviso de incendio en la parte baja del predio "
                                          "y ajustar la propuesta FO-PB-520-B con la Delegación.", [agua_blanca], drff_unidad,
                                          causa="Aviso de incendio de la Delegación Toluca del 10/11/2026.")
        # Incidente: La Joya Alta desiste; su recurso se reasigna a la primera de la lista de espera (Las Trojes).
        joya.refresh_from_db()
        baja = None
        if joya.estado.clave == "aprobada":
            baja = seguimiento.registrar_acuerdo(
                st, seg, "desistimiento", f"Se acepta el desistimiento de {joya.solicitante.nombre} y se libera su recurso.",
                [joya], drff_unidad, causa="Escrito de desistimiento presentado en la Delegación Amecameca el 10/11/2026.")
            lista = seguimiento.lista_de_espera(ejercicio)
            if lista and (lista[0]["monto"] is None or lista[0]["monto"] <= seguimiento.recurso_liberado(ejercicio)):
                seguimiento.registrar_acuerdo(
                    st, seg, "reasignacion", "Reasignar el recurso liberado por el desistimiento a la primera solicitud de la "
                                             "lista de espera.", [lista[0]["expediente"]], drff_unidad)
        seguimiento.registrar_acuerdo(st, seg, "otro", "Revisar con la Unidad Jurídica la situación del titular del Cerro de la Cruz.",
                                      [cruz], Unidad.objects.get(clave="UJ"))
    if baja is not None:
        with paso("2026-11-12", 10):
            seguimiento.cumplir(drff, baja, "Se notificó la baja por conducto de la Delegación Amecameca.")
    return creadas
