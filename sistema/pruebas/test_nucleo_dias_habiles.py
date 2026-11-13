"""Núcleo: días hábiles y vencimientos (fines de semana e inhábiles del catálogo)."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from nucleo import dias_habiles as dh
from nucleo.models import DiaInhabil

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def calendario():
    DiaInhabil.objects.all().delete()
    DiaInhabil.objects.create(fecha=date(2026, 3, 16), descripcion="Natalicio de Benito Juárez")
    DiaInhabil.objects.create(fecha=date(2026, 4, 2), descripcion="Jueves Santo")
    DiaInhabil.objects.create(fecha=date(2026, 4, 3), descripcion="Viernes Santo")


def test_nucleo_fin_de_semana_e_inhabil_no_son_habiles():
    assert dh.es_habil(date(2026, 3, 13))          # viernes
    assert not dh.es_habil(date(2026, 3, 14))      # sábado
    assert not dh.es_habil(date(2026, 3, 15))      # domingo
    assert not dh.es_habil(date(2026, 3, 16))      # inhábil del catálogo


def test_nucleo_cinco_dias_habiles_desde_un_lunes_vencen_el_lunes_siguiente():
    assert dh.sumar_dias_habiles(date(2026, 2, 23), 5) == date(2026, 3, 2)


def test_nucleo_sumar_dias_habiles_salta_fin_de_semana_e_inhabil():
    # Jueves 12-mar + 5 hábiles: 13 (vie), [14-15 fin], [16 inhábil], 17, 18, 19, 20 -> 20-mar
    assert dh.sumar_dias_habiles(date(2026, 3, 12), 5) == date(2026, 3, 20)


def test_nucleo_plazo_iniciado_en_sabado_cuenta_desde_el_lunes():
    assert dh.sumar_dias_habiles(date(2026, 3, 7), 1) == date(2026, 3, 9)


def test_nucleo_semana_santa_se_salta():
    # Miércoles 1-abr + 1 hábil: 2 y 3 inhábiles, 4-5 fin de semana -> lunes 6-abr
    assert dh.sumar_dias_habiles(date(2026, 4, 1), 1) == date(2026, 4, 6)


def test_nucleo_vencimiento_acepta_fecha_y_hora_local():
    recibida = datetime(2026, 3, 12, 23, 30, tzinfo=ZoneInfo("America/Mexico_City"))
    assert dh.calcular_vencimiento(recibida, 5, "dias_habiles") == date(2026, 3, 20)


def test_nucleo_dias_naturales_que_vencen_en_inhabil_pasan_al_siguiente_habil():
    # 10-mar + 6 naturales = 16-mar (inhábil) -> 17-mar
    assert dh.calcular_vencimiento(date(2026, 3, 10), 6, "dias_naturales") == date(2026, 3, 17)


def test_nucleo_meses_y_anios():
    assert dh.calcular_vencimiento(date(2026, 1, 30), 1, "meses") == date(2026, 3, 2)  # 28-feb sábado -> lunes 2-mar
    assert dh.calcular_vencimiento(date(2023, 5, 10), 3, "anios") == date(2026, 5, 11)  # 10-may-2026 domingo
    assert dh.sumar_meses(date(2026, 5, 31), -3) == date(2026, 2, 28)


def test_nucleo_plazo_sin_cantidad_no_se_calcula():
    with pytest.raises(ValueError):
        dh.calcular_vencimiento(date(2026, 3, 1), None, "fecha_limite")


def test_nucleo_dias_habiles_entre_fechas():
    assert dh.dias_habiles_entre(date(2026, 3, 12), date(2026, 3, 20)) == 5
    assert dh.dias_habiles_entre(date(2026, 3, 20), date(2026, 3, 12)) == -5
