"""HU-7.4 «Cambio de uso del suelo» (CF-DEV-04 de las Tablas de necesidades v12).

Criterio 1: la pérdida está clasificada como agrícola, urbana u otra, con el año y la fuente de los datos.
Criterio 2: un año sin datos de uso del suelo queda señalado.

El destino de las otras pérdidas es una estimación (clasificador de imágenes Sentinel-2 entrenado con la
Serie VII de INEGI, 2021): la página la presenta con su exactitud medida. Las cifras salen de
resultados/*/destino_perdidas_*.csv y destino_exactitud_*.csv; aquí se comparan con
docs/calculadora/datos/destino/<periodo>.json y con lo que muestra la página en Chromium sin interfaz.
"""

from __future__ import annotations

import json
import os

import pandas as pd
import pytest

from conftest import ARCHIVO_UNICO, DATOS, PRELIMINAR, RAIZ, SERIE, Registro, captura, esperar_lista, miles

CAPTURAS_S3 = RAIZ / "entregas" / "sprint_3" / "capturas"
COLUMNAS = ["otras_perdidas_ha", "agricola_ha", "pecuario_ha", "urbano_ha", "otro_ha", "sin_dato_ha"]
NOMBRES = ["Agrícola", "Pecuario", "Urbano", "Otro uso", "Sin dato"]


def _leer(ruta):
    return json.loads((DATOS / ruta).read_text(encoding="utf-8"))


def _carpeta(c):
    return PRELIMINAR if c["preliminar"] else SERIE


def _csv(c):
    return pd.read_csv(_carpeta(c) / f"destino_perdidas_{c['clave']}.csv")


@pytest.fixture(scope="module")
def comparaciones(indice):
    return indice["comparaciones"]


def _c(comparaciones, id_):
    return next(x for x in comparaciones if x["id"] == id_)


def _elegir_par(page, c):
    page.select_option("#hasta", str(c["actual"]))
    page.select_option("#desde", str(c["base"]))
    etiqueta = c["etiqueta"] + (" (preliminar)" if c["preliminar"] else "")
    page.wait_for_function(
        "e => document.getElementById('destino-titulo')?.textContent.includes(e) && document.getElementById('cargando').hidden",
        arg=etiqueta, timeout=30_000)


def _elegir_municipio(page, muni):
    page.fill("#buscar", muni)
    page.dispatch_event("#buscar", "change")
    page.wait_for_function("n => document.getElementById('destino-resumen')?.textContent.startsWith(n)", arg=muni, timeout=20_000)


def _vista_destino(page, capa):
    page.get_by_role("radio", name="Destino de la pérdida", exact=True).click()
    esperar_lista(page, capa)


def _barras(page):
    """{destino: (texto de hectáreas y %)} de las barras de la tarjeta."""
    return page.eval_on_selector_all("#barras-destino li", "ls => Object.fromEntries(ls.map(l => [l.dataset.destino, l.querySelector('.cifra').textContent]))")


def _pct(x, total):
    return f"{redondeo_1(x / total * 100)} %"


def redondeo_1(v):
    """Un decimal con .5 hacia arriba (Intl.NumberFormat), punto decimal es-MX."""
    import math
    return f"{math.floor(v * 10 + 0.5 + 1e-9) / 10:.1f}"


# ------------------------------------------------ Criterio 1: clasificada, con año y fuente

def test_hu_7_4_las_hectareas_por_destino_coinciden_con_los_csv(indice, comparaciones):
    for c in comparaciones:
        d = _leer(f"destino/{c['id']}.json")
        assert f"destino/{c['id']}.json" in indice["archivos"]
        assert d["estado"] == "completo" and c["destino_estado"] == "completo"
        t = _csv(c)
        assert set(d["filas"]) == set(t["unidad"]), c["id"]
        for _, r in t.iterrows():
            assert d["filas"][r["unidad"]] == pytest.approx([round(r[k], 2) for k in COLUMNAS], abs=0.011)
        assert d["total"] == pytest.approx([t[k].sum() for k in COLUMNAS], abs=0.05)


