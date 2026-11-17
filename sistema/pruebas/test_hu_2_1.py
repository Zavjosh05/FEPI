"""HU-2.1 · Dictamen técnico (criterios tomados de especificacion/modelo.json)."""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management import call_command
from django.utils import timezone

from dictamen import juridico, tecnico
from dictamen.models import DictamenTecnico
from nucleo import dias_habiles
from nucleo.models import bandeja

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def test_hu_2_1_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-2.1")
    assert len(hu["criterios"]) == 3 and "45 días hábiles" in hu["criterios"][2]
    assert "M2.1" in modelo["necesidad_a_funciones"]["CC-ARP-02"]
    assert "análisis cartográfico" in necesidades["CC-ARP-02"]["texto"]


def test_hu_2_1_cada_solicitud_tiene_dictamen_tecnico_con_motivo(validada, usuarios):
    """Criterio 1: cada solicitud tiene un dictamen técnico factible o no factible, con su motivo."""
    exp = validada()
    with pytest.raises(ValidationError, match="motivo"):
        tecnico.dictaminar(usuarios["dir_drff"], exp, "factible", "  ")
    d = tecnico.dictaminar(usuarios["dir_drff"], exp, "no_factible", "Densidad arbolada menor a 60 %.")
    assert d.resultado == "no_factible" and d.motivo.startswith("Densidad")
    assert d.acuse.archivo.open("rb").read(4) == b"%PDF"
    assert exp.eventos.filter(tipo="dictamen_tecnico", acuse=d.acuse).exists()
    with pytest.raises(ValidationError, match="ya tiene"):
        tecnico.dictaminar(usuarios["dir_drff"], exp, "factible", "Otra vez")


def test_hu_2_1_lista_de_verificacion_sale_de_las_reglas(cc):
    items = tecnico.lista_verificacion(cc)
    datos = cc.datos
    assert sum(i["clave"].startswith("elegibilidad-") for i in items) == len(datos["criterios_elegibilidad_tecnica"])
    assert sum(i["clave"].startswith("inelegible-") for i in items) == len(datos["inelegibles"])
    assert sum(i["clave"].startswith("priorizacion-") for i in items) == len(datos["criterios_seleccion"])
    assert any(i["clave"] == "superficie" and "1 a 200 ha" in i["texto"] for i in items)


def test_hu_2_1_criterio_no_cumplido_impide_factible(validada, usuarios):
    exp = validada()
    with pytest.raises(ValidationError, match="no cumple"):
        tecnico.dictaminar(usuarios["dir_drff"], exp, "factible", "x", {"inelegible-6": {"respuesta": "no"}})
    d = tecnico.dictaminar(usuarios["dir_drff"], exp, "no_factible", "Área afectada por incendio",
                           {"inelegible-6": {"respuesta": "no", "nota": "Incendio 2026"}})
    assert next(i for i in d.verificacion if i["clave"] == "inelegible-6")["nota"] == "Incendio 2026"


def test_hu_2_1_no_se_dictamina_con_criterios_sin_revisar(validada, usuarios, client):
    """La lista de verificación llega sin marcar: desde la pantalla no se dictamina con criterios sin revisar."""
    exp = validada()
    revisables = [i for i in tecnico.lista_verificacion(exp.ejercicio) if not i.get("informativo")]
    with pytest.raises(ValidationError, match=f"Falta marcar {len(revisables)} criterios"):
        tecnico.dictaminar(usuarios["dir_drff"], exp, "factible", "Cumple", {}, exigir_revision=True)
    parcial = {revisables[0]["clave"]: {"respuesta": "si"}}
    with pytest.raises(ValidationError, match=f"Falta marcar {len(revisables) - 1} criterios"):
        tecnico.dictaminar(usuarios["dir_drff"], exp, "factible", "Cumple", parcial, exigir_revision=True)
    completa = {i["clave"]: {"respuesta": "si"} for i in revisables}
    d = tecnico.dictaminar(usuarios["dir_drff"], exp, "factible", "Cumple", completa, exigir_revision=True)
    assert d.resultado == "factible"
    # Por la pantalla: sin marcar no se registra; el formulario no trae ningún criterio preseleccionado.
    otro = validada(nombre="Otro predio")
    client.force_login(usuarios["dir_drff"])
    url = f"/dictamen/tecnico/{otro.folio}/"
    assert 'checked' not in client.get(url).content.decode().split("tabla-verificacion")[1].split("</table>")[0]
    cliente = client.post(url, {"resultado": "factible", "motivo": "Cumple"}, follow=True)
    assert "Falta marcar" in cliente.content.decode()
    assert not DictamenTecnico.objects.filter(expediente=otro).exists()


