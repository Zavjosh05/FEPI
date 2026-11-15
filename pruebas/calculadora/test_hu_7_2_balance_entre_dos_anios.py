"""HU-7.2 «Balance entre dos años» (CF-DEV-02 de las Tablas de necesidades v12).

Criterio 1: existe la pérdida, la ganancia y el cambio neto en hectáreas, para el Estado y cada municipio.
Criterio 2: existe el histograma del periodo elegido.

Las cifras salen de los CSV de resultados/ (balance_<par>.csv); las pruebas leen los archivos de
docs/calculadora/datos y la página en Chromium sin interfaz.
"""

from __future__ import annotations

import json

import pandas as pd
import pytest

from conftest import captura, ARCHIVO_UNICO, CAPTURAS_S2, DATOS, PRELIMINAR, SERIE, Registro, esperar_lista

BORDES = [-10, -8, -6, -4, -2, 0, 2, 4, 6, 8, 10]
MINIMO = 500
N_MUNICIPIOS = 125


def _leer(ruta):
    return json.loads((DATOS / ruta).read_text(encoding="utf-8"))


def _csv(c):
    carpeta = PRELIMINAR if c["preliminar"] else SERIE
    return pd.read_csv(carpeta / f"balance_{c['clave']}.csv")


def _bin(v):
    k = 0
    while k < len(BORDES) and v >= BORDES[k]:
        k += 1
    return k


def _cuentas(bal):
    b = bal[bal["bosque_base_ha"] >= MINIMO]
    cuentas = [0] * (len(BORDES) + 1)
    for v in b["cambio_neto_ha"] / b["bosque_base_ha"] * 100:
        cuentas[_bin(v)] += 1
    return cuentas


def _num(texto):
    """Número de una celda de la página: «+1,234», «−1,234» (U+2212) o «1,234»."""
    return float(texto.replace("−", "-").replace("+", "").replace(",", "").replace("†", ""))


def _igual(tabla, esperado):
    """La tabla de la página (conceptos y hectáreas redondeadas) contra los valores de los CSV.
    La página redondea los totales a 0.1 ha y luego a 1 ha, así que se tolera 1 ha."""
    assert [c for c, _ in tabla] == [c for c, _ in esperado]
    for (c, texto), (_, v) in zip(tabla, esperado):
        if texto == "sin dato":  # HU-7.3: un año sin capa de CONAFOR no se presenta como cero
            assert c == "Pérdida por incendio" and v == 0
            continue
        assert _num(texto) == pytest.approx(v, abs=1.0), (c, texto, v)


@pytest.fixture(scope="module")
def comparaciones(indice):
    return indice["comparaciones"]


def _elegir_par(page, c):
    """Elige el par de años de la comparación `c` con los selectores Desde y Hasta."""
    page.select_option("#hasta", str(c["actual"]))
    page.select_option("#desde", str(c["base"]))
    etiqueta = c["etiqueta"] + (" (preliminar)" if c["preliminar"] else "")
    page.wait_for_function(
        "e => document.getElementById('balance-titulo')?.textContent.includes(e) && document.getElementById('cargando').hidden",
        arg=etiqueta, timeout=30_000)


def _tabla(page, selector):
    """Filas de una tabla como [(texto1, texto2)]."""
    return [tuple(td.strip() for td in fila) for fila in
            page.eval_on_selector_all(f"{selector} tbody tr", "trs => trs.map(t => [...t.cells].map(c => c.textContent))")]


# ---------------------------------------------------------------- Criterio 1: pérdida, ganancia y neto

def test_hu_7_2_balance_del_estado_coincide_con_los_csv(comparaciones):
    assert len(comparaciones) == 4
    for c in comparaciones:
        bal = _csv(c)
        tot = _leer(f"comparaciones/{c['id']}.json")["tot"]
        for corto, col in {"base": "bosque_base_ha", "inc": "perdida_incendio_ha", "otras": "otras_perdidas_ha",
                           "gan": "ganancia_ha", "actual": "bosque_actual_ha", "neto": "cambio_neto_ha"}.items():
            assert tot[corto] == pytest.approx(bal[col].sum(), abs=1.0), f"{c['id']} {corto}"