def test_hu_7_4_los_destinos_suman_las_otras_perdidas_del_periodo(comparaciones):
    for c in comparaciones:
        d = _leer(f"destino/{c['id']}.json")
        comp = _leer(f"comparaciones/{c['id']}.json")
        otras = comp["campos"].index("otras")
        assert sum(d["total"][1:]) == pytest.approx(d["total"][0], abs=0.1), c["id"]
        assert d["total"][0] == pytest.approx(comp["tot"]["otras"], abs=0.1), c["id"]
        for muni, v in d["filas"].items():
            assert sum(v[1:]) == pytest.approx(v[0], abs=0.03), (c["id"], muni)
            assert v[0] == pytest.approx(comp["filas"][muni][otras], abs=0.011), (c["id"], muni)


def test_hu_7_4_la_exactitud_es_la_de_los_archivos(comparaciones):
    esperadas = {"2023_2024": [("2023_2024", 2024)], "2024_2025": [("2024_2025", 2025)],
                 "2023_2025": [("2023_2024", 2024), ("2024_2025", 2025)]}
    for c in comparaciones:
        d = _leer(f"destino/{c['id']}.json")
        pares = esperadas.get(c["id"]) or [("2025_2026", 2026)]
        assert [x["anio"] for x in d["exactitud"]] == [a for _, a in pares], c["id"]
        for x, (clave, _) in zip(d["exactitud"], pares):
            g = pd.read_csv(_carpeta(c) / f"destino_exactitud_{clave}.csv").set_index("clase").loc["global"]
            assert x["global"] == pytest.approx(g["exactitud_global"], abs=5e-5)
            assert x["kappa"] == pytest.approx(g["kappa"], abs=5e-5)
            assert x["prueba"] == int(g["prueba"])
            assert 0.4 < x["global"] < 0.7  # una estimación de calidad media, no un dato exacto


def test_hu_7_4_la_tarjeta_muestra_las_cifras_del_estado(abrir, comparaciones):
    c = _c(comparaciones, "2023_2024")
    t = _csv(c)
    page, reg = abrir()
    _elegir_par(page, c)
    assert page.locator("#destino").is_visible()
    barras = _barras(page)
    assert list(barras) == ["agricola", "pecuario", "urbano", "otro", "sin_dato"]
    total = t["otras_perdidas_ha"].sum()
    for k, col in zip(barras, COLUMNAS[1:]):
        texto = barras[k]
        assert miles(t[col].sum()) + " ha" in texto, (k, texto)
        assert _pct(t[col].sum(), total) in texto, (k, texto)
    # La tabla equivalente trae las mismas hectáreas y el total de las otras pérdidas
    filas = page.eval_on_selector_all("#tabla-destino tbody tr", "rs => rs.map(r => r.textContent)")
    assert len(filas) == 6 and miles(total) in filas[-1]
    assert reg.errores == [], reg.errores


def test_hu_7_4_la_pagina_rotula_estimacion_fuente_y_anio(abrir, comparaciones):
    c = _c(comparaciones, "2023_2024")
    page, _ = abrir()
    _elegir_par(page, c)
    aviso = page.locator("#destino-estimacion").inner_text()
    assert "estimación" in aviso.lower()
    assert "Sentinel-2" in aviso and "Serie VII" in aviso and "2021" in aviso
    assert "de 2024" in aviso  # año de las imágenes = año final del periodo
    g = _leer("destino/2023_2024.json")["exactitud"][0]
    assert f"{g['global'] * 100:.1f} %" in aviso and f"{g['kappa']:.2f}" in aviso and f"{g['prueba']:,}" in aviso
    assert "no ha publicado uso del suelo oficial posterior" in aviso
    fuente = page.locator("#tabla-destino-anios tbody tr[data-estado=clasificado]")
    assert fuente.count() == 1 and "2024" in fuente.inner_text() and "INEGI" in fuente.inner_text()


def test_hu_7_4_el_periodo_largo_muestra_la_exactitud_de_cada_anio(abrir, comparaciones):
    c = _c(comparaciones, "2023_2025")
    page, _ = abrir()
    _elegir_par(page, c)
    aviso = page.locator("#destino-estimacion").inner_text()
    assert "2024: exactitud global" in aviso and "2025: exactitud global" in aviso
    assert page.locator("#tabla-destino-anios tbody tr[data-estado=clasificado]").count() == 2


