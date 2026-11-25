"""Fixtures comunes. Los catálogos (municipios, Delegaciones, estados, reglas de CC) se cargan con los
mismos comandos que usa el sistema, a partir de reglas/*.json y datos/*.json."""
import io
import json
import os
import re
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from nucleo.catalogos import cargar_catalogos, cargar_reglas_disponibles
from nucleo.demo import CONTRASENA_DEMO, _pdf_demo, crear_usuarios
from nucleo.models import Ejercicio, Municipio, Usuario

# La demostración toma por fecha de corte el día de la carga (D-32); las pruebas la fijan en la fecha de corte de referencia
# para ser deterministas (las que prueban otra la cambian con monkeypatch).
os.environ["DEMO_FECHA_CORTE"] = "2026-11-19"

RAIZ_SISTEMA = Path(__file__).resolve().parents[1]
ESPECIFICACION = RAIZ_SISTEMA / "especificacion"


def pytest_collection_modifyitems(items):
    """Todo lo que usa Playwright (fixture `page` o `live_server`, o está en pruebas/e2e) lleva el marcador
    `navegador`; esas pruebas van al final porque live_server vacía la base al terminar."""
    for it in items:
        if "e2e" in str(it.fspath) or {"page", "live_server"} & set(getattr(it, "fixturenames", ())):
            it.add_marker(pytest.mark.navegador)
    items.sort(key=lambda it: it.get_closest_marker("navegador") is not None)


def asegurar_catalogos():
    if not Municipio.objects.exists():
        cargar_catalogos()
        cargar_reglas_disponibles()
    if not Usuario.objects.filter(username="del_amecameca").exists():
        crear_usuarios()


def pdf_real_forzado():
    """PDF_REAL=1 obliga a renderizar con WeasyPrint en toda la batería (se corre antes de cada entrega)."""
    return os.environ.get("PDF_REAL", "").strip().lower() in ("1", "true", "si", "sí", "yes")


def _pdf_ligero(html):
    """Sustituto de WeasyPrint: un PDF mínimo válido (empieza con %PDF) con el texto visible del documento, para que
    cada documento tenga su propia huella y se pueda buscar su texto."""
    from nucleo.demo import _pdf_demo

    html = re.sub(r"(?is)<(?:style|head|script)[ >].*?</(?:style|head|script)>", " ", html)
    texto = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()[:400]
    texto = texto.replace("\\", " ").replace("(", "[").replace(")", "]")
    return _pdf_demo(texto)


@pytest.fixture(autouse=True)
def pdf_ligero(request, monkeypatch):
    """Por omisión las pruebas no renderizan los PDF con WeasyPrint (4 a 8 s cada uno): usan `_pdf_ligero`.
    Conservan el render verdadero las marcadas `@pytest.mark.pdf_real`, las de navegador (descargan y abren
    documentos) y toda la batería con `PDF_REAL=1`."""
    if pdf_real_forzado() or request.node.get_closest_marker("pdf_real") or request.node.get_closest_marker("navegador"):
        return
    from nucleo import acuses

    monkeypatch.setattr(acuses, "_render_pdf", _pdf_ligero)


@pytest.fixture(scope="session", autouse=True)
def archivos_temporales(tmp_path_factory):
    """Los archivos subidos y los acuses de las pruebas van a una carpeta temporal nueva."""
    from django.conf import settings

    settings.MEDIA_ROOT = str(tmp_path_factory.mktemp("archivos"))


@pytest.fixture(scope="session", autouse=True)
def hash_rapido():
    """Las contraseñas de demostración se cifran con MD5 solo en las pruebas (PBKDF2 tarda ~0.5 s por inicio de
    sesión). Va antes de crear los usuarios de la base de pruebas."""
    from django.test.utils import override_settings

    with override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"]):
        yield


@pytest.fixture(scope="session")
def django_db_setup(hash_rapido, django_db_setup, django_db_blocker):
    """Carga los catálogos una sola vez en la base de pruebas (cada prueba corre en su transacción)."""
    with django_db_blocker.unblock():
        asegurar_catalogos()


@pytest.fixture
def catalogos(db):
    asegurar_catalogos()


@pytest.fixture
def cc(catalogos):
    return Ejercicio.objects.get(programa__clave="CC", anio=2026)


@pytest.fixture
def usuarios(catalogos):
    return {u.username: u for u in Usuario.objects.select_related("unidad")}


def _leer_contexto(nombre):
    ruta = ESPECIFICACION / nombre
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture
def modelo():
    return _leer_contexto("modelo.json")


@pytest.fixture
def necesidades():
    return _leer_contexto("necesidades_v12.json")


def historia(modelo, hu):
    return next(h for h in modelo["historias"] if h["id"] == hu)


@pytest.fixture
def pdf():
    def _crear(nombre="documento.pdf"):
        return SimpleUploadedFile(nombre, _pdf_demo(nombre), content_type="application/pdf")
    return _crear


@pytest.fixture
def nueva_solicitud(cc, usuarios):
    """Registra una solicitud de CC con los servicios del sistema."""
    from recepcion import servicios

    def _crear(usuario="del_amecameca", municipio="Amecameca", tipo="fisica", modalidad="reforestacion",
               refrendo=False, nombre="Predio de prueba", **extra):
        datos = servicios.DatosSolicitud(
            ejercicio=cc, municipio=Municipio.objects.get(nombre=municipio), nombre_predio=nombre,
            tipo_persona=cc.tipos_persona.get(clave=tipo),
            modalidad=cc.modalidades.get(clave=modalidad) if modalidad else None,
            solicitante_nombre="Persona Solicitante de Prueba", solicitante_tipo=tipo if tipo != "dependencia_publica" else "juridica_colectiva",
            es_refrendo=refrendo, **extra,
        )
        return servicios.registrar_solicitud(usuarios[usuario], datos)
    return _crear


@pytest.fixture
def contrasena():
    return CONTRASENA_DEMO
