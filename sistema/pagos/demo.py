"""Datos de demostración del módulo M5 (idempotente): un lote de solicitudes aprobadas, publicadas, contratadas y con su oficio
en CC, PS, RHF y PSAHEM, con la solicitud de la primera ministración en cada punto del camino. Todo con los servicios de M1, M2,
M3 y M5, igual que la interfaz, y en las fechas del calendario de 2026 (reloj simulado, ``nucleo/reloj.py``; ver
``nucleo/demo_calendario.py`` para la fecha de corte, por omisión el día de la carga).

**Calendario del lote** (``CALENDARIO``): registro en marzo (recepción hasta el 27-mar), dictámenes en abril a junio, sesión de
aprobación del Comité en julio (CC y PSAHEM; aprobación del 1 al 31-jul) o en agosto (PS y RHF, sin fecha límite), publicación dos
días hábiles después, notificación, contrato elaborado y enviado, y firma dentro de los 10 días hábiles; el oficio de la Delegación
y la solicitud de pago siguen después, cada destino en su fecha (``FECHAS_DESTINO``). Las fechas de octubre y noviembre son del
calendario de referencia (corte el 19-nov-2026) y se trasladan a la fecha de corte de la carga en días hábiles (``reciente``,
D-32); las de Loma Verde, a partir de su entrega (``entrega_cheque_por_vencer``), para que su cheque quede siempre por vencer.

HU-5.1: CC (pago único de 4 ha, 70 % de 6 a 9 ha), PS, RHF y PSAHEM con su oficio de la Delegación y su comprobante de cuenta
donde las reglas lo piden: solicitudes enviadas a Administración y Finanzas, una por enviar con todos sus soportes y un contrato
firmado al que todavía le falta el oficio (con la solicitud incompleta). En PSAHEM, la instrucción de pago del Comité Técnico
(acuerdo de seguimiento) es el soporte que completa la primera ministración.

HU-5.2: Administración y Finanzas revisa las solicitudes enviadas: devuelve una con observaciones (CC), acepta y paga las de
``pagada`` (transferencia en CC y PS; cheque excepcional con su motivo en RHF), acepta la de ``aceptada`` (PSAHEM, por solicitar a la
Fiduciaria) y, en PSAHEM, la Secretaría Técnica solicita a la Fiduciaria el pago de las demás (``remitida`` en adelante), siempre
dentro de sus 5 días hábiles.

HU-5.3: la Fiduciaria emite el cheque de las solicitudes remitidas; uno queda emitido (Paraje Las Ánimas), otro enviado a la
Delegación (Monte Alto), otro entregado a la persona (Cerro del Venado) y otro entregado hace casi tres meses (el 21-ago con el
corte de referencia), que vence a dos días hábiles de la fecha de corte y está por vencer sin cobro (Loma Verde).
``revisar_cobros`` deja el aviso en la bitácora.

Cada solicitud lleva su ``destino``: lo que las historias HU-5.2 y HU-5.3 hacen después con ella (devolver, pagar, remitir a la
Fiduciaria, emitir y entregar el cheque); cada historia agrega su paso al final de ``cargar_demo``.
"""
from django.core.files.base import ContentFile
from django.db import transaction

from contrato import contratos, planta, publicacion
from contrato.demo import _delegacion, _firmar_demo, _modelo_validado, dictaminar_lote
from contrato.models import Especie, Vivero
from dictamen import seguimiento, sesiones
from dictamen.demo import paso, sesion_aprobacion
from dictamen.models import TipoSesion
from nucleo.demo import _pdf_demo, archivo_demo
from nucleo.demo_calendario import (con_corte, cuando, entrega_cheque_por_vencer, fecha_corte, habil, habil_antes, reciente,
                                    trasladar)
from nucleo.models import Ejercicio, Expediente, Unidad, Usuario

from . import cheques, pagos, solicitudes
from .models import EstadoSolicitud, SolicitudPago

