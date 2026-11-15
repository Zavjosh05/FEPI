"""Núcleo · apps «contrato» (M3) y «pagos» (M5) listas para sus historias, y demostración (S2-02g)."""
import pytest
from django.apps import apps
from django.core.management import call_command

from nucleo import extensiones, montos
from nucleo.models import Estado, Expediente

pytestmark = pytest.mark.django_db


def test_nucleo_apps_instaladas_con_modelos_por_historia():
    for nombre in ("contrato", "pagos"):
        app = apps.get_app_config(nombre)
        assert app.module.__name__ == nombre
        assert __import__(f"{nombre}.models", fromlist=["*"]).__file__.endswith("__init__.py")  # paquete models/
    claves = [p["clave"] for p in extensiones.PESTANAS_EXPEDIENTE]
    assert claves.count("contrato") == 1 and claves.count("pagos") == 1


def test_nucleo_pestanas_contrato_y_pagos_dicen_que_historia_las_llena(client, nueva_solicitud, contrasena):
    exp = nueva_solicitud(superficie_solicitada_ha=6)
    client.login(username="dir_drff", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    assert "HU-3.2 Elaboración del contrato" in html and "El monto se calcula cuando el Comité" in html
    Expediente.objects.filter(pk=exp.pk).update(estado=Estado.objects.get(clave="aprobada"))
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=pagos").content.decode()
    assert "HU-5.3 Entrega de cheques" in html and 'data-prueba="monto-aprobado"' in html and "$12,000.00" in html
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    assert "firma_programada" in html and "sin fecha todavía" in html
    assert "Ver lo que sigue: publicación y contrato" in html  # siguiente paso de lo aprobado


def test_nucleo_demo_deja_aprobadas_de_ps_rhf_y_psahem(catalogos):
    call_command("cargar_demo")
    call_command("cargar_demo")  # idempotente
    for clave in ("PS", "RHF", "PSA"):
        aprobadas = Expediente.objects.filter(ejercicio__programa__clave=clave, estado__clave="aprobada")
        assert aprobadas.count() == 2, clave
        for exp in aprobadas:
            m = montos.monto_aprobado(exp)
            assert m.total > 0 and m.ministraciones and exp.resoluciones_comite.get().monto == m.total
    assert Expediente.objects.filter(ejercicio__programa__clave="CC", estado__clave="aprobada").count() >= 2
