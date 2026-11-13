import os
from pathlib import Path

import pytest

from pruebas.conftest import asegurar_catalogos

CAPTURAS = Path(os.environ.get("CAPTURAS_DIR", Path(__file__).resolve().parents[3] / "entregas" / "sprint_1" / "capturas"))


@pytest.fixture
def datos_e2e(transactional_db):
    asegurar_catalogos()


@pytest.fixture
def browser_context_args(browser_context_args):
    return {**browser_context_args, "viewport": {"width": 1366, "height": 900}, "locale": "es-MX",
            "timezone_id": "America/Mexico_City"}


@pytest.fixture
def captura(page):
    CAPTURAS.mkdir(parents=True, exist_ok=True)

    def _tomar(nombre, pagina=None):
        (pagina or page).screenshot(path=str(CAPTURAS / f"{nombre}.png"), full_page=True)
    return _tomar


@pytest.fixture
def entrar(page, live_server, contrasena):
    def _entrar(usuario):
        page.context.clear_cookies()
        page.goto(f"{live_server.url}/entrar/")
        page.fill("#id_username", usuario)
        page.fill("#id_password", contrasena)
        page.click("button[type=submit]")
        page.wait_for_url("**/bandeja/**")
    return _entrar