# programa: [(usuario de la Delegación, municipio, predio, persona, modalidad, hectáreas, destino)]
# destino: sin_oficio · por_enviar · enviada · devuelta · pagada · (PSAHEM) aceptada · remitida · cheque_emitido ·
# cheque_enviado · cheque_entregado · cheque_por_vencer
LOTES = {
    "CC": [("del_amecameca", "Amecameca", "Predio La Ciénega", "Mario Vázquez Luna", "reforestacion", 4, "pagada"),
           ("del_toluca", "Zinacantepec", "Predio Las Palomas", "Rosa Elena Mejía Soto", "reforestacion", 8, "enviada"),
           ("del_valle", "Amanalco", "Predio El Fresno", "Héctor Salgado Rivas", "reforestacion", 7, "devuelta"),
           ("del_amecameca", "Juchitepec", "Predio Santa Cruz", "Lucía Ortega Paz", "reforestacion", 6, "por_enviar"),
           ("del_toluca", "Temoaya", "Predio El Paraíso", "Mauricio Díaz Rey", "reforestacion", 9, "sin_oficio")],
    "PS": [("del_amecameca", "Tlalmanalco", "Plantación El Cedro", "Verónica Ibarra Luna", "plantacion_forestal_comercial", 3, "enviada"),
           ("del_toluca", "Zinacantepec", "Plantación La Mesa", "Arturo Quiroz Peña", "mantenimiento_plantaciones", 2, "pagada")],
    "RHF": [("del_amecameca", "Ozumba", "Cañada Verde", "Raquel Montes Alba", "rfi_modalidad_uno", 3, "por_enviar"),
            ("del_valle", "Amanalco", "Manantial Alto", "Teodoro Ríos Cano", "rfi_modalidad_uno", 2, "pagada")],
    "PSA": [("del_toluca", "Ocoyoacac", "Rancho El Pedregal", "Alberto Cruz Vilchis", "cuenca_alta", 20, "enviada"),
            ("del_valle", "Villa Victoria", "Ejido La Joya", "Marcela Peña Dorantes", "cuenca_media_baja", 25, "aceptada"),
            ("del_toluca", "Ocoyoacac", "Bosque Los Cedros", "Ramón Estrada Lugo", "cuenca_alta", 18, "remitida"),
            ("del_valle", "Villa Victoria", "Paraje Las Ánimas", "Dolores Nava Ibáñez", "cuenca_media_baja", 22, "cheque_emitido"),
            ("del_toluca", "Ocoyoacac", "Monte Alto", "Gerardo Salinas Mora", "cuenca_alta", 16, "cheque_enviado"),
            ("del_valle", "Villa Victoria", "Cerro del Venado", "Patricia Lozano Gil", "cuenca_media_baja", 24, "cheque_entregado"),
            ("del_toluca", "Ocoyoacac", "Loma Verde", "Efraín Rojas Soto", "cuenca_alta", 15, "cheque_por_vencer")],
}
SIN_COMPROBANTE = ("sin_oficio",)
DESTINOS = {fila[2]: fila[6] for plan in LOTES.values() for fila in plan}

