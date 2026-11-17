"""Datos de demostración de MFS y Guardabosques (idempotente; S3-02e): solicitudes recibidas y, para las historias de M4,
expedientes contratados y con la primera ministración pagada, listos para comprobar. Todo con los servicios de M1 a M5, igual
que la interfaz, en las fechas del calendario de 2026 (reloj simulado, ``nucleo/reloj.py``):

- **MFS** (Comité de Admisión y Seguimiento; aprobación hasta el 24-jun y firma hasta el 15-jul): registro en marzo, sesión el
  16-jun, firma el 26-jun y primera ministración pagada en julio. Bosque Los Volcanes (Programa de Manejo maderable de 7 a 95 ha,
  70 %) y Aserradero La Cumbre (certificación FSC de cadena de custodia, 50 %) quedan pagados y esperan su entregable (Bitácora
  o solicitud de auditoría, HU-4.1); Predio El Mirador queda contratado. El polígono lo levanta el prestador con RFN.
- **PEG** (CASPEG; la Dirección de Protección Forestal es la Instancia Ejecutora): solicitan los núcleos agrarios y la persona
  beneficiaria es el Guardabosque. Sesión del CASPEG el 9-jun, firma el 16-jun (10 días hábiles desde la aprobación),
  validación de los reportes de junio el 7-jul y depósito del 25 % el 14-jul en Ejido San Juan y Ejido San Bartolo; Ejido
  Santa Ana queda contratado. La cuenta del portal de Margarito Sánchez Ruiz (usuario ``SARM800101HMCNZR09``) queda activa con
  la contraseña de demostración.
- Una solicitud recién recibida de cada programa (Predio Agua Fría en MFS y Ejido San Lorenzo en PEG).
"""
from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.db import transaction

from contrato import contratos, publicacion
from contrato.demo import _delegacion, _firmar_demo
from contrato.models import ModeloContrato, TipoModelo
from dictamen import juridico, seguimiento, sesiones, tecnico
from dictamen.demo import _validada, paso, sesion_aprobacion
from dictamen.models import TipoSesion
from nucleo.demo import CONTRASENA_DEMO, _pdf_demo, _solicitud, archivo_demo, completar_requisitos
from nucleo.demo_calendario import cuando, habil, habil_antes
from nucleo.models import Ejercicio, Expediente, Usuario
from pagos import pagos, solicitudes

# programa: [(Delegación, municipio, predio, persona que solicita, modalidad, ha, destino, extra)]
LOTES = {
    "MFS": [("del_amecameca", "Amecameca", "Bosque Los Volcanes", "Ejido San Pedro Nexapa", "etf_pmf_maderable_7_95", 40,
             "pagada", {"tipo": "nucleo_agrario", "levantado_por": "prestador"}),
            ("del_toluca", "Zinacantepec", "Aserradero La Cumbre", "Maderas La Cumbre", "fsc_certificacion_cadena_custodia", 12,
             "pagada", {"tipo": "juridica_colectiva", "levantado_por": "prestador"}),
            ("del_valle", "Amanalco", "Predio El Mirador", "Andrés Colín Mercado", "etf_no_maderables", 20,
             "contratada", {"tipo": "fisica", "curp": "COMA750612HMCLRN04", "levantado_por": "delegacion"})],
    "PEG": [("del_amecameca", "Amecameca", "Ejido San Juan", "Ejido San Juan", "apoyo_monetario_guardabosque", None, "pagada",
             {"tipo": "nucleo_agrario", "beneficiaria_nombre": "Margarito Sánchez Ruiz", "beneficiaria_curp": "SARM800101HMCNZR09"}),
            ("del_valle", "Amanalco", "Ejido San Bartolo", "Ejido San Bartolo", "apoyo_monetario_guardabosque", None, "pagada",
             {"tipo": "nucleo_agrario", "beneficiaria_nombre": "Juana Colín Esquivel", "beneficiaria_curp": "COEJ850315MMCLSN02"}),
            ("del_toluca", "Temoaya", "Ejido Santa Ana", "Ejido Santa Ana", "apoyo_monetario_guardabosque", None, "contratada",
             {"tipo": "nucleo_agrario", "beneficiaria_nombre": "Bernardo Flores Nava", "beneficiaria_curp": "FONB780921HMCLVR01"})],
}
RECIBIDAS = {
    "MFS": ("del_toluca", "Zinacantepec", "Predio Agua Fría", "Ofelia Ramos Cruz", "fisica", "etf_pmf_maderable_95_250", "150",
            "2026-03-23", {}),
    "PEG": ("del_valle", "Villa Victoria", "Ejido San Lorenzo", "Ejido San Lorenzo", "nucleo_agrario",
            "apoyo_monetario_guardabosque", None, "2026-03-27",
            {"beneficiaria_nombre": "Tomás Reyes Albarrán", "beneficiaria_curp": "REAT820704HMCYLM03"}),
}
CALENDARIO = {
    "MFS": dict(registro="2026-03-09", tecnico="2026-04-20", juridico="2026-05-04", sesion="2026-06-16", publicacion="2026-06-18",
                notificacion="2026-06-22", contrato="2026-06-23", firma="2026-06-26", oficio="2026-06-29", solicitud="2026-07-01",
                revision="2026-07-03", pago="2026-07-07"),
    "PEG": dict(registro="2026-03-24", tecnico="2026-04-20", juridico="2026-04-27", sesion="2026-06-09", publicacion="2026-06-11",
                notificacion="2026-06-12", contrato="2026-06-12", firma="2026-06-16", validacion="2026-07-07",
                solicitud="2026-07-08", revision="2026-07-10", pago="2026-07-14"),
}
PERIODO_VALIDADO = "2026-06"  # PEG: reportan desde el mes de la firma (Convocatoria base quinta, VII)


