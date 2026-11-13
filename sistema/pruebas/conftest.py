"""Fixtures comunes. Los catálogos (municipios, Delegaciones, estados, reglas de CC) se cargan con los
mismos comandos que usa el sistema, a partir de reglas/*.json y datos/*.json."""
import io
import json
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from nucleo.catalogos import cargar_catalogos, cargar_reglas_disponibles
from nucleo.demo import CONTRASENA_DEMO, _pdf_demo, crear_usuarios
from nucleo.models import Ejercicio, Municipio, Usuario

RAIZ_SISTEMA = Path(__file__).resolve().parents[1]
ESPECIFICACION = RAIZ_SISTEMA / "especificacion"


def pytest_collection_modifyitems(items):
    """Los recorridos de Playwright (live_server vacía la base al terminar) van al final."""
    items.sort(key=lambda it: "e2e" in str(it.fspath))


def asegurar_catalogos():
    if not Municipio.objects.exists():
        cargar_catalogos()
        cargar_reglas_disponibles()
    if not Usuario.objects.filter(username="del_amecameca").exists():
        crear_usuarios()


@pytest.fixture(scope="session", autouse=True)
def archivos_temporales(tmp_path_factory):
    """Los archivos subidos y los acuses de las pruebas van a una carpeta temporal nueva."""
    from django.conf import settings

    settings.MEDIA_ROOT = str(tmp_path_factory.mktemp("archivos"))


@pytest.fixture(scope="session")
def django_db_setup(django_db_setup, django_db_blocker):
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