# Calendario de cada lote (todas son fechas hábiles de 2026; el registro y los dictámenes avanzan un día hábil por solicitud).
CALENDARIO = {
    "CC": dict(registro="2026-03-11", tecnico="2026-05-04", juridico="2026-06-01", sesion="2026-07-21",
               publicacion="2026-07-23", notificacion="2026-07-27", contrato="2026-07-29", firma="2026-08-03",
               oficio="2026-08-10"),
    "PS": dict(registro="2026-03-12", tecnico="2026-04-22", juridico="2026-04-27", sesion="2026-08-11",
               publicacion="2026-08-13", notificacion="2026-08-14", contrato="2026-08-18", firma="2026-08-24",
               oficio="2026-09-14", planta="2026-09-02"),
    "RHF": dict(registro="2026-03-13", tecnico="2026-04-22", juridico="2026-04-28", sesion="2026-08-12",
                publicacion="2026-08-14", notificacion="2026-08-17", contrato="2026-08-19", firma="2026-08-25",
                oficio="2026-09-01"),
    "PSA": dict(registro="2026-03-16", tecnico="2026-05-18", juridico="2026-06-08", sesion="2026-07-22",
                publicacion="2026-07-24", notificacion="2026-07-27", contrato="2026-07-28", firma="2026-08-03",
                oficio="2026-08-10"),
}
# Fechas de cada destino (la solicitud se envía a Administración y Finanzas, ésta la revisa y, según el caso, la paga o la
# Secretaría Técnica la remite). Las «enviada» y «aceptada» se envían dos días hábiles antes de la fecha de corte: en PSAHEM la
# Secretaría Técnica tiene 5 días hábiles desde ese envío para remitirlas a la Fiduciaria y deben quedar en plazo (D-38). Loma Verde es el cheque por vencer: se tramitó en agosto; los demás cheques, en noviembre.
FECHAS_DESTINO = {
    "pagada": dict(solicitud="2026-09-21", revision="2026-09-24", pago="2026-09-28"),
    "enviada": dict(solicitud="2026-11-17"),
    "devuelta": dict(solicitud="2026-10-20", revision="2026-10-22"),
    "por_enviar": dict(preparar="2026-11-12"),
    "aceptada": dict(solicitud="2026-11-17", revision="2026-11-18"),
    "remitida": dict(solicitud="2026-11-05", revision="2026-11-09", remision="2026-11-10"),
    "cheque_emitido": dict(solicitud="2026-11-05", revision="2026-11-09", remision="2026-11-10", emision="2026-11-12"),
    "cheque_enviado": dict(solicitud="2026-11-05", revision="2026-11-09", remision="2026-11-10", emision="2026-11-12",
                           envio="2026-11-13"),
    "cheque_entregado": dict(solicitud="2026-11-05", revision="2026-11-09", remision="2026-11-10", emision="2026-11-12",
                             envio="2026-11-13", entrega="2026-11-17"),
    "cheque_por_vencer": dict(solicitud="2026-08-13", revision="2026-08-14", remision="2026-08-17", emision="2026-08-18",
                              envio="2026-08-19", entrega="2026-08-21"),
}
# Instrucciones de pago del Comité Técnico de PSAHEM (sesión de seguimiento): las de noviembre y la de agosto (Loma Verde).
# Fechas del calendario de referencia: «pagada» se queda en septiembre; lo demás se traslada (``_fecha``).
ENTREGA_POR_VENCER = "2026-08-21"   # entrega del cheque de Loma Verde en la referencia: todo su trámite se cuenta desde ella
SESIONES_INSTRUCCION = (("2026-11-04", ("Rancho El Pedregal", "Ejido La Joya", "Bosque Los Cedros", "Paraje Las Ánimas",
                                        "Monte Alto", "Cerro del Venado")),
                        ("2026-08-12", ("Loma Verde",)))


def _fecha(fecha, destino):
    """Fecha de un paso de ``destino`` llevada a la fecha de corte: la de «pagada» (septiembre) queda fija; las de Loma Verde se
    cuentan desde su entrega por vencer; las demás desde la fecha de corte (``reciente``)."""
    if destino == "pagada":
        return fecha
    if destino == "cheque_por_vencer":
        return trasladar(fecha, ENTREGA_POR_VENCER, entrega_cheque_por_vencer())
    return reciente(fecha)


def _ejercicio(clave):
    return Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()