def test_hu_7_2_el_bosque_de_cada_anio_es_el_mismo_en_el_balance_y_en_la_evolucion():
    """La cifra de un año no cambia según la vista: el bosque inicial y final de cada comparación de la serie es,
    hectárea por hectárea ya redondeada, el de la evolución anual (evita el doble redondeo: 473,148 y no 473,149)."""
    indice = json.loads((DATOS / "indice.json").read_text(encoding="utf-8"))
    por_anio = {e["anio"]: e["bosque_ha"] for e in indice["evolucion_estatal"]}
    revisadas = 0
    for c in indice["comparaciones"]:
        if c.get("preliminar"):
            continue                    # otra temporada: sus hectáreas no son las de la serie
        ruta = next(DATOS.glob(f"comparaciones/{c['base']}_{c['actual']}*.json"))
        tot = json.loads(ruta.read_text(encoding="utf-8"))["tot"]
        assert round(tot["base"]) == round(por_anio[c["base"]]), ruta.name
        assert round(tot["actual"]) == round(por_anio[c["actual"]]), ruta.name
        revisadas += 1
    assert revisadas >= 3


def test_hu_7_2_el_balance_cuadra_en_el_estado_y_en_cada_municipio(comparaciones):
    """inicial − pérdida por incendio − otras pérdidas + ganancia = final, y final − inicial = neto."""
    for c in comparaciones:
        d = _leer(f"comparaciones/{c['id']}.json")
        t = d["tot"]
        assert t["base"] - t["inc"] - t["otras"] + t["gan"] == pytest.approx(t["actual"], abs=1.0), c["id"]
        assert t["actual"] - t["base"] == pytest.approx(t["neto"], abs=1.0), c["id"]
        I = {k: i for i, k in enumerate(d["campos"])}
        assert len(d["filas"]) == N_MUNICIPIOS, f"{c['id']}: {len(d['filas'])} municipios"
        for nombre, f in d["filas"].items():
            assert f[I["base"]] - f[I["inc"]] - f[I["otras"]] + f[I["gan"]] == pytest.approx(f[I["actual"]], abs=0.03), (c["id"], nombre)
            assert f[I["actual"]] - f[I["base"]] == pytest.approx(f[I["neto"]], abs=0.03), (c["id"], nombre)


def test_hu_7_2_balance_de_cada_municipio_coincide_con_los_csv(comparaciones):
    for c in comparaciones:
        d = _leer(f"comparaciones/{c['id']}.json")
        I = {k: i for i, k in enumerate(d["campos"])}
        bal = _csv(c).set_index("unidad")
        assert set(d["filas"]) == set(bal.index)
        for nombre, f in d["filas"].items():
            r = bal.loc[nombre]
            for corto, col in {"base": "bosque_base_ha", "inc": "perdida_incendio_ha", "otras": "otras_perdidas_ha",
                               "gan": "ganancia_ha", "actual": "bosque_actual_ha", "neto": "cambio_neto_ha"}.items():
                assert f[I[corto]] == pytest.approx(r[col], abs=0.006), (c["id"], nombre, corto)


def test_hu_7_2_la_pagina_muestra_el_balance_del_estado_de_cada_periodo(abrir, comparaciones):
    page, reg = abrir()
    assert page.locator("#balance").is_visible()
    for c in comparaciones:
        _elegir_par(page, c)
        bal = _csv(c)
        inicial, final = bal["bosque_base_ha"].sum(), bal["bosque_actual_ha"].sum()
        esperado = [
            ("Bosque inicial", inicial),
            ("Pérdida por incendio", -bal["perdida_incendio_ha"].sum()),
            ("Otras pérdidas", -bal["otras_perdidas_ha"].sum()),
            ("Ganancia", bal["ganancia_ha"].sum()),
            ("Bosque final", final),
            ("Cambio neto", final - inicial),
        ]
        _igual(_tabla(page, "#tabla-balance"), esperado)
        # Las barras de la cascada: pérdidas hacia abajo, ganancia hacia arriba
        barras = page.eval_on_selector_all("#cascada rect.barra-b", "rs => rs.map(r => [r.dataset.barra, r.dataset.ha])")
        barras = [[n, v if v == "sin dato" else float(v)] for n, v in barras]
        assert [b[0] for b in barras] == ["Incendio", "Otras pérdidas", "Ganancia", "Cambio neto"]
        if barras[0][1] != "sin dato":
            assert barras[0][1] == pytest.approx(-bal["perdida_incendio_ha"].sum(), abs=1)
        assert barras[1][1] == pytest.approx(-bal["otras_perdidas_ha"].sum(), abs=1)
        assert barras[2][1] == pytest.approx(bal["ganancia_ha"].sum(), abs=1)
        assert barras[3][1] == pytest.approx(final - inicial, abs=1)
        assert "Estado de México" in page.locator("#balance-resumen").inner_text()
    assert reg.errores == [], reg.errores


