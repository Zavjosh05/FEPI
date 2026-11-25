"""Datos de demostración de MFS y Guardabosques (idempotente; S3-02e): solicitudes recibidas y, para las historias de M4,
expedientes contratados y con la primera ministración pagada, listos para comprobar. Todo con los servicios de M1 a M5, igual
que la interfaz, en las fechas del calendario de 2026 (reloj simulado, ``nucleo/reloj.py``). Lo de M4 depende del calendario
de las reglas (fechas límite de conclusión y de entrega del informe o la verificación) y va fijo; solo los reportes mensuales
del PEG siguen a la fecha de corte (``nucleo/demo_calendario.py``, por omisión el día de la carga):

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

**HU-4.1 · Envío de comprobaciones** (``_comprobaciones``): en MFS, Bosque Los Volcanes entrega su Bitácora en la Delegación el
2-oct (queda por verificar y su segunda ministración tiene soporte) y Aserradero La Cumbre sigue esperando su solicitud de
auditoría; en PEG, Margarito Sánchez Ruiz envía por el portal sus reportes de junio a octubre (el de octubre, del 4-nov, está
por revisar en la Delegación; cargada después de noviembre, también los meses que hayan terminado antes de la fecha de corte, y
el último es el que queda por revisar: ``_reportes_san_juan``) y la Delegación recaba su acuse de depósito; Ejido San Bartolo
entrega en ventanilla los de junio y julio (le falta agosto). Del lote de pagos (``pagos/demo.py``): Predio La Ciénega (CC)
avisa el término el 10-nov y entrega su Informe Final el 17-nov, Plantación La Mesa (PS) avisa el término el 28-sep y Manantial Alto (RHF, Restauración Forestal
Integral Modalidad uno, que concluye en octubre) el 28-oct.

**HU-4.2 · Verificación en campo** (``_verificaciones``): el área responsable revisa la Bitácora de Bosque Los Volcanes el 6-oct y
su segunda ministración (30 %, $9,000) se paga el 14-oct; la Delegación de Toluca verifica Plantación La Mesa el 15-oct con 1.8 de
2 ha (90 %), sobrevivencia del 78 % y una helada como caso fortuito con su acta, así que su segunda ministración queda por
solicitar en $2,000 (la parte proporcional: 1.8 ha × $5,000 menos los $7,000 ya ministrados); Manantial Alto se verifica completo
el 9-nov, en plazo por concluir en octubre; Predio La Ciénega (pago único) se verifica el 18-nov con el Informe Final firmado y
el área da por concluidas sus actividades el 19-nov.

**HU-4.3 · Evaluación de reportes** (PEG; ``_reportes_junio`` y ``_evaluaciones``): los reportes de junio (San Juan por el portal el
3-jul, San Bartolo en ventanilla el 6-jul) se revisan, se evalúan «cumple» y la Dirección de Protección Forestal envía la evaluación
del periodo al CASPEG el 6-jul, que la valida el 7-jul con su acuerdo de seguimiento: de ahí sale el depósito del 14-jul. Santa Ana
no entrega ningún reporte y queda «no entregó» (señalado) en todos los periodos. Julio y agosto se evalúan el 6-ago y el 4-sep y el
CASPEG los valida el 15-sep: San Juan cobra su segunda ministración (22-sep); San Bartolo entregó julio pero no agosto, así que
queda «no entregó» en agosto y su segunda ministración no se puede solicitar. Septiembre (San Juan, con observaciones) queda por
evaluar y el reporte de octubre de San Juan por revisar en la Delegación.
"""
from datetime import date, timedelta

from django.contrib.auth.hashers import make_password
from django.core.files.base import ContentFile
from django.db import transaction

from contrato import contratos, publicacion
from contrato.demo import _delegacion, _firmar_demo
from contrato.models import ModeloContrato, TipoModelo
from dictamen import juridico, seguimiento, sesiones, tecnico
from dictamen.demo import _validada, paso, propiedad_en_regla, sesion_aprobacion
from dictamen.models import TipoSesion
from nucleo import dias_habiles
from nucleo.demo import CONTRASENA_DEMO, _pdf_demo, _solicitud, archivo_demo, completar_requisitos
from nucleo.demo_calendario import con_corte, cuando, fecha_corte, habil, habil_antes, meses_terminados
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


