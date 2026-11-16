"""Fixtures del módulo M5 (HU-5.x): expedientes con el contrato firmado y sus soportes de pago."""
import pytest

from dictamen import seguimiento, sesiones
from dictamen.models import TipoSesion
from nucleo.models import Unidad
from pagos import solicitudes

from .fixtures_m2 import documento_sesion, fecha_sesion
from .fixtures_m3 import SOLICITUDES_M3, delegado_de

__all__ = ["con_soportes", "instruir_pago", "solicitada"]


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
