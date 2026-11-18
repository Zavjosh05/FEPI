"""Recorrido completo del prototipo, de la solicitud al padrón, con los servicios y una solicitud por programa.

Cada programa con reglas (CC, PS, RHF, PSAHEM, MFS y PEG) recorre: registro de la solicitud, revisión y validación, dictámenes
técnico y jurídico, sesión de aprobación del Comité, publicación y notificación, contrato y firma (con la cuenta del portal),
primera ministración, ejecución (envíos por el portal o en ventanilla), verificación (o evaluación de reportes en PEG), las
ministraciones siguientes, el cierre del expediente, el padrón publicado (consultado sin cuenta) y el informe anual enviado al
Comité y recibido por la Secretaría Técnica. El tramo hasta la primera ministración lo arman las fixtures con los mismos servicios
(sus relevos se comprueban paso a paso en los recorridos de los sprints 1 y 2); desde la ejecución, cada relevo se comprueba aquí:
estado, en la bandeja de quién queda, acuse y renglón de la bitácora. Al final, la bitácora cuenta toda la historia en orden.

Además, dos caminos alternos: el incumplimiento (omisión vencida → cancelación → Listado de Incumplidas → requerimiento → depósito
→ cierre) y la reasignación del recurso de un desistimiento a la lista de espera (hasta la firma de la reasignada y su alta en el
padrón)."""
from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from contrato import contratos, firma, publicacion
from dictamen.models import PersonaIncumplida
from ejecucion import comprobaciones, reportes, verificacion
from nucleo import montos, reloj
from nucleo.demo import archivo_demo
from pagos import cheques, pagos, solicitudes
from pagos.models import EstadoSolicitud
from seguimiento import cierre, incumplimientos, reasignacion
from seguimiento.models import RecursoLiberado, Senalamiento

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de, elementos_propios
from .fixtures_m4 import *  # noqa: F401,F403
from .fixtures_m5 import *  # noqa: F401,F403
from .fixtures_m5 import instruir_pago
from .test_hu_4_3 import _reporte, _validar
from .test_hu_6_1 import _acordar_y_cumplir, _desistir, _sesion
from .test_hu_6_2 import _cuenta, _cumplir
from .test_sprint_2_recorrido_completo import Rastro, atiende
from .test_sprint_3_recorrido_ejecucion import CASOS, _doc

pytestmark = pytest.mark.django_db

# Estados por los que pasa cada programa, en orden (subsucesión de la bitácora).
TRAMITE = ["recibida", "enviada_direccion", "validada", "dictaminada", "aprobada", "publicada", "notificada",
           "contrato_elaborado", "contrato_en_delegacion", "contratada"]
PRIMER_PAGO = {"PS": ["vale_entregado", "planta_entregada", "ministracion_solicitada", "pagada"],
               "RHF": ["vale_entregado", "planta_entregada", "ministracion_solicitada", "pagada"],
               "PSA": ["ministracion_solicitada", "remitida_fiduciaria", "cheque_emitido", "cheque_enviado", "cheque_entregado"]}
SEGUNDO_PAGO = {"PSA": ["ministracion_solicitada", "remitida_fiduciaria", "cheque_emitido", "cheque_enviado", "cheque_entregado"]}
CIERRE = ["concluida", "ejercicio_cerrado"]


def en_orden(estados, esperados):
    """``esperados`` aparece en ``estados`` en ese orden (pueden ir otros en medio)."""
    i = 0
    for e in esperados:
        while i < len(estados) and estados[i] != e:
            i += 1
        assert i < len(estados), f"falta «{e}» en orden en la bitácora: {estados}"
        i += 1


def estados_de(exp):
    return [e.estado_destino.clave for e in exp.eventos.order_by("fecha_hora", "pk") if e.estado_destino_id]


