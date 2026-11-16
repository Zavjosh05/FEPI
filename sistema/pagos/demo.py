"""Datos de demostración del módulo M5 (idempotente): un lote de solicitudes aprobadas, publicadas, contratadas y con su oficio
en CC, PS, RHF y PSAHEM, con la solicitud de la primera ministración en cada punto del camino. Todo con los servicios de M1, M2,
M3 y M5, igual que la interfaz.

HU-5.1: CC (pago único de 4 ha, 70 % de 6 a 9 ha), PS, RHF y PSAHEM con su oficio de la Delegación y su comprobante de cuenta
donde las reglas lo piden: solicitudes enviadas a Administración y Finanzas, una por enviar con todos sus soportes y un contrato
firmado al que todavía le falta el oficio (con la solicitud incompleta). En PSAHEM, la instrucción de pago del Comité Técnico
(acuerdo de seguimiento) es el soporte que completa la primera ministración.

HU-5.2: Administración y Finanzas revisa las solicitudes enviadas: devuelve una con observaciones (CC), acepta y paga las de
``pagada`` (transferencia en CC y PS; cheque excepcional con su motivo en RHF), acepta la de ``aceptada`` (PSAHEM, por solicitar a la
Fiduciaria) y, en PSAHEM, la Secretaría Técnica solicita a la Fiduciaria el pago de las demás (``remitida`` en adelante).

HU-5.3: la Fiduciaria emite el cheque de las solicitudes remitidas; uno queda emitido (Paraje Las Ánimas), otro enviado a la
Delegación (Monte Alto), otro entregado a la persona (Cerro del Venado) y otro entregado hace casi 3 meses, por vencer sin cobro
(Loma Verde; calendario simulado). ``revisar_cobros`` deja el aviso en la bitácora.

Cada solicitud lleva su ``destino``: lo que las historias HU-5.2 y HU-5.3 hacen después con ella (devolver, pagar, remitir a la
Fiduciaria, emitir y entregar el cheque); cada historia agrega su paso al final de ``cargar_demo``.
"""
from datetime import datetime, time, timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from contrato import contratos, planta, publicacion
from contrato.demo import _delegacion, _despues, _firmar_demo, _modelo_validado
from contrato.models import Especie, Vivero
from dictamen import aprobacion, juridico, seguimiento, sesiones, tecnico
from dictamen.demo import _validada
from dictamen.models import SesionComite, TipoSesion
from nucleo import dias_habiles
from nucleo.demo import _pdf_demo, archivo_demo
from nucleo.models import Ejercicio, Expediente, Hito, Unidad, Usuario

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


def _ejercicio(clave):
    return Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()


def _aprobar_y_contratar(u, ejercicio, plan):
    """Dictamina, aprueba en sesión con acta, publica, notifica, elabora el contrato, lo envía y lo firma. Devuelve los
    expedientes (con su destino) ya en ``contratada``."""
    clave = ejercicio.programa.clave
    drff, uj, st = u["dir_drff"], u["juridica"], u["comite"]
    exps = []
    for i, (usuario, municipio, predio, persona, modalidad, ha, destino) in enumerate(plan):
        # Cada polígono se desplaza para no traslapar con los de otras solicitudes del mismo municipio.
        exp = _validada(u[usuario], drff, ejercicio, municipio, predio, persona, modalidad, ha,
                        desplazamiento=(3000 + i * 900, 1500 + (i % 3) * 600))
        tecnico.dictaminar(drff, exp, "factible", "Cumple los criterios técnicos de elegibilidad de las reglas.")
        juridico.dictaminar(uj, exp, "procedente", "Documentación legal completa y vigente.")
        exps.append((exp, destino))
    fecha = timezone.localtime(timezone.now()) - timedelta(hours=1)
    sesion = sesiones.crear_sesion(
        st, ejercicio, TipoSesion.APROBACION, fecha, "Sala de juntas de PROBOSQUE, Metepec",
        "\n".join(["Lista de asistencia y declaración de quórum", "Presentación del listado preliminar",
                   "Aprobación de los listados", "Autorización de la publicación de resultados"]))
    sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo(f"Listado preliminar {clave} (pagos)"),
                                                       name="listado_preliminar.pdf"), "Listado preliminar")
    sesiones.enviar_convocatoria(st, sesion, momento=fecha - timedelta(days=21))
    aprobacion.proponer_listados(st, sesion)
    aprobacion.registrar_acta(st, sesion, True, "Se aprueban los listados por unanimidad.",
                              momento=fecha + timedelta(minutes=20))
    sesion.refresh_from_db()
    pub = publicacion.publicar(drff, sesion, momento=_despues(sesion.acta_fecha, 10))
    modelo = _modelo_validado(u, ejercicio, f"Contrato de Adhesión {clave} {ejercicio.anio} (modelo de demostración)")
    for exp, _ in exps:
        publicacion.registrar_entrega(_delegacion(u, exp), exp.notificaciones.get(tipo="resultados"), "personal",
                                      fecha_hora=_despues(pub.publicada_en, 15), observaciones="Entregado (demostración).")
        exp.refresh_from_db()
        contrato = contratos.elaborar_contrato(drff, exp, modelo)
        contratos.enviar_a_delegacion(drff, contrato)
        exp.refresh_from_db()
        _firmar_demo(u, exp)
        exp.refresh_from_db()
    return exps