def _aprobar_y_contratar(u, ejercicio, plan):
    """Dictamina, aprueba en sesión con acta, publica, notifica, elabora el contrato, lo envía y lo firma, cada paso en su fecha.
    Devuelve los expedientes (con su destino) ya en ``contratada``."""
    clave = ejercicio.programa.clave
    c = CALENDARIO[clave]
    drff, st = u["dir_drff"], u["comite"]
    filas = [(*f[:6], habil(c["registro"], i)) for i, f in enumerate(plan)]
    resultado = dictaminar_lote(u, ejercicio, filas, c["tecnico"], c["juridico"])
    exps = [(exp, fila[6]) for (exp, _), fila in zip(resultado, plan)]
    sesion = sesion_aprobacion(st, ejercicio, c["sesion"], [f"Listado preliminar {clave} (pagos)"])
    with paso(c["publicacion"], 10):
        publicacion.publicar(drff, sesion)
    modelo = _modelo_validado(u, ejercicio, f"Contrato de Adhesión {clave} {ejercicio.anio} (modelo de demostración)")
    for i, (exp, _) in enumerate(exps):
        with paso(c["notificacion"], 11):
            publicacion.registrar_entrega(_delegacion(u, exp), exp.notificaciones.get(tipo="resultados"), "personal",
                                          observaciones="Entregado (demostración).")
        exp.refresh_from_db()
        with paso(c["contrato"], 10):
            contrato = contratos.elaborar_contrato(drff, exp, modelo)
        with paso(c["contrato"], 15):
            contratos.enviar_a_delegacion(drff, contrato)
        exp.refresh_from_db()
        with paso(habil(c["firma"], i // 4), 12):
            _firmar_demo(u, exp)
        exp.refresh_from_db()
    return exps


def _planta_completa(u, exp, fecha):
    """PS con Vale: la planta se entrega completa para poder solicitar la ministración."""
    with paso(fecha, 10):
        planta.cargar_catalogo()
        vivero = Vivero.objects.filter(unidad__isnull=False).first()
        especie = Especie.objects.get(nombre="Pino patula")
        vale = planta.emitir_vale(_delegacion(u, exp), exp, vivero, [(especie, 900)], motivo_ajuste="Cantidad de demostración.")
    with paso(habil(fecha, 2), 12):
        planta.registrar_salida(u["vivero"], vale, especie, 900)
    exp.refresh_from_db()


def _instruccion_de_pago(u, ejercicio, expedientes, fecha):
    """PSAHEM: el Comité Técnico instruye a la Fiduciaria el pago de la primera ministración (sesión de seguimiento, que se
    convoca con 5 días hábiles de anticipación; el acuerdo se registra el día de la sesión, después de celebrada)."""
    st = u["comite"]
    fecha = habil(fecha)
    with paso(habil_antes(fecha, 7), 12):
        sesion = sesiones.crear_sesion(
            st, ejercicio, TipoSesion.SEGUIMIENTO, cuando(fecha, 11), "Sala de juntas de PROBOSQUE, Metepec",
            "Lista de asistencia y declaración de quórum\nInstrucción de pago a la Fiduciaria\nAsuntos generales")
        sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo("Solicitudes de pago PSAHEM"), name="pagos.pdf"),
                                   "Solicitudes de pago")
    with paso(habil_antes(fecha, 5), 10):
        sesiones.enviar_convocatoria(st, sesion)
    with paso(fecha, 12):
        return seguimiento.registrar_acuerdo(
            st, sesion, "instruccion_pago", "Instruir a la Fiduciaria el pago de la primera ministración (70 %) de las personas "
            "beneficiarias de la lista.", expedientes, Unidad.objects.get(clave="FIDUCIARIA"), ministracion=1)


def _tramitar(u, exp, destino, clave):
    """HU-5.1: el oficio de la Delegación, el comprobante de la cuenta y la solicitud de la primera ministración."""
    deleg, drff = _delegacion(u, exp), u["dir_drff"]
    if destino in SIN_COMPROBANTE:
        return
    f = {k: _fecha(v, destino) for k, v in FECHAS_DESTINO.get(destino, {}).items()}
    oficio = CALENDARIO[clave]["oficio"]
    if destino == "cheque_por_vencer":
        oficio = _fecha("2026-08-10", destino)
    with paso(oficio, 10):
        solicitudes.emitir_oficio(deleg, exp)
        if any(s["clave"] == "comprobante_cuenta" for s in solicitudes.soportes_requeridos(exp, 1)):
            solicitudes.adjuntar_comprobante(deleg, exp, archivo_demo(f"cuenta_{exp.folio}.pdf", f"Estado de cuenta {exp.folio}"),
                                             "Estado de cuenta bancario (demostración)")
    if destino == "por_enviar":
        with paso(f["preparar"], 10):
            solicitudes.preparar_solicitud(drff, exp, 1)
        return
    with paso(f["solicitud"], 10):
        solicitudes.enviar_solicitud(drff, exp, 1, "Solicitud de demostración.")


