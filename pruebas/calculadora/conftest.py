"""Piezas comunes de las pruebas de la Calculadora forestal (sitio estático en docs/calculadora).

Sirve la carpeta con http.server en un puerto libre y abre la página en Chromium sin interfaz
(pytest-playwright). Las pruebas no regeneran el sitio: prueban lo que está en docs/; para
regenerarlo, ver «Página interactiva» en el README.
"""

from __future__ import annotations

import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SITIO = RAIZ / "docs" / "calculadora"
DATOS = SITIO / "datos"
ARCHIVO_UNICO = RAIZ / "docs" / "mapa_edomex.html"
SERIE = RAIZ / "resultados" / "edomex_serie_2023_2025"
CAPTURAS = RAIZ / "entregas" / "sprint_1" / "capturas"
VIEWPORT = {"width": 1366, "height": 900}


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="session", autouse=True)
def _carpeta_capturas():
    CAPTURAS.mkdir(parents=True, exist_ok=True)


def redondeo(x):
    """Entero más cercano, con .5 hacia arriba, como Intl.NumberFormat en la página."""
    import math
    return int(math.floor(x + 0.5))


def miles(x):
    """Hectáreas como las muestra la página (es-MX, sin decimales)."""
    return f"{redondeo(x):,}"


@pytest.fixture(scope="session")
def indice():
    return json.loads((DATOS / "indice.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def servidor():
    """URL de docs/calculadora servida en 127.0.0.1 con un puerto libre."""
    if not (SITIO / "index.html").exists():
        pytest.fail("No existe docs/calculadora/index.html: genera el sitio con src/mapa_interactivo.py --sitio")
    manejador = functools.partial(_Silencioso, directory=str(SITIO))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), manejador)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/"
    srv.shutdown()
    srv.server_close()


@pytest.fixture
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": VIEWPORT, "locale": "es-MX"}


class Registro:
    """Errores de consola y peticiones de la página."""

    def __init__(self, page):
        self.errores, self.peticiones = [], []
        page.on("console", lambda m: self.errores.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: self.errores.append(str(e)))
        page.on("requestfailed", lambda r: self.errores.append(f"falló {r.url}"))
        page.on("request", lambda r: self.peticiones.append(r.url))

    def datos(self, base):
        """Rutas pedidas dentro de datos/ (relativas a datos/)."""
        return [u.removeprefix(base + "datos/") for u in self.peticiones if u.startswith(base + "datos/")]


def esperar_lista(page, capa=None):
    """Espera a que la página termine de cargar lo que pide y pinte el ráster de la vista
    (o, si se da, la cuadrícula `capa`, p. ej. "bosque_2023.png")."""
    page.wait_for_function(
        """capa => {
            const c = document.getElementById("cargando");
            const r = document.querySelector("image.raster");
            const coropleta = document.getElementById("mapa").classList.contains("vista-coropleta");
            const pintada = r && (r.getAttribute("href") || "").startsWith("data:")
                && (!capa || r.getAttribute("data-capa") === capa);
            return c && c.hidden && document.querySelectorAll("#filas tr").length > 0 && (coropleta || pintada);
        }""", arg=capa, timeout=30_000)


@pytest.fixture
def abrir(page, servidor):
    """Abre la página y regresa (page, registro)."""
    def _abrir(url=None):
        reg = Registro(page)
        page.goto(url or servidor)
        esperar_lista(page)
        return page, reg
    return _abrir