def test_hu_2_1_analisis_cartografico_con_postgis(validada, usuarios):
    primero = validada(municipio="Juchitepec", nombre="Predio A", ha=9)
    segundo = validada(municipio="Juchitepec", nombre="Predio B", ha=5, desplazamiento=(180, 120))
    analisis = tecnico.analisis_cartografico(segundo)
    assert analisis["tiene_poligono"] and abs(analisis["superficie_ha"] - 5) < 0.05
    assert analisis["ubicacion_municipio"] == "dentro" and analisis["superficie_en_rango"]
    assert [t["folio"] for t in analisis["traslapes"]] == [primero.folio]
    assert 0.5 < analisis["traslapes"][0]["superficie_ha"] < 2
    d = tecnico.dictaminar(usuarios["dir_drff"], segundo, "factible", "Se ajustará el traslape en campo")
    assert d.analisis["traslapes"] and abs(float(d.superficie_factible_ha) - 5) < 0.05


def test_hu_2_1_existe_listado_preliminar_con_resultado_tecnico_y_juridico(validada, usuarios, client, contrasena, cc):
    """Criterio 2: existe un listado preliminar con el resultado técnico y jurídico de cada solicitud."""
    a = validada(nombre="Predio Factible")
    b = validada(nombre="Predio No Factible", municipio="Tlalmanalco")
    c = validada(nombre="Predio Pendiente", municipio="Ozumba")
    tecnico.dictaminar(usuarios["dir_drff"], a, "factible", "Cumple")
    juridico.dictaminar(usuarios["juridica"], a, "procedente", "Documentación vigente")
    tecnico.dictaminar(usuarios["dir_drff"], b, "no_factible", "Bosque natural mayor al 30 %")
    from nucleo.models import expedientes_visibles
    filas = {f["folio"]: f for f in tecnico.listado_preliminar(cc, expedientes_visibles(usuarios["dir_drff"]))}
    assert filas[a.folio]["resultado"] == "factible" and filas[a.folio]["juridico"] == "Procedente"
    assert filas[b.folio]["resultado"] == "no_factible" and filas[b.folio]["juridico"] == "Pendiente"
    assert filas[c.folio]["resultado"] == "pendiente"
    client.login(username="dir_drff", password=contrasena)
    r = client.get(f"/dictamen/listado/?ejercicio={cc.pk}&formato=csv")
    texto = r.content.decode("utf-8")
    assert r["Content-Type"].startswith("text/csv") and texto.startswith("﻿Folio,")
    assert a.folio in texto and "Bosque natural mayor al 30 %" in texto
    assert client.get("/dictamen/listado/").status_code == 200