def _direccion(u, clave):
    return u["dir_dpf"] if clave == "PEG" else u["dir_drff"]


def _modelo(u, ejercicio, direccion):
    nombre = f"Contrato de Adhesión {ejercicio.programa.clave} {ejercicio.anio} (modelo de demostración)"
    existente = ModeloContrato.objects.filter(ejercicio=ejercicio, nombre=nombre).first()
    if existente:
        return existente
    texto = contratos.PLANTILLAS_BASE[TipoModelo.CONTRATO_ADHESION].replace(contratos.MARCA_BORRADOR, "").strip()
    with paso("2026-06-01", 10):
        m = contratos.registrar_modelo(direccion, ejercicio, TipoModelo.CONTRATO_ADHESION, nombre, texto)
    with paso("2026-06-02", 11):
        contratos.validar_version(u["juridica"], m.vigente, "Cláusulas revisadas contra las Reglas de Operación 2026 (demostración).")
    return m


def _validar_reportes(u, ejercicio, expedientes, fecha):
    """PEG: el CASPEG valida la evaluación de los reportes del periodo (sesión de seguimiento, 5 días hábiles de anticipación)."""
    st = u["comite"]
    fecha = habil(fecha)
    with paso(habil_antes(fecha, 7), 12):
        s = sesiones.crear_sesion(st, ejercicio, TipoSesion.SEGUIMIENTO, cuando(fecha, 11), "Sala de juntas de PROBOSQUE, Metepec",
                                  "Lista de asistencia y declaración de quórum\nValidación de la evaluación de reportes\nAsuntos generales")
        sesiones.agregar_documento(st, s, ContentFile(_pdf_demo("Evaluación de reportes de junio"), name="reportes.pdf"),
                                   "Evaluación de reportes")
    with paso(habil_antes(fecha, 5), 10):
        sesiones.enviar_convocatoria(st, s)
    with paso(fecha, 12):
        seguimiento.registrar_acuerdo(st, s, "validacion_reportes", "Se valida la evaluación de los reportes mensuales de junio "
                                      "de los Guardabosques de la lista.", expedientes, periodo=PERIODO_VALIDADO)


