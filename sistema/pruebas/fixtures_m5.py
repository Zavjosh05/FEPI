"""Fixtures del módulo M5 (HU-5.x): expedientes con el contrato firmado y sus soportes de pago."""
from decimal import Decimal

import pytest

from contrato import firma
from dictamen import seguimiento, sesiones
from dictamen.models import TipoSesion
from nucleo.models import Ministracion, MontoApoyo, Unidad
from pagos import pagos, solicitudes

from .fixtures_m2 import documento_sesion, fecha_sesion
from .fixtures_m3 import SOLICITUDES_M3, delegado_de

__all__ = ["con_soportes", "instruir_pago", "solicitada", "aceptada", "peg_contratado", "remitida", "entregado"]


def instruir_pago(usuarios, expediente, ministracion=1):
    """PSAHEM: acuerdo de seguimiento del Comité Técnico que instruye a la Fiduciaria el pago de la ministración."""
    ejercicio = expediente.ejercicio
    s = sesiones.crear_sesion(usuarios["comite"], ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(6), "Sala",
                              "Quórum\nInstrucción de pago")
    sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(), "Pagos")
    sesiones.enviar_convocatoria(usuarios["comite"], s)
    return seguimiento.registrar_acuerdo(
        usuarios["comite"], s, "instruccion_pago", f"Instruir el pago de la ministración {ministracion}", [expediente],
        Unidad.objects.get(clave="FIDUCIARIA"), ministracion=ministracion)


@pytest.fixture
def con_soportes(contratadas, usuarios, pdf, monkeypatch):
    """``con_soportes("CC", ha=None, oficio=True, comprobante=True, instruccion=True)`` → expediente con el contrato firmado
    y los soportes de la primera ministración que se pidan (la Delegación emite el oficio y guarda el comprobante donde las
    reglas lo piden; en PSAHEM el Comité da la instrucción de pago)."""

    def _crear(programa="CC", ha=None, oficio=True, comprobante=True, instruccion=True, cuantas=1):
        if ha is not None:
            monkeypatch.setitem(SOLICITUDES_M3, programa, [(*fila[:5], ha) for fila in SOLICITUDES_M3[programa][:cuantas]])
        _, exps = contratadas(programa, cuantas=cuantas)
        for exp in exps:
            deleg = delegado_de(usuarios, exp)
            if oficio:
                solicitudes.emitir_oficio(deleg, exp)
            if comprobante and any(s["clave"] == "comprobante_cuenta" for s in solicitudes.soportes_requeridos(exp, 1)):
                solicitudes.adjuntar_comprobante(deleg, exp, pdf("cuenta.pdf"))
            if instruccion and programa == "PSA":
                instruir_pago(usuarios, exp)
            exp.refresh_from_db()
        return exps[0] if cuantas == 1 else exps
    return _crear


@pytest.fixture
def solicitada(con_soportes, usuarios):
    """``solicitada("CC")`` → expediente con la primera ministración ya enviada a Administración y Finanzas."""

    def _crear(programa="CC", **kw):
        exp = con_soportes(programa, **kw)
        solicitudes.enviar_solicitud(usuarios["dir_drff"], exp, 1)
        exp.refresh_from_db()
        return exp
    return _crear


@pytest.fixture
def aceptada(solicitada, usuarios):
    """``aceptada("CC")`` → ``(expediente, solicitud)`` con la primera ministración aceptada por Administración y Finanzas."""

    def _crear(programa="CC", **kw):
        exp = solicitada(programa, **kw)
        sol = exp.solicitudes_pago.get(ministracion=1)
        pagos.revisar_solicitud(usuarios["finanzas"], sol, "aceptada")
        sol.refresh_from_db()
        return exp, sol
    return _crear


@pytest.fixture
def peg_contratado(peg, contrato_manual, usuarios, pdf):
    """Guardabosques (PEG, sin archivo de reglas) con su contrato firmado, un monto de 5,000 por hectárea y cuatro
    ministraciones de 25 %: sirve para probar el tipo de pago «depósito»."""

    def _crear():
        MontoApoyo.objects.create(ejercicio=peg, concepto="Apoyo al Guardabosque (prueba)", monto=Decimal("5000"),
                                  unidad="por hectárea")
        for n in range(1, 5):
            Ministracion.objects.create(ejercicio=peg, numero=n, porcentaje=Decimal("25"), regimen="anual")
        exp = contrato_manual(peg, direccion="dir_dpf", modalidad=None)
        firma.registrar_firma(
            delegado_de(usuarios, exp), exp, None, "persona", "Guardabosque", pdf("firmado.pdf"),
            [p["clave"] for p in firma.puntos_de_verificacion(exp)],
            {"credencial_guardabosque": {"archivo": pdf("credencial.pdf"), "dato": "CRED-0001"}})
        exp.refresh_from_db()
        return exp
    return _crear


@pytest.fixture
def remitida(aceptada, usuarios):
    """``remitida()`` → ``(expediente, solicitud)`` de PSAHEM con el pago ya solicitado a la Fiduciaria por la Secretaría Técnica."""

    def _crear(**kw):
        exp, sol = aceptada("PSA", **kw)
        pagos.remitir_a_fiduciaria(usuarios["comite"], sol)
        sol.refresh_from_db()
        exp.refresh_from_db()
        return exp, sol
    return _crear


@pytest.fixture
def entregado(remitida, usuarios):
    """``entregado()`` → ``(expediente, cheque)`` con el cheque emitido, enviado y entregado a la persona."""
    from pagos import cheques

    def _crear(**kw):
        exp, sol = remitida(**kw)
        c = cheques.emitir_cheque(usuarios["fiduciaria"], sol, "CHQ-0001")
        cheques.enviar_a_delegacion(usuarios["fiduciaria"], c)
        c = cheques.registrar_entrega(delegado_de(usuarios, exp), c, exp.solicitante.nombre)
        exp.refresh_from_db()
        return exp, c
    return _crear
