"""Recorrido de la ejecución hasta el segundo pago (HU-4.1 y HU-4.2) en CC, PS, RHF, PSAHEM y MFS.

Parte de la primera ministración pagada (o del cheque entregado en PSAHEM) y sigue, cada paso con la unidad que le toca: la
persona envía su comprobación (en CC por el portal; en los demás la entrega en la Delegación), la Delegación (o, en MFS, el área
responsable con la Bitácora) registra la verificación, el área responsable solicita la segunda ministración con el soporte de
la verificación o del entregable y Administración y Finanzas la paga (en PSAHEM: instrucción del Comité Técnico, remisión a la
Fiduciaria, cheque del 30 % y entrega en la Delegación). En cada relevo se comprueba el estado, la bandeja, el acuse y la
bitácora. CC y PS verifican menos superficie de la aprobada y cobran la parte proporcional; PSAHEM cobra su 30 % completo."""
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone

from ejecucion import comprobaciones, verificacion
from nucleo import montos, reloj
from pagos import cheques, pagos, solicitudes
from pagos.models import EstadoSolicitud

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m4 import *  # noqa: F401,F403
from .fixtures_m5 import *  # noqa: F401,F403
from .fixtures_m5 import instruir_pago
from .test_sprint_2_recorrido_completo import Rastro, atiende

pytestmark = pytest.mark.django_db

# programa: (envío, documento de verificación, superficie verificada, fecha del envío, fecha de la verificación, segunda esperada)
CASOS = {
    "CC": ("aviso_termino", "informe_final_firmado", "5.4", "2026-11-12 10:00", "2026-11-20 10:00", Decimal("2400.00")),
    "PS": ("aviso_termino", "formato_verificacion", "3.6", "2026-09-28 10:00", "2026-10-15 10:00", Decimal("8000.00")),
    "RHF": ("aviso_termino", "formato_verificacion", "3", "2026-09-28 10:00", "2026-10-06 10:00", Decimal("12600.00")),
    "PSA": ("informe_final", "minuta_verificacion", "28", "2026-10-15 10:00", "2026-10-22 10:00", Decimal("31500.00")),
    "MFS": ("bitacora_etf", "revision_entregable", None, "2026-10-01 10:00", "2026-10-05 10:00", Decimal("9000.00")),
}


def _doc(nombre):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from nucleo.demo import _pdf_demo
    return SimpleUploadedFile(nombre, _pdf_demo(nombre), content_type="application/pdf")


@pytest.mark.parametrize("programa", list(CASOS))
def test_sprint_3_la_ejecucion_se_comprueba_se_verifica_y_cobra_la_segunda_ministracion(programa, pagada, cuenta_portal, usuarios):
    u = usuarios
    tipo, documento, superficie, fecha_envio, fecha_verif, segunda = CASOS[programa]
    with reloj.en("2026-08-03 10:00"):
        exp = pagada(programa)
        persona = cuenta_portal(exp) if programa == "CC" else None
    deleg, area, finanzas = delegado_de(u, exp), u["dir_drff"], u["finanzas"]
    primera = exp.solicitudes_pago.get(ministracion=1)
    assert exp.estado.clave == ("cheque_entregado" if programa == "PSA" else "pagada")
    r = Rastro(exp)

    # --- HU-4.1: la comprobación llega por el portal (CC) o se entrega en la Delegación --------------------------------
    with reloj.en(fecha_envio):
        quien = persona or deleg
        c = comprobaciones.registrar_envio(quien, exp, tipo, archivo=None if tipo == "aviso_termino" else _doc(f"{tipo}.pdf"),
                                           fecha_hecho=date(2026, 9, 25) if tipo == "aviso_termino" and programa != "CC"
                                           else date(2026, 11, 11) if programa == "CC" else None)
    assert c.acuse.tipo == "comprobacion" and c.medio == ("portal" if programa == "CC" else "ventanilla")
    assert c.en_plazo is not False
    exp.refresh_from_db()
    estados = [e.estado_destino.clave for e in exp.eventos.order_by("fecha_hora", "pk") if e.estado_destino_id]
    assert estados[-2:] == ["en_ejecucion", "comprobacion_enviada"]
    assert exp.estado.clave == "comprobacion_enviada"
    assert atiende(exp, u) == {deleg.username, area.username}
    r.eventos, r.acuses = exp.eventos.count(), exp.acuses.count()

    # --- HU-4.2: la verificación (MFS: el área revisa la Bitácora) con su superficie y su ajuste, en plazo --------------
    verifica = area if programa == "MFS" else deleg
    with reloj.en(fecha_verif):
        v = verificacion.registrar_verificacion(verifica, exp, documento, _doc("verificacion.pdf"),
                                                fecha_visita=date(2026, 9, 30) if programa != "MFS" else None,
                                                superficie_verificada=superficie,
                                                sobrevivencia="80" if programa in ("PS", "RHF") else None)
    assert v.en_plazo is not False and v.resultado in ("cumple", "ajuste")
    r.relevo("verificada", verifica, None, {area.username}, u, tipo_acuse="verificacion_campo")

    # --- HU-5.1 y 5.2: segunda ministración con el soporte de la verificación o del entregable --------------------------
    m2 = montos.monto_aprobado(exp).ministraciones[1]
    assert m2.importe == segunda
    soportes = {s["clave"]: s for s in solicitudes.soportes(exp, 2)}
    assert soportes["entregable_etf" if programa == "MFS" else "verificacion_campo"]["cumple"]
    with reloj.en(fecha_verif) as rel:
        rel.avanzar(days=3)
        if programa == "PSA":
            instruir_pago(u, exp, 2)                     # el Comité Técnico instruye el pago de la ministración 2
        sol = solicitudes.enviar_solicitud(area, exp, 2)
        assert sol.importe == segunda and sol.ministracion == 2 and all(s["cumple"] for s in sol.soportes)
        r.relevo("ministracion_solicitada", area, None, {"finanzas"}, u, tipo_acuse="solicitud_pago")
        pagos.revisar_solicitud(finanzas, sol, "aceptada")
        sol.refresh_from_db()
        if programa == "PSA":
            pagos.remitir_a_fiduciaria(u["comite"], sol)
            sol.refresh_from_db()
            ch = cheques.emitir_cheque(u["fiduciaria"], sol, "CHQ-0002")
            cheques.enviar_a_delegacion(u["fiduciaria"], ch)
            ch = cheques.registrar_entrega(deleg, ch, exp.solicitante.nombre)
            assert ch.importe == segunda and ch.ministracion == 2
            r.relevo("cheque_entregado", deleg, None, {area.username}, u, nuevos_acuses=3, tipo_acuse="entrega_cheque")
        else:
            pago = pagos.registrar_pago(finanzas, sol, "SPEI-0002", timezone.localdate())
            assert pago.importe == segunda
            r.relevo("pagada", finanzas, None, {area.username}, u, tipo_acuse="pago_ministracion")
    sol.refresh_from_db()
    assert sol.estado == EstadoSolicitud.PAGADA
    total_pagado = primera.importe + sol.importe
    aprobado = montos.monto_aprobado(exp, superficie=montos.superficie_aprobada(exp)).total
    if programa in ("CC", "PS"):                         # proporcional: se pagó lo verificado
        assert total_pagado == (Decimal(superficie) * montos.monto_aprobado(exp).monto_ha).quantize(Decimal("0.01")) < aprobado
    else:                                                # RHF verificó todo; PSAHEM y MFS pagan el 30 % completo
        assert total_pagado == aprobado
    assert not verificacion.ministraciones_pendientes(exp)
