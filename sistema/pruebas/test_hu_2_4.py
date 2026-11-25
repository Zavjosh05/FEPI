"""HU-2.4 · Reasignaciones e incidentes (sesiones de seguimiento del Comité)."""
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from dictamen import aprobacion, seguimiento, sesiones
from dictamen.models import MovimientoListado, TipoSesion
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


@pytest.fixture
def listados(cc, dictaminada, usuarios):
    """Acta con dos personas beneficiarias (5 ha a $2,000/ha = $10,000 cada una) y tres en lista de espera
    (lugares 1 a 3; la tercera de 8 ha = $16,000)."""
    def _crear():
        b1 = dictaminada(nombre="Beneficiaria Uno", ha=5)
        b2 = dictaminada(nombre="Beneficiaria Dos", municipio="Tlalmanalco", ha=5)
        e1 = dictaminada(nombre="Espera Uno", municipio="Ozumba", ha=5)
        e2 = dictaminada(nombre="Espera Dos", municipio="Ayapango", ha=5)
        e3 = dictaminada(nombre="Espera Tres", municipio="Juchitepec", ha=8)
        s = sesiones.crear_sesion(usuarios["comite"], cc, TipoSesion.APROBACION, fecha_sesion(6), "Sala", "Quórum\nListados")
        sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(), "Listado")
        sesiones.enviar_convocatoria(usuarios["comite"], s)
        aprobacion.proponer_listados(usuarios["comite"], s, Decimal("20000"))
        aprobacion.registrar_acta(usuarios["comite"], s, True, "Unanimidad", momento=despues_de(s))
        for e in (b1, b2, e1, e2, e3):
            e.refresh_from_db()
        assert [e.estado.clave for e in (b1, b2, e1, e2, e3)] == ["aprobada"] * 2 + ["lista_espera"] * 3
        return b1, b2, e1, e2, e3
    return _crear


def test_hu_2_4_criterios_y_necesidades_vienen_del_modelo(modelo):
    hu = historia(modelo, "HU-2.4")
    assert hu["titulo"] == "Reasignaciones e incidentes"
    assert len(hu["criterios"]) == 3
    assert "incidente" in hu["criterios"][0] and "causa" in hu["criterios"][0]
    assert "lista de espera, en su orden" in hu["criterios"][1] and "recurso liberado" in hu["criterios"][1]
    assert "trazabilidad" in hu["criterios"][2]
    assert "M2.4" in modelo["necesidad_a_funciones"]["PSA-COM-03"]


def test_hu_2_4_cada_incidente_tiene_acuerdo_con_causa_expedientes_y_area(cc, validada, usuarios):
    """Criterio 1: cada incidente tiene un acuerdo con su causa, los expedientes a los que aplica y el área que lo atiende;
    esa área lo ve pendiente."""
    a, b = validada(nombre="Uno"), validada(nombre="Dos", municipio="Tlalmanalco")
    s = _sesion(usuarios, cc)
    with pytest.raises(ValidationError, match="expedientes"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "suspension", "Suspender", [], causa="Omisiones")
    with pytest.raises(ValidationError, match="causa del incidente"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "suspension", "Suspender", [a, b])
    acuerdo = seguimiento.registrar_acuerdo(usuarios["comite"], s, "suspension",
                                            "Suspender el apoyo para subsanar omisiones (8.1.9 a)", [a, b],
                                            causa="Informe de la Delegación: omisiones en la bitácora")
    assert set(acuerdo.expedientes.all()) == {a, b} and acuerdo.causa.startswith("Informe")
    assert acuerdo.unidad_responsable.clave == "DRFF"   # unidad por omisión del tipo (datos/dictamen.json)
    assert acuerdo in seguimiento.acuerdos_pendientes(usuarios["dir_drff"].unidad)
    assert acuerdo not in seguimiento.acuerdos_pendientes(usuarios["juridica"].unidad)
    assert a.eventos.filter(tipo="acuerdo_comite", descripcion__contains="Causa: Informe").exists()
    otro = seguimiento.registrar_acuerdo(usuarios["comite"], s, "reintegro", "Requerir el reintegro", [a],
                                         Unidad.objects.get(clave="UJ"), causa="Recurso no ejercido")
    assert otro in seguimiento.acuerdos_pendientes(usuarios["juridica"].unidad)


