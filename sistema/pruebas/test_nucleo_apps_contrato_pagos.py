"""Núcleo · apps «contrato» (M3) y «pagos» (M5) listas para sus historias, y demostración (S2-02g)."""
import pytest
from django.apps import apps
from django.core.management import call_command

from contrato.models import FirmaContrato, SalidaPlanta, SinFirma, ValePlanta
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
    assert "Entrega de planta (HU-3.4)" in html and 'data-prueba="por-construir"' not in html and "El monto se calcula cuando el Comité" in html
    Expediente.objects.filter(pk=exp.pk).update(estado=Estado.objects.get(clave="aprobada"))
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=pagos").content.decode()
    assert "HU-5.3 Entrega de cheques" in html and 'data-prueba="monto-aprobado"' in html and "$12,000.00" in html
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    assert "Fecha programada de firma del contrato" in html and "sin fecha todavía" in html
    assert "Ver lo que sigue: publicación y contrato" in html  # siguiente paso de lo aprobado


def test_nucleo_demo_deja_aprobadas_de_ps_rhf_y_psahem(catalogos):
    call_command("cargar_demo")
    call_command("cargar_demo")  # idempotente
    # Primer lote (HU-3.1 y HU-3.2): PS y RHF ya publicaron y tienen contratos en distintos puntos; PSAHEM sigue con sus
    # dos aprobadas por publicar. Segundo lote (HU-3.3): tres más en PS y en RHF, con contratos firmados y uno sin firma.
    estados = {"PS": {"contrato_en_delegacion", "publicada", "vale_entregado", "sin_firma_en_plazo"},
               "RHF": {"contrato_elaborado", "notificada", "contratada", "vale_entregado"}, "PSA": {"aprobada"}}
    cuantos = {"PS": 5, "RHF": 5, "PSA": 2}
    for clave in ("PS", "RHF", "PSA"):
        expedientes = Expediente.objects.filter(ejercicio__programa__clave=clave, resoluciones_comite__resultado="beneficiaria")
        assert expedientes.count() == cuantos[clave], clave
        assert {e.estado.clave for e in expedientes} == estados[clave], clave
        for exp in expedientes:
            m = montos.monto_aprobado(exp)
            assert m.total > 0 and m.ministraciones and exp.resoluciones_comite.get().monto == m.total
    assert Expediente.objects.filter(ejercicio__programa__clave="CC", estado__clave="aprobada").count() >= 2
    # HU-3.3: contratos firmados (con su acuse y verificación) y, en PS, uno sin firma por liberar.
    assert Expediente.objects.filter(ejercicio__programa__clave="PS", estado__clave="sin_firma_en_plazo").count() == 1
    assert Expediente.objects.filter(ejercicio__programa__clave="PS", estado__clave="vale_entregado").count() == 2
    assert Expediente.objects.filter(ejercicio__programa__clave="RHF", estado__clave="contratada").count() == 1  # Peña Blanca: sin planta
    assert FirmaContrato.objects.count() == 5 and SinFirma.objects.count() == 1
    # HU-3.4: vales vigentes, uno vencido (PS, sin reposición) y uno vencido con su reposición (RHF), con salidas parciales.
    vales = ValePlanta.objects.all()
    assert vales.count() == 5 and {v.situacion() for v in vales} == {"vigente", "vencido", "repuesto"}
    assert ValePlanta.objects.filter(repone__isnull=False).count() == 1 and SalidaPlanta.objects.count() >= 4
    assert not any(v.surtido for v in vales)