def _planta_completa(u, exp):
    """PS y RHF con Vale: la planta se entrega completa para poder solicitar la ministración."""
    planta.cargar_catalogo()
    vivero = Vivero.objects.filter(unidad__isnull=False).first()
    especie = Especie.objects.get(nombre="Pino patula")
    vale = planta.emitir_vale(_delegacion(u, exp), exp, vivero, [(especie, 900)],
                              motivo_ajuste="Cantidad de demostración.")
    planta.registrar_salida(u["vivero"], vale, especie, 900)
    exp.refresh_from_db()


def _instruccion_de_pago(u, ejercicio, expedientes):
    """PSAHEM: el Comité Técnico instruye a la Fiduciaria el pago de la primera ministración (sesión de seguimiento)."""
    st = u["comite"]
    cuando = timezone.make_aware(datetime.combine(dias_habiles.sumar_dias_habiles(timezone.now(), 15), time(11, 0)))
    sesion = sesiones.crear_sesion(st, ejercicio, TipoSesion.SEGUIMIENTO, cuando, "Sala de juntas de PROBOSQUE, Metepec",
                                   "Lista de asistencia y declaración de quórum\nInstrucción de pago a la Fiduciaria\nAsuntos generales")
    sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo("Solicitudes de pago PSAHEM"), name="pagos.pdf"),
                               "Solicitudes de pago")
    sesiones.enviar_convocatoria(st, sesion)
    return seguimiento.registrar_acuerdo(
        st, sesion, "instruccion_pago", "Instruir a la Fiduciaria el pago de la primera ministración (70 %) de las personas "
        "beneficiarias de la lista.", expedientes, Unidad.objects.get(clave="FIDUCIARIA"), ministracion=1)


def _tramitar(u, exp, destino, clave):
    """HU-5.1: el oficio de la Delegación, el comprobante de la cuenta y la solicitud de la primera ministración."""
    deleg, drff = _delegacion(u, exp), u["dir_drff"]
    if destino in SIN_COMPROBANTE:
        return
    solicitudes.emitir_oficio(deleg, exp)
    if any(s["clave"] == "comprobante_cuenta" for s in solicitudes.soportes_requeridos(exp, 1)):
        solicitudes.adjuntar_comprobante(deleg, exp, archivo_demo(f"cuenta_{exp.folio}.pdf", f"Estado de cuenta {exp.folio}"),
                                         "Estado de cuenta bancario (demostración)")
    if destino == "por_enviar":
        solicitudes.preparar_solicitud(drff, exp, 1)
        return
    solicitudes.enviar_solicitud(drff, exp, 1, "Solicitud de demostración.")


def _revisiones(u):
    """HU-5.2: revisión de Administración y Finanzas, pagos y remisión a la Fiduciaria de las solicitudes enviadas."""
    af, st = u["finanzas"], u["comite"]
    hechas = 0
    for sol in SolicitudPago.objects.filter(estado=EstadoSolicitud.ENVIADA, ministracion=1).select_related(
            "expediente__predio", "expediente__ejercicio__programa"):
        destino = DESTINOS.get(sol.expediente.predio.nombre)
        if destino == "devuelta":
            pagos.revisar_solicitud(af, sol, "devuelta", "El comprobante de la cuenta bancaria no es legible; la Delegación debe "
                                                         "recabar uno nuevo y el área reenviar la solicitud.")
        elif destino in ("pagada", "aceptada", "remitida", "cheque_emitido", "cheque_enviado", "cheque_entregado",
                         "cheque_por_vencer"):
            pagos.revisar_solicitud(af, sol, "aceptada", "Soportes completos.")
            if destino == "pagada":
                excepcional = sol.expediente.programa.clave == "RHF"
                pagos.registrar_pago(
                    af, sol, f"{'CHQ' if excepcional else 'SPEI'}-{sol.pk:06d}", timezone.localdate(),
                    tipo="cheque_excepcional" if excepcional else None,
                    motivo_cheque="La persona beneficiaria no cuenta con la cuenta bancaria vigente (demostración)."
                    if excepcional else "")
            elif destino != "aceptada":
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
        cheque = cheques.emitir_cheque(fid, sol, f"FIPASAHEM-{sol.pk:06d}")
        if destino != "cheque_emitido":
            cheques.enviar_a_delegacion(fid, cheque)
        if destino in ("cheque_entregado", "cheque_por_vencer"):
            cheque = cheques.registrar_entrega(_delegacion(u, sol.expediente), cheque, sol.expediente.solicitante.nombre)
        if destino == "cheque_por_vencer":  # calendario simulado: se entregó hace casi 3 meses
            antes = timezone.now() - timedelta(days=88)
            cheque.entregado_en = antes
            cheque.vence_cobro = cheques.vencimiento_cobro(cheque).vencimiento
            cheque.save(update_fields=["entregado_en", "vence_cobro"])
            Hito.objects.filter(expediente=sol.expediente, clave="entrega_cheque").update(fecha_hora=antes)
            cheques.revisar_cobros(timezone.localdate())
        hechas += 1
    return hechas


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
            _instruccion_de_pago(u, ejercicio, [e for e, d in exps if d != "sin_oficio"])
        for exp, destino in exps:
            if clave == "PS" and destino != "sin_oficio":
                _planta_completa(u, exp)
            _tramitar(u, exp, destino, clave)
            hechas += 1
    hechas += _revisiones(u)
    hechas += _cheques(u)
    return hechas