def test_hu_2_1_peg_dictamen_dentro_de_45_dias_habiles(peg, usuarios):
    """Criterio 3: en PEG, el dictamen existe dentro de los 45 días hábiles (plazo de los datos del programa)."""
    exp = registrar_peg(usuarios, peg, nombre="Guardabosque Ejido San Juan")
    limite, plazo = tecnico.fecha_limite_dictamen(exp)
    assert plazo.cantidad == 45 and plazo.unidad == "dias_habiles"
    assert limite == dias_habiles.sumar_dias_habiles(exp.fecha_recepcion, 45)
    assert tecnico.situacion_plazo(exp)["situacion"] == "en_plazo"
    assert tecnico.situacion_plazo(exp, hoy=limite - timedelta(days=1))["situacion"] == "por_vencer"
    d = tecnico.dictaminar(usuarios["dir_dpf"], exp, "factible", "Cumple los criterios del PEG")
    assert d.dentro_de_plazo is True and d.fecha_limite == limite
    exp.refresh_from_db()
    assert tecnico.situacion_plazo(exp)["situacion"] == "cumplido"


def test_hu_2_1_peg_dictamen_fuera_de_plazo_queda_senalado(peg, usuarios):
    exp = registrar_peg(usuarios, peg, nombre="Guardabosque Tardío")
    exp.fecha_recepcion = timezone.now() - timedelta(days=120)
    exp.save()
    assert tecnico.situacion_plazo(exp)["situacion"] == "vencido"
    call_command("revisar_plazos")
    call_command("revisar_plazos")
    assert exp.eventos.filter(tipo="plazo_dictamen_vencido").count() == 1
    d = tecnico.dictaminar(usuarios["dir_dpf"], exp, "factible", "Se dictamina fuera de plazo")
    assert d.dentro_de_plazo is False
    exp.refresh_from_db()
    assert tecnico.situacion_plazo(exp)["situacion"] == "fuera_de_plazo"


def test_hu_2_1_peg_por_vencer_se_avisa(peg, usuarios):
    exp = registrar_peg(usuarios, peg, nombre="Guardabosque Por Vencer")
    limite, _ = tecnico.fecha_limite_dictamen(exp)
    assert tecnico.revisar_plazos_dictamen(limite - timedelta(days=1)) == 1
    assert exp.eventos.filter(tipo="plazo_dictamen_por_vencer").exists()


def test_hu_2_1_solo_la_direccion_del_programa_dictamina(validada, usuarios):
    exp = validada()
    with pytest.raises(PermissionDenied):
        tecnico.dictaminar(usuarios["juridica"], exp, "factible", "x")
    with pytest.raises(PermissionDenied):
        tecnico.dictaminar(usuarios["dir_dpf"], exp, "factible", "x")   # DPF no es Instancia Ejecutora de CC


def test_hu_2_1_bandeja_de_la_direccion_y_paso_a_dictaminada(validada, usuarios):
    exp = validada()
    assert exp in bandeja(usuarios["dir_drff"]) and exp in bandeja(usuarios["juridica"])
    tecnico.dictaminar(usuarios["dir_drff"], exp, "factible", "Cumple")
    assert exp not in bandeja(usuarios["dir_drff"]) and exp in bandeja(usuarios["juridica"])
    juridico.dictaminar(usuarios["juridica"], exp, "procedente", "Vigente")
    exp.refresh_from_db()
    assert exp.estado.clave == "dictaminada" and exp in bandeja(usuarios["comite"])
    assert exp.eventos.filter(tipo="dictaminada").exists()


def test_hu_2_1_pantalla_de_dictamen_tecnico(validada, client, contrasena):
    exp = validada()
    client.login(username="dir_drff", password=contrasena)
    r = client.get(f"/dictamen/tecnico/{exp.folio}/")
    assert r.status_code == 200 and "Lista de verificación" in r.content.decode()
    assert client.get(f"/dictamen/tecnico/{exp.folio}/mapa.json").json()["poligonos"]["features"]
    marcas = {f"v-{i['clave']}": "si" for i in tecnico.lista_verificacion(exp.ejercicio) if not i.get("informativo")}
    r = client.post(f"/dictamen/tecnico/{exp.folio}/", {"resultado": "factible", "motivo": "Cumple", **marcas})
    assert r.status_code == 302 and DictamenTecnico.objects.filter(expediente=exp).exists()
    r = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=dictamenes")
    assert "Dictamen técnico" in r.content.decode()