def _validar_reportes(u, ejercicio, periodos, fecha):
    """PEG: el CASPEG valida la evaluación de los reportes (sesión de seguimiento, 5 días hábiles de anticipación).
    ``periodos``: ``[(clave del periodo, nombre, expedientes evaluados)]``."""
    st = u["comite"]
    fecha = habil(fecha)
    nombres = " y ".join(n for _, n, _ in periodos)
    with paso(habil_antes(fecha, 7), 12):
        s = sesiones.crear_sesion(st, ejercicio, TipoSesion.SEGUIMIENTO, cuando(fecha, 11), "Sala de juntas de PROBOSQUE, Metepec",
                                  "Lista de asistencia y declaración de quórum\nValidación de la evaluación de reportes\nAsuntos generales")
        sesiones.agregar_documento(st, s, ContentFile(_pdf_demo(f"Evaluación de reportes de {nombres}"), name="reportes.pdf"),
                                   "Evaluación de reportes")
    with paso(habil_antes(fecha, 5), 10):
        sesiones.enviar_convocatoria(st, s)
    with paso(fecha, 12):
        for clave, nombre, expedientes in periodos:
            seguimiento.registrar_acuerdo(st, s, "validacion_reportes", f"Se valida la evaluación de los reportes mensuales de "
                                          f"{nombre} de los Guardabosques de la lista.", expedientes, periodo=clave)


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
            juridico.dictaminar(uj, exp, "procedente", "Documentación legal completa y vigente.",
                                propiedad=propiedad_en_regla(exp))
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
        _portal_demo()
        _reportes_junio(u, ejercicio, [exp for exp, _ in exps])
        _validar_reportes(u, ejercicio, [(PERIODO_VALIDADO, "junio", [exp for exp, _ in exps])], c["validacion"])
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


@con_corte
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
    _comprobaciones(u)
    _evaluaciones(u)
    _verificaciones(u)
    return hechas


# ----------------------------------------------------------------------------- HU-4.1
def _envio(usuario, exp, tipo, fecha, hora=10, **kw):
    from . import comprobaciones

    archivo = kw.pop("archivo", None)
    if archivo is None and comprobaciones.tipo_de_envio(exp, tipo).get("requiere_archivo"):
        archivo = archivo_demo(f"{tipo}_{exp.folio}.pdf", f"{tipo} {exp.folio}")
    with paso(fecha, hora):
        return comprobaciones.registrar_envio(usuario, exp, tipo, archivo=archivo, **kw)


def _revisar(u, c, fecha, resultado="revisado", observaciones="", hora=16):
    """La Delegación revisa un reporte o un acuse de depósito (HU-4.3)."""
    from . import reportes

    with paso(fecha, hora):
        return reportes.revisar(_delegacion(u, c.expediente), c, resultado, observaciones)


def _reportes_san_juan():
    """Reportes mensuales de San Juan por el portal: ``[(periodo, fecha de envío, revisión o None)]``. Julio a septiembre van
    fijos; desde octubre, uno por cada mes que terminó antes de la fecha de corte (``meses_terminados``), enviado el segundo día
    hábil del mes siguiente (o la fecha de corte, si ésta llega antes) y revisado ese día, salvo el último, que queda por revisar
    en la Delegación. Con el corte de referencia (19-nov) es solo octubre, enviado el 4-nov."""
    filas = [("2026-07", "2026-08-04", ("revisado", "")), ("2026-08", "2026-09-03", ("revisado", "")),
             ("2026-09", "2026-10-05", ("con_observaciones", "Falta la evidencia fotográfica de dos recorridos."))]
    meses = meses_terminados("2026-10")
    for i, periodo in enumerate(meses):
        anio, mes = map(int, periodo.split("-"))
        fin = dias_habiles.sumar_meses(date(anio, mes, 1), 1) - timedelta(days=1)
        envio = min(habil(fin, 2), fecha_corte())
        filas.append((periodo, envio, None if i == len(meses) - 1 else ("revisado", "")))
    return filas


