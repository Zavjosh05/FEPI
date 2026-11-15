"""Ajuste P-19 · La pestaña «Contrato» muestra nombres legibles de los plazos y del régimen de pago."""
import re

import pytest
from django.utils.html import escape

from nucleo import montos, plazos
from nucleo.catalogos import datos_sistema

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def test_p_19_cada_uso_de_plazo_configurado_tiene_nombre_legible():
    usos = datos_sistema()["usos_de_plazo"]
    for programa, config in usos.items():
        if not isinstance(config, dict):
            continue
        for uso, c in config.items():
            if c is not False and programa == "por_omision":
                assert c.get("nombre") and "_" not in c["nombre"], uso
    assert usos["PS"]["recoger_planta"]["nombre"] and usos["RHF"]["recoger_planta"]["nombre"]


def test_p_19_el_vencimiento_da_su_nombre_y_la_clave_solo_si_falta_el_dato(notificadas):
    _, (exp,) = notificadas("PS")
    v = plazos.vencimiento(exp, "firma_programada")
    assert v.nombre == "Fecha programada de firma del contrato"
    v.config = {}
    assert v.nombre == "Firma programada"


def test_p_19_el_regimen_se_nombra_por_su_modalidad_o_por_el_dato(notificadas):
    _, (ps,) = notificadas("PS")
    m = montos.monto_aprobado(ps)
    assert m.regimen == "plantacion_forestal_comercial" and m.regimen_nombre == ps.modalidad.nombre
    _, (cc,) = notificadas("CC")
    assert montos.monto_aprobado(cc).regimen_nombre == "Pago único (superficie de hasta 5 ha)" or \
        montos.monto_aprobado(cc).regimen_nombre.startswith("Dos ministraciones")


@pytest.mark.parametrize("programa", ["CC", "PS", "RHF", "PSA"])
def test_p_19_la_pestana_no_muestra_claves_internas(notificadas, usuarios, client, contrasena, programa):
    _, (exp,) = notificadas(programa)
    client.login(username="dir_drff", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    visible = re.sub(r"<[^>]+>", " ", html)   # el texto que se ve (no los atributos data-*)
    for clave in ("firma_programada", "firma_liberacion", "cita_firma", "recoger_planta", "ptrfi_actualizado",
                  "plantacion_forestal_comercial", "mantenimiento_plantaciones", "pago_unico_hasta_5_ha",
                  "dos_ministraciones"):
        assert clave not in visible, clave
    assert "Fecha programada de firma del contrato" in html and "Vencimiento para liberar el recurso" in html
    if programa == "PS":
        assert "Cita a firma por la Delegación" in html and "Vigencia del Vale de Planta" in html
    if programa == "PS":
        assert f"régimen: {escape(exp.modalidad.nombre)}" in html
