"""Núcleo · plazos de M4 y M6 por programa y avisos antes de vencer y al vencer (S3-02d). Solo avisan: no cambian
estados ni ejecutan nada (P-08)."""
from datetime import date, datetime

import pytest
from django.core.management import call_command
from django.utils import timezone

from nucleo import avisos, plazos, reloj
from nucleo.models import Estado, Expediente

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def _momento(texto):
    return timezone.make_aware(datetime.fromisoformat(texto))


def test_nucleo_entrega_de_la_comprobacion_es_plazo_de_entrega_desde_la_conclusion(contratadas):
    _, (cc,) = contratadas("CC")
    v = plazos.vencimiento(cc, "entrega_comprobacion")
    # CC: 15 días hábiles desde el 13-nov-2026 (R-04: entregar el Informe Final, no hacer la visita; el 16-nov es inhábil).
    assert v.fecha_evento == date(2026, 11, 13) and v.plazo.cantidad == 15 and str(v.vencimiento) == "2026-12-07"
    assert "fecha límite de conclusión" in v.texto
    assert str(plazos.vencimiento(cc, "fecha_limite_conclusion").vencimiento) == "2026-11-13"
    _, (ps,) = contratadas("PS")
    assert plazos.vencimiento(ps, "entrega_comprobacion").plazo.cantidad == 30


def test_nucleo_mfs_y_peg_no_traen_esos_plazos(contratadas):
    _, (mfs,) = contratadas("MFS")
    v = plazos.vencimiento(mfs, "entrega_comprobacion")
    assert v.sin_plazo_en_reglas and v.estado() in (plazos.SIN_PLAZO, plazos.SIN_FECHA)
    assert plazos.vencimiento(mfs, "aviso_caso_fortuito") is None              # MFS no prevé caso fortuito (R-17)
    _, (peg,) = contratadas("PEG")
    for uso in ("entrega_comprobacion", "fecha_limite_conclusion", "aviso_caso_fortuito", "interes_segunda_beneficiaria"):
        assert plazos.vencimiento(peg, uso) is None, uso
    assert plazos.vencimiento(mfs, "reporte_mensual") is None


def test_nucleo_peg_reporte_mensual_vence_al_fin_del_mes(contratadas):
    _, (peg,) = contratadas("PEG")
    with reloj.en("2026-08-27 10:00"):
        v = plazos.vencimiento(peg, "reporte_mensual", fecha_evento=_momento("2026-07-20 10:00"))
        assert str(v.vencimiento) == "2026-08-31" and v.decision_propia and v.estado() == "por vencer"


def test_nucleo_plazos_que_arrancan_con_un_hito_de_m6(contratadas, usuarios):
    _, (rhf,) = contratadas("RHF")
    plazos.registrar_hito(rhf, "siniestro", usuarios["del_amecameca"], _momento("2026-10-01 08:00"))
    assert str(plazos.vencimiento(rhf, "aviso_caso_fortuito").vencimiento) == "2026-10-22"      # 15 días hábiles
    plazos.registrar_hito(rhf, "fallecimiento_titular", usuarios["del_amecameca"], _momento("2026-10-01 08:00"))
    assert plazos.vencimiento(rhf, "interes_segunda_beneficiaria").plazo.cantidad == 30
    assert plazos.vencimiento(rhf, "subsanar_omisiones").vencimiento is None
    plazos.registrar_hito(rhf, "aviso_omision", usuarios["dir_drff"], _momento("2026-11-02 10:00"), datos={"vence": "2026-11-20"})
    v = plazos.vencimiento(rhf, "subsanar_omisiones")
    assert str(v.vencimiento) == "2026-11-20" and v.decision_propia                     # el plazo que fijó el área


def test_nucleo_revisar_plazos_avisa_antes_y_al_vencer_una_sola_vez_sin_cambiar_nada(contratadas):
    _, (cc,) = contratadas("CC")
    estado = cc.estado.clave
    with reloj.en("2026-11-09 07:00"):
        call_command("revisar_plazos")
        call_command("revisar_plazos")
    por_vencer = cc.eventos.filter(tipo="aviso_plazo", datos__uso="fecha_limite_conclusion", datos__situacion="por vencer")
    assert por_vencer.count() == 1 and por_vencer.get().usuario_id is None
    with reloj.en("2026-11-16 07:00"):
        assert avisos.revisar() >= 1
        assert avisos.revisar() == 0
    assert cc.eventos.filter(tipo="aviso_plazo", datos__uso="fecha_limite_conclusion", datos__situacion="vencido").count() == 1
    cc.refresh_from_db()
    assert cc.estado.clave == estado                                                   # P-08: solo aviso


def test_nucleo_panel_por_vencer_en_la_bandeja_de_cada_unidad(contratadas, usuarios, client, contrasena):
    _, (cc,) = contratadas("CC")
    with reloj.en("2026-11-10 09:00"):
        filas = avisos.por_vencer(usuarios["dir_drff"])
        assert [f["expediente"] for f in filas if f["vencimiento"].uso == "fecha_limite_conclusion"] == [cc]
        assert avisos.por_vencer(usuarios["juridica"]) == []
        assert avisos.por_vencer(usuarios["del_toluca"]) == []                      # otra Delegación no lo ve
        assert avisos.por_vencer(usuarios["dir_dpf"]) == []                         # otra Dirección tampoco
        client.login(username="del_amecameca", password=contrasena)
        html = client.get("/bandeja/").content.decode()
    assert 'data-prueba="panel-por-vencer"' in html and cc.folio in html


def test_nucleo_omisiones_por_subsanar_se_avisan_con_el_plazo_del_area(contratadas, usuarios):
    _, (ps,) = contratadas("PS")
    Expediente.objects.filter(pk=ps.pk).update(estado=Estado.objects.get(clave="omisiones_por_subsanar"))
    plazos.registrar_hito(ps, "aviso_omision", usuarios["dir_drff"], _momento("2026-11-02 10:00"), datos={"vence": "2026-11-12"})
    with reloj.en("2026-11-13 08:00"):
        avisos.revisar()
        assert [f["situacion"] for f in avisos.por_vencer(usuarios["del_amecameca"])
                if f["vencimiento"].uso == "subsanar_omisiones"] == ["vencido"]