def _comprobaciones(u):
    """HU-4.1: envíos por el portal y entregas en ventanilla, cada uno en su fecha (idempotente por expediente)."""
    def exp_de(nombre):
        return Expediente.objects.filter(predio__nombre=nombre, firma_contrato__isnull=False).first()

    volcanes = exp_de("Bosque Los Volcanes")
    if volcanes is not None and not volcanes.comprobaciones.exists():
        _envio(_delegacion(u, volcanes), volcanes, "bitacora_etf", "2026-10-02", persona_entrega="Prestador de servicios forestales (RFN)",
               descripcion="Copia de la Bitácora ingresada para la autorización del Programa de Manejo.")
    san_juan = exp_de("Ejido San Juan")
    margarito = Usuario.objects.filter(username="SARM800101HMCNZR09", cuenta_externa__activada_en__isnull=False).first()
    if san_juan is not None and margarito is not None:
        for periodo, fecha, revision in _reportes_san_juan():
            if san_juan.comprobaciones.filter(tipo="reporte_mensual", periodo=periodo).exists():
                continue
            c = _envio(margarito, san_juan, "reporte_mensual", fecha, 9, periodo=periodo,
                       descripcion="Recorridos de vigilancia y brechas cortafuego.")
            if revision:
                _revisar(u, c, fecha, *revision)
        if not san_juan.comprobaciones.filter(tipo="acuse_deposito").exists():
            c = _envio(_delegacion(u, san_juan), san_juan, "acuse_deposito", "2026-07-16", fecha_hecho=date(2026, 7, 14))
            _revisar(u, c, "2026-07-16")
    san_bartolo = exp_de("Ejido San Bartolo")
    if san_bartolo is not None and not san_bartolo.comprobaciones.filter(tipo="reporte_mensual", periodo="2026-07").exists():
        c = _envio(_delegacion(u, san_bartolo), san_bartolo, "reporte_mensual", "2026-08-05", periodo="2026-07")
        _revisar(u, c, "2026-08-05")  # agosto no lo entrega: «no entregó»
    for nombre, fecha, termino in (("Plantación La Mesa", "2026-09-28", date(2026, 9, 25)),
                                   ("Manantial Alto", "2026-10-28", date(2026, 10, 27)),
                                   ("Predio La Ciénega", "2026-11-10", date(2026, 11, 9))):
        exp = exp_de(nombre)
        if exp is None or exp.comprobaciones.exists() or exp.estado.clave != "pagada":
            continue
        _envio(_delegacion(u, exp), exp, "aviso_termino", fecha, fecha_hecho=termino,
               descripcion="La persona beneficiaria informa en la Delegación que concluyó las actividades.")
        if exp.programa.clave == "CC":
            _envio(_delegacion(u, exp), exp, "informe_final", "2026-11-17", 12,
                   descripcion="Informe Final de Actividades FO-PB-509-A firmado por la persona beneficiaria y el técnico.")


# ----------------------------------------------------------------------------- HU-4.2
def _verificaciones(u):
    """HU-4.2: resultados de la verificación (y su segunda ministración en MFS), idempotente por expediente."""
    from . import verificacion

    def pendiente(nombre):
        exp = Expediente.objects.filter(predio__nombre=nombre, estado__clave="comprobacion_enviada").first()
        return exp if exp is not None and not exp.verificaciones.exists() else None

    volcanes = pendiente("Bosque Los Volcanes")
    if volcanes is not None:
        with paso("2026-10-06", 11):
            verificacion.registrar_verificacion(u["dir_drff"], volcanes, "revision_entregable",
                                                archivo_demo("revision_bitacora.pdf", "Revisión de la Bitácora"),
                                                observaciones="La Bitácora corresponde al Programa de Manejo del concepto aprobado.")
        with paso("2026-10-08", 10):
            sol = solicitudes.enviar_solicitud(u["dir_drff"], volcanes, 2, "Segunda ministración con la Bitácora.")
        with paso("2026-10-12", 10):
            pagos.revisar_solicitud(u["finanzas"], sol, "aceptada", "Soportes completos.")
        with paso("2026-10-14", 11):
            pagos.registrar_pago(u["finanzas"], sol, f"SPEI-{sol.pk:06d}", cuando("2026-10-14").date())
    la_mesa = pendiente("Plantación La Mesa")
    if la_mesa is not None:
        with paso("2026-10-15", 12):
            verificacion.registrar_verificacion(
                _delegacion(u, la_mesa), la_mesa, "formato_verificacion", archivo_demo("formato_la_mesa.pdf", "Formato de verificación"),
                fecha_visita=date(2026, 10, 13), superficie_verificada="1.8", sobrevivencia="78",
                incidencias=[{"tipo": "caso_fortuito", "descripcion": "Helada en 0.2 ha del rodal norte.",
                              "archivo": archivo_demo("acta_helada.pdf", "Acta de la helada")}])
    manantial = pendiente("Manantial Alto")
    if manantial is not None:
        with paso("2026-11-09", 12):
            verificacion.registrar_verificacion(
                _delegacion(u, manantial), manantial, "formato_verificacion", archivo_demo("formato_manantial.pdf", "Formato"),
                fecha_visita=date(2026, 11, 5), superficie_verificada="2", sobrevivencia="85")
    cienega = pendiente("Predio La Ciénega")
    if cienega is not None:
        with paso("2026-11-18", 12):
            verificacion.registrar_verificacion(
                _delegacion(u, cienega), cienega, "informe_final_firmado", archivo_demo("informe_firmado.pdf", "Informe Final"),
                fecha_visita=date(2026, 11, 13), superficie_verificada="4")
        with paso("2026-11-19", 10):
            verificacion.dar_por_concluida(u["dir_drff"], cienega)