def test_hu_2_4_desistimiento_da_de_baja_y_libera_el_recurso(cc, listados, usuarios):
    """Criterio 1 y 2: el desistimiento saca a la persona beneficiaria de la lista y libera su monto."""
    b1, b2, e1, e2, e3 = listados()
    s = _sesion(usuarios, cc)
    with pytest.raises(ValidationError, match="personas beneficiarias aprobadas"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "desistimiento", "Desiste", [e1], causa="Escrito")
    a = seguimiento.registrar_acuerdo(usuarios["comite"], s, "desistimiento", "Se acepta el desistimiento", [b1],
                                      causa="Escrito de desistimiento del 10/11/2026")
    b1.refresh_from_db()
    assert b1.estado.clave == "baja" and b1.estado.final
    assert a.monto_liberado == Decimal("10000.00") and seguimiento.recurso_liberado(cc) == Decimal("10000.00")
    m = MovimientoListado.objects.get(acuerdo=a)
    assert (m.expediente, m.movimiento, m.estado_anterior, m.estado_nuevo) == (b1, "sale", "aprobada", "baja")
    assert b1.eventos.filter(tipo="baja_comite", motivo__startswith="Escrito").exists()


def test_hu_2_4_reasignacion_sigue_el_orden_de_la_lista_de_espera(cc, listados, usuarios):
    """Criterio 2: entra la siguiente de la lista de espera, en su orden, sin rebasar el recurso liberado."""
    b1, b2, e1, e2, e3 = listados()
    s = _sesion(usuarios, cc)
    with pytest.raises(ValidationError, match="no alcanza"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "reasignacion", "Reasignar", [e1])   # nada liberado aún
    seguimiento.registrar_acuerdo(usuarios["comite"], s, "cancelacion", "Cancelar el apoyo", [b2],
                                  causa="Dictamen de cancelación por falsedad de información")
    with pytest.raises(ValidationError, match="orden de la lista de espera"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "reasignacion", "Reasignar", [e2])  # se salta a e1
    with pytest.raises(ValidationError, match="no alcanza"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "reasignacion", "Reasignar", [e1, e2])  # $20,000 > $10,000
    a = seguimiento.registrar_acuerdo(usuarios["comite"], s, "reasignacion", "Reasignar a la primera de la lista", [e1])
    e1.refresh_from_db()
    assert e1.estado.clave == "aprobada" and a.monto_reasignado == Decimal("10000.00")
    assert seguimiento.recurso_liberado(cc) == Decimal("0.00")
    entra = MovimientoListado.objects.get(acuerdo=a)
    assert (entra.movimiento, entra.lugar_lista_espera, entra.estado_anterior) == ("entra", 1, "lista_espera")
    assert [x["expediente"] for x in seguimiento.lista_de_espera(cc)] == [e2, e3]   # e2 ahora es la primera


def test_hu_2_4_sustitucion_en_un_solo_acuerdo(cc, listados, usuarios):
    """Criterio 2 (sustitución): sale la persona beneficiaria y entra la siguiente de la lista en el mismo acuerdo."""
    b1, b2, e1, e2, e3 = listados()
    s = _sesion(usuarios, cc)
    with pytest.raises(ValidationError, match="sale al menos una"):
        seguimiento.registrar_acuerdo(usuarios["comite"], s, "sustitucion", "Sustituir", [b1], causa="Fallecimiento")
    a = seguimiento.registrar_acuerdo(usuarios["comite"], s, "sustitucion", "Sustituir a la persona beneficiaria", [b1, e1],
                                      causa="Fallecimiento de la persona titular sin segunda persona beneficiaria")
    b1.refresh_from_db()
    e1.refresh_from_db()
    assert (b1.estado.clave, e1.estado.clave) == ("baja", "aprobada")
    assert a.monto_liberado == a.monto_reasignado == Decimal("10000.00")
    assert set(a.movimientos.values_list("movimiento", flat=True)) == {"sale", "entra"}


def test_hu_2_4_incidente_sin_efecto_solo_deja_constancia(cc, listados, usuarios):
    b1, *_ = listados()
    s = _sesion(usuarios, cc)
    a = seguimiento.registrar_acuerdo(usuarios["comite"], s, "caso_fortuito", "Atender el caso fortuito", [b1],
                                      causa="Incendio en la parte baja del predio")
    b1.refresh_from_db()
    assert b1.estado.clave == "aprobada" and not a.movimientos.exists()


def test_hu_2_4_trazabilidad(cc, listados, usuarios):
    """Criterio 3: el acuerdo, los cambios de estado y los movimientos quedan en el historial con su usuario."""
    from nucleo.trazabilidad import historial_expediente

    b1, b2, e1, *_ = listados()
    s = _sesion(usuarios, cc)
    a = seguimiento.registrar_acuerdo(usuarios["comite"], s, "sustitucion", "Sustituir", [b1, e1], causa="Desistimiento")
    assert a.history.get(history_type="+").history_user == usuarios["comite"]
    assert all(m.history.get().history_user == usuarios["comite"] for m in a.movimientos.all())
    b1.refresh_from_db()
    assert b1.history.filter(estado__clave="baja", history_user=usuarios["comite"]).exists()
    filas = historial_expediente(e1)
    assert any(f["registro"] == "Movimiento de listado" and f["usuario"] == usuarios["comite"] for f in filas)
    assert any(f["registro"] == "Expediente" and any(c["antes"] == "Lista de espera" for c in f["cambios"]) for f in filas)


