"""Recorrido completo del prototipo del sprint 2 con una solicitud por programa (CC, PS, RHF, PSAHEM, MFS y PEG).

«La solicitud de prueba se publica, su contrato se firma y se paga su primera ministración.» Parte de una solicitud
aprobada por la sesión del Comité (recorrido del sprint 1) y cada paso lo hace la unidad que le toca. En cada relevo
se comprueba el estado del expediente, en la bandeja de quién queda, el acuse, el renglón de la bitácora (usuario y
unidad) y las fechas que piden los criterios (publicación, envío, notificación, firma, pago o remisión, entrega).
MFS firma con su contrato de servicios técnicos (RFN) y carta compromiso, cobra un monto fijo por concepto (70/30 en
estudio técnico) y su segunda ministración espera la Bitácora (HU-4.1). PEG lo atiende la Dirección de Protección
Forestal: firma con la credencial del Guardabosque, la firma corre desde la aprobación del CASPEG, se paga por depósito
el 25 % (supuesto de las reglas) con la evaluación de reportes validada por el Comité.
"""
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from contrato import contratos, firma, planta, publicacion
from contrato.models import TipoModelo
from nucleo import montos, notificaciones
from nucleo.demo import archivo_demo
from nucleo.models import Hito, bandeja
from pagos import cheques, pagos, solicitudes
from pagos.models import EstadoSolicitud

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de, direccion_de, elementos_propios
from .fixtures_m5 import instruir_pago, validar_reportes

pytestmark = pytest.mark.django_db

UNIDADES = ("del_amecameca", "del_toluca", "del_valle", "dir_drff", "dir_dpf", "juridica", "comite", "finanzas",
            "vivero", "fiduciaria")
PROGRAMAS = ("CC", "PS", "RHF", "PSA", "MFS", "PEG")
# Lo que impide pedir la segunda ministración mientras no exista su historia de M4.
SEGUNDA_BLOQUEADA = {"MFS": "Copia de la Bitácora", "PEG": "Evaluación de los reportes"}


def atiende(exp, usuarios):
    """Usuarios de demostración que tienen el expediente en su bandeja (lo que les toca atender)."""
    return {u for u in UNIDADES if exp in bandeja(usuarios[u])}


class Rastro:
    """Lleva la cuenta de la bitácora y de los acuses de un expediente para comprobar cada relevo."""

    def __init__(self, exp):
        self.exp = exp
        self.eventos = exp.eventos.count()
        self.acuses = exp.acuses.count()

    def relevo(self, estado, quien, unidad_clave, bandeja_de, usuarios, nuevos_acuses=1, tipo_acuse=None):
        """El estado, la bandeja, el acuse y la bitácora del paso recién hecho."""
        self.exp.refresh_from_db()
        assert self.exp.estado.clave == estado, f"estado: {self.exp.estado.clave} (se esperaba {estado})"
        assert atiende(self.exp, usuarios) == set(bandeja_de), f"bandejas en {estado}: {atiende(self.exp, usuarios)}"
        nuevos = list(self.exp.eventos.order_by("-fecha_hora", "-pk")[: self.exp.eventos.count() - self.eventos])
        assert nuevos, "el paso no dejó renglón en la bitácora"
        assert all(e.fecha_hora for e in nuevos)
        if quien is not None:
            assert quien.pk in {e.usuario_id for e in nuevos}, "el renglón no lleva al usuario que lo hizo"
            assert quien.unidad_id in {e.unidad_id for e in nuevos}, "el renglón no lleva la unidad"
            assert unidad_clave is None or quien.unidad.clave == unidad_clave
        acuses = list(self.exp.acuses.order_by("-pk")[: self.exp.acuses.count() - self.acuses])
        assert len(acuses) >= nuevos_acuses, f"acuses nuevos: {[a.tipo for a in acuses]}"
        assert all(a.archivo for a in acuses)
        if tipo_acuse:
            assert tipo_acuse in {a.tipo for a in acuses}, [a.tipo for a in acuses]
        self.eventos = self.exp.eventos.count()
        self.acuses = self.exp.acuses.count()
        return acuses


def hito(exp, clave):
    return Hito.objects.get(expediente=exp, clave=clave)