def cerrar_publicar_e_informar(u, exp, area, client, r, cuando):
    """Cierre del expediente, padrón publicado (consultado sin cuenta) e informe anual enviado y recibido; ``cuando`` es el día
    del cierre (el padrón y el informe van los días hábiles siguientes)."""
    ej = exp.ejercicio
    with reloj.en(f"{cuando} 10:00") as rel:
        fila = cierre.resultado_expediente(exp)
        assert fila["diferencias"] == [] and fila["puede_cerrar"], fila
        assert cierre.puede_cerrar(exp) == (True, "")
        cierre.cerrar_expediente(area, exp)
        r.relevo("ejercicio_cerrado", area, None, set(), u, tipo_acuse="cierre_expediente")
        assert exp.cierre.cerrado_por == area and exp.cierre.resumen["pagado"] == str(fila["pagado"])
        rel.avanzar(days=1)
        pub = cierre.publicar_padron(area, ej)
        assert pub.acuse.folio and pub.publicada_en == timezone.now()
        rel.avanzar(days=1)
        informe = cierre.enviar_informe(area, ej)
        assert informe.enviado_en == timezone.now() and informe.acuse.folio and informe.resumen["cerrados"] == 1
        assert informe.resumen["diferencias"] == [] and informe in cierre.informes_por_recibir()
        sesion = _sesion(u, ej)
        rel.avanzar(days=1)
        cierre.registrar_recepcion(u["comite"], informe, sesion, "Se presenta en la sesión de seguimiento.")
    informe.refresh_from_db()
    assert informe.recibido_en > informe.enviado_en and informe.acuse_recepcion.folio and informe.sesion == sesion
    assert cierre.estado_cierre(ej)["cerrado"]
    # El padrón se consulta sin iniciar sesión.
    client.logout()
    html = client.get(reverse("padron:programa", args=[ej.programa.clave, ej.anio])).content.decode()
    assert f'data-folio="{exp.folio}"' in html
    return html, fila


def primera_ministracion(u, exp, catalogo_planta, pdf):
    """Del contrato firmado a la primera ministración pagada (o al cheque entregado): en PS y RHF antes el Vale de Planta y su
    salida del vivero; después el oficio de la Delegación, el comprobante de la cuenta (o, en PSAHEM, la instrucción del Comité
    Técnico), la solicitud del área, la revisión y el pago."""
    deleg, area, finanzas = delegado_de(u, exp), u["dir_drff"], u["finanzas"]
    from contrato import planta

    if planta.aplica(exp)[0]:
        vivero, esp = catalogo_planta
        total = planta.propuesta(exp)["total"]
        vale = planta.emitir_vale(deleg, exp, vivero, [(esp["Pino patula"], total)])
        planta.registrar_salida(u["vivero"], vale, esp["Pino patula"], total)
    solicitudes.emitir_oficio(deleg, exp)
    if any(s["clave"] == "comprobante_cuenta" for s in solicitudes.soportes_requeridos(exp, 1)):
        solicitudes.adjuntar_comprobante(deleg, exp, pdf("cuenta.pdf"))
    if exp.programa.clave == "PSA":
        instruir_pago(u, exp, 1)
    sol = solicitudes.enviar_solicitud(area, exp, 1)
    pagos.revisar_solicitud(finanzas, sol, "aceptada")
    sol.refresh_from_db()
    if exp.programa.clave == "PSA":
        pagos.remitir_a_fiduciaria(u["comite"], sol)
        sol.refresh_from_db()
        c = cheques.emitir_cheque(u["fiduciaria"], sol, "CHQ-0001")
        cheques.enviar_a_delegacion(u["fiduciaria"], c)
        cheques.registrar_entrega(deleg, c, exp.solicitante.nombre)
    else:
        pagos.registrar_pago(finanzas, sol, "SPEI-0001", timezone.localdate())
    exp.refresh_from_db()
    sol.refresh_from_db()
    return sol


