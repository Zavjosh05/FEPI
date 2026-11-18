"""HU-2.4 · Sesiones de seguimiento."""
import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from dictamen import seguimiento, sesiones
from dictamen.models import TipoSesion
from nucleo.models import Unidad

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def _sesion(usuarios, ejercicio):
    s = sesiones.crear_sesion(usuarios["comite"], ejercicio, TipoSesion.SEGUIMIENTO, fecha_sesion(6), "Sala",
                              "Quórum\nSeguimiento de casos")
    sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(), "Casos")
    sesiones.enviar_convocatoria(usuarios["comite"], s)
    return s


def test_hu_2_4_criterios_y_necesidades_vienen_del_modelo(modelo):
    hu = historia(modelo, "HU-2.4")
    assert len(hu["criterios"]) == 2 and "instrucción de pago" in hu["criterios"][1]
    assert "M2.4" in modelo["necesidad_a_funciones"]["PSA-COM-03"]


def test_hu_2_4_cada_acuerdo_indica_expedientes_y_area_que_debe_cumplirlo(cc, validada, usuarios):
    """Criterio 1: cada acuerdo indica a qué expedientes aplica y qué área debe cumplirlo; esa área lo ve pendiente."""
    a, b = validada(nombre="Uno"), validada(nombre="Dos", municipio="Tlalmanalco")
    s = _sesion(usuarios, cc)
    with pytest.raises(ValidationError, match="expedientes"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "suspension", "Suspender", [])
    acuerdo = seguimiento.registrar_acuerdo(usuarios["comite"], s, "suspension",
                                            "Suspender el apoyo para subsanar omisiones (8.1.9 a)", [a, b])
    assert set(acuerdo.expedientes.all()) == {a, b}
    assert acuerdo.unidad_responsable.clave == "DRFF"   # unidad por omisión del tipo (datos/dictamen.json)
    assert acuerdo in seguimiento.acuerdos_pendientes(usuarios["dir_drff"].unidad)
    assert acuerdo not in seguimiento.acuerdos_pendientes(usuarios["juridica"].unidad)
    assert a.eventos.filter(tipo="acuerdo_comite").exists()
    otro = seguimiento.registrar_acuerdo(usuarios["comite"], s, "reintegro", "Requerir el reintegro", [a],
                                         Unidad.objects.get(clave="UJ"))
    assert otro in seguimiento.acuerdos_pendientes(usuarios["juridica"].unidad)


def test_hu_2_4_la_sesion_de_seguimiento_no_se_cierra_antes_de_celebrarse(cc, validada, usuarios):
    exp = validada()
    s = _sesion(usuarios, cc)
    seguimiento.registrar_acuerdo(usuarios["comite"], s, "caso_fortuito", "Atender el caso fortuito", [exp])
    with pytest.raises(ValidationError, match="antes de celebrarse"):
        seguimiento.cerrar_sesion(usuarios["comite"], s, "Cierre")
    seguimiento.cerrar_sesion(usuarios["comite"], s, "Cierre", momento=despues_de(s))
    s.refresh_from_db()
    assert s.estado == "celebrada" and s.acta_fecha > s.fecha_hora


def test_hu_2_4_acuerdo_pendiente_en_la_bandeja_y_cumplimiento(cc, validada, usuarios, client, contrasena):
    exp = validada()
    s = _sesion(usuarios, cc)
    acuerdo = seguimiento.registrar_acuerdo(usuarios["comite"], s, "caso_fortuito", "Atender el caso fortuito", [exp])
    client.login(username="dir_drff", password=contrasena)
    html = client.get("/bandeja/").content.decode()
    assert "Acuerdos del Comité pendientes de cumplir" in html and acuerdo.numero in html
    with pytest.raises(PermissionDenied):
        seguimiento.cumplir(usuarios["juridica"], acuerdo)
    r = client.post(f"/dictamen/acuerdos/{acuerdo.pk}/cumplir/", {"observaciones": "Atendido"})
    assert r.status_code == 302
    acuerdo.refresh_from_db()
    assert acuerdo.estado == "cumplido" and acuerdo.cumplido_por == usuarios["dir_drff"]
    assert "Acuerdos del Comité pendientes de cumplir" not in client.get("/bandeja/").content.decode()