@pytest.mark.parametrize("programa", PROGRAMAS)
def test_sprint_2_una_solicitud_se_publica_se_contrata_y_cobra_su_primera_ministracion(
        programa, aprobadas, modelo_validado, catalogo_planta, usuarios, pdf):
    u = usuarios
    sesion, (exp,) = aprobadas(programa, cuantas=1)
    ejercicio = exp.ejercicio
    dir_, jur, finanzas = direccion_de(u, ejercicio), u["juridica"], u["finanzas"]
    area = {dir_.username}
    deleg = delegado_de(u, exp)
    otra_deleg = u["del_valle"]
    assert otra_deleg.unidad_id != deleg.unidad_id
    assert exp.estado.clave == "aprobada" and atiende(exp, u) == area              # el área responsable publica
    r = Rastro(exp)

    # --- M3.1 Publicación de los listados autorizados y aviso de resultado ---------------------------------------
    for quien in ("del_amecameca", "finanzas", "comite", "juridica"):
        with pytest.raises(PermissionDenied):
            publicacion.publicar(u[quien], sesion)                  # solo la Dirección Instancia Ejecutora
    antes = timezone.now()
    pub = publicacion.publicar(dir_, sesion)
    assert antes <= pub.publicada_en <= timezone.now() and pub.publicada_por == dir_
    assert pub.acuse.tipo == "publicacion_resultados" and pub.acuse.archivo.open("rb").read(4) == b"%PDF"
    with pytest.raises(ValidationError):
        publicacion.publicar(dir_, sesion)                          # una sola vez por sesión
    assert hito(exp, "publicacion_resultados").fecha_hora == pub.publicada_en
    r.relevo("publicada", dir_, None, {delegado_de(u, exp).username}, u,
             tipo_acuse="envio_notificacion_resultados")
    aviso = exp.notificaciones.get(tipo="resultados")
    assert aviso.enviada_por == dir_ and aviso.enviada_en and aviso.notificada_en is None
    assert aviso in publicacion.por_entregar(deleg) and aviso not in publicacion.por_entregar(otra_deleg)

    # La Delegación registra la notificación a la persona (fecha, hora y medio); una Delegación ajena no puede.
    with pytest.raises(PermissionDenied):
        publicacion.registrar_entrega(otra_deleg, aviso, "personal")
    with pytest.raises(PermissionDenied):
        publicacion.registrar_entrega(dir_, aviso, "personal")
    publicacion.registrar_entrega(deleg, aviso, "personal")
    aviso.refresh_from_db()
    assert aviso.notificada_en and aviso.notificada_en >= pub.publicada_en and aviso.acuse_notificacion
    acuses = r.relevo("notificada", deleg, None, area, u, tipo_acuse=aviso.acuse_notificacion.tipo)
    # (la fecha de notificación arranca los plazos desde la Notificación misma, no desde un Hito: ver README)

    # --- M3.2 Modelo de contrato validado por la Unidad Jurídica; elaboración y envío a la Delegación -----------------
    texto = contratos.PLANTILLAS_BASE[TipoModelo.CONTRATO_ADHESION].replace(contratos.MARCA_BORRADOR, "").strip()
    mod = contratos.registrar_modelo(dir_, ejercicio, TipoModelo.CONTRATO_ADHESION, "Modelo del recorrido", texto)
    with pytest.raises(ValidationError, match="validad"):
        contratos.elaborar_contrato(dir_, exp, mod)                 # sin modelo validado no se elabora
    exp.refresh_from_db()
    assert exp.estado.clave == "notificada"
    with pytest.raises(PermissionDenied):
        contratos.validar_version(dir_, mod.vigente, "No me toca validarlo")
    contratos.validar_version(jur, mod.vigente, "Conforme.")
    mod.refresh_from_db()
    assert mod.vigente.revisada_por == jur and mod.vigente.revisada_en
    for quien in ("del_amecameca", "finanzas", "juridica"):
        with pytest.raises(PermissionDenied):
            contratos.elaborar_contrato(u[quien], exp, mod)
    contrato = contratos.elaborar_contrato(dir_, exp, mod)
    assert contrato.folio.startswith(f"CTO-{programa}-2026-") and contrato.archivo and not contrato.enviado
    r.relevo("contrato_elaborado", dir_, None, area, u, nuevos_acuses=0)
    with pytest.raises(PermissionDenied):
        contratos.enviar_a_delegacion(deleg, contrato)
    antes = timezone.now()
    contratos.enviar_a_delegacion(dir_, contrato)
    contrato.refresh_from_db()
    assert antes <= contrato.enviado_en <= timezone.now() and contrato.estado == "enviado"
    r.relevo("contrato_en_delegacion", dir_, None, {delegado_de(u, exp).username}, u, tipo_acuse="envio_contrato")

    # --- M3.3 Firma en la Delegación: solo la del expediente, con la verificación de firmas y sello completa ------
    with pytest.raises(PermissionDenied):
        firma.registrar_firma(otra_deleg, exp, None, "persona", exp.beneficiaria.nombre, archivo_demo("f.pdf"),
                              [p["clave"] for p in firma.puntos_de_verificacion(exp)])
    puntos = [p["clave"] for p in firma.puntos_de_verificacion(exp)]
    with pytest.raises(ValidationError):
        firma.registrar_firma(deleg, exp, None, "persona", exp.beneficiaria.nombre, archivo_demo("f.pdf"), puntos[:-1],
                              elementos_propios(exp))
    propios = elementos_propios(exp)
    if programa in ("MFS", "PEG"):                                   # formalización propia del programa
        assert propios
        with pytest.raises(ValidationError):
            firma.registrar_firma(deleg, exp, None, "persona", exp.beneficiaria.nombre, archivo_demo("f.pdf"), puntos)
    exp.refresh_from_db()
    assert exp.estado.clave == "contrato_en_delegacion"
    programada, liberacion = firma.fechas_de_firma(exp)
    assert programada.vencimiento and liberacion.vencimiento                                # R-03: dos fechas
    if programa == "PEG":                                           # R-18: desde la aprobación del CASPEG
        assert programada.evento == liberacion.evento == "aprobacion_comite"
        assert programada.fecha_evento == hito(exp, "aprobacion_comite").fecha_hora
    antes = timezone.now()
    f = firma.registrar_firma(deleg, exp, None, "persona", exp.beneficiaria.nombre, archivo_demo("firmado.pdf"), puntos,
                              propios)
    assert antes <= f.firmado_en <= timezone.now() and f.dentro_de_plazo is not False
    hf = hito(exp, "firma_contrato")
    assert hf.fecha_hora == f.firmado_en and hf.fecha_hora >= contrato.enviado_en
    # PS y RHF: la firma deja el expediente en `contratada` (el vale se emite después, con la planta aún sin entregar)
    r.relevo("contratada", deleg, None, area, u, tipo_acuse="firma_contrato")

    # --- M3.4 PS y RHF: Vale de Planta, salida parcial y salida final del vivero --------------------------------------
    vivero, esp = catalogo_planta
    if programa in ("PS", "RHF"):
        assert planta.aplica(exp)[0] and exp.modalidad.clave in ("plantacion_forestal_comercial", "rfi_modalidad_dos")
        total = planta.propuesta(exp)["total"]
        assert total > 1
        for quien in ("dir_drff", "vivero", "juridica", otra_deleg.username):
            with pytest.raises(PermissionDenied):
                planta.emitir_vale(u[quien], exp, vivero, [(esp["Pino patula"], total)])
        antes = timezone.now()
        vale = planta.emitir_vale(deleg, exp, vivero, [(esp["Pino patula"], total)])
        assert vale.entregado_en >= antes and vale.vivero == vivero and vale.total_autorizado == total
        assert vale.acuse.tipo == "entrega_vale" and hito(exp, "entrega_vale").fecha_hora == vale.entregado_en
        assert vale.vence_el and vale.situacion() == "vigente"
        r.relevo("vale_entregado", deleg, None, {"vivero"}, u, tipo_acuse="entrega_vale")
        with pytest.raises(PermissionDenied):
            planta.registrar_salida(dir_, vale, esp["Pino patula"], 1)
        assert planta.validar_vale(u["vivero"], vale) == "vigente"
        mitad = total // 2
        s1 = planta.registrar_salida(u["vivero"], vale, esp["Pino patula"], mitad, observaciones="Primer camión")
        assert s1.salido_en and s1.cantidad == mitad and s1.acuse.tipo == "salida_planta"
        r.relevo("vale_entregado", u["vivero"], None, {"vivero"}, u, tipo_acuse="salida_planta")  # parcial: sigue con el vivero
        with pytest.raises(ValidationError):
            planta.registrar_salida(u["vivero"], vale, esp["Pino patula"], total - mitad + 1)     # más de lo autorizado
        s2 = planta.registrar_salida(u["vivero"], vale, esp["Pino patula"], total - mitad)
        assert s2.salido_en >= s1.salido_en
        r.relevo("planta_entregada", u["vivero"], None, {"dir_drff"}, u, tipo_acuse="salida_planta")
        with pytest.raises(ValidationError):
            planta.registrar_salida(u["vivero"], vale, esp["Pino patula"], 1)                    # ya surtido
    else:
        with pytest.raises(ValidationError, match="no entrega planta con Vale"):
            planta.emitir_vale(deleg, exp, vivero, [(esp["Pino patula"], 10)])

    # --- M5.1 Oficio de la Delegación y solicitud de la primera ministración ---------------------------------------
    with pytest.raises(PermissionDenied):
        solicitudes.emitir_oficio(otra_deleg, exp)
    with pytest.raises(PermissionDenied):
        solicitudes.emitir_oficio(dir_, exp)
    # Sin soportes el servicio impide el envío y dice cuál falta (queda «por enviar»). PEG no pide oficio de la
    # Delegación: la solicitud la genera la Instancia Ejecutora (ROP PEG 10.1 fr. XIII).
    with pytest.raises(ValidationError, match="Comprobante" if programa == "PEG" else "Oficio de solicitud de pago"):
        solicitudes.enviar_solicitud(dir_, exp, 1)
    oficio = solicitudes.emitir_oficio(deleg, exp)
    assert oficio.folio.startswith(f"OFP-{programa}-2026-") and oficio.acuse.tipo == "oficio_solicitud_pago"
    exp.refresh_from_db()
    estado_previo = exp.estado.clave
    assert estado_previo == ("planta_entregada" if programa in ("PS", "RHF") else "contratada")   # el oficio no cambia el estado
    pide_comprobante = any(s["clave"] == "comprobante_cuenta" for s in solicitudes.soportes_requeridos(exp, 1))
    assert pide_comprobante == (programa != "PSA")                                              # PSAHEM paga con cheque
    if pide_comprobante:
        with pytest.raises(ValidationError, match="Comprobante de la cuenta bancaria"):
            solicitudes.enviar_solicitud(dir_, exp, 1)
        with pytest.raises(PermissionDenied):
            solicitudes.adjuntar_comprobante(otra_deleg, exp, pdf("cuenta.pdf"))
        solicitudes.adjuntar_comprobante(deleg, exp, pdf("cuenta.pdf"))
        if programa == "PEG":
            with pytest.raises(ValidationError, match="Evaluación de los reportes"):
                solicitudes.enviar_solicitud(dir_, exp, 1)
            validar_reportes(u, exp, ["2026-01"])                   # el CASPEG valida el primer periodo (HU-2.4)
    else:
        with pytest.raises(ValidationError, match="instruye el pago de la ministración 1"):
            solicitudes.enviar_solicitud(dir_, exp, 1)
        with pytest.raises(ValidationError, match="no pide comprobante"):
            solicitudes.adjuntar_comprobante(deleg, exp, pdf("cuenta.pdf"))
        instruir_pago(u, exp, 1)                                    # acuerdo del Comité Técnico (sesión de seguimiento)
    for quien in (deleg, finanzas, u["comite"]):
        with pytest.raises(PermissionDenied):
            solicitudes.enviar_solicitud(quien, exp, 1)             # solo el área responsable envía
    with pytest.raises(ValidationError):
        solicitudes.enviar_solicitud(dir_, exp, 2)                  # no existe la segunda sin la primera
    sol = solicitudes.enviar_solicitud(dir_, exp, 1)
    esperado = montos.monto_aprobado(exp).ministraciones[0]
    primera = {"PEG": 25}.get(programa, 70)                          # PEG: 25 % (supuesto marcado en las reglas)
    assert sol.importe == esperado.importe and sol.porcentaje == esperado.porcentaje == primera and sol.ministracion == 1
    assert sol.enviada_en and sol.acuse_envio.tipo == "solicitud_pago" and all(s["cumple"] for s in sol.soportes)
    assert sol.tipo_pago == {"PSA": "cheque_fiduciaria", "PEG": "deposito"}.get(programa, "transferencia")
    # Mientras no se pague, la segunda ministración no se puede pedir.
    with pytest.raises(ValidationError):
        solicitudes.enviar_solicitud(dir_, exp, 2)
    bandeja_pago = {"finanzas"}
    r.relevo("ministracion_solicitada", dir_, None, bandeja_pago, u, tipo_acuse="solicitud_pago")
    if programa == "PSA":
        assert hito(exp, "solicitud_pago_fiduciaria").fecha_hora == sol.enviada_en
        assert solicitudes.plazo_remision(sol).vencimiento                              # 5 días hábiles de la Secretaría Técnica

    # --- M5.2 Revisión y pago --------------------------------------------------------------------------------------
    with pytest.raises(PermissionDenied):
        pagos.revisar_solicitud(dir_, sol, "aceptada")              # solo Administración y Finanzas revisa
    with pytest.raises(ValidationError):
        pagos.registrar_pago(finanzas, sol, "SPEI-1", timezone.localdate())   # no se paga lo no aceptado
    pagos.revisar_solicitud(finanzas, sol, "aceptada")
    sol.refresh_from_db()
    assert sol.estado == EstadoSolicitud.ACEPTADA

    if programa != "PSA":
        for quien in (dir_, deleg, u["comite"]):
            with pytest.raises(PermissionDenied):
                pagos.registrar_pago(quien, sol, "SPEI-1", timezone.localdate())
        with pytest.raises(ValidationError, match="debe ser igual al solicitado"):
            pagos.registrar_pago(finanzas, sol, "SPEI-1", timezone.localdate(), importe=sol.importe - 1)
        pago = pagos.registrar_pago(finanzas, sol, "SPEI-0001", timezone.localdate())
        assert pago.importe == sol.importe == esperado.importe and pago.fecha_pago == timezone.localdate()
        assert pago.tipo == sol.tipo_pago and pago.acuse.tipo == "pago_ministracion"
        assert hito(exp, "pago_ministracion").fecha_hora is not None
        with pytest.raises(ValidationError, match="no se paga dos veces"):
            pagos.registrar_pago(finanzas, sol, "SPEI-OTRA", timezone.localdate())
        r.relevo("pagada", finanzas, None, area, u, tipo_acuse="pago_ministracion")
        # El aviso de pago llega a la persona por conducto de la Delegación.
        assert pago.aviso.tipo == "pago" and pago.aviso in notificaciones.pendientes_de_notificar(exp.delegacion)
        pagado = pago.importe
        fecha_pago_o_entrega = pago.fecha_pago
    else:
        # PSAHEM: Administración y Finanzas acepta; la Secretaría Técnica remite a la Fiduciaria (R-16); la Fiduciaria
        # emite y envía el cheque; la Delegación lo entrega.
        r.eventos = exp.eventos.count()
        with pytest.raises(ValidationError):
            pagos.registrar_pago(finanzas, sol, "SPEI-1", timezone.localdate())   # PSAHEM paga con cheque, no por transferencia
        with pytest.raises(PermissionDenied):
            pagos.remitir_a_fiduciaria(finanzas, sol)               # remite la Secretaría Técnica
        with pytest.raises(PermissionDenied):
            cheques.emitir_cheque(u["fiduciaria"], sol, "CHQ-0001")  # la Fiduciaria no ve lo no remitido
        antes = timezone.now()
        rem = pagos.remitir_a_fiduciaria(u["comite"], sol)
        assert antes <= rem.remitida_en <= timezone.now() and rem.acuse.tipo == "remision_fiduciaria"
        assert hito(exp, "remision_fiduciaria").fecha_hora == rem.remitida_en
        with pytest.raises(ValidationError, match="ya se remitió"):
            pagos.remitir_a_fiduciaria(u["comite"], sol)
        r.relevo("remitida_fiduciaria", u["comite"], None, {"fiduciaria"}, u, tipo_acuse="remision_fiduciaria")
        with pytest.raises(ValidationError, match="debe ser igual al solicitado"):
            cheques.emitir_cheque(u["fiduciaria"], sol, "CHQ-0001", importe=sol.importe - 1)
        c = cheques.emitir_cheque(u["fiduciaria"], sol, "CHQ-0001")
        assert c.importe == sol.importe and c.persona == exp.solicitante and c.ministracion == 1
        r.relevo("cheque_emitido", u["fiduciaria"], None, {"fiduciaria"}, u, tipo_acuse="emision_cheque")
        with pytest.raises(ValidationError, match="un cheque por persona y ministración"):
            cheques.emitir_cheque(u["fiduciaria"], sol, "CHQ-0002")
        with pytest.raises(PermissionDenied):
            cheques.enviar_a_delegacion(finanzas, c)
        cheques.enviar_a_delegacion(u["fiduciaria"], c)
        c.refresh_from_db()
        assert c.enviado_en and c.aviso.tipo == "pago" and c.aviso.delegacion == exp.delegacion
        r.relevo("cheque_enviado", u["fiduciaria"], None, {delegado_de(u, exp).username}, u, tipo_acuse="envio_cheque")
        with pytest.raises(PermissionDenied):
            cheques.registrar_entrega(otra_deleg, c, exp.solicitante.nombre)
        c = cheques.registrar_entrega(deleg, c, exp.solicitante.nombre)
        sol.refresh_from_db()
        assert c.entregado_en >= c.enviado_en and c.recibe_nombre == exp.solicitante.nombre
        assert hito(exp, "entrega_cheque").fecha_hora == c.entregado_en and sol.estado == EstadoSolicitud.PAGADA
        assert cheques.vencimiento_cobro(c).vencimiento                    # 3 meses para cobrar, desde la entrega
        r.relevo("cheque_entregado", deleg, None, {"dir_drff"}, u, tipo_acuse="entrega_cheque")
        with pytest.raises(ValidationError, match="ya se entregó"):
            cheques.registrar_entrega(deleg, c, "Otra persona")
        pagado = c.importe
        fecha_pago_o_entrega = c.entregado_en

    # --- La primera ministración quedó pagada por el importe de las reglas; la segunda sigue bloqueada --------------
    sol.refresh_from_db()
    assert sol.estado == EstadoSolicitud.PAGADA and pagado == sol.importe == esperado.importe
    pct = esperado.porcentaje / 100
    assert Decimal(pagado) == (montos.monto_aprobado(exp).total * pct).quantize(Decimal("0.01"))
    if programa == "PSA":
        assert pagado == Decimal("73500.00")                                  # 30 ha de cuenca alta (3,500 por ha) × 70 %
    if programa == "MFS":
        assert pagado == Decimal("21000.00")                                  # monto fijo de $30,000 (ETF de 7 a 95 ha) × 70 %
    if programa == "PEG":
        assert pagado == Decimal("6387.50")                                   # $25,550 por Guardabosque × 25 %
    assert fecha_pago_o_entrega
    with pytest.raises(ValidationError, match=SEGUNDA_BLOQUEADA.get(programa, "Verificación en campo o evaluación de reportes")):
        solicitudes.enviar_solicitud(dir_, exp, 2)                   # espera su comprobación o verificación (M4)
    assert atiende(exp, u) == area

    # --- La bitácora cuenta toda la historia en orden, con usuario y unidad en cada renglón --------------------------
    estados = [e.estado_destino.clave for e in exp.eventos.order_by("fecha_hora", "pk") if e.estado_destino_id]
    esperado_estados = ["aprobada", "publicada", "notificada", "contrato_elaborado", "contrato_en_delegacion", "contratada"]
    if programa in ("PS", "RHF"):
        esperado_estados += ["vale_entregado", "planta_entregada"]
    esperado_estados += ["ministracion_solicitada"]
    esperado_estados += ["remitida_fiduciaria", "cheque_emitido", "cheque_enviado", "cheque_entregado"] if programa == "PSA" else ["pagada"]
    assert estados[-len(esperado_estados):] == esperado_estados, estados
    assert all(e.usuario_id and e.unidad_id and e.fecha_hora for e in exp.eventos.all())
    momentos = [e.fecha_hora for e in exp.eventos.order_by("fecha_hora", "pk")]
    assert momentos == sorted(momentos)
    tipos = {a.tipo for a in exp.acuses.all()}
    assert {"envio_notificacion_resultados", "envio_contrato", "firma_contrato", "oficio_solicitud_pago", "solicitud_pago"} <= tipos
    assert ("pago_ministracion" in tipos) == (programa != "PSA")
    assert ("entrega_cheque" in tipos) == (programa == "PSA")
