"""Fixtures del módulo M4 (HU-4.x): expedientes con la primera ministración pagada (o el cheque entregado en PSAHEM) y
cuentas del portal activas."""
import re

import pytest
from django.utils import timezone

from pagos import cheques, pagos, solicitudes
from portal import cuentas

from .fixtures_m3 import delegado_de, direccion_de

__all__ = ["pagada", "cuenta_portal", "CONTRASENA_PORTAL"]

CONTRASENA_PORTAL = "Bosque-Seguro-2026"
CURPS = {"CC": "LAPB800101MMCRNT05", "PS": "COVA700305HMCNGB01", "RHF": "SAOR650920HMCNRF08", "PSA": "HERF600712HMCRML02",
         "MFS": "COMA750612HMCLRN04"}


@pytest.fixture
def pagada(con_soportes, usuarios):
    """``pagada("CC", cuantas=1, ha=None)`` → expediente (o lista) con la primera ministración pagada (estado ``pagada``); en
    PSAHEM con el cheque entregado (``cheque_entregado``). La solicitud la envía la Instancia Ejecutora del programa."""

    def _crear(programa="CC", cuantas=1, **kw):
        exps = con_soportes(programa, cuantas=cuantas, **kw)
        exps = exps if isinstance(exps, list) else [exps]
        for exp in exps:
            sol = solicitudes.enviar_solicitud(direccion_de(usuarios, exp.ejercicio), exp, 1)
            pagos.revisar_solicitud(usuarios["finanzas"], sol, "aceptada")
            sol.refresh_from_db()
            if programa == "PSA":
                pagos.remitir_a_fiduciaria(usuarios["comite"], sol)
                sol.refresh_from_db()
                c = cheques.emitir_cheque(usuarios["fiduciaria"], sol, f"CHQ-{sol.pk:04d}")
                cheques.enviar_a_delegacion(usuarios["fiduciaria"], c)
                cheques.registrar_entrega(delegado_de(usuarios, exp), c, exp.solicitante.nombre)
            else:
                pagos.registrar_pago(usuarios["finanzas"], sol, f"SPEI-{sol.pk:04d}", timezone.localdate())
            exp.refresh_from_db()
        return exps[0] if cuantas == 1 else exps
    return _crear


def _codigos(acuse):
    return re.findall(r"[A-Z2-9]{4}-[A-Z2-9]{4}", str(acuse.contenido))


@pytest.fixture
def cuenta_portal(usuarios):
    """``cuenta_portal(exp)`` → usuario del portal activo (contraseña ``CONTRASENA_PORTAL``) de la persona beneficiaria,
    con acceso al expediente; ``con_codigos=True`` devuelve también ``(usuario, codigo_acceso, codigo_consulta)`` sin activar."""

    def _crear(exp, curp=None, con_codigos=False):
        persona = exp.beneficiaria
        if not cuentas.curp_valida(persona.curp):
            persona.curp = curp or CURPS.get(exp.programa.clave, "LAPB800101MMCRNT05")
            persona.save(update_fields=["curp"])
        res = cuentas.dar_acceso(delegado_de(usuarios, exp), exp, persona)
        cuenta = res["cuenta"] or persona.cuentas_portal.first()
        if con_codigos:
            return cuenta.usuario, res["codigo_acceso"], res["codigo_consulta"]
        if cuenta.activada_en is None:
            cuentas.primer_acceso(cuenta.usuario.username, res["codigo_acceso"], CONTRASENA_PORTAL)
        cuenta.usuario.refresh_from_db()
        return cuenta.usuario
    return _crear