def test_hu_2_4_psahem_existe_instruccion_de_pago_por_ministracion(psa, usuarios):
    """Criterio 2 (PSAHEM): existe la instrucción de pago de cada ministración, dirigida a la Fiduciaria."""
    exp = registrar_validada(usuarios, psa, nombre="Predio PSA", modalidad=None)
    s = _sesion(usuarios, psa)
    assert seguimiento.ministraciones_sin_instruccion(exp) == [1, 2]
    with pytest.raises(ValidationError, match="ministración"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "instruccion_pago", "Pagar", [exp])
    with pytest.raises(ValidationError, match="no tiene la ministración 3"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "instruccion_pago", "Pagar", [exp], ministracion=3)
    primera = seguimiento.registrar_acuerdo(usuarios["comite"], s, "instruccion_pago",
                                            "Instruir a la Fiduciaria el pago del 70 %", [exp], ministracion=1)
    assert primera.unidad_responsable.tipo == "fiduciaria"
    assert seguimiento.ministraciones_sin_instruccion(exp) == [2]
    seguimiento.registrar_acuerdo(usuarios["comite"], s, "instruccion_pago", "Pago del 30 %", [exp], ministracion=2)
    assert seguimiento.ministraciones_sin_instruccion(exp) == []


def test_hu_2_4_peg_existe_validacion_de_cada_periodo_de_reportes(peg, usuarios):
    """Criterio 2 (PEG): existe la validación de la evaluación de reportes de cada periodo."""
    exp = registrar_peg(usuarios, peg, nombre="Guardabosque")
    s = _sesion(usuarios, peg)
    with pytest.raises(ValidationError, match="periodo"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "validacion_reportes", "Validar", [exp])
    with pytest.raises(ValidationError, match="no es un periodo de reportes"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "validacion_reportes", "Validar", [exp], periodo="2026-T1")
    # Los periodos son los 12 meses del ejercicio que trae reglas/PEG.json (derivados: las ROP no publican el calendario).
    assert len(seguimiento.periodos_sin_validacion(peg)) == 12
    acuerdo = seguimiento.registrar_acuerdo(usuarios["comite"], s, "validacion_reportes",
                                            "Se valida la evaluación de los reportes de enero", [exp], periodo="2026-01")
    assert acuerdo.unidad_responsable.clave == "DPF"
    assert seguimiento.periodos_sin_validacion(peg)[:2] == ["2026-02", "2026-03"]
    assert len(seguimiento.periodos_sin_validacion(peg)) == 11


def test_hu_2_4_acuerdos_propios_de_otro_programa_no_aplican(cc, validada, usuarios):
    exp = validada()
    s = _sesion(usuarios, cc)
    with pytest.raises(ValidationError, match="no aplica"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "instruccion_pago", "Pagar", [exp], ministracion=1)


def test_hu_2_4_punto_de_conexion_con_los_modulos_siguientes(cc, validada, usuarios, monkeypatch):
    exp = validada()
    s = _sesion(usuarios, cc)
    llamados = []
    # Se agrega un receptor más y se restaura la lista al terminar (M6 ya registra los suyos, HU-6.1).
    monkeypatch.setitem(seguimiento.RECEPTORES, "sustitucion", [*seguimiento.RECEPTORES.get("sustitucion", []), llamados.append])
    a = seguimiento.registrar_acuerdo(usuarios["comite"], s, "sustitucion", "Sustituir", [exp])
    seguimiento.cumplir(usuarios["dir_drff"], a)
    assert llamados == [a]


def test_hu_2_4_pantalla_de_la_sesion_de_seguimiento(cc, validada, usuarios, client, contrasena):
    exp = validada()
    s = _sesion(usuarios, cc)
    client.login(username="comite", password=contrasena)
    r = client.post(f"/dictamen/sesiones/{s.pk}/acuerdo/", {
        "tipo": "cancelacion", "descripcion": "Cancelar el apoyo", "expedientes": [exp.pk], "unidad_responsable": ""})
    assert r.status_code == 302
    html = client.get(f"/dictamen/sesiones/{s.pk}/").content.decode()
    assert "Cancelar el apoyo" in html and "Unidad Jurídica" in html