def _revisiones(u):
    """HU-5.2: revisión de Administración y Finanzas, pagos y remisión a la Fiduciaria de las solicitudes enviadas."""
    af, st = u["finanzas"], u["comite"]
    hechas = 0
    for sol in SolicitudPago.objects.filter(estado=EstadoSolicitud.ENVIADA, ministracion=1).select_related(
            "expediente__predio", "expediente__ejercicio__programa"):
        destino = DESTINOS.get(sol.expediente.predio.nombre)
        f = {k: _fecha(v, destino) for k, v in FECHAS_DESTINO.get(destino, {}).items()}
        if destino == "devuelta":
            with paso(f["revision"], 10):
                pagos.revisar_solicitud(af, sol, "devuelta", "El comprobante de la cuenta bancaria no es legible; la Delegación debe "
                                                             "recabar uno nuevo y el área reenviar la solicitud.")
        elif destino in ("pagada", "aceptada", "remitida", "cheque_emitido", "cheque_enviado", "cheque_entregado",
                         "cheque_por_vencer"):
            with paso(f["revision"], 10):
                pagos.revisar_solicitud(af, sol, "aceptada", "Soportes completos.")
            if destino == "pagada":
                excepcional = sol.expediente.programa.clave == "RHF"
                with paso(f["pago"], 11):
                    pagos.registrar_pago(
                        af, sol, f"{'CHQ' if excepcional else 'SPEI'}-{sol.pk:06d}", cuando(f["pago"]).date(),
                        tipo="cheque_excepcional" if excepcional else None,
                        motivo_cheque="La persona beneficiaria no cuenta con la cuenta bancaria vigente (demostración)."
                        if excepcional else "")
            elif destino != "aceptada":
                with paso(f["remision"], 10):
                    pagos.remitir_a_fiduciaria(st, sol, f"ST-FIPASAHEM/{sol.pk:03d}/2026", "Con la instrucción del Comité Técnico.")
        else:
            continue
        hechas += 1
    return hechas


def _cheques(u):
    """HU-5.3: cheques emitidos, enviados y entregados de las solicitudes remitidas a la Fiduciaria."""
    fid = u["fiduciaria"]
    hechas = 0
    for sol in SolicitudPago.objects.filter(estado=EstadoSolicitud.REMITIDA, cheque__isnull=True).select_related(
            "expediente__predio"):
        destino = DESTINOS.get(sol.expediente.predio.nombre)
        if destino not in ("cheque_emitido", "cheque_enviado", "cheque_entregado", "cheque_por_vencer"):
            continue
        f = {k: _fecha(v, destino) for k, v in FECHAS_DESTINO[destino].items()}
        with paso(f["emision"], 10):
            cheque = cheques.emitir_cheque(fid, sol, f"FIPASAHEM-{sol.pk:06d}")
        if destino != "cheque_emitido":
            with paso(f["envio"], 10):
                cheques.enviar_a_delegacion(fid, cheque)
        if destino in ("cheque_entregado", "cheque_por_vencer"):
            with paso(f["entrega"], 12):
                cheque = cheques.registrar_entrega(_delegacion(u, sol.expediente), cheque, sol.expediente.solicitante.nombre)
        hechas += 1
    # Loma Verde se entregó hace casi tres meses: en la fecha de corte le quedan 2 días hábiles (contados desde el ancla) para
    # cobrarlo.
    with paso(fecha_corte(), 9):
        cheques.revisar_cobros(fecha_corte())
    return hechas


@con_corte
@transaction.atomic
def cargar_demo():
    u = {x.username: x for x in Usuario.objects.all()}
    hechas = 0
    for clave, plan in LOTES.items():
        ejercicio = _ejercicio(clave)
        if ejercicio is None or Expediente.objects.filter(ejercicio=ejercicio, predio__nombre=plan[0][2]).exists():
            continue
        exps = _aprobar_y_contratar(u, ejercicio, plan)
        if clave == "PSA":
            por_nombre = {e.predio.nombre: e for e, _ in exps}
            for fecha, nombres in SESIONES_INSTRUCCION:
                destino = DESTINOS[nombres[0]]
                _instruccion_de_pago(u, ejercicio, [por_nombre[n] for n in nombres], _fecha(fecha, destino))
        for exp, destino in exps:
            if clave == "PS" and destino != "sin_oficio":
                _planta_completa(u, exp, CALENDARIO["PS"]["planta"])
            _tramitar(u, exp, destino, clave)
            hechas += 1
    hechas += _revisiones(u)
    hechas += _cheques(u)
    return hechas
