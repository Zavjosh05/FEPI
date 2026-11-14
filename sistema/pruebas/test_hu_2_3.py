"""HU-2.3 · Sesión de aprobación."""
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from dictamen import aprobacion, sesiones
from dictamen.models import ResultadoListado, SesionComite, TipoSesion

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


@pytest.fixture
def sesion(cc, usuarios):
    def _crear(dias=6, caracter="ordinaria", documentos=1):
        s = sesiones.crear_sesion(usuarios["comite"], cc, TipoSesion.APROBACION, fecha_sesion(dias), "Sala de juntas",
                                  "Quórum\nListado preliminar\nAprobación de listados\nAutorización de publicación",
                                  caracter=caracter)
        for i in range(documentos):
            sesiones.agregar_documento(usuarios["comite"], s, documento_sesion(f"doc{i}.pdf"), f"Documento {i}")
        return s
    return _crear


def test_hu_2_3_criterios_y_necesidades_vienen_del_modelo(modelo):
    hu = historia(modelo, "HU-2.3")
    assert len(hu["criterios"]) == 2 and "autorización de publicación" in hu["criterios"][1]


def test_hu_2_3_existe_convocatoria_con_orden_del_dia_documentos_y_fecha_hora_de_envio(sesion, usuarios):
    """Criterio 1: existe la convocatoria con orden del día y documentos, y la fecha y la hora de su envío."""
    s = sesion()
    acuse = sesiones.enviar_convocatoria(usuarios["comite"], s)
    s.refresh_from_db()
    assert s.convocatoria_enviada and s.estado == "convocada" and s.acuse_convocatoria == acuse
    assert len(s.puntos) == 4 and s.documentos.count() == 1
    renglones = dict(acuse.contenido["renglones"])
    assert renglones["Fecha y hora del envío"] and "3 días hábiles" in renglones["Anticipación requerida"]
    assert acuse.expediente is None and acuse.archivo.open("rb").read(4) == b"%PDF"
    assert any("CONAFOR" in d["texto"] for d in acuse.contenido["detalle"])   # integrantes de CC.json


def test_hu_2_3_convocatoria_sin_anticipacion_o_sin_documentos_se_rechaza(sesion, usuarios):
    with pytest.raises(ValidationError, match="documentos"):
        sesiones.enviar_convocatoria(usuarios["comite"], sesion(documentos=0))
    tarde = sesion(dias=1)
    with pytest.raises(ValidationError, match="3 días hábiles"):
        sesiones.enviar_convocatoria(usuarios["comite"], tarde)
    extraordinaria = sesion(dias=2, caracter="extraordinaria")   # 24 horas (plazo de los datos)
    assert sesiones.enviar_convocatoria(usuarios["comite"], extraordinaria)


def test_hu_2_3_existe_acta_con_listados_aprobados_y_autorizacion_de_publicacion(sesion, dictaminada, usuarios):
    """Criterio 2: existe un acta con los listados aprobados y la autorización de publicación."""
    a = dictaminada(nombre="Predio Reforestado", ha=5)
    b = dictaminada(nombre="Predio Plantación", municipio="Tlalmanalco", modalidad="plantacion_maderable", ha=5)
    c = dictaminada(nombre="Predio Tarde", municipio="Ozumba", ha=5)
    d = dictaminada(nombre="Predio No Procedente", municipio="Ayapango", juridico_resultado="no_procedente")
    s = sesion()
    sesiones.enviar_convocatoria(usuarios["comite"], s)
    aprobacion.proponer_listados(usuarios["comite"], s, Decimal("20500"))   # alcanza para dos de 5 ha a $2,000/ha
    res = {r.expediente_id: r for r in s.resoluciones.all()}
    # Priorización: reforestaciones primero (8.1.2 fr. I), desempate por fecha de registro
    assert (res[a.pk].resultado, res[a.pk].orden) == (ResultadoListado.BENEFICIARIA, 1)
    assert (res[c.pk].resultado, res[c.pk].orden) == (ResultadoListado.BENEFICIARIA, 2)
    assert (res[b.pk].resultado, res[b.pk].orden) == (ResultadoListado.LISTA_ESPERA, 1)
    assert res[d.pk].resultado == ResultadoListado.NO_FACTIBLE
    acta = aprobacion.registrar_acta(usuarios["comite"], s, True, "Unanimidad", momento=despues_de(s))
    s.refresh_from_db()
    assert s.estado == "celebrada" and s.autoriza_publicacion and s.acuse_acta == acta
    assert "Sí" in dict(acta.contenido["renglones"])["Autorización de publicación"]
    assert any("$10,000.00" in x["texto"] for x in acta.contenido["detalle"])   # monto con separador de miles
    listados = {x["clave"] for x in acta.contenido["detalle"]}
    assert listados == {"Lista de Personas Beneficiarias", "Lista de espera", "Lista de solicitudes No factibles"}
    for exp, estado in [(a, "aprobada"), (c, "aprobada"), (b, "lista_espera"), (d, "no_factible")]:
        exp.refresh_from_db()
        assert exp.estado.clave == estado
    assert b.estado.flujo_alterno == "C" and d.estado.flujo_alterno == "B"