def test_hu_7_4_la_perdida_por_incendio_va_aparte(abrir, comparaciones):
    c = _c(comparaciones, "2023_2024")
    comp = _leer(f"comparaciones/{c['id']}.json")
    page, _ = abrir()
    _elegir_par(page, c)
    aparte = page.locator("#destino-incendio").inner_text()
    assert miles(comp["tot"]["inc"]) + " ha" in aparte and "no se clasifica" in aparte
    assert page.locator("#barras-destino li").count() == 5  # el incendio no es una barra


def test_hu_7_4_un_municipio_muestra_sus_hectareas(abrir, comparaciones):
    c = _c(comparaciones, "2023_2024")
    t = _csv(c).set_index("unidad")
    muni = t["otras_perdidas_ha"].idxmax()
    page, _ = abrir()
    _elegir_par(page, c)
    _elegir_municipio(page, muni)
    barras = _barras(page)
    for k, col in zip(barras, COLUMNAS[1:]):
        assert miles(t.loc[muni, col]) + " ha" in barras[k], (muni, k, barras[k])


# ------------------------------------------------ Criterio 2: un año sin datos queda señalado

def test_hu_7_4_el_anio_base_sin_clasificacion_dice_sin_dato(abrir, comparaciones):
    c = _c(comparaciones, "2023_2024")
    d = _leer("destino/2023_2024.json")
    assert [(a["anio"], a["estado"]) for a in d["anios"]] == [(2023, "sin_dato"), (2024, "clasificado")]
    page, _ = abrir()
    _elegir_par(page, c)
    fila = page.locator("#tabla-destino-anios tbody tr[data-anio='2023']")
    assert "sin dato" in fila.inner_text() and fila.get_attribute("data-estado") == "sin_dato"
    assert "0" not in fila.inner_text().replace("2023", "")  # no lo presenta como cero


def test_hu_7_4_un_periodo_sin_clasificacion_dice_sin_dato_y_no_cero(abrir, comparaciones, page):
    """Si un periodo no trae clasificación, la tarjeta dice «sin dato» (no barras en cero) y el mapa también."""
    sin = {**_leer("destino/2023_2024.json"), "estado": "sin_datos", "filas": {}, "total": None, "exactitud": [],
           "anio_imagenes": [], "tiene_cuadricula": False,
           "anios": [{"anio": a, "etiqueta": str(a), "estado": "sin_dato", "motivo": "no se clasificó"} for a in (2023, 2024)]}
    page.route("**/datos/destino/2023_2024.json", lambda r: r.fulfill(json=sin))
    c = _c(comparaciones, "2023_2024")
    page, reg = abrir()
    _elegir_par(page, c)
    assert "Sin dato" in page.locator("#destino-sin-dato").inner_text()
    assert page.locator("#barras-destino").count() == 0
    assert page.locator("#destino-resumen").inner_text().startswith("Estado de México: sin dato")
    assert page.locator("#tabla-destino-anios tbody tr[data-estado=sin_dato]").count() == 2
    assert "sin medir" in page.locator("#destino-estimacion").inner_text()
    page.get_by_role("radio", name="Destino de la pérdida", exact=True).click()
    page.wait_for_function("() => document.getElementById('cargando').hidden")
    assert "Sin dato" in page.locator("#nota-mapa").inner_text()
    assert reg.errores == [], reg.errores


def test_hu_7_4_el_preliminar_lleva_su_aviso_de_otra_temporada(abrir, comparaciones):
    c = next(x for x in comparaciones if x["preliminar"])
    page, _ = abrir()
    _elegir_par(page, c)
    aviso = page.locator("#destino-estimacion").inner_text()
    assert "Preliminar" in aviso and "otra temporada" in aviso
    d = _leer(f"destino/{c['id']}.json")
    assert [(a["anio"], a["estado"]) for a in d["anios"]] == [(2025, "sin_dato"), (2026, "clasificado")]
    assert "de 2026" in aviso