@pytest.mark.parametrize("programa", list(CASOS))
def test_sprint_3_recorrido_completo_de_la_solicitud_al_padron(programa, contratadas, catalogo_planta, cuenta_portal, usuarios,
                                                               pdf, client):
    u = usuarios
    tipo, documento, superficie, fecha_envio, fecha_verif, segunda = CASOS[programa]
    # --- Solicitud, validación, dictámenes, Comité, publicación, contrato, firma y primera ministración ---------------------
    with reloj.en("2026-08-03 10:00", tic=1):
        _, (exp,) = contratadas(programa, cuantas=1)
        persona = cuenta_portal(exp) if programa == "CC" else None    # la cuenta del portal se dio al firmar
        primera = primera_ministracion(u, exp, catalogo_planta, pdf)
    deleg, area, finanzas = delegado_de(u, exp), u["dir_drff"], u["finanzas"]
    assert primera.estado == EstadoSolicitud.PAGADA and exp.acuses.filter(tipo="alta_portal").exists()
    en_orden(estados_de(exp), TRAMITE + PRIMER_PAGO.get(programa, ["ministracion_solicitada", "pagada"]))
    r = Rastro(exp)

    # --- Ejecución: la comprobación llega por el portal (CC) o se entrega en la Delegación ---------------------------------
    with reloj.en(fecha_envio) as rel:
        quien = persona or deleg
        c = comprobaciones.registrar_envio(quien, exp, tipo, archivo=None if tipo == "aviso_termino" else _doc(f"{tipo}.pdf"),
                                           fecha_hecho=date(2026, 9, 25) if tipo == "aviso_termino" and programa != "CC"
                                           else date(2026, 11, 11) if programa == "CC" else None)
        assert c.acuse.tipo == "comprobacion" and c.medio == ("portal" if programa == "CC" else "ventanilla")
        r.relevo("comprobacion_enviada", None if persona else deleg, None, {deleg.username, area.username}, u,
                 tipo_acuse="comprobacion")
        if persona:                                     # CC: también el Informe Final, por el portal
            rel.avanzar(hours=2)
            informe_final = comprobaciones.registrar_envio(persona, exp, "informe_final", archivo=_doc("informe_final.pdf"))
            assert informe_final.medio == "portal" and informe_final in comprobaciones.por_revisar(deleg)
            r.relevo("comprobacion_enviada", None, None, {deleg.username, area.username}, u, tipo_acuse="comprobacion")

    # --- Verificación (MFS: el área revisa la Bitácora) ------------------------------------------------------------------
    verifica = area if programa == "MFS" else deleg
    with reloj.en(fecha_verif):
        v = verificacion.registrar_verificacion(verifica, exp, documento, _doc("verificacion.pdf"),
                                                fecha_visita=date(2026, 9, 30) if programa != "MFS" else None,
                                                superficie_verificada=superficie,
                                                sobrevivencia="80" if programa in ("PS", "RHF") else None)
    assert v.en_plazo is not False and v.resultado in ("cumple", "ajuste")
    r.relevo("verificada", verifica, None, {area.username}, u, tipo_acuse="verificacion_campo")

    # --- Segunda ministración con el soporte de la verificación o del entregable -------------------------------------------
    with reloj.en(fecha_verif) as rel:
        rel.avanzar(days=3)
        if programa == "PSA":
            instruir_pago(u, exp, 2)
        sol = solicitudes.enviar_solicitud(area, exp, 2)
        assert sol.importe == segunda and all(s["cumple"] for s in sol.soportes)
        r.relevo("ministracion_solicitada", area, None, {"finanzas"}, u, tipo_acuse="solicitud_pago")
        pagos.revisar_solicitud(finanzas, sol, "aceptada")
        sol.refresh_from_db()
        if programa == "PSA":
            pagos.remitir_a_fiduciaria(u["comite"], sol)
            sol.refresh_from_db()
            ch = cheques.emitir_cheque(u["fiduciaria"], sol, "CHQ-0002")
            cheques.enviar_a_delegacion(u["fiduciaria"], ch)
            cheques.registrar_entrega(deleg, ch, exp.solicitante.nombre)
            r.relevo("cheque_entregado", deleg, None, {area.username}, u, nuevos_acuses=3, tipo_acuse="entrega_cheque")
        else:
            pagos.registrar_pago(finanzas, sol, "SPEI-0002", timezone.localdate())
            r.relevo("pagada", finanzas, None, {area.username}, u, tipo_acuse="pago_ministracion")
    assert not verificacion.ministraciones_pendientes(exp)

    # --- Cierre del expediente, padrón e informe anual -------------------------------------------------------------------
    html, fila = cerrar_publicar_e_informar(u, exp, area, client, r, "2026-11-25")
    assert exp.beneficiaria.nombre in html and 'data-situacion="vigente"' in html
    assert fila["pagado"] == primera.importe + segunda and fila["reintegrado"] == 0
    if programa in ("CC", "PS"):                         # se pagó lo verificado (proporcional)
        assert fila["pagado"] == (Decimal(superficie) * montos.monto_aprobado(exp).monto_ha).quantize(Decimal("0.01"))
    if exp.beneficiaria.curp:
        assert exp.beneficiaria.curp not in html
    if persona:                                          # la persona ve su expediente cerrado en el portal
        client.force_login(persona)
        assert exp.folio in client.get(reverse("portal:expediente", args=[exp.folio])).content.decode()

    # --- La bitácora cuenta toda la historia en orden, con usuario y unidad donde actuó una persona ----------------------
    estados = estados_de(exp)
    en_orden(estados, TRAMITE + PRIMER_PAGO.get(programa, ["ministracion_solicitada", "pagada"])
             + ["en_ejecucion", "comprobacion_enviada", "verificada"]
             + SEGUNDO_PAGO.get(programa, ["ministracion_solicitada", "pagada"]) + CIERRE)
    assert estados[-1] == "ejercicio_cerrado"
    momentos = [e.fecha_hora for e in exp.eventos.order_by("fecha_hora", "pk")]
    assert momentos == sorted(momentos)
    assert {"recepcion", "firma_contrato", "solicitud_pago", "comprobacion", "verificacion_campo", "cierre_expediente"} <= {
        a.tipo for a in exp.acuses.all()}


