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
    assert 'data-prueba="por-construir"' not in html and "Solicitud de pago (HU-5.1)" in html  # M5 completo
    assert 'data-prueba="monto-aprobado"' in html and "$12,000.00" in html
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    assert "Fecha programada de firma del contrato" in html and "sin fecha todavía" in html
    assert "Ver lo que sigue: publicación y contrato" in html  # siguiente paso de lo aprobado


def test_nucleo_demo_deja_aprobadas_de_ps_rhf_y_psahem(catalogos):
    call_command("cargar_demo")
    call_command("cargar_demo")  # idempotente
    from pagos.demo import LOTES
    from pagos.models import Cheque, EstadoSolicitud, OficioPago, Pago, RemisionFiduciaria, SolicitudPago

    # Lote de pagos (HU-5.1): expedientes propios de M5, aparte de los de M3 que siguen como estaban.
    nuevos = [fila[2] for plan in LOTES.values() for fila in plan]
    # (MFS y Guardabosques tienen su propio lote, ejecucion/demo.py, que se prueba en test_nucleo_apps_ejecucion_seguimiento.py.)
    # (El lote de lista de espera y sustituciones de RHF, seguimiento/demo.py, se prueba en test_nucleo_apps_ejecucion_seguimiento.py.)
    from seguimiento.demo import NOMBRES_LOTE

    antes = Expediente.objects.exclude(predio__nombre__in=nuevos + NOMBRES_LOTE).exclude(ejercicio__programa__clave__in=["MFS", "PEG"])
    # Primer lote (HU-3.1 y HU-3.2): PS y RHF ya publicaron y tienen contratos en distintos puntos; PSAHEM sigue con sus
    # dos aprobadas por publicar. Segundo lote (HU-3.3): tres más en PS y en RHF, con contratos firmados y uno sin firma.
    estados = {"PS": {"contrato_en_delegacion", "publicada", "vale_entregado", "sin_firma_en_plazo"},
               "RHF": {"contrato_elaborado", "notificada", "contratada", "vale_entregado"}, "PSA": {"aprobada"}}
    cuantos = {"PS": 5, "RHF": 5, "PSA": 2}
    for clave in ("PS", "RHF", "PSA"):
        expedientes = antes.filter(ejercicio__programa__clave=clave, resoluciones_comite__resultado="beneficiaria")
        assert expedientes.count() == cuantos[clave], clave
        assert {e.estado.clave for e in expedientes} == estados[clave], clave
        for exp in expedientes:
            m = montos.monto_aprobado(exp)
            assert m.total > 0 and m.ministraciones and exp.resoluciones_comite.get().monto == m.total
    assert Expediente.objects.filter(ejercicio__programa__clave="CC", estado__clave="aprobada").count() >= 2
    # HU-3.3: contratos firmados (con su acuse y verificación) y, en PS, uno sin firma por liberar.
    assert antes.filter(ejercicio__programa__clave="PS", estado__clave="sin_firma_en_plazo").count() == 1
    assert antes.filter(ejercicio__programa__clave="PS", estado__clave="vale_entregado").count() == 2
    assert antes.filter(ejercicio__programa__clave="RHF", estado__clave="contratada").count() == 1  # Peña Blanca: sin planta
    assert FirmaContrato.objects.filter(expediente__in=antes).count() == 5 and SinFirma.objects.count() == 1
    # HU-3.4: vales vigentes, uno vencido (PS, sin reposición) y uno vencido con su reposición (RHF), con salidas parciales.
    vales = ValePlanta.objects.filter(expediente__in=antes)
    assert vales.count() == 5 and {v.situacion() for v in vales} == {"vigente", "vencido", "repuesto"}
    assert ValePlanta.objects.filter(repone__isnull=False).count() == 1 and SalidaPlanta.objects.count() >= 4
    assert not any(v.surtido for v in vales)
    # HU-5.1: contratos firmados de CC, PS, RHF y PSAHEM con su oficio y la solicitud de la primera ministración.
    lote = Expediente.objects.filter(predio__nombre__in=nuevos)
    assert lote.count() == 16 and FirmaContrato.objects.filter(expediente__in=lote).count() == 16
    assert OficioPago.objects.filter(expediente__in=lote).count() == 15  # a Predio El Paraíso (CC) todavía no se le emite
    assert not hasattr(Expediente.objects.get(predio__nombre="Predio El Paraíso"), "oficio_pago")
    solicitudes_demo = {s.expediente.predio.nombre: s for s in SolicitudPago.objects.filter(expediente__in=lote)
                        .select_related("expediente__predio")}
    assert solicitudes_demo["Predio Santa Cruz"].estado == EstadoSolicitud.BORRADOR  # por enviar, con todos sus soportes
    assert solicitudes_demo["Cañada Verde"].estado == EstadoSolicitud.BORRADOR
    enviadas = [s for s in SolicitudPago.objects.filter(expediente__in=lote) if s.estado != EstadoSolicitud.BORRADOR]
    assert len(enviadas) == 13 and all(s.enviada_en and s.acuse_envio and s.soportes for s in enviadas)
    assert solicitudes_demo["Predio La Ciénega"].importe == 8000 and solicitudes_demo["Predio La Ciénega"].porcentaje == 100
    # HU-5.2: devuelta, pagadas (transferencia y un cheque excepcional), aceptada y remitidas a la Fiduciaria, en cada programa.
    estado = {n: s.estado for n, s in solicitudes_demo.items()}
    assert estado["Predio Las Palomas"] == estado["Plantación El Cedro"] == estado["Rancho El Pedregal"] == "enviada"
    assert estado["Predio El Fresno"] == "devuelta" and Expediente.objects.get(predio__nombre="Predio El Fresno").estado.clave == "contratada"
    assert {estado[n] for n in ("Predio La Ciénega", "Plantación La Mesa", "Manantial Alto")} == {"pagada"}
    assert Pago.objects.filter(expediente__in=lote).count() == 3 and Pago.objects.get(solicitud__expediente__predio__nombre="Manantial Alto").tipo == "cheque_excepcional"
    assert all(p.solicitud == p.solicitud.expediente.solicitudes_pago.get() and p.fecha_pago and p.aviso
               for p in Pago.objects.filter(expediente__in=lote))
    assert estado["Ejido La Joya"] == "aceptada"
    assert RemisionFiduciaria.objects.count() == 5 and all(r.acuse and r.remitida_en and r.en_plazo for r in RemisionFiduciaria.objects.all())
    # HU-5.3: la Fiduciaria emite el cheque de las remitidas; en cada punto del camino hasta la entrega (y uno por vencer).
    de = {n: Expediente.objects.get(predio__nombre=n).estado.clave for n in (
        "Bosque Los Cedros", "Paraje Las Ánimas", "Monte Alto", "Cerro del Venado", "Loma Verde")}
    assert de == {"Bosque Los Cedros": "remitida_fiduciaria", "Paraje Las Ánimas": "cheque_emitido", "Monte Alto": "cheque_enviado",
                  "Cerro del Venado": "cheque_entregado", "Loma Verde": "cheque_entregado"}
    assert Cheque.objects.count() == 4 and Cheque.objects.filter(enviado_en__isnull=False).count() == 3
    assert Cheque.objects.filter(entregado_en__isnull=False).count() == 2
    assert all(c.persona == c.expediente.solicitante and c.ministracion == 1 for c in Cheque.objects.all())
    assert Expediente.objects.get(predio__nombre="Loma Verde").eventos.filter(tipo="cheque_por_vencer").count() == 1