def test_hu_2_3_ajuste_del_orden_deja_constancia(sesion, dictaminada, usuarios):
    a = dictaminada(nombre="Primero", ha=5)
    b = dictaminada(nombre="Segundo", municipio="Tlalmanalco", ha=5)
    s = sesion()
    aprobacion.proponer_listados(usuarios["comite"], s)
    rb = s.resoluciones.get(expediente=b)
    with pytest.raises(ValidationError, match="motivo"):
        aprobacion.ajustar(usuarios["comite"], rb, "beneficiaria", 1, "")
    aprobacion.ajustar(usuarios["comite"], rb, "beneficiaria", 1, "Predio en Área Natural Protegida (8.1.2 fr. V)")
    rb.refresh_from_db()
    ra = s.resoluciones.get(expediente=a)
    assert (rb.orden, ra.orden) == (1, 2) and rb.ajustada and rb.orden_propuesto == 2
    assert rb.history.first().history_change_reason.startswith("Ajuste del Comité")
    assert b.eventos.filter(tipo="ajuste_comite").exists()


def test_hu_2_3_ajustado_solo_en_la_fila_que_el_comite_movio(sesion, dictaminada, usuarios, client, contrasena):
    a = dictaminada(nombre="Primero", ha=5)
    b = dictaminada(nombre="Segundo", municipio="Tlalmanalco", ha=5)
    c = dictaminada(nombre="Tercero", municipio="Ozumba", ha=5)
    s = sesion()
    aprobacion.proponer_listados(usuarios["comite"], s)
    aprobacion.ajustar(usuarios["comite"], s.resoluciones.get(expediente=c), "beneficiaria", 1, "Zona prioritaria")
    por_exp = {r.expediente_id: r for r in s.resoluciones.all()}
    assert [por_exp[x.pk].orden for x in (c, a, b)] == [1, 2, 3]      # a y b solo se recorrieron
    assert por_exp[c.pk].ajustada and por_exp[c.pk].motivo_ajuste == "Zona prioritaria"
    assert not por_exp[a.pk].ajustada and not por_exp[b.pk].ajustada
    assert por_exp[a.pk].motivo_ajuste == "" and por_exp[b.pk].motivo_ajuste == ""
    client.login(username="comite", password=contrasena)
    html = client.get(f"/dictamen/sesiones/{s.pk}/").content.decode()
    assert html.count("ajustado</span>") == 1 and html.count("Constancia:") == 1


def test_hu_2_3_no_factible_no_pasa_a_listados_de_apoyo(sesion, dictaminada, usuarios):
    d = dictaminada(tecnico_resultado="no_factible")
    s = sesion()
    aprobacion.proponer_listados(usuarios["comite"], s)
    with pytest.raises(ValidationError):
        aprobacion.ajustar(usuarios["comite"], s.resoluciones.get(expediente=d), "beneficiaria", 1, "Caso especial")


