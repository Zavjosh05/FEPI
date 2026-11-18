"""Núcleo · apps ``ejecucion`` (M4) y ``seguimiento`` (M6) vacías pero listas (S3-02e): pestañas del expediente que dicen
qué historia las llenará, modelos por historia y demostración de MFS y Guardabosques."""
from decimal import Decimal

import pytest
from django.apps import apps
from django.urls import reverse

from ejecucion import registro as reg_ejecucion
from nucleo import extensiones, reloj
from nucleo.demo import crear_usuarios
from nucleo.models import Expediente
from seguimiento import registro as reg_seguimiento

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def test_nucleo_apps_de_m4_y_m6_registradas_con_su_pestana():
    assert apps.is_installed("ejecucion") and apps.is_installed("seguimiento")
    claves = [p["clave"] for p in extensiones.PESTANAS_EXPEDIENTE]
    assert {"ejecucion", "seguimiento"} <= set(claves) and claves.index("pagos") < claves.index("ejecucion")
    assert [h[0] for h in reg_ejecucion.historias_pendientes()] == []   # HU-4.1, HU-4.2 y HU-4.3 ya construidas
    assert [h[0] for h in reg_seguimiento.historias_pendientes()] == ["HU-6.1", "HU-6.2", "HU-6.3"]
    assert apps.get_app_config("ejecucion").get_models() is not None


def test_nucleo_pestanas_ejecucion_y_seguimiento_dicen_que_historia_las_llenara(contratadas, client, contrasena):
    _, (exp,) = contratadas("CC")
    client.login(username="dir_drff", password=contrasena)
    for pestana, historia, plazo in (("ejecucion", "Ejecución y verificación", "Entrega del informe final"),
                                     ("seguimiento", "HU-6.2 Incumplimientos y reintegros", "Subsanar las omisiones")):
        html = client.get(reverse("recepcion:expediente", args=[exp.folio]) + f"?pestana={pestana}").content.decode()
        assert historia in html and plazo in html and 'data-prueba="monto-aprobado"' in html, pestana
        assert "sprint" not in html.lower()


def test_nucleo_demo_de_mfs_y_peg_lista_para_comprobar_e_idempotente(catalogos):
    from ejecucion import demo
    from ejecucion import reportes as ejecucion_reportes
    from portal.models import CuentaExterna

    crear_usuarios()
    with reloj.en("2031-03-01 08:00"):                   # el día de la carga no cuenta
        assert demo.cargar_demo() == 8
        assert demo.cargar_demo() == 0
    pagadas = Expediente.objects.filter(estado__clave="pagada")
    assert {e.predio.nombre for e in pagadas} == {"Bosque Los Volcanes", "Aserradero La Cumbre", "Ejido San Juan",
                                                  "Ejido San Bartolo"}
    volcanes = pagadas.get(predio__nombre="Bosque Los Volcanes")
    # HU-4.1 y HU-4.2: Los Volcanes entrega su Bitácora en la Delegación, el área la revisa y se paga la segunda ministración.
    assert volcanes.comprobaciones.get().tipo == "bitacora_etf" and volcanes.verificaciones.get().resultado == "cumple"
    assert [p.importe for p in volcanes.pagos.order_by("solicitud__ministracion")] == [Decimal("21000.00"), Decimal("9000.00")]
    assert volcanes.poligonos.get(vigente=True).levantado_por == "prestador"
    assert pagadas.get(predio__nombre="Aserradero La Cumbre").pagos.get().importe == Decimal("70000.00")  # 50 % FSC
    san_juan = pagadas.get(predio__nombre="Ejido San Juan")
    pago = san_juan.pagos.order_by("solicitud__ministracion").first()   # la segunda (22-sep) la cobra con la evaluación de HU-4.3
    assert san_juan.pagos.count() == 2 and pago.tipo == "deposito" and pago.importe == Decimal("6387.50")
    assert san_juan.pagos.count() == 2 and ejecucion_reportes.periodos_senalados(san_juan) == []
    assert [e.resultado for e in ejecucion_reportes.periodos_senalados(pagadas.get(predio__nombre="Ejido San Bartolo"))] == ["no_entrego"]
    assert san_juan.beneficiaria.nombre == "Margarito Sánchez Ruiz"
    assert CuentaExterna.objects.get(usuario__username="SARM800101HMCNZR09").activada_en
    # HU-4.1: reportes de junio a octubre por el portal (el último por revisar) y en ventanilla los de San Bartolo.
    reportes = san_juan.comprobaciones.filter(tipo="reporte_mensual")
    assert [c.periodo for c in reportes.order_by("periodo")] == ["2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
    assert {c.medio for c in reportes} == {"portal"} and reportes.filter(revisada_en__isnull=True).count() == 1
    assert san_juan.comprobaciones.filter(tipo="acuse_deposito", medio="ventanilla").count() == 1
    bartolo = pagadas.get(predio__nombre="Ejido San Bartolo")
    assert sorted(bartolo.comprobaciones.values_list("periodo", flat=True)) == ["2026-06", "2026-07"]
    assert all(c.acuse and c.enviada_en.year == 2026 for c in san_juan.comprobaciones.all())
    assert Expediente.objects.filter(predio__nombre__in=["Predio Agua Fría", "Ejido San Lorenzo"], estado__clave="recibida").count() == 2
    assert not Expediente.objects.filter(fecha_recepcion__year__gt=2026).exists()
