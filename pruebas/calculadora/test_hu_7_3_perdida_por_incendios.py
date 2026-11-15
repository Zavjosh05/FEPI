"""HU-7.3 «Pérdida por incendios» (CF-DEV-03 de las Tablas de necesidades v12).

Criterio 1: cada incendio tiene su ubicación y su fecha.
Criterio 2: existe la pérdida por incendio en hectáreas, por año y por municipio.
Criterio 3: un año que CONAFOR no ha publicado queda señalado (y no se presenta como cero).

Los datos de cada incendio salen de resultados/edomex_serie_2023_2025/incendios_dnbr*.csv y de los
polígonos de CONAFOR (datos/edomex/incendios_conafor_edomex.gpkg); aquí se leen los archivos
docs/calculadora/datos/incendios/<periodo>.json y la página en Chromium sin interfaz.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from conftest import ARCHIVO_UNICO, CAPTURAS_S2, DATOS, SERIE, Registro, captura, esperar_lista

N_MUNICIPIOS = 125
ULTIMO_CONAFOR = 2024


def _leer(ruta):
    return json.loads((DATOS / ruta).read_text(encoding="utf-8"))


def _csv(c):
    """Incendios de la comparación `c` según los CSV de la corrida (vacío si no hay)."""
    if c["preliminar"]:
        return pd.DataFrame(columns=["incendio", "fecha_inicio", "poligono_ha", "quemado_dnbr_ha",
                                     "quemado_en_bosque_ha", "perdido_al_cierre_ha"])
    largo = SERIE / f"incendios_dnbr_{c['clave']}.csv"
    if largo.exists():
        return pd.read_csv(largo)
    i = pd.read_csv(SERIE / "incendios_dnbr.csv")
    return i[i["periodo"].astype(str) == c["clave"]]


def _elegir_par(page, c):
    page.select_option("#hasta", str(c["actual"]))
    page.select_option("#desde", str(c["base"]))
    etiqueta = c["etiqueta"] + (" (preliminar)" if c["preliminar"] else "")
    page.wait_for_function(
        "e => document.getElementById('incendios-titulo')?.textContent.includes(e) && document.getElementById('cargando').hidden",
        arg=etiqueta, timeout=30_000)


def _vista_incendios(page):
    page.get_by_role("radio", name="Incendios", exact=True).click()
    page.wait_for_function("() => document.getElementById('cargando').hidden && document.querySelector('#vistas [data-vista=incendios]').getAttribute('aria-checked') === 'true'", timeout=30_000)


def _abrir_tabla(page):
    page.locator("#inc-abrir").click()
    page.wait_for_function("() => document.querySelector('#tabla-incendios tbody') !== null && document.getElementById('cargando').hidden", timeout=30_000)


@pytest.fixture(scope="module")
def comparaciones(indice):
    return indice["comparaciones"]


# ------------------------------------------------ Criterio 1: ubicación y fecha de cada incendio

def test_hu_7_3_cada_incendio_tiene_ubicacion_y_fecha(indice, comparaciones):
    for c in comparaciones:
        d = _leer(f"incendios/{c['id']}.json")
        assert f"incendios/{c['id']}.json" in indice["archivos"]
        idx = {k: i for i, k in enumerate(d["campos"])}
        esperado = _csv(c)
        assert d["sin_ubicacion"] == 0
        assert len(d["lista"]) == len(esperado), c["id"]
        assert {r[idx["clave"]] for r in d["lista"]} == set(esperado["incendio"]), c["id"]
        fechas = esperado.set_index("incendio")["fecha_inicio"]
        for r in d["lista"]:
            assert r[idx["fecha"]] == fechas[r[idx["clave"]]]
            assert 0 <= r[idx["px"]] <= indice["ancho"] and 0 <= r[idx["py"]] <= indice["alto"], r
            assert -101 < r[idx["lon"]] < -98 and 18 < r[idx["lat"]] < 20.5, r  # Estado de México
            assert r[idx["municipio"]], r


def test_hu_7_3_las_coordenadas_de_la_malla_coinciden_con_lon_lat(indice, comparaciones):
    """px, py y lon/lat son el mismo punto: se pasa lon/lat a la malla y se compara."""
    from pyproj import Transformer
    m = indice["malla"]
    t = Transformer.from_crs(4326, m["crs"], always_xy=True)
    c = next(x for x in comparaciones if x["id"] == "2023_2024")
    d = _leer(f"incendios/{c['id']}.json")
    idx = {k: i for i, k in enumerate(d["campos"])}
    for r in d["lista"][:200]:
        x, y = t.transform(r[idx["lon"]], r[idx["lat"]])
        assert (x - m["izq"]) / m["tam"] == pytest.approx(r[idx["px"]], abs=0.6)
        assert (m["arriba"] - y) / m["tam"] == pytest.approx(r[idx["py"]], abs=0.6)


def test_hu_7_3_municipios_de_los_incendios_son_los_de_la_pagina(indice, comparaciones):
    nombres = set(_leer("comparaciones/2023_2024.json")["filas"])
    assert len(nombres) == N_MUNICIPIOS
    for c in comparaciones:
        d = _leer(f"incendios/{c['id']}.json")
        idx = {k: i for i, k in enumerate(d["campos"])}
        assert {r[idx["municipio"]] for r in d["lista"]} <= nombres


def test_hu_7_3_el_mapa_dibuja_un_punto_por_incendio_con_su_globo(abrir, comparaciones):
    c = next(x for x in comparaciones if x["id"] == "2023_2024")
    d = _leer(f"incendios/{c['id']}.json")
    idx = {k: i for i, k in enumerate(d["campos"])}
    page, reg = abrir()
    _elegir_par(page, c)
    _vista_incendios(page)
    claves = page.eval_on_selector_all("circle.punto-inc", "cs => cs.map(c => c.dataset.clave)")
    assert sorted(claves) == sorted(r[idx["clave"]] for r in d["lista"])
    # El globo trae clave, fecha, municipio y hectáreas
    r = max(d["lista"], key=lambda x: x[idx["en_bosque_ha"]])
    # Pasa el cursor por un punto que quede encima (los demás lo pueden tapar)
    page.locator("#mapa").scroll_into_view_if_needed()
    centro = page.evaluate("""() => {
        for (const c of document.querySelectorAll("circle.punto-inc")) {
            const b = c.getBoundingClientRect(), x = b.x + b.width / 2, y = b.y + b.height / 2;
            if (b.width > 3 && x > 0 && y > 0 && x < innerWidth && y < innerHeight && document.elementFromPoint(x, y) === c) return [c.dataset.clave, x, y];
        }
        return null;
    }""")
    assert centro, "ningún punto visible"
    page.mouse.move(centro[1] - 3, centro[2] - 3)
    page.mouse.move(centro[1], centro[2])
    globo = page.locator("#globo")
    globo.wait_for(state="visible")
    texto = globo.inner_text()
    r = next(x for x in d["lista"] if x[idx["clave"]] == centro[0])
    assert r[idx["clave"]] in texto and r[idx["fecha"]] in texto and r[idx["municipio"]] in texto
    assert f"{r[idx['poligono_ha']]:,.1f}" in texto and f"{r[idx['en_bosque_ha']]:,.1f}" in texto
    # Tamaño por superficie quemada en bosque: el mayor incendio tiene el punto más grande
    r = max(d["lista"], key=lambda x: x[idx["en_bosque_ha"]])
    radios = page.eval_on_selector_all("circle.punto-inc", "cs => cs.map(c => [c.dataset.clave, Number(c.getAttribute('r'))])")
    assert max(radios, key=lambda x: x[1])[0] == r[idx["clave"]]
    assert reg.errores == [], reg.errores


def test_hu_7_3_los_datos_de_incendios_solo_se_piden_al_consultarlos(abrir, comparaciones, servidor):
    page, reg = abrir()
    assert not [u for u in reg.datos(servidor) if u.startswith("incendios/")], "no deben pedirse al abrir"
    c = next(x for x in comparaciones if x["id"] == "2023_2024")
    _elegir_par(page, c)
    assert not [u for u in reg.datos(servidor) if u.startswith("incendios/")]
    _vista_incendios(page)
    pedidos = [u for u in reg.datos(servidor) if u.startswith("incendios/")]
    assert pedidos == ["incendios/2023_2024.json"], pedidos


# ------------------------------------------- Tabla ordenable de incendios

def test_hu_7_3_tabla_de_incendios_ordenable(abrir, comparaciones):
    c = next(x for x in comparaciones if x["id"] == "2023_2024")
    esperado = _csv(c)
    page, reg = abrir()
    _elegir_par(page, c)
    _abrir_tabla(page)
    filas = page.locator("#tabla-incendios tbody tr")
    assert filas.count() == len(esperado)
    cab = page.eval_on_selector_all("#tabla-incendios th button", "bs => bs.map(b => b.textContent)")
    assert cab == ["Fecha", "Municipio", "Reportadas (ha)", "Quemadas en bosque (ha)", "Sin copa al cierre (ha)", "Clave"]

    def columna(n):
        return page.eval_on_selector_all(f"#tabla-incendios tbody tr td:nth-child({n})", "ts => ts.map(t => t.textContent)")

    page.locator("#tabla-incendios th[data-c=fecha] button").click()  # ascendente
    fechas = columna(1)
    assert fechas == sorted(fechas) and fechas[0] == esperado["fecha_inicio"].min()
    page.locator("#tabla-incendios th[data-c=fecha] button").click()  # descendente
    assert columna(1) == sorted(fechas, reverse=True)
    page.locator("#tabla-incendios th[data-c=en_bosque_ha] button").click()
    asc = [float(x.replace(",", "")) for x in columna(4)]
    assert asc == sorted(asc, reverse=True) or asc == sorted(asc)
    assert page.locator("#tabla-incendios th[aria-sort]").get_attribute("data-c") == "en_bosque_ha"
    # La suma de «sin copa al cierre» es la del resumen del periodo (redondeos de 1 decimal por renglón)
    sin_copa = sum(float(x.replace(",", "")) for x in columna(5))
    assert sin_copa == pytest.approx(esperado["perdido_al_cierre_ha"].sum(), abs=0.05 * len(esperado))
    assert reg.errores == [], reg.errores


# ------------------------------------------- Criterio 2: pérdida por incendio por año y municipio

def test_hu_7_3_perdida_por_incendio_por_periodo_y_municipio_en_los_datos(comparaciones):
    """Cada periodo trae la pérdida por incendio del Estado y de cada municipio (balance de resultados/)."""
    for c in comparaciones:
        d = _leer(f"comparaciones/{c['id']}.json")
        assert len(d["filas"]) == N_MUNICIPIOS
        assert d["tot"]["inc"] == pytest.approx(sum(f[d["campos"].index("inc")] for f in d["filas"].values()), abs=1)
    # Lo de la lista coincide con lo del periodo (suma de «sin copa al cierre»)
    for c in comparaciones:
        if c["preliminar"]:
            continue
        lista = _leer(f"incendios/{c['id']}.json")
        idx = {k: i for i, k in enumerate(lista["campos"])}
        assert sum(r[idx["perdido_ha"]] for r in lista["lista"]) == pytest.approx(
            _leer(f"comparaciones/{c['id']}.json")["incendios"]["perdido"], abs=1.5)


def test_hu_7_3_tabla_por_anio_del_estado_y_de_un_municipio(abrir, comparaciones):
    c = next(x for x in comparaciones if x["id"] == "2023_2025")
    esperado = _csv(c)
    esperado = esperado.assign(anio=esperado["fecha_inicio"].str[:4].astype(int))
    page, reg = abrir()
    _elegir_par(page, c)
    _abrir_tabla(page)

    def filas():
        return {int(r[0][:4]): r[1:] for r in page.eval_on_selector_all(
            "#tabla-incendios-anio tbody tr", "trs => trs.map(t => [...t.cells].map(c => c.textContent))")}

    f = filas()
    for a in (2023, 2024):
        g = esperado[esperado["anio"] == a]
        assert int(f[a][0]) == len(g)
        assert float(f[a][3].replace(",", "")) == pytest.approx(g["perdido_al_cierre_ha"].sum(), abs=0.05 * len(g) + 0.1)
    # Un municipio con incendios: sus cifras son las de sus incendios
    d = _leer("incendios/2023_2025.json")
    idx = {k: i for i, k in enumerate(d["campos"])}
    por_muni = pd.Series([r[idx["municipio"]] for r in d["lista"]]).value_counts()
    muni = por_muni.index[0]
    page.fill("#buscar", muni)
    page.dispatch_event("#buscar", "change")
    page.wait_for_function("n => document.getElementById('inc-cuenta')?.textContent.includes(n)", arg=muni, timeout=20_000)
    f = filas()
    suyos = [r for r in d["lista"] if r[idx["municipio"]] == muni]
    for a in (2023, 2024):
        n = sum(1 for r in suyos if r[idx["fecha"]].startswith(str(a)))
        assert int(f[a][0]) == n, (muni, a)
    assert page.locator("#tabla-incendios tbody tr").count() == len(suyos)
    assert reg.errores == [], reg.errores


def test_hu_7_3_la_pagina_muestra_la_perdida_por_incendio_por_municipio_y_periodo(abrir, comparaciones):
    """La tabla de municipios (columna Incendio) y el detalle traen la pérdida por incendio de cada periodo."""
    c = next(x for x in comparaciones if x["id"] == "2023_2024")
    d = _leer(f"comparaciones/{c['id']}.json")
    ii = d["campos"].index("inc")
    muni = max(d["filas"], key=lambda n: d["filas"][n][ii])
    page, _ = abrir()
    _elegir_par(page, c)
    fila = page.locator(f"#filas tr[data-n='{muni}']")
    assert str(round(d["filas"][muni][ii])) in fila.inner_text().replace(",", "")
    page.fill("#buscar", muni)
    page.dispatch_event("#buscar", "change")
    page.wait_for_function("n => document.querySelector('#detalle h3')?.textContent === n && document.querySelector('#detalle table')", arg=muni, timeout=20_000)
    renglon = page.locator("#detalle tbody tr", has_text="Pérdida por incendio").first
    assert len(renglon.locator("td").all_text_contents()) == 1 + len(_leer("indice.json")["comparaciones"])


# ------------------------------------------- Criterio 3: años sin capa de CONAFOR

def test_hu_7_3_el_indice_marca_los_anios_sin_capa(indice, comparaciones):
    assert indice["conafor"]["ultimo"] == ULTIMO_CONAFOR
    por_id = {c["id"]: c for c in comparaciones}
    assert por_id["2023_2024"]["anios_sin_capa"] == [] and por_id["2023_2024"]["incendios_estado"] == "completo"
    assert por_id["2024_2025"]["anios_sin_capa"] == [2025] and por_id["2024_2025"]["incendios_estado"] == "parcial"
    assert por_id["2023_2025"]["anios_sin_capa"] == [2025] and por_id["2023_2025"]["incendios_estado"] == "parcial"
    pre = next(c for c in comparaciones if c["preliminar"])
    assert pre["anios_sin_capa"] == [2025, 2026] and pre["incendios_estado"] == "sin_datos"
    for c in comparaciones:
        d = _leer(f"incendios/{c['id']}.json")
        assert d["anios_sin_capa"] == c["anios_sin_capa"] and d["estado"] == c["incendios_estado"]


def test_hu_7_3_anio_sin_capa_se_senala_en_cifras_tabla_y_capa(abrir, comparaciones):
    c = next(x for x in comparaciones if x["id"] == "2024_2025")
    page, reg = abrir()  # el periodo inicial es 2024 → 2025
    assert "CONAFOR aún no publica los incendios de 2025" in page.locator("#cifras").inner_text()
    assert "CONAFOR aún no publica los incendios de 2025" in page.locator("#incendios-aviso").inner_text()
    assert "†" in page.locator("#tabla-balance").text_content() and "†" in page.locator("#cascada svg").text_content()
    assert "CONAFOR aún no publica los incendios de 2025" in page.locator("#nota-tabla").inner_text()
    _abrir_tabla(page)
    fila = page.locator("#tabla-incendios-anio tr[data-anio='2025']")
    assert fila.get_attribute("data-sin-capa") == "1"
    assert "CONAFOR aún no publica los incendios de 2025" in fila.inner_text()
    anterior = page.locator("#tabla-incendios-anio tr[data-anio='2024']")
    assert anterior.get_attribute("data-sin-capa") is None
    _vista_incendios(page)
    assert page.locator("#aviso-capa").is_visible()
    assert "CONAFOR aún no publica los incendios de 2025" in page.locator("#aviso-capa").inner_text()
    assert "2025" in page.locator("#nota-mapa").inner_text()
    assert reg.errores == [], reg.errores


def test_hu_7_3_periodo_sin_incendios_publicados_no_se_muestra_como_cero(abrir, comparaciones):
    pre = next(c for c in comparaciones if c["preliminar"])
    page, reg = abrir()
    page.select_option("#hasta", str(pre["actual"]))
    page.select_option("#desde", str(pre["base"]))
    page.wait_for_function("() => document.getElementById('incendios-titulo')?.textContent.includes('preliminar')", timeout=30_000)
    tile = page.locator("#cifras .cifra", has_text="Pérdida por incendio")
    assert "sin dato" in tile.inner_text()
    assert "CONAFOR aún no publica los incendios de 2025 y 2026" in tile.inner_text()
    assert "sin dato" in page.locator("#tabla-balance").text_content()
    celdas = page.eval_on_selector_all("#filas tr td:nth-child(3)", "ts => ts.map(t => t.textContent)")
    assert celdas and set(celdas) == {"sin dato"}, "ningún municipio muestra 0 ha de incendio"
    _vista_incendios(page)
    assert "no hay incendios que mostrar" in page.locator("#aviso-capa").inner_text()
    assert page.locator("circle.punto-inc").count() == 0
    _abrir_tabla(page)
    assert page.locator("#tabla-incendios-anio tr[data-sin-capa='1']").count() == 2
    assert reg.errores == [], reg.errores


def test_hu_7_3_el_periodo_completo_no_lleva_aviso_de_sin_capa(abrir, comparaciones):
    c = next(x for x in comparaciones if x["id"] == "2023_2024")
    page, _ = abrir()
    _elegir_par(page, c)
    assert page.locator("#incendios-aviso").count() == 0
    assert "CONAFOR aún no publica" not in page.locator("#cifras").inner_text()
    assert page.locator("#nota-tabla").is_hidden()


# ------------------------------------------- Los dos modos de salida

def test_hu_7_3_archivo_unico_trae_los_incendios_y_la_capa(page, comparaciones):
    reg = Registro(page)
    page.goto(ARCHIVO_UNICO.as_uri())
    esperar_lista(page)
    c = next(x for x in comparaciones if x["id"] == "2023_2024")
    _elegir_par(page, c)
    _vista_incendios(page)
    assert page.locator("circle.punto-inc").count() == len(_csv(c))
    assert not [u for u in reg.peticiones if "/datos/" in u]
    assert reg.errores == [], reg.errores


# ------------------------------------------- Capturas (solo con CAPTURAS=1)

def test_hu_7_3_capturas(browser, servidor):
    for tema, ancho, alto, sufijo in [("light", 1366, 900, ""), ("dark", 1366, 900, "_oscuro"), ("light", 375, 812, "_movil")]:
        ctx = browser.new_context(viewport={"width": ancho, "height": alto}, color_scheme=tema, locale="es-MX",
                                  is_mobile=ancho < 500, device_scale_factor=2 if ancho < 500 else 1)
        page = ctx.new_page()
        reg = Registro(page)
        page.goto(servidor)
        esperar_lista(page)
        page.select_option("#hasta", "2024")
        page.select_option("#desde", "2023")
        page.wait_for_function("() => document.getElementById('incendios-titulo')?.textContent.includes('2023 → 2024')")
        _vista_incendios(page)
        page.wait_for_timeout(500)
        captura(page.locator(".principal"), CAPTURAS_S2 / f"hu_7_3_capa_incendios{sufijo}.png")
        _abrir_tabla(page)
        captura(page.locator("#incendios"), CAPTURAS_S2 / f"hu_7_3_tabla_incendios{sufijo}.png")
        page.select_option("#hasta", "2025")
        page.wait_for_function("() => document.getElementById('incendios-titulo')?.textContent.includes('2023 → 2025')")
        page.wait_for_timeout(500)
        captura(page.locator("#incendios"), CAPTURAS_S2 / f"hu_7_3_anio_sin_publicar{sufijo}.png")
        captura(page.locator("#aviso-capa"), CAPTURAS_S2 / f"hu_7_3_aviso_capa{sufijo}.png")
        if ancho < 500:
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "scroll horizontal en móvil"
        assert reg.errores == [], reg.errores
        ctx.close()
