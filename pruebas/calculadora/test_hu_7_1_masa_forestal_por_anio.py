"""HU-7.1 «Masa forestal por año» (CF-DEV-01 de las Tablas de necesidades v12).

Criterio 1: existe la superficie en hectáreas de cada año disponible, por municipio y para el Estado.
Criterio 2: existe la evolución año con año (y se ve en la página).

Las pruebas del criterio 1 leen los archivos de docs/calculadora/datos y los comparan con la serie
de resultados/; las del criterio 2 abren la página en Chromium sin interfaz.
"""

from __future__ import annotations

import base64
import json
import re

import pandas as pd
import pytest

from conftest import captura, ARCHIVO_UNICO, CAPTURAS, DATOS, RAIZ, SERIE, Registro, esperar_lista, miles

# Bosque del Estado en la serie 2023-2025 (resultados/edomex_serie_2023_2025/LEEME.md)
REFERENCIA = {2023: 473_148, 2024: 467_955, 2025: 466_058}
N_MUNICIPIOS = 125
TOL_HA = 1.0  # las cifras van redondeadas a 2 decimales (municipios) o 1 (Estado)


def _leer(ruta):
    return json.loads((DATOS / ruta).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def serie_csv():
    return pd.read_csv(SERIE / "serie_2023_2025.csv")


# ---------------------------------------------------------------- Criterio 1: superficie por año

def test_hu_7_1_cada_anio_del_indice_tiene_su_archivo(indice):
    anios = indice["anios"]
    assert anios == sorted(REFERENCIA), "el índice debe listar los años de la serie"
    for a in anios:
        ruta = DATOS / "anios" / f"{a}.json"
        assert ruta.exists(), f"falta {ruta}"
        assert f"anios/{a}.json" in indice["archivos"]
        assert _leer(f"anios/{a}.json")["anio"] == a


def test_hu_7_1_cada_anio_trae_los_125_municipios_y_el_estado(indice):
    campos = indice["serie"]["campos"]
    for a in indice["anios"]:
        d = _leer(f"anios/{a}.json")
        assert d["campos"] == campos
        assert len(d["filas"]) == N_MUNICIPIOS, f"{a}: {len(d['filas'])} municipios"
        assert all("Todos" in porTipo for porTipo in d["filas"].values())
        assert "Todos" in d["estado"], f"{a}: falta el total del Estado"
        # Los tipos de bosque del índice, en el Estado
        assert set(d["estado"]) - {"Todos"} <= set(indice["tipos"])


def test_hu_7_1_hectareas_coinciden_con_la_serie(indice, serie_csv):
    """Cada municipio, tipo y año contra serie_2023_2025.csv."""
    IS = {c: i for i, c in enumerate(indice["serie"]["campos"])}
    columnas = {"zona": "zona_forestal_ha", "bosque": "bosque_ha", "inc": "perdida_incendio_ha",
                "otras": "otras_perdidas_ha", "gan": "ganancia_ha", "neto": "cambio_neto_ha"}
    revisadas = 0
    for a in indice["anios"]:
        d = _leer(f"anios/{a}.json")
        csv = serie_csv[serie_csv["anio"] == a]
        assert len(csv) == sum(len(x) for x in d["filas"].values()), f"{a}: no son las mismas filas"
        for _, r in csv.iterrows():
            fila = d["filas"][r["unidad"]][r["tipo_bosque"]]
            for corto, col in columnas.items():
                v = fila[IS[corto]]
                if pd.isna(r[col]):
                    assert v is None, f"{a} {r['unidad']} {r['tipo_bosque']} {corto}: {v}"
                else:
                    assert v == pytest.approx(r[col], abs=0.006), f"{a} {r['unidad']} {r['tipo_bosque']} {corto}"
            revisadas += 1
    assert revisadas == len(serie_csv)


def test_hu_7_1_estado_coincide_con_la_referencia_y_con_la_suma_de_municipios(indice):
    IS = {c: i for i, c in enumerate(indice["serie"]["campos"])}
    for a in indice["anios"]:
        d = _leer(f"anios/{a}.json")
        suma = sum(f["Todos"][IS["bosque"]] for f in d["filas"].values())
        estado = d["estado"]["Todos"][IS["bosque"]]
        assert estado == pytest.approx(suma, abs=TOL_HA), f"{a}: Estado {estado} contra suma {suma}"
        assert estado == pytest.approx(REFERENCIA[a], abs=TOL_HA), f"{a}: {estado} contra {REFERENCIA[a]}"
        # Lo mismo por tipo de bosque
        for tipo, fila in d["estado"].items():
            s = sum((f[tipo][IS["bosque"]] or 0) for f in d["filas"].values() if tipo in f)
            assert (fila[IS["bosque"]] or 0) == pytest.approx(s, abs=TOL_HA), f"{a} {tipo}"


# ------------------------------------------------------------ Criterio 2: evolución año con año

def test_hu_7_1_indice_trae_la_evolucion_estatal(indice):
    """La evolución del Estado se dibuja solo con el índice (sin cargar los años)."""
    ev = indice["evolucion_estatal"]
    assert [e["anio"] for e in ev] == indice["anios"]
    for e in ev:
        assert e["bosque_ha"] == pytest.approx(REFERENCIA[e["anio"]], abs=TOL_HA)
    assert ev[0]["cambio_neto_ha"] is None
    for antes, despues in zip(ev, ev[1:]):
        # El cambio neto de cada año es la diferencia con el anterior (balance encadenado)
        assert despues["cambio_neto_ha"] == pytest.approx(despues["bosque_ha"] - antes["bosque_ha"], abs=TOL_HA)
    tend = indice["serie"]["tend_total"]["Todos"]
    assert tend[0] == pytest.approx(-3545.43, abs=0.01)


def test_hu_7_1_evolucion_de_cada_municipio_en_los_archivos_de_anio(indice):
    IS = {c: i for i, c in enumerate(indice["serie"]["campos"])}
    anios = [_leer(f"anios/{a}.json") for a in indice["anios"]]
    for u in anios[0]["filas"]:
        b = [d["filas"][u]["Todos"][IS["bosque"]] for d in anios]
        for t in range(1, len(anios)):
            neto = anios[t]["filas"][u]["Todos"][IS["neto"]]
            assert neto == pytest.approx(b[t] - b[t - 1], abs=0.02), f"{u} {indice['anios'][t]}"


def test_hu_7_1_pagina_carga_sin_errores_y_muestra_la_evolucion(abrir, indice):
    page, reg = abrir()
    assert reg.errores == [], reg.errores
    ev = page.locator("#evolucion")
    assert ev.is_visible(), "la evolución del Estado debe verse sin abrir ningún detalle"
    assert ev.locator("circle.punto").count() == len(indice["anios"])
    assert sorted(int(x) for x in ev.locator("circle.punto").evaluate_all("els => els.map(e => e.dataset.anio)")) == indice["anios"]
    # Un rótulo y una fila por año, con sus hectáreas
    filas = ev.locator("tbody tr")
    assert filas.count() == len(indice["anios"])
    for i, e in enumerate(indice["evolucion_estatal"]):
        texto = filas.nth(i).inner_text()
        assert str(e["anio"]) in texto
        assert miles(e["bosque_ha"]) in texto, texto
    rotulos = ev.locator("text.rotulo").all_text_contents()
    assert rotulos == [miles(e["bosque_ha"]) for e in indice["evolucion_estatal"]]
    # Sin municipio elegido, el detalle no tiene la gráfica (está en la evolución)
    assert page.locator("#detalle .serie-graf").count() == 0
    captura(page, CAPTURAS / "hu_7_1_vista_inicial.png", full_page=False)
    captura(ev, CAPTURAS / "hu_7_1_evolucion.png")


def test_hu_7_1_carga_diferida(abrir, indice, servidor):
    page, reg = abrir()
    inicial = reg.datos(servidor)
    # Vista inicial: el balance anual más reciente de un año
    anuales = [c for c in indice["comparaciones"] if not c["preliminar"]]
    c0 = sorted(anuales, key=lambda c: (-c["actual"], c["actual"] - c["base"]))[0]
    esperado = {"indice.json", "municipios.topojson", f"comparaciones/{c0['id']}.json",
                f"cuadriculas/cambio_{c0['id']}.png",
                f"destino/{c0['id']}.json"}  # la tarjeta de HU-7.4 (~7 kB) se ve en la vista inicial
    assert set(inicial) == esperado, inicial
    assert not [r for r in inicial if r.startswith("anios/")], "no debe pedir años al abrir"
    # Al elegir un año (botón «ver» de la evolución) se pide ese año y su cuadrícula, no los demás
    a = indice["anios"][0]
    page.get_by_role("button", name=f"Ver el bosque de {a}").click()
    esperar_lista(page, f"bosque_{a}.png")
    despues = set(reg.datos(servidor)) - set(inicial)
    assert f"anios/{a}.json" in despues and f"cuadriculas/bosque_{a}.png" in despues, despues
    otros = [x for x in indice["anios"] if x != a]
    assert not any(f"anios/{x}.json" in despues for x in otros), despues
    assert not any(r.startswith("cuadriculas/bosque_") and r != f"cuadriculas/bosque_{a}.png" for r in despues)
    assert page.locator("#anio").input_value() == "0"
    ev = {e["anio"]: e["bosque_ha"] for e in indice["evolucion_estatal"]}
    assert miles(ev[a]) in page.locator("#cifras").inner_text()
    # Otro año desde el selector
    b = indice["anios"][-1]
    page.select_option("#anio", str(len(indice["anios"]) - 1))
    esperar_lista(page, f"bosque_{b}.png")
    assert f"anios/{b}.json" in reg.datos(servidor)
    assert miles(ev[b]) in page.locator("#cifras").inner_text()
    assert reg.errores == [], reg.errores
    captura(page, CAPTURAS / "hu_7_1_un_anio.png", full_page=True)


def test_hu_7_1_detalle_de_un_municipio_muestra_su_evolucion(abrir, indice):
    page, reg = abrir()
    nombre = "Amecameca"
    page.fill("#buscar", nombre)
    page.dispatch_event("#buscar", "change")
    page.wait_for_function(f"document.querySelector('#detalle h3')?.textContent === {json.dumps(nombre)} "
                           f"&& document.querySelectorAll('#detalle circle.punto').length > 0", timeout=20_000)
    det = page.locator("#detalle")
    assert det.locator("circle.punto").count() == len(indice["anios"])
    IS = {c: i for i, c in enumerate(indice["serie"]["campos"])}
    rotulos = det.locator("text.rotulo").all_text_contents()
    for a, r in zip(indice["anios"], rotulos):
        b = _leer(f"anios/{a}.json")["filas"][nombre]["Todos"][IS["bosque"]]
        assert r == miles(b), (a, r, b)
    assert reg.errores == [], reg.errores
    page.wait_for_timeout(800)  # termina el acercamiento
    captura(page.locator(".principal"), CAPTURAS / "hu_7_1_detalle_municipio.png")


def test_hu_7_1_alineacion_municipios_y_cuadricula(abrir, indice):
    """El contorno estatal (TopoJSON) y la cuadrícula deben coincidir: la cuadrícula casi no tiene
    celdas fuera del contorno, y moverla una o más celdas en cualquier dirección deja más fuera."""
    page, _ = abrir()
    r = page.evaluate("""async () => {
        const W = %d, H = %d;
        const img = new Image(); img.src = "datos/cuadriculas/bosque_%d.png"; await img.decode();
        const c = document.createElement("canvas"); c.width = W; c.height = H;
        const ctx = c.getContext("2d"); ctx.drawImage(img, 0, 0);
        const px = ctx.getImageData(0, 0, W, H).data;
        const m = document.createElement("canvas"); m.width = W; m.height = H;
        const mc = m.getContext("2d");
        mc.fill(new Path2D(document.querySelector("path.contorno").getAttribute("d")), "evenodd");
        const mask = mc.getImageData(0, 0, W, H).data;
        const celdas = [];
        for (let j = 0; j < W * H; j++) if (px[j * 4] > 0) celdas.push(j);
        const fuera = {};
        for (let dx = -2; dx <= 2; dx++) for (let dy = -2; dy <= 2; dy++) {
          let n = 0;
          for (const j of celdas) {
            const x = j %% W + dx, y = Math.floor(j / W) + dy;
            if (x < 0 || y < 0 || x >= W || y >= H || mask[(y * W + x) * 4 + 3] < 128) n++;
          }
          fuera[dx + "," + dy] = n;
        }
        const bb = document.querySelector("path.contorno").getBBox();
        return { total: celdas.length, fuera, bbox: [bb.x, bb.y, bb.x + bb.width, bb.y + bb.height] };
    }""" % (indice["ancho"], indice["alto"], indice["anios"][0]))
    cero = r["fuera"]["0,0"]
    assert r["total"] > 10_000
    assert cero / r["total"] < 0.005, f"{cero} de {r['total']} celdas de bosque fuera del Estado"
    for k, v in r["fuera"].items():
        if k != "0,0":
            assert v > cero, f"con la cuadrícula movida {k} quedan {v} fuera, contra {cero} sin moverla"
    # El contorno queda dentro del lienzo de la cuadrícula
    x0, y0, x1, y1 = r["bbox"]
    assert -1 <= x0 and -1 <= y0 and x1 <= indice["ancho"] + 1 and y1 <= indice["alto"] + 1, r["bbox"]


def test_hu_7_1_alineacion_contra_la_capa_de_municipios(abrir, indice):
    """El contorno que dibuja la página está donde la capa de municipios lo pone en la malla."""
    gpkg = RAIZ / "datos" / "edomex" / "municipios_edomex.gpkg"
    if not gpkg.exists():
        pytest.skip("falta datos/edomex/municipios_edomex.gpkg")
    import geopandas as gpd
    m = indice["malla"]
    x0, y0, x1, y1 = gpd.read_file(gpkg).to_crs(m["crs"]).total_bounds
    esperado = [(x0 - m["izq"]) / m["tam"], (m["arriba"] - y1) / m["tam"],
                (x1 - m["izq"]) / m["tam"], (m["arriba"] - y0) / m["tam"]]
    page, _ = abrir()
    bb = page.evaluate("(() => { const b = document.querySelector('path.contorno').getBBox(); "
                       "return [b.x, b.y, b.x + b.width, b.y + b.height]; })()")
    for a, b in zip(bb, esperado):
        assert a == pytest.approx(b, abs=1.0), (bb, esperado)  # menos de una celda (90 m)


def test_hu_7_1_tema_oscuro(browser, servidor, indice):
    ctx = browser.new_context(viewport={"width": 1366, "height": 900}, color_scheme="dark", locale="es-MX")
    page = ctx.new_page()
    reg = Registro(page)
    page.goto(servidor)
    esperar_lista(page)
    assert page.evaluate("getComputedStyle(document.documentElement).colorScheme").startswith("dark")
    assert page.locator("#evolucion circle.punto").count() == len(indice["anios"])
    captura(page, CAPTURAS / "hu_7_1_vista_inicial_oscuro.png", full_page=False)
    captura(page.locator("#evolucion"), CAPTURAS / "hu_7_1_evolucion_oscuro.png")
    assert reg.errores == [], reg.errores
    ctx.close()


def test_hu_7_1_archivo_falta_muestra_mensaje(page, servidor):
    """Si un archivo no llega, la página lo dice y ofrece reintentar (no se queda en blanco)."""
    page.route("**/datos/anios/*.json", lambda ruta: ruta.fulfill(status=404, body="no"))
    reg = Registro(page)
    page.goto(servidor)
    esperar_lista(page)
    page.locator("#evolucion button[data-t]").first.click()
    falla = page.locator("#falla")
    falla.wait_for(state="visible", timeout=10_000)
    assert "No se pudieron cargar los datos" in falla.inner_text()
    assert "anios/" in falla.inner_text()
    assert falla.get_by_role("button", name="Reintentar").is_visible()
    # Sigue mostrando la comparación que ya tenía
    assert page.locator("#modos button[aria-checked='true']").inner_text() == "Comparar años"
    assert all("anios/" in e or "404" in e for e in reg.errores), reg.errores


# ------------------------------------------------- Los dos modos de salida comparten los datos

def _embebidos():
    t = ARCHIVO_UNICO.read_text(encoding="utf-8")
    m = re.search(r'<script type="application/json" id="datos">(.*?)</script>', t, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))["archivos"]


def test_hu_7_1_archivo_unico_trae_los_mismos_datos_que_el_sitio(indice):
    emb = _embebidos()
    assert set(emb) == set(indice["archivos"]) | {"indice.json"}
    for ruta, v in emb.items():
        disco = DATOS / ruta
        if ruta.endswith(".png"):
            assert v == "data:image/png;base64," + base64.b64encode(disco.read_bytes()).decode("ascii"), ruta
        elif ruta == "indice.json":
            assert {k: x for k, x in v.items() if k != "generado"} == {k: x for k, x in indice.items() if k != "generado"}
        else:
            assert v == json.loads(disco.read_text(encoding="utf-8")), ruta


def test_hu_7_1_archivo_unico_funciona_sin_servidor(page, indice):
    reg = Registro(page)
    page.goto(ARCHIVO_UNICO.as_uri())
    esperar_lista(page)
    assert reg.errores == [], reg.errores
    assert not [u for u in reg.peticiones if "/datos/" in u], "el archivo único no debe pedir datos/"
    assert page.locator("#evolucion circle.punto").count() == len(indice["anios"])