def test_hu_7_2_la_pagina_muestra_el_balance_de_un_municipio(abrir, comparaciones):
    c = next(x for x in comparaciones if x["id"] == "2023_2024")
    bal = _csv(c)
    nombre = bal.sort_values("bosque_base_ha").iloc[-1]["unidad"]  # el de más bosque
    r = bal.set_index("unidad").loc[nombre]
    page, reg = abrir()
    _elegir_par(page, c)
    page.fill("#buscar", nombre)
    page.dispatch_event("#buscar", "change")
    page.wait_for_function("n => document.getElementById('balance-resumen').textContent.startsWith(n)", arg=nombre, timeout=20_000)
    esperado = [
        ("Bosque inicial", r["bosque_base_ha"]),
        ("Pérdida por incendio", -r["perdida_incendio_ha"]),
        ("Otras pérdidas", -r["otras_perdidas_ha"]),
        ("Ganancia", r["ganancia_ha"]),
        ("Bosque final", r["bosque_actual_ha"]),
        ("Cambio neto", r["cambio_neto_ha"]),
    ]
    _igual(_tabla(page, "#tabla-balance"), esperado)
    assert page.locator("#cascada svg").get_attribute("aria-label").startswith(f"Balance de {nombre}")
    # Con el municipio elegido, el balance deja de ser el del Estado (sin selección vuelve al Estado)
    assert abs(r["bosque_base_ha"] - _csv(c)["bosque_base_ha"].sum()) > 1
    assert reg.errores == [], reg.errores


# ---------------------------------------------------------------- Criterio 2: el histograma

def test_hu_7_2_existe_el_histograma_de_cada_periodo_y_suma_los_municipios_con_dato(abrir, comparaciones):
    page, reg = abrir()
    todas = []
    for c in comparaciones:
        _elegir_par(page, c)
        bal = _csv(c)
        con_dato = int((bal["bosque_base_ha"] >= MINIMO).sum())
        cuentas = page.eval_on_selector_all("#histograma rect[data-bin]", "rs => rs.map(r => Number(r.dataset.n))")
        assert len(cuentas) == len(BORDES) + 1, "intervalos fijos: 12"
        assert sum(cuentas) == con_dato, f"{c['id']}: {sum(cuentas)} contra {con_dato}"
        assert cuentas == _cuentas(bal), c["id"]
        # Tabla equivalente y texto alternativo con las mismas cuentas
        assert [int(f[1]) for f in _tabla(page, "#tabla-histograma")] == cuentas
        alt = page.locator("#histograma svg").get_attribute("aria-label")
        assert f"Histograma de {con_dato} municipios" in alt
        # Cuántos pierden y cuántos ganan, en el texto
        pierden = sum(cuentas[:6])
        assert f"{pierden} pierden bosque y {con_dato - pierden} ganan" in page.locator("#hist-resumen").inner_text()
        todas.append(cuentas)
    assert len({tuple(x) for x in todas}) == len(todas), "el histograma debe cambiar con el periodo"
    assert reg.errores == [], reg.errores


def test_hu_7_2_los_intervalos_son_simetricos_alrededor_de_cero(abrir):
    page, _ = abrir()
    etiquetas = page.eval_on_selector_all("#histograma rect[data-bin] title", "ts => ts.map(t => t.textContent.split(':')[0])")
    assert etiquetas[0] == "menos de −10 %" and etiquetas[-1] == "10 % o más"
    assert etiquetas[5] == "−2 a 0 %" and etiquetas[6] == "0 a 2 %"
    # Pierden a la izquierda de 0 (6 intervalos) y ganan a la derecha (6): mismo número a cada lado
    colores = page.eval_on_selector_all("#histograma rect[data-bin]", "rs => rs.map(r => r.style.fill)")
    assert colores[:6] == [colores[0]] * 6 and colores[6:] == [colores[6]] * 6 and colores[0] != colores[6]