def test_sprint_3_recorrido_completo_peg_reportes_evaluacion_caspeg_y_cuatro_ministraciones(contratadas, cuenta_portal, usuarios,
                                                                                            pdf, client):
    """Guardabosques: el Guardabosque firma el 16-jun (cuenta del portal al firmar) y reporta cada mes, por el portal o en la
    Delegación; la Delegación revisa, la Dirección de Protección Forestal evalúa cada periodo y lo envía al CASPEG, que lo valida, y
    con cada evaluación validada se paga la ministración que cubre (1: junio; 2: julio y agosto; 3: septiembre y octubre; 4:
    noviembre y diciembre, supuesto R-18). Pagadas las cuatro, el área cierra el expediente, publica el padrón (con el núcleo
    agrario, sin el nombre del Guardabosque) y envía el informe anual."""
    u = usuarios
    with reloj.en("2026-06-16 10:00"):
        _, (exp,) = contratadas("PEG", cuantas=1)
        guardabosque = cuenta_portal(exp)
    deleg, dpf, finanzas = delegado_de(u, exp), u["dir_dpf"], u["finanzas"]
    assert exp.estado.clave == "contratada" and exp.beneficiaria.nombre != exp.solicitante.nombre
    en_orden(estados_de(exp), TRAMITE)
    with reloj.en("2026-06-17 10:00"):
        solicitudes.adjuntar_comprobante(deleg, exp, pdf("cuenta.pdf"))
    r = Rastro(exp)
    # periodo: (entrega, revisión, evaluación y envío, validación del CASPEG); los nones son en el portal.
    calendario = [("2026-06", "2026-07-02 10:00", "2026-07-03 10:00", "2026-07-06 11:00", "2026-07-07 11:00"),
                  ("2026-07", "2026-08-04 10:00", "2026-08-05 10:00", "2026-08-06 11:00", "2026-08-10 11:00"),
                  ("2026-08", "2026-09-02 10:00", "2026-09-03 10:00", "2026-09-04 11:00", "2026-09-10 11:00"),
                  ("2026-09", "2026-10-02 10:00", "2026-10-05 10:00", "2026-10-06 11:00", "2026-10-08 11:00"),
                  ("2026-10", "2026-11-03 10:00", "2026-11-04 10:00", "2026-11-05 11:00", "2026-11-09 11:00"),
                  ("2026-11", "2026-12-02 10:00", "2026-12-03 10:00", "2026-12-04 11:00", "2026-12-08 11:00"),
                  ("2026-12", "2027-01-05 10:00", "2027-01-06 10:00", "2027-01-07 11:00", "2027-01-11 11:00")]
    pagar_tras = {"2026-06": 1, "2026-08": 2, "2026-10": 3, "2026-12": 4}
    por_portal = {"2026-07", "2026-09", "2026-11"}
    pagado = Decimal("0")
    for periodo, entrega, revision, evaluacion, validacion in calendario:
        if periodo in por_portal:
            with reloj.en(entrega):
                rep = comprobaciones.registrar_envio(guardabosque, exp, "reporte_mensual", pdf(f"reporte_{periodo}.pdf"),
                                                     periodo=periodo)
            assert rep.medio == "portal"
        else:
            rep = _reporte(u, exp, periodo, pdf, entrega)
            assert rep.medio == "ventanilla"
        assert rep.acuse.tipo == "comprobacion"
        with reloj.en(revision):
            reportes.revisar(deleg, rep, "revisado")
        with reloj.en(evaluacion):
            reportes.evaluar_periodo(dpf, exp, periodo, "cumple")
            envio = reportes.enviar_evaluacion(dpf, exp.ejercicio, periodo)
        assert (envio.cumplen, envio.no_entregaron) == (1, 0) and envio.acuse.tipo == "evaluacion_reportes"
        _validar(u, exp.ejercicio, periodo, [exp], validacion)
        n = pagar_tras.get(periodo)
        if n is None:
            continue
        with reloj.en(validacion) as rel:
            rel.avanzar(days=1)
            sol = solicitudes.enviar_solicitud(dpf, exp, n)
            assert sol.ministracion == n and all(s["cumple"] for s in sol.soportes)
            assert {s["clave"] for s in sol.soportes} >= {"evaluacion_reportes"}
            r.relevo("ministracion_solicitada", dpf, None, {"finanzas"}, u, tipo_acuse="solicitud_pago")
            pagos.revisar_solicitud(finanzas, sol, "aceptada")
            sol.refresh_from_db()
            pago = pagos.registrar_pago(finanzas, sol, f"DEP-{n:04d}", timezone.localdate())
            assert pago.tipo == "deposito"
            r.relevo("pagada", finanzas, None, {dpf.username}, u, tipo_acuse="pago_ministracion")
        pagado += sol.importe
    assert [e.nombre_periodo for e in reportes.periodos_senalados(exp)] == []
    assert pagado == montos.monto_aprobado(exp).total == Decimal("25550.00")
    assert not verificacion.ministraciones_pendientes(exp)
    html, fila = cerrar_publicar_e_informar(u, exp, dpf, client, r, "2027-01-15")
    assert fila["pagado"] == pagado and exp.solicitante.nombre in html and exp.beneficiaria.nombre not in html
    assert 'data-tipo="Alta"' in html
    en_orden(estados_de(exp), TRAMITE + ["ministracion_solicitada", "pagada"] * 4 + CIERRE)