def test_hu_7_4_el_modo_un_anio_no_muestra_la_tarjeta(abrir):
    page, _ = abrir()
    page.get_by_role("radio", name="Un año").click() if page.get_by_role("radio", name="Un año").count() else page.locator("#modos button[data-modo=anio]").click()
    page.wait_for_function("() => document.getElementById('cargando').hidden")
    assert not page.locator("#destino").is_visible()


# ------------------------------------------------ Capa del mapa

def test_hu_7_4_la_cuadricula_del_destino_se_carga_solo_al_consultarla(abrir, comparaciones, indice):
    c = _c(comparaciones, "2023_2024")
    page, reg = abrir()
    assert not [u for u in reg.datos(page.url) if u.startswith("cuadriculas/destino_")]
    _elegir_par(page, c)
    assert not [u for u in reg.datos(page.url) if u.startswith("cuadriculas/destino_")]
    assert "destino/2023_2024.json" in reg.datos(page.url)
    _vista_destino(page, "destino_2023_2024.png")
    assert "cuadriculas/destino_2023_2024.png" in reg.datos(page.url)
    assert "Destino de la pérdida" in page.locator("#leyenda-titulo").inner_text()
    leyenda = page.locator("#leyenda").inner_text()
    for n in NOMBRES:
        assert n in leyenda
    assert reg.errores == [], reg.errores


def test_hu_7_4_la_cuadricula_trae_las_clases_de_los_destinos():
    from PIL import Image
    import numpy as np
    img = np.array(Image.open(DATOS / "cuadriculas" / "destino_2023_2024.png"))
    paso = _leer("indice.json")["pasos"]["destino"]
    clases = set((np.unique(img) // paso).tolist())
    assert {0, 1, 2, 3, 4} <= clases and 5 not in clases  # sin dato: 0 ha en este periodo
    assert (img > 0).sum() > 1000


# ------------------------------------------------ Archivo único y capturas

def test_hu_7_4_el_archivo_unico_trae_los_mismos_datos_embebidos(browser, comparaciones):
    page = browser.new_page(viewport={"width": 1366, "height": 900}, locale="es-MX")
    reg = Registro(page)
    page.goto(ARCHIVO_UNICO.as_uri())
    esperar_lista(page)
    c = _c(comparaciones, "2023_2024")
    _elegir_par(page, c)
    t = _csv(c)
    barras = _barras(page)
    assert miles(t["pecuario_ha"].sum()) + " ha" in barras["pecuario"]
    assert not [u for u in reg.peticiones if "/datos/" in u]
    assert reg.errores == [], reg.errores
    page.close()


def test_hu_7_4_capturas(browser, servidor):
    if os.environ.get("CAPTURAS") == "1":
        CAPTURAS_S3.mkdir(parents=True, exist_ok=True)
    for tema, ancho, alto, sufijo in [("light", 1366, 900, ""), ("dark", 1366, 900, "_oscuro"), ("light", 375, 812, "_movil")]:
        ctx = browser.new_context(viewport={"width": ancho, "height": alto}, color_scheme=tema, locale="es-MX",
                                  is_mobile=ancho < 500, device_scale_factor=2 if ancho < 500 else 1)
        page = ctx.new_page()
        reg = Registro(page)
        page.goto(servidor)
        esperar_lista(page)
        _elegir_par(page, {"base": 2023, "actual": 2024, "etiqueta": "2023 → 2024", "preliminar": False})
        page.wait_for_timeout(300)
        captura(page.locator("#destino"), CAPTURAS_S3 / f"hu_7_4_tarjeta_destino{sufijo}.png")
        _vista_destino(page, "destino_2023_2024.png")
        page.wait_for_timeout(500)
        captura(page.locator(".principal"), CAPTURAS_S3 / f"hu_7_4_capa_destino{sufijo}.png")
        page.select_option("#hasta", "2025")
        page.wait_for_function("() => document.getElementById('destino-titulo')?.textContent.includes('2023 → 2025')")
        captura(page.locator("#destino"), CAPTURAS_S3 / f"hu_7_4_periodo_largo{sufijo}.png")
        if ancho < 500:
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "scroll horizontal en móvil"
        assert reg.errores == [], reg.errores
        ctx.close()