def _lote(u, ejercicio, clave):
    c = CALENDARIO[clave]
    direccion, uj, st, af = _direccion(u, clave), u["juridica"], u["comite"], u["finanzas"]
    exps = []
    for i, (deleg, municipio, predio, persona, modalidad, ha, destino, extra) in enumerate(LOTES[clave]):
        exp = _validada(u[deleg], direccion, ejercicio, municipio, predio, persona, modalidad, ha,
                        registro=habil(c["registro"], i), **extra)
        with paso(habil(c["tecnico"], i), 10):
            tecnico.dictaminar(direccion, exp, "factible", "Cumple los criterios técnicos de elegibilidad de las reglas.")
        with paso(habil(c["juridico"], i), 10):
            juridico.dictaminar(uj, exp, "procedente", "Documentación legal completa y vigente.")
        exps.append((exp, destino))
    sesion = sesion_aprobacion(st, ejercicio, c["sesion"], [f"Listado preliminar {clave}"])
    with paso(c["publicacion"], 10):
        publicacion.publicar(direccion, sesion)
    modelo = _modelo(u, ejercicio, direccion)
    for exp, _ in exps:
        exp.refresh_from_db()
        with paso(c["notificacion"], 11):
            publicacion.registrar_entrega(_delegacion(u, exp), exp.notificaciones.get(tipo="resultados"), "personal",
                                          observaciones="Entregado (demostración).")
        with paso(c["contrato"], 13):
            contrato = contratos.elaborar_contrato(direccion, exp, modelo)
        with paso(c["contrato"], 15):
            contratos.enviar_a_delegacion(direccion, contrato)
        exp.refresh_from_db()
        with paso(c["firma"], 12):
            _firmar_demo(u, exp)
    pagados = [exp for exp, destino in exps if destino == "pagada"]
    for exp in pagados:
        exp.refresh_from_db()
        deleg = _delegacion(u, exp)
        with paso(c.get("oficio", c["firma"]), 16):
            if any(s["clave"] == "oficio_delegacion" for s in solicitudes.soportes_requeridos(exp, 1)):
                solicitudes.emitir_oficio(deleg, exp)
            solicitudes.adjuntar_comprobante(deleg, exp, archivo_demo(f"cuenta_{exp.folio}.pdf", f"Estado de cuenta {exp.folio}"),
                                             "Estado de cuenta bancario (demostración)")
    if clave == "PEG":
        _validar_reportes(u, ejercicio, pagados, c["validacion"])
    for exp in pagados:
        with paso(c["solicitud"], 10):
            sol = solicitudes.enviar_solicitud(direccion, exp, 1, "Solicitud de demostración.")
        with paso(c["revision"], 10):
            pagos.revisar_solicitud(af, sol, "aceptada", "Soportes completos.")
        with paso(c["pago"], 11):
            pagos.registrar_pago(af, sol, f"{'DEP' if clave == 'PEG' else 'SPEI'}-{sol.pk:06d}", cuando(c["pago"]).date())
    return len(exps)


def _recibida(u, ejercicio, clave):
    deleg, municipio, predio, persona, tipo, modalidad, ha, fecha, extra = RECIBIDAS[clave]
    with paso(habil(fecha), 10):
        exp = _solicitud(u[deleg], ejercicio, municipio, predio, persona, tipo, modalidad, ha, **extra)
        completar_requisitos(u[deleg], exp)
    return 1


def _portal_demo():
    """La cuenta del portal del primer Guardabosque queda activa con la contraseña de demostración."""
    from django.utils import timezone

    from portal.models import CuentaExterna

    cuenta = CuentaExterna.objects.filter(usuario__username="SARM800101HMCNZR09", activada_en__isnull=True).first()
    if cuenta:
        cuenta.usuario.password = make_password(CONTRASENA_DEMO)
        cuenta.usuario.save(update_fields=["password"])
        cuenta.activada_en, cuenta.codigo_hash = timezone.now(), ""
        cuenta.save(update_fields=["activada_en", "codigo_hash"])


@transaction.atomic
def cargar_demo():
    u = {x.username: x for x in Usuario.objects.all()}
    hechas = 0
    for clave in ("MFS", "PEG"):
        ejercicio = Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()
        if ejercicio is None:
            continue
        if not Expediente.objects.filter(ejercicio=ejercicio, predio__nombre=LOTES[clave][0][2]).exists():
            hechas += _lote(u, ejercicio, clave)
        if not Expediente.objects.filter(ejercicio=ejercicio, predio__nombre=RECIBIDAS[clave][2]).exists():
            hechas += _recibida(u, ejercicio, clave)
    _portal_demo()
    return hechas