def test_sprint_3_recorrido_completo_incumplimiento_cancelacion_reintegro_y_cierre(pagada, usuarios, client):
    """CC: la persona no entrega la evidencia; vence el plazo del aviso de omisiones, el sistema lo señala y el área lo confirma; el
    Comité acuerda la cancelación y la Unidad Jurídica la cumple (Listado de Incumplidas y requerimiento); Administración y
    Finanzas registra la cuenta, Jurídica emite el requerimiento, Finanzas comprueba el depósito y el área cierra el expediente,
    que queda en el padrón como baja por cancelación."""
    u = usuarios
    area, jur, finanzas = u["dir_drff"], u["juridica"], u["finanzas"]
    with reloj.en("2026-09-01 10:00"):
        exp = pagada("CC")
        deleg = delegado_de(u, exp)
        r = Rastro(exp)
        aviso = incumplimientos.avisar_omision(area, exp, "No entregó la evidencia de los trabajos.", date(2026, 9, 15))
    assert aviso.vence == date(2026, 9, 15) and aviso.notificacion.tipo == "omision"
    r.relevo("omisiones_por_subsanar", area, None, {deleg.username, area.username}, u)
    # Vence sin subsanar: el sistema lo señala (no ejecuta nada) y una persona confirma la propuesta.
    with reloj.en("2026-09-16 08:00"):
        assert incumplimientos.revisar(date(2026, 9, 15)) == 0 and incumplimientos.revisar(date(2026, 9, 16)) == 1
    s = Senalamiento.objects.get(expediente=exp, tipo="omision_vencida")
    exp.refresh_from_db()
    assert exp.estado.clave == "omisiones_por_subsanar" and not exp.propuestas_seguimiento.exists()
    with reloj.en("2026-09-17 10:00"):
        incumplimientos.confirmar(area, s)
        s.refresh_from_db()
        assert s.propuesta.tipo == "cancelacion"
        acuerdo = _cumplir(u, s.propuesta)
    assert acuerdo.unidad_responsable.clave == "UJ"
    r.relevo("cancelada", jur, None, {jur.username}, u)
    inscrita = PersonaIncumplida.objects.get(persona=exp.beneficiaria)
    assert inscrita.activa and acuerdo.numero in inscrita.acuerdo
    req = exp.requerimientos.get()
    assert req.estado == "por_emitir" and req.monto_total == Decimal("8400.00")
    assert not cierre.puede_cerrar(exp)[0]
    with reloj.en("2026-09-21 10:00"):
        with pytest.raises(ValidationError, match="cuenta para los reintegros"):
            incumplimientos.emitir_requerimiento(jur, req)
        _cuenta(u)
        incumplimientos.emitir_requerimiento(jur, req)
    req.refresh_from_db()
    r.relevo("en_devolucion", jur, None, {"finanzas"}, u)                 # la Delegación lo notifica desde sus avisos
    assert req.notificacion.tipo == "devolucion" and req.notificacion.delegacion == exp.delegacion
    with reloj.en("2026-09-28 10:00"):
        incumplimientos.comprobar_deposito(finanzas, req, timezone.localdate(), req.monto_total, "DEP-INC-01", _doc("deposito.pdf"))
    r.relevo("reintegrada", finanzas, None, {area.username}, u)
    assert RecursoLiberado.objects.filter(expediente=exp, origen="reintegro").exists()
    html, fila = cerrar_publicar_e_informar(u, exp, area, client, r, "2026-11-25")
    assert exp.cierre.tipo == "reintegrada" and fila["reintegrado"] == fila["pagado"] == Decimal("8400.00")
    assert 'data-situacion="cancelada"' in html and "Baja por cancelación del apoyo" in html
    en_orden(estados_de(exp), TRAMITE + ["ministracion_solicitada", "pagada", "omisiones_por_subsanar", "cancelada",
                                         "en_devolucion", "reintegrada", "ejercicio_cerrado"])