def test_hu_7_2_el_municipio_elegido_se_resalta_en_su_intervalo(abrir, comparaciones):
    c = next(x for x in comparaciones if x["id"] == "2023_2024")
    bal = _csv(c)
    bal = bal[bal["bosque_base_ha"] >= MINIMO]
    r = bal.iloc[len(bal) // 2]
    page, _ = abrir()
    _elegir_par(page, c)
    assert page.locator("#histograma rect.sel").count() == 0
    page.fill("#buscar", r["unidad"])
    page.dispatch_event("#buscar", "change")
    page.wait_for_function("() => document.querySelectorAll('#histograma rect.sel').length === 1", timeout=20_000)
    k = int(page.locator("#histograma rect.sel").get_attribute("data-bin"))
    assert k == _bin(r["cambio_neto_ha"] / r["bosque_base_ha"] * 100)
    assert r["unidad"] in page.locator("#hist-resumen").inner_text()
    # Un municipio con poco bosque no entra en el histograma y la página lo dice
    chico = _csv(c).query("bosque_base_ha < @MINIMO").iloc[0]["unidad"]
    page.fill("#buscar", chico)
    page.dispatch_event("#buscar", "change")
    page.wait_for_function("() => document.querySelectorAll('#histograma rect.sel').length === 0", timeout=20_000)
    assert "no entra en el histograma" in page.locator("#hist-resumen").inner_text()


def test_hu_7_2_el_periodo_preliminar_lleva_su_aviso(abrir, comparaciones):
    pre = next(c for c in comparaciones if c["preliminar"])
    anual = next(c for c in comparaciones if not c["preliminar"])
    page, _ = abrir()
    assert page.locator("#balance-aviso").count() == 0, "el balance anual no lleva el aviso de preliminar"
    _elegir_par(page, pre)
    aviso = page.locator("#balance-aviso")
    assert aviso.is_visible() and "Preliminar" in aviso.inner_text() and "otra temporada" in aviso.inner_text()
    assert "(preliminar)" in page.locator("#balance-titulo").inner_text()
    _elegir_par(page, anual)
    assert page.locator("#balance-aviso").count() == 0


def test_hu_7_2_el_balance_solo_va_en_el_modo_comparar_anios(abrir):
    page, _ = abrir()
    assert page.locator("#balance").is_visible()
    page.get_by_role("radio", name="Un año").click()
    page.wait_for_function("() => document.getElementById('balance').hidden", timeout=20_000)
    page.get_by_role("radio", name="Comparar años").click()
    page.wait_for_function("() => !document.getElementById('balance').hidden", timeout=20_000)


def test_hu_7_2_archivo_unico_tambien_trae_el_balance_y_el_histograma(page, comparaciones):
    reg = Registro(page)
    page.goto(ARCHIVO_UNICO.as_uri())
    esperar_lista(page)
    assert page.locator("#balance").is_visible()
    c = next(x for x in comparaciones if x["id"] == "2024_2025")
    _elegir_par(page, c)
    cuentas = page.eval_on_selector_all("#histograma rect[data-bin]", "rs => rs.map(r => Number(r.dataset.n))")
    assert cuentas == _cuentas(_csv(c))
    _igual(_tabla(page, "#tabla-balance")[:1], [("Bosque inicial", _csv(c)["bosque_base_ha"].sum())])
    assert reg.errores == [], reg.errores


# ---------------------------------------------------------------- Capturas (claro, oscuro, móvil)

def test_hu_7_2_capturas_claro_oscuro_y_movil(browser, servidor):
    nombre = "Valle de Bravo"
    for tema, ancho, alto, sufijo in [("light", 1366, 900, ""), ("dark", 1366, 900, "_oscuro"), ("light", 375, 812, "_movil"),
                                      ("dark", 375, 812, "_movil_oscuro")]:
        ctx = browser.new_context(viewport={"width": ancho, "height": alto}, color_scheme=tema, locale="es-MX",
                                  is_mobile=ancho < 500, device_scale_factor=2 if ancho < 500 else 1)
        page = ctx.new_page()
        reg = Registro(page)
        page.goto(servidor)
        esperar_lista(page)
        page.select_option("#desde", "2023")
        page.select_option("#hasta", "2024")
        page.wait_for_function("() => document.getElementById('balance-titulo')?.textContent.includes('2023 → 2024')")
        captura(page.locator("#balance"), CAPTURAS_S2 / f"hu_7_2_balance_estado{sufijo}.png")
        page.fill("#buscar", nombre)
        page.dispatch_event("#buscar", "change")
        page.wait_for_function("n => document.getElementById('balance-resumen').textContent.startsWith(n)", arg=nombre, timeout=20_000)
        page.wait_for_timeout(800)
        captura(page.locator("#balance"), CAPTURAS_S2 / f"hu_7_2_balance_municipio{sufijo}.png")
        if ancho < 500:  # sin desbordar a los lados
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), "scroll horizontal en móvil"
        assert reg.errores == [], reg.errores
        ctx.close()
