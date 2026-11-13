"""Núcleo: carga de catálogos y de reglas desde JSON (nada de requisitos ni plazos en el código)."""
import json

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

from nucleo.catalogos import cargar_delegaciones, cargar_reglas_programa, leer_json
from nucleo.models import (
    DiaInhabil, Ejercicio, Estado, Municipio, Plazo, Programa, Requisito, TipoUnidad, Transicion, Unidad,
)

pytestmark = pytest.mark.django_db


def test_nucleo_carga_de_reglas_de_cc_coincide_con_el_archivo(cc):
    datos = leer_json(settings.REGLAS_DIR / "CC.json")
    assert cc.requisitos.count() == len(datos["requisitos"])
    assert cc.plazos.count() == len(datos["plazos"])
    assert cc.tipos_persona.count() == len(datos["tipos_persona"])
    assert cc.formatos.count() == len(datos["formatos"])
    for r in datos["requisitos"]:
        req = cc.requisitos.get(clave=r["clave"])
        assert req.es_documento_legal == bool(r.get("es_documento_legal"))
        assert req.aplica_en_refrendo == r.get("aplica_en_refrendo")
        assert sorted(req.tipos_persona.values_list("clave", flat=True)) == sorted(r["tipos_persona"])


def test_nucleo_plazos_admiten_cantidad_nula_y_unidades_no_calculables(cc):
    faltantes = cc.plazo("complemento_documentacion_faltante")
    assert (faltantes.cantidad, faltantes.unidad, faltantes.es_calculable) == (5, "dias_habiles", True)
    recepcion = cc.plazo("recepcion_solicitudes")
    assert recepcion.cantidad is None and not recepcion.es_calculable
    assert recepcion.fecha_fin is not None
    vigencia = cc.plazo("vigencia_documentacion_legal_refrendo")
    assert (vigencia.cantidad, vigencia.unidad) == (3, "anios")


def test_nucleo_carga_de_reglas_es_idempotente(cc):
    antes = (Requisito.objects.count(), Plazo.objects.count())
    cargar_reglas_programa(settings.REGLAS_DIR / "CC.json")
    call_command("cargar_reglas")
    assert (Requisito.objects.count(), Plazo.objects.count()) == antes


def test_nucleo_carga_de_reglas_actualiza_lo_que_cambia_en_el_archivo(cc, tmp_path):
    datos = leer_json(settings.REGLAS_DIR / "CC.json")
    for p in datos["plazos"]:
        if p["clave"] == "complemento_documentacion_faltante":
            p["cantidad"] = 7
    ruta = tmp_path / "CC.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    cargar_reglas_programa(ruta)
    assert cc.plazo("complemento_documentacion_faltante").cantidad == 7


def test_nucleo_seis_programas_en_el_catalogo_y_solo_cc_con_reglas(catalogos):
    assert set(Programa.objects.values_list("clave", flat=True)) == {"CC", "MFS", "PS", "RHF", "PSA", "PEG"}
    con_reglas = set(Ejercicio.objects.filter(reglas_cargadas__isnull=False).values_list("programa__clave", flat=True))
    assert "CC" in con_reglas
    assert not Programa.objects.get(clave="PEG").usa_poligono


def test_nucleo_municipios_empatan_con_las_delegaciones_de_la_convocatoria(catalogos):
    catalogo = leer_json(settings.REGLAS_DIR / "catalogos.json")
    assert Municipio.objects.count() == 125
    assert not Municipio.objects.filter(delegacion__isnull=True).exists()
    for d in catalogo["delegaciones"]:
        assert Municipio.objects.filter(delegacion__clave=d["clave"]).count() == len(d["municipios"])
    assert Municipio.objects.get(nombre="Acambay de Ruíz Castañeda").delegacion.clave == "ATLACOMULCO"
    assert Municipio.objects.get(nombre="Tultitlán").delegacion.clave == "NAUCALPAN"
    assert Unidad.objects.filter(tipo=TipoUnidad.DELEGACION).count() == 9
    assert not Unidad.objects.filter(tipo=TipoUnidad.DELEGACION, asignacion_confirmada=True).exists()


def test_nucleo_municipio_que_no_empata_da_error_claro(catalogos):
    catalogo = leer_json(settings.REGLAS_DIR / "catalogos.json")
    catalogo["delegaciones"][0]["municipios"].append("Municipio Inexistente")
    with pytest.raises(CommandError, match="Municipio Inexistente"):
        cargar_delegaciones(catalogo)


def test_nucleo_estados_transiciones_y_calendario_vienen_de_datos(catalogos):
    assert Estado.objects.filter(clave__in=["recibida", "enviada_direccion", "faltantes", "validada",
                                            "no_factible", "desechada"]).count() == 6
    assert Estado.objects.get(clave="faltantes").flujo_alterno == "A"
    assert Estado.objects.get(clave="no_factible").flujo_alterno == "B"
    assert Transicion.objects.count() >= 8
    assert DiaInhabil.objects.filter(fecha__year=2026).count() >= 7


def test_nucleo_cargar_catalogos_es_idempotente(catalogos):
    antes = (Municipio.objects.count(), Unidad.objects.count(), Transicion.objects.count())
    call_command("cargar_catalogos")
    assert (Municipio.objects.count(), Unidad.objects.count(), Transicion.objects.count()) == antes