# ----------------------------------------------------------------------------- HU-4.3
def _reportes_junio(u, ejercicio, exps):
    """HU-4.3 (primer periodo, antes del primer depósito): los reportes de junio de San Juan (portal, 3-jul) y San Bartolo
    (ventanilla, 6-jul) se revisan, la Dirección los evalúa «cumple» y envía la evaluación del periodo al CASPEG el 6-jul. Santa
    Ana no entregó: «no entregó» en automático."""
    from . import reportes

    por_predio = {e.predio.nombre: e for e in exps}
    margarito = Usuario.objects.filter(username="SARM800101HMCNZR09", cuenta_externa__activada_en__isnull=False).first()
    direccion = u["dir_dpf"]
    san_juan, san_bartolo = por_predio["Ejido San Juan"], por_predio["Ejido San Bartolo"]
    c1 = _envio(margarito, san_juan, "reporte_mensual", "2026-07-03", 9, periodo="2026-06",
                descripcion="Recorridos de vigilancia y brechas cortafuego.")
    _revisar(u, c1, "2026-07-03")
    c2 = _envio(_delegacion(u, san_bartolo), san_bartolo, "reporte_mensual", "2026-07-06", 10, periodo="2026-06")
    _revisar(u, c2, "2026-07-06", hora=12)
    for exp in (san_juan, san_bartolo):
        with paso("2026-07-06", 14):
            reportes.evaluar_periodo(direccion, exp, "2026-06", "cumple")
    with paso("2026-07-06", 15):
        reportes.enviar_evaluacion(direccion, ejercicio, "2026-06")


def _evaluaciones(u):
    """HU-4.3: julio y agosto se evalúan y se envían al CASPEG (6-ago y 4-sep), que los valida el 15-sep; San Juan cobra su segunda
    ministración y San Bartolo, que no entregó agosto, no (idempotente por periodo)."""
    from . import reportes
    from .models import EnvioEvaluacion

    ejercicio = Ejercicio.objects.filter(programa__clave="PEG", reglas_cargadas__isnull=False).order_by("-anio").first()
    if ejercicio is None:
        return
    direccion = u["dir_dpf"]
    exps = {e.predio.nombre: e for e in Expediente.objects.filter(ejercicio=ejercicio, firma_contrato__isnull=False)
            .select_related("predio")}
    if not {"Ejido San Juan", "Ejido San Bartolo", "Ejido Santa Ana"} <= set(exps):
        return
    san_juan, san_bartolo = exps["Ejido San Juan"], exps["Ejido San Bartolo"]
    if EnvioEvaluacion.objects.filter(ejercicio=ejercicio, periodo="2026-07").exists():
        return
    # El reporte de julio de los dos llegó en agosto; el de agosto solo lo entregó San Juan (3-sep).
    for exp in (san_juan, san_bartolo):
        with paso("2026-08-06", 14):
            reportes.evaluar_periodo(direccion, exp, "2026-07", "cumple")
    with paso("2026-08-06", 15):
        reportes.enviar_evaluacion(direccion, ejercicio, "2026-07")
    with paso("2026-09-04", 14):
        reportes.evaluar_periodo(direccion, san_juan, "2026-08", "cumple")
    with paso("2026-09-04", 15):
        reportes.enviar_evaluacion(direccion, ejercicio, "2026-08")
    todos = list(exps.values())
    _validar_reportes(u, ejercicio, [("2026-07", "julio", todos), ("2026-08", "agosto", todos)], "2026-09-15")
    with paso("2026-09-17", 10):
        sol = solicitudes.enviar_solicitud(direccion, san_juan, 2, "Segunda ministración con la evaluación de julio y agosto validada.")
    with paso("2026-09-21", 10):
        pagos.revisar_solicitud(u["finanzas"], sol, "aceptada", "Soportes completos.")
    with paso("2026-09-22", 11):
        pagos.registrar_pago(u["finanzas"], sol, f"DEP-{sol.pk:06d}", cuando("2026-09-22").date())
