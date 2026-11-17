"""HU-7.5 «Especies por municipio» (CF-DEV-05 de las Tablas de necesidades v12).

Criterio 1: cada municipio tiene su lista de especies registradas, con el periodo del inventario.
Criterio 2: un municipio sin registros queda señalado.

Los datos salen del INFyS 2015-2020 de CONAFOR (datos/edomex/infys/*.csv, que git no versiona; ver su
LEEME.md). Aquí se compara docs/calculadora/datos/especies.json con esos CSV (se omite la comparación si
no están en el equipo) y se prueba lo que muestra la página en Chromium sin interfaz.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from conftest import ARCHIVO_UNICO, DATOS, RAIZ, Registro, captura, esperar_lista

CAPTURAS_S3 = RAIZ / "entregas" / "sprint_3" / "capturas"
INFYS = RAIZ / "datos" / "edomex" / "infys"
FUENTE = "Inventario Nacional Forestal y de Suelos 2015–2020 (CONAFOR)"
ENCABEZADO = FUENTE + "; muestreo en una malla de 5 km: es la lista de lo registrado, no un inventario completo"
CON, SIN_ARBOL, SIN_CGL = "con_registros", "conglomerado_sin_arbolado", "sin_conglomerado"
MUNI_CON, MUNI_SIN_ARBOL, MUNI_SIN_CGL = "Luvianos", "Apaxco", "Acolman"


def _esp():
    return json.loads((DATOS / "especies.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def esp():
    return _esp()


@pytest.fixture(scope="module")
def csv_arbolado():
    if not (INFYS / "arbolado_edomex_2015_2020.csv").exists():
        pytest.skip("falta datos/edomex/infys (ver su LEEME.md)")
    return pd.read_csv(INFYS / "arbolado_edomex_2015_2020.csv")


@pytest.fixture(scope="module")
def csv_cobertura():
    if not (INFYS / "cobertura_municipios_2015_2020.csv").exists():
        pytest.skip("falta datos/edomex/infys (ver su LEEME.md)")
    return pd.read_csv(INFYS / "cobertura_municipios_2015_2020.csv")


def _elegir(page, muni):
    page.fill("#buscar", muni)
    page.dispatch_event("#buscar", "change")
    page.wait_for_function("n => document.getElementById('especies-titulo')?.textContent.endsWith(n) && document.getElementById('cargando').hidden",
                           arg=muni, timeout=20_000)


def _vista_inventario(page):
    page.get_by_role("radio", name="Inventario forestal", exact=True).click()
    page.wait_for_function("document.getElementById('mapa').classList.contains('vista-coropleta') && document.querySelectorAll('#mapa .u.i-con').length > 0",
                           timeout=20_000)


# ------------------------------------------------ Criterio 1: lista por municipio, con periodo

def test_hu_7_5_los_125_municipios_estan_con_su_situacion(esp, indice, csv_cobertura):
    assert len(esp["municipios"]) == 125
    assert {m: r["situacion"] for m, r in esp["municipios"].items()} == dict(zip(csv_cobertura["NOM_MUN"], csv_cobertura["estado"]))
    cuenta = pd.Series([r["situacion"] for r in esp["municipios"].values()]).value_counts().to_dict()
    assert cuenta == {CON: 55, SIN_ARBOL: 20, SIN_CGL: 50}
    assert esp["resumen"]["situacion"] == cuenta
    assert indice["inventario"]["resumen"]["situacion"] == cuenta
    assert "especies.json" in indice["archivos"]


def test_hu_7_5_los_municipios_son_los_de_la_pagina(esp):
    topo = json.loads((DATOS / "municipios.topojson").read_text(encoding="utf-8"))
    nombres = {g["properties"]["nombre"] for g in topo["objects"]["municipios"]["geometries"]}
    assert set(esp["municipios"]) == nombres and len(nombres) == 125


def test_hu_7_5_las_cuentas_por_municipio_coinciden_con_los_csv(esp, csv_arbolado):
    por_muni = {m: g for m, g in csv_arbolado.groupby("municipio")}
    assert set(por_muni) == {m for m, r in esp["municipios"].items() if r["situacion"] == CON}
    for muni, g in por_muni.items():
        r = esp["municipios"][muni]
        sp = g[g["nivel"] == "especie"]
        assert r["arboles"] == len(g)
        assert r["a_especie"] == len(sp) and r["solo_genero"] == int((g["nivel"] == "genero").sum())
        assert r["sin_identificar"] == int((g["nivel"] == "desconocido").sum())
        assert r["cgl"][2] == g["id_conglomerado"].nunique()
        assert r["anios"] == sorted(g["anio"].unique().tolist())
        assert {f[0]: (f[4], f[5]) for f in r["especies"]} == {
            e: (len(x), x["id_conglomerado"].nunique()) for e, x in sp.groupby("especie")}, muni
        assert sum(f[4] for f in r["especies"]) == len(sp)
        assert sum(f[4] for f in r["generos"]) == r["solo_genero"]
        # ordenadas por número de árboles, de más a menos
        n = [f[4] for f in r["especies"]]
        assert n == sorted(n, reverse=True)


def test_hu_7_5_las_cuentas_coinciden_con_el_csv_de_especies_por_municipio(esp):
    ruta = INFYS / "especies_por_municipio_2015_2020.csv"
    if not ruta.exists():
        pytest.skip("falta datos/edomex/infys")
    e = pd.read_csv(ruta)
    pub = {(m, f[0]): (f[4], f[5]) for m, r in esp["municipios"].items() if r["situacion"] == CON
           for f in r["especies"] + r["generos"]}
    ref = {(r["municipio"], r["especie"]): (r["n_registros"], r["n_conglomerados"]) for _, r in e.iterrows()}
    assert pub == ref


def test_hu_7_5_los_totales_del_estado(esp, csv_arbolado):
    r = esp["resumen"]
    assert r["arboles"] == len(csv_arbolado) == 10391
    assert r["especies_distintas"] == csv_arbolado.loc[csv_arbolado["nivel"] == "especie", "especie"].nunique() == 139
    assert 0.55 < r["pct_a_especie"] < 0.57  # poco más de la mitad llega a especie
    assert esp["periodo"] == "2015–2020" and esp["anios_campo"] == [2015, 2016, 2018, 2019]


def test_hu_7_5_un_municipio_con_registros_muestra_su_lista(abrir, esp):
    page, reg = abrir()
    _elegir(page, MUNI_CON)
    r = esp["municipios"][MUNI_CON]
    filas = page.eval_on_selector_all("#tabla-especies tbody tr", "rs => rs.map(r => [...r.cells].map(c => c.textContent))")
    assert len(filas) == len(r["especies"]) > 5
    ref = r["especies"][0]
    assert filas[0][0] == ref[0] and filas[0][2] == ref[2] and filas[0][3] == f"{ref[4]:,}"
    assert [int(f[3].replace(",", "")) for f in filas] == sorted((int(f[3].replace(",", "")) for f in filas), reverse=True)
    assert f"{r['arboles']:,}" in page.locator("#especies-resumen").inner_text()
    # lo identificado solo a género va aparte y rotulado así
    assert "Identificado solo a género" in page.locator("#generos-titulo").inner_text()
    generos = page.eval_on_selector_all("#tabla-generos tbody tr", "rs => rs.map(r => r.cells[0].textContent)")
    assert generos == [f[0] for f in r["generos"]]
    assert not set(generos) & {f[0] for f in r["especies"]}
    assert reg.errores == [], reg.errores


def test_hu_7_5_el_periodo_y_la_fuente_aparecen(abrir):
    page, _ = abrir()
    # sin elegir municipio ya están a la vista
    fuente = page.locator("#especies-fuente").inner_text()
    assert ENCABEZADO in fuente
    assert "Poco más de la mitad" in fuente
    _elegir(page, MUNI_CON)
    assert ENCABEZADO in page.locator("#especies-fuente").inner_text()
    resumen = page.locator("#especies-resumen").inner_text()
    assert "2015" in resumen and "2019" in resumen
    pie = page.locator("#especies .atribucion").inner_text()
    assert "CONAFOR" in pie and "2015–2020" in pie and "licencia" in pie and "por confirmar" in pie
    assert page.locator("#especies-titulo").inner_text().startswith("Especies registradas en el inventario")


# ------------------------------------------------ Criterio 2: sin registros, señalado

def test_hu_7_5_un_conglomerado_sin_arbolado_dice_sin_registros_y_su_tipo(abrir, esp):
    assert esp["municipios"][MUNI_SIN_ARBOL]["situacion"] == SIN_ARBOL
    page, _ = abrir()
    _elegir(page, MUNI_SIN_ARBOL)
    t = page.locator("#especies-sin-registros").inner_text()
    assert "Sin registros en el inventario" in t
    assert "Conglomerado sin arbolado" in t
    assert "sin especies" not in t.lower()
    assert page.locator("#tabla-especies").count() == 0


def test_hu_7_5_un_municipio_sin_conglomerado_dice_sin_registros_y_su_tipo(abrir, esp):
    assert esp["municipios"][MUNI_SIN_CGL]["situacion"] == SIN_CGL
    page, _ = abrir()
    _elegir(page, MUNI_SIN_CGL)
    t = page.locator("#especies-sin-registros").inner_text()
    assert "Sin registros en el inventario" in t
    assert "no cayó ningún conglomerado" in t
    assert "sin especies" not in t.lower()
    assert page.locator("#tabla-especies").count() == 0


def test_hu_7_5_todo_municipio_sin_registros_se_senala(abrir, esp):
    """Los 70 municipios sin registros dicen «Sin registros en el inventario» y ninguno trae lista."""
    page, _ = abrir()
    sin = [m for m, r in esp["municipios"].items() if r["situacion"] != CON]
    assert len(sin) == 70
    for muni in sin[::7]:  # una muestra repartida; la regla es la misma para todos
        _elegir(page, muni)
        assert "Sin registros en el inventario" in page.locator("#especies").inner_text(), muni
    for r in esp["municipios"].values():
        assert (r["situacion"] == CON) == ("especies" in r)


def test_hu_7_5_la_vista_del_mapa_muestra_la_cobertura_con_sus_conteos(abrir, esp):
    page, reg = abrir()
    assert not [u for u in reg.datos(page.url) if u == "especies.json"]  # no se pide al abrir
    _vista_inventario(page)
    assert "especies.json" in reg.datos(page.url)
    clases = page.eval_on_selector_all("#mapa .u", "us => us.map(u => [...u.classList].find(c => c.startsWith('i-')))")
    assert {k: clases.count(k) for k in ("i-con", "i-cgl", "i-sin")} == {"i-con": 55, "i-cgl": 20, "i-sin": 50}
    leyenda = page.eval_on_selector_all("#leyenda li", "ls => ls.map(l => l.textContent)")
    assert [x for x in leyenda if "Con registros" in x][0].endswith("55")
    assert [x for x in leyenda if "Conglomerado sin arbolado" in x][0].endswith("20")
    assert [x for x in leyenda if "Sin conglomerado" in x][0].endswith("50")
    assert "Inventario forestal 2015–2020" in page.locator("#leyenda-titulo").inner_text()
    assert "licencia" in page.locator("#nota-mapa").inner_text()
    assert reg.errores == [], reg.errores


def test_hu_7_5_la_vista_funciona_tambien_en_el_modo_un_anio(abrir):
    page, reg = abrir()
    page.click("#modos button[data-modo=anio]")
    page.wait_for_function("document.getElementById('cargando').hidden")
    _vista_inventario(page)
    assert page.locator("#mapa .u.i-sin").count() == 50
    assert reg.errores == [], reg.errores


# ------------------------------------------------ Datos publicados y carga

def test_hu_7_5_el_archivo_publicado_no_trae_registros_por_arbol_ni_coordenadas(esp, csv_arbolado):
    texto = (DATOS / "especies.json").read_text(encoding="utf-8")
    prohibidas = {"lon", "lat", "longitud", "latitud", "id_conglomerado", "coordenadas", "x", "y"}

    def claves(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from claves(v)
        elif isinstance(o, list):
            for v in o:
                yield from claves(v)
    assert not prohibidas & {k.lower() for k in claves(esp)}
    # Ninguna coordenada ni identificador de conglomerado del CSV de árboles aparece en lo publicado
    for col in ("lon", "lat", "id_conglomerado"):
        for v in csv_arbolado[col].drop_duplicates().astype(str).head(150):
            for archivo in (texto, (DATOS / "indice.json").read_text(encoding="utf-8")):
                assert f'"{v}"' not in archivo and f",{v}," not in archivo, (col, v)
    # Cada fila es un agregado (especie, común, familia, género, árboles, conglomerados), no un árbol
    for r in esp["municipios"].values():
        for f in r.get("especies", []) + r.get("generos", []):
            assert len(f) == 6 and f[4] >= 1 and f[5] >= 1
    assert len(texto) < 150_000  # un agregado por municipio, no 10,391 registros


def test_hu_7_5_las_especies_se_piden_solo_al_consultarlas(abrir):
    page, reg = abrir()
    assert "especies.json" not in reg.datos(page.url)
    _elegir(page, MUNI_CON)
    assert reg.datos(page.url).count("especies.json") == 1
    _elegir(page, MUNI_SIN_ARBOL)
    assert reg.datos(page.url).count("especies.json") == 1  # una sola vez


def test_hu_7_5_una_falla_al_cargar_las_especies_se_avisa(abrir, page):
    page.route("**/datos/especies.json", lambda r: r.fulfill(status=404, body="no"))
    page, _ = abrir()
    page.fill("#buscar", MUNI_CON)
    page.dispatch_event("#buscar", "change")
    page.wait_for_selector("#falla:not([hidden])", timeout=20_000)
    assert "No se pudieron cargar los datos" in page.locator("#falla").inner_text()
    assert "especies.json" in page.locator("#falla").inner_text()


def test_hu_7_5_el_archivo_unico_trae_las_especies_embebidas(browser, esp):
    page = browser.new_page(viewport={"width": 1366, "height": 900}, locale="es-MX")
    reg = Registro(page)
    page.goto(ARCHIVO_UNICO.as_uri())
    esperar_lista(page)
    _elegir(page, MUNI_CON)
    filas = page.eval_on_selector_all("#tabla-especies tbody tr", "rs => rs.length")
    assert filas == len(esp["municipios"][MUNI_CON]["especies"])
    assert ENCABEZADO in page.locator("#especies-fuente").inner_text()
    assert not [u for u in reg.peticiones if "/datos/" in u]
    assert reg.errores == [], reg.errores
    page.close()


def test_hu_7_5_el_generador_falla_con_claro_si_un_municipio_no_empata():
    import sys
    sys.path.insert(0, str(RAIZ / "src"))
    import especies_infys
    with pytest.raises(SystemExit) as e:
        especies_infys.empatar(["Luvianos", "Municipio Inexistente"], ["Luvianos", "Acolman"])
    assert "Municipio Inexistente" in str(e.value)
    # Acentos y mayúsculas distintos sí empatan
    assert especies_infys.empatar(["ACAMBAY DE RUIZ CASTANEDA"], ["Acambay de Ruíz Castañeda"]) == {
        "ACAMBAY DE RUIZ CASTANEDA": "Acambay de Ruíz Castañeda"}


# ------------------------------------------------ Capturas

def test_hu_7_5_capturas(browser, servidor):
    if os.environ.get("CAPTURAS") == "1":
        CAPTURAS_S3.mkdir(parents=True, exist_ok=True)
    for tema, ancho, alto, sufijo in [("light", 1366, 900, ""), ("dark", 1366, 900, "_oscuro"), ("light", 375, 812, "_movil")]:
        ctx = browser.new_context(viewport={"width": ancho, "height": alto}, color_scheme=tema, locale="es-MX",
                                  is_mobile=ancho < 500, device_scale_factor=2 if ancho < 500 else 1)
        page = ctx.new_page()
        reg = Registro(page)
        page.goto(servidor)
        esperar_lista(page)
        _elegir(page, MUNI_CON)
        page.wait_for_timeout(300)
        captura(page.locator("#detalle"), CAPTURAS_S3 / f"hu_7_5_detalle_con_registros{sufijo}.png")
        _elegir(page, MUNI_SIN_CGL)
        page.wait_for_timeout(300)
        captura(page.locator("#detalle"), CAPTURAS_S3 / f"hu_7_5_detalle_sin_registros{sufijo}.png")
        _vista_inventario(page)
        page.wait_for_timeout(500)
        captura(page.locator(".principal"), CAPTURAS_S3 / f"hu_7_5_vista_cobertura{sufijo}.png")
        if ancho < 500:
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "scroll horizontal en móvil"
        assert reg.errores == [], reg.errores
        ctx.close()
