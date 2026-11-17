"""Núcleo · monto aprobado del expediente y sus ministraciones (S2-02d)."""
from decimal import Decimal

import pytest

from nucleo import extensiones, montos
from nucleo.models import Ejercicio, Expediente

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def exp_con(nueva_solicitud):
    def _crear(programa, modalidad, superficie=None):
        exp = nueva_solicitud()
        ej = Ejercicio.objects.get(programa__clave=programa, anio=2026)
        Expediente.objects.filter(pk=exp.pk).update(
            ejercicio=ej, modalidad=ej.modalidades.get(clave=modalidad),
            superficie_solicitada_ha=superficie)
        return Expediente.objects.get(pk=exp.pk)
    return _crear


def _importes(m):
    return [(x.numero, x.porcentaje, x.importe) for x in m.ministraciones]


def test_nucleo_cc_pago_unico_hasta_5_ha(exp_con):
    m = montos.monto_aprobado(exp_con("CC", "reforestacion"), D("4"))
    assert m.monto_ha == D("2000") and m.total == D("8000.00") and m.regimen == "pago_unico_hasta_5_ha"
    assert _importes(m) == [(1, D("100"), D("8000.00"))]
    m = montos.monto_aprobado(exp_con("CC", "plantacion_navidena"), D("5"))  # el umbral es «menor o igual»
    assert m.regimen == "pago_unico_hasta_5_ha" and len(m.ministraciones) == 1


def test_nucleo_cc_dos_ministraciones_arriba_de_5_ha_y_la_suma_cuadra(exp_con):
    m = montos.monto_aprobado(exp_con("CC", "plantacion_maderable"), D("12.3457"))
    assert m.total == D("24691.40") and m.regimen == "dos_ministraciones_mas_de_5_ha"
    assert _importes(m) == [(1, D("70"), D("17283.98")), (2, D("30"), D("7407.42"))]
    assert sum(x.importe for x in m.ministraciones) == m.total
    assert "firma del Contrato" in m.ministraciones[0].condicion


def test_nucleo_ps_monto_por_concepto_y_navidenas_sin_dinero(exp_con):
    ps = Ejercicio.objects.get(programa__clave="PS", anio=2026)
    assert ps.montos.filter(modalidad__clave="plantacion_forestal_comercial", monto=10000).exists()
    m = montos.monto_aprobado(exp_con("PS", "plantacion_forestal_comercial"), D("3"))
    assert m.total == D("30000.00") and _importes(m) == [(1, D("70"), D("21000.00")), (2, D("30"), D("9000.00"))]
    m = montos.monto_aprobado(exp_con("PS", "mantenimiento_plantaciones"), D("2"))
    assert m.total == D("10000.00") and m.regimen == "mantenimiento_plantaciones"
    m = montos.monto_aprobado(exp_con("PS", "mantenimiento_navidenas"), D("8"))
    assert m.total == 0 and m.sin_dinero and m.ministraciones == [] and "sin recurso" in m.nota


def test_nucleo_rhf_monto_de_cada_modalidad(exp_con):
    esperado = {"rfi_modalidad_uno": "30000", "rfi_modalidad_dos": "14000", "bosques_de_agua": "3500",
                "preservacion_reforestaciones": "3000"}
    for modalidad, monto_ha in esperado.items():
        m = montos.monto_aprobado(exp_con("RHF", modalidad), D("1.5"))
        assert m.monto_ha == D(monto_ha) and m.total == (D("1.5") * D(monto_ha)).quantize(D("0.01"))
        assert [x.porcentaje for x in m.ministraciones] == [D("70"), D("30")] and m.regimen == modalidad


def test_nucleo_psahem_por_cuenca_y_con_certificacion_fsc(exp_con):
    alta = exp_con("PSA", "cuenca_alta")
    assert montos.monto_aprobado(alta, D("30")).total == D("105000.00")
    assert montos.monto_aprobado(alta, D("30"), condiciones={"certificacion_FSC"}).total == D("108000.00")
    m = montos.monto_aprobado(exp_con("PSA", "cuenca_media_baja"), D("25"))
    assert m.total == D("37500.00") and m.regimen == "dos_ministraciones" and len(m.ministraciones) == 2


def test_nucleo_superficie_del_dictamen_o_la_solicitada(exp_con):
    exp = exp_con("CC", "reforestacion", superficie=D("3"))
    assert montos.monto_aprobado(exp).superficie_ha == D("3")  # sin dictamen: la solicitada
    extensiones.SUPERFICIE_APROBADA.insert(0, lambda e: D("2.5"))
    try:
        assert montos.monto_aprobado(exp).total == D("5000.00")
    finally:
        extensiones.SUPERFICIE_APROBADA.pop(0)


# ----------------------------------------------------------------------------- MFS y PEG (S3-02)
def test_nucleo_mfs_monto_fijo_por_apoyo_y_regimen_por_modalidad(exp_con):
    """MFS paga un monto fijo por concepto (7.2 A y B), no por hectárea; el régimen sale del mapa de las reglas."""
    m = montos.monto_aprobado(exp_con("MFS", "etf_pmf_maderable_95_250"), D("120"))
    assert m.tipo_monto == montos.POR_APOYO and m.total == D("65000.00") and m.regimen == "etf"
    assert _importes(m) == [(1, D("70"), D("45500.00")), (2, D("30"), D("19500.00"))]
    assert montos.monto_aprobado(exp_con("MFS", "etf_pmf_maderable_95_250"), D("200")).total == D("65000.00")
    assert "Bitácora" in m.ministraciones[1].condicion and "monto fijo por apoyo" in m.texto_calculo
    m = montos.monto_aprobado(exp_con("MFS", "fsc_certificacion_cadena_custodia"), D("10"))
    assert m.regimen == "fsc" and [x.porcentaje for x in m.ministraciones] == [D("50"), D("50")]
    assert "50 %" in m.regimen_nombre


def test_nucleo_mfs_certificacion_grupal_suma_sus_componentes(exp_con):
    m = montos.monto_aprobado(exp_con("MFS", "fsc_certificacion_manejo_grupal"), D("300"))
    assert m.total == D("600000.00") and "componentes" in m.nota  # 210,000 + 350,000 + 40,000 (cuadro por confirmar)


def test_nucleo_peg_monto_por_guardabosque_en_cuatro_ministraciones_supuestas(exp_con):
    m = montos.monto_aprobado(exp_con("PEG", "apoyo_monetario_guardabosque"))
    assert m.tipo_monto == montos.POR_PERSONA and m.cantidad == 1 and m.total == D("25550.00")
    assert _importes(m) == [(n, D("25"), D("6387.50")) for n in (1, 2, 3, 4)]
    assert m.supuesto and all(x.supuesto for x in m.ministraciones) and "supuesto" in m.nota
    assert m.texto_base == "$25,550.00 por persona beneficiaria al año"
    cc = montos.monto_aprobado(exp_con("CC", "reforestacion"), D("4"))
    assert not cc.supuesto and cc.texto_calculo == "4 ha × $2,000.00 = $8,000.00"