def test_sprint_3_recorrido_completo_reasignacion_a_la_lista_de_espera_hasta_el_padron(notificadas, modelo_validado, usuarios,
                                                                                        client):
    """CC con recurso para una de tres: la aprobada desiste antes de firmar, el Comité acuerda la baja y se libera su recurso; la
    propuesta de reasignación alcanza al lugar 1 de la lista de espera; al cumplirse el acuerdo queda aprobada, se le notifica,
    firma su contrato y entra al padrón, junto a la baja del lugar liberado."""
    u = usuarios
    area = u["dir_drff"]
    with reloj.en("2026-08-03 10:00", tic=1):
        _, (uno, dos, tres) = notificadas("CC", cuantas=3, presupuesto=12000)
        assert (uno.estado.clave, dos.estado.clave, tres.estado.clave) == ("notificada", "lista_espera", "lista_espera")
        ej = uno.ejercicio
        _desistir(u, uno)
        uno.refresh_from_db()
        assert uno.estado.clave == "sustitucion"
        baja = reasignacion.proponer(area, uno, "desistimiento")
        _acordar_y_cumplir(u, baja)
        uno.refresh_from_db()
        assert uno.estado.clave == "recurso_liberado"
        propuesta = reasignacion.proponer_reasignacion(area, ej, "Recurso del desistimiento.")
        assert list(propuesta.expedientes.all()) == [dos] and propuesta.monto_liberado == Decimal("12000.00")
    r = Rastro(dos)
    with reloj.en("2026-08-10 10:00", tic=1):
        _acordar_y_cumplir(u, propuesta)
        # Queda en la bandeja del área (estado «aprobada»); el aviso del resultado le llega a la Delegación para notificarlo.
        r.relevo("aprobada", area, None, {area.username}, u)
        tres.refresh_from_db()
        assert tres.estado.clave == "lista_espera"
        aviso = dos.notificaciones.filter(tipo="resultados").order_by("-enviada_en").first()
        assert aviso in publicacion.por_entregar(delegado_de(u, dos))
        publicacion.registrar_entrega(delegado_de(u, dos), aviso, "personal")
        r.relevo("notificada", delegado_de(u, dos), None, {area.username}, u)
        modelo = modelo_validado(ej)
        contratos.enviar_a_delegacion(area, contratos.elaborar_contrato(area, dos, modelo))
        r.relevo("contrato_en_delegacion", area, None, {delegado_de(u, dos).username}, u, tipo_acuse="envio_contrato")
        firma.registrar_firma(delegado_de(u, dos), dos, None, "persona", dos.beneficiaria.nombre, archivo_demo("firmado.pdf"),
                              [p["clave"] for p in firma.puntos_de_verificacion(dos)], elementos_propios(dos))
        r.relevo("contratada", delegado_de(u, dos), None, {area.username}, u, tipo_acuse="firma_contrato")
        assert dos.acuses.filter(tipo="alta_portal").exists()                   # la cuenta del portal llega con la firma
        cierre.publicar_padron(area, ej)
    html = client.get(reverse("padron:programa", args=[ej.programa.clave, ej.anio])).content.decode()
    assert f'data-folio="{dos.folio}"' in html and 'data-situacion="vigente"' in html
    assert uno.folio not in html and tres.folio not in html                       # sin contrato firmado no están en el padrón
    en_orden(estados_de(dos), ["lista_espera", "aprobada", "notificada", "contrato_elaborado", "contrato_en_delegacion",
                               "contratada"])