def test_hu_2_4_la_sesion_de_seguimiento_no_se_cierra_antes_de_celebrarse(cc, validada, usuarios):
    exp = validada()
    s = _sesion(usuarios, cc)
    seguimiento.registrar_acuerdo(usuarios["comite"], s, "caso_fortuito", "Atender el caso fortuito", [exp], causa="Aviso")
    with pytest.raises(ValidationError, match="antes de celebrarse"):
        seguimiento.cerrar_sesion(usuarios["comite"], s, "Cierre")
    seguimiento.cerrar_sesion(usuarios["comite"], s, "Cierre", momento=despues_de(s))
    s.refresh_from_db()
    assert s.estado == "celebrada" and s.acta_fecha > s.fecha_hora


def test_hu_2_4_acuerdo_pendiente_en_la_bandeja_y_cumplimiento(cc, validada, usuarios, client, contrasena):
    exp = validada()
    s = _sesion(usuarios, cc)
    acuerdo = seguimiento.registrar_acuerdo(usuarios["comite"], s, "caso_fortuito", "Atender el caso fortuito", [exp],
                                            causa="Aviso de la Delegación")
    client.login(username="dir_drff", password=contrasena)
    html = client.get("/bandeja/").content.decode()
    assert "Acuerdos del Comité pendientes de cumplir" in html and acuerdo.numero in html
    with pytest.raises(PermissionDenied):
        seguimiento.cumplir(usuarios["juridica"], acuerdo)
    r = client.post(f"/dictamen/acuerdos/{acuerdo.pk}/cumplir/", {"observaciones": "Atendido"})
    assert r.status_code == 302
    acuerdo.refresh_from_db()
    assert acuerdo.estado == "cumplido" and acuerdo.cumplido_por == usuarios["dir_drff"]
    assert acuerdo.history.filter(estado="cumplido", history_user=usuarios["dir_drff"]).exists()
    assert "Acuerdos del Comité pendientes de cumplir" not in client.get("/bandeja/").content.decode()


def test_hu_2_4_psahem_instruccion_de_pago_por_ministracion(psa, usuarios):
    """Acuerdo propio de PSAHEM (deja constancia): instrucción de pago de cada ministración a la Fiduciaria."""
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


def test_hu_2_4_peg_validacion_de_cada_periodo_de_reportes(peg, usuarios):
    """Acuerdo propio de PEG (deja constancia): validación de la evaluación de reportes de cada periodo."""
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
    monkeypatch.setitem(seguimiento.RECEPTORES, "caso_fortuito", [*seguimiento.RECEPTORES.get("caso_fortuito", []),
                                                                  llamados.append])
    a = seguimiento.registrar_acuerdo(usuarios["comite"], s, "caso_fortuito", "Atender", [exp], causa="Aviso")
    seguimiento.cumplir(usuarios["dir_drff"], a)
    assert llamados == [a]


def test_hu_2_4_pantalla_de_la_sesion_de_seguimiento(cc, listados, usuarios, client, contrasena):
    b1, b2, e1, e2, e3 = listados()
    s = _sesion(usuarios, cc)
    client.login(username="comite", password=contrasena)
    html = client.get(f"/dictamen/sesiones/{s.pk}/").content.decode()
    assert "Lista de espera (en su orden)" in html and e1.folio in html and "Recurso liberado sin reasignar" in html
    r = client.post(f"/dictamen/sesiones/{s.pk}/acuerdo/", {
        "tipo": "desistimiento", "descripcion": "Se acepta el desistimiento", "expedientes": [b1.pk], "unidad_responsable": ""})
    assert r.status_code == 302
    assert "causa del incidente" in client.get(f"/dictamen/sesiones/{s.pk}/").content.decode()
    r = client.post(f"/dictamen/sesiones/{s.pk}/acuerdo/", {
        "tipo": "desistimiento", "descripcion": "Se acepta el desistimiento", "expedientes": [b1.pk],
        "causa": "Escrito del 10/11/2026", "unidad_responsable": ""})
    r = client.post(f"/dictamen/sesiones/{s.pk}/acuerdo/", {
        "tipo": "reasignacion", "descripcion": "Reasignar", "expedientes": [e1.pk], "unidad_responsable": ""})
    html = client.get(f"/dictamen/sesiones/{s.pk}/").content.decode()
    assert "Escrito del 10/11/2026" in html and "Libera $10,000.00" in html and "Reasigna $10,000.00" in html
    e1.refresh_from_db()
    assert e1.estado.clave == "aprobada"
    html = client.get(f"/dictamen/beneficiarios/?ejercicio={cc.pk}").content.decode()
    assert "Reasignación · acuerdo" in html and b1.folio in html   # b1 aparece entre las que salieron