def test_hu_2_3_el_acta_no_se_registra_antes_de_la_sesion(sesion, dictaminada, usuarios):
    dictaminada()
    s = sesion()
    sesiones.enviar_convocatoria(usuarios["comite"], s)
    aprobacion.proponer_listados(usuarios["comite"], s)
    with pytest.raises(ValidationError, match="antes de la sesión"):
        aprobacion.registrar_acta(usuarios["comite"], s, True)
    with pytest.raises(ValidationError, match="antes de la sesión"):
        aprobacion.registrar_acta(usuarios["comite"], s, True, momento=s.fecha_hora - timedelta(minutes=1))
    s.refresh_from_db()
    assert s.estado == "convocada" and s.acuse_acta_id is None
    # Una sesión ya celebrada (convocada con su anticipación en una fecha pasada) sí admite el acta.
    pasada = sesion(dias=6)
    envio = pasada.fecha_hora - timedelta(days=15)
    sesiones.enviar_convocatoria(usuarios["comite"], pasada, momento=envio)
    pasada.refresh_from_db()
    assert pasada.convocatoria_enviada == envio
    tarde = sesion(dias=6)
    with pytest.raises(ValidationError, match="anticipación"):
        sesiones.enviar_convocatoria(usuarios["comite"], tarde, momento=tarde.fecha_hora - timedelta(days=1))


def test_hu_2_3_acta_requiere_convocatoria_y_la_hace_la_secretaria_tecnica(sesion, dictaminada, usuarios):
    dictaminada()
    s = sesion()
    aprobacion.proponer_listados(usuarios["comite"], s)
    with pytest.raises(ValidationError, match="convocatoria"):
        aprobacion.registrar_acta(usuarios["comite"], s, True)
    with pytest.raises(PermissionDenied):
        aprobacion.registrar_acta(usuarios["dir_drff"], s, True)


def test_hu_2_3_pantallas_de_la_sesion(sesion, dictaminada, client, contrasena):
    dictaminada()
    client.login(username="comite", password=contrasena)
    assert "Bandeja de Secretaría Técnica del Comité" in client.get("/bandeja/").content.decode()
    r = client.post("/dictamen/sesiones/nueva/", {
        "ejercicio": client.get("/dictamen/sesiones/nueva/").context["form"].fields["ejercicio"].queryset.get(programa__clave="CC").pk,
        "tipo": "aprobacion", "caracter": "ordinaria",
        "fecha_hora": timezone.localtime(fecha_sesion(8)).strftime("%Y-%m-%dT%H:%M"), "lugar": "Sala",
        "orden_del_dia": "Quórum\nAprobación"})
    assert r.status_code == 302
    url = r["Location"]
    client.post(url + "documento/", {"archivo": documento_sesion(), "nombre": "Listado"})
    client.post(url + "convocar/")
    client.post(url + "proponer/", {"presupuesto": ""})
    r = client.get(url)
    assert "Lista de Personas Beneficiarias" in r.content.decode()
    # La sesión es dentro de 8 días hábiles: el acta no se registra todavía.
    client.post(url + "acta/", {"autoriza_publicacion": "on"})
    assert "Acta registrada" not in client.get(url).content.decode()
    SesionComite.objects.update(fecha_hora=timezone.now() - timedelta(hours=3))   # la sesión ya se celebró
    client.post(url + "acta/", {"autoriza_publicacion": "on"})
    assert "Acta registrada" in client.get(url).content.decode()


def test_hu_2_3_no_factible_solo_por_acuerdo_del_comite(validada, dictaminada, usuarios):
    """Las ROP (CC 9.4.3 fr. I) dejan al Comité aprobar la Lista de No factibles: ya no hay atajo validada -> no_factible."""
    from nucleo.models import TransicionNoPermitida

    exp = validada()
    for usuario in ("dir_drff", "juridica"):
        with pytest.raises(TransicionNoPermitida):
            exp.cambiar_estado("no_factible", usuarios[usuario], motivo="x")
    d = dictaminada(tecnico_resultado="no_factible", municipio="Tlalmanalco")
    with pytest.raises(TransicionNoPermitida):
        d.cambiar_estado("no_factible", usuarios["dir_drff"], motivo="x")
