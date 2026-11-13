"""HU-2.2 · Dictamen jurídico."""
import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from dictamen import juridico
from dictamen.models import DictamenJuridico, PersonaIncumplida, PredioSancionado

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def test_hu_2_2_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-2.2")
    assert len(hu["criterios"]) == 2 and "Listado de Personas Beneficiarias Incumplidas" in hu["criterios"][1]
    assert "M2.2" in modelo["necesidad_a_funciones"]["CC-UJ-01"]


def test_hu_2_2_cada_solicitud_tiene_dictamen_juridico_con_motivo(validada, usuarios):
    """Criterio 1: cada solicitud tiene un dictamen jurídico procedente o no procedente, con su motivo."""
    exp = validada()
    with pytest.raises(ValidationError, match="motivo"):
        juridico.dictaminar(usuarios["juridica"], exp, "procedente", "")
    d = juridico.dictaminar(usuarios["juridica"], exp, "procedente", "Escritura pública vigente y CURP actualizada.")
    assert d.resultado == "procedente" and d.motivo and d.cotejo == []
    assert d.acuse.archivo.open("rb").read(4) == b"%PDF"
    assert exp.eventos.filter(tipo="dictamen_juridico").exists()


def test_hu_2_2_no_procedente_con_motivo(validada, usuarios):
    exp = validada()
    d = juridico.dictaminar(usuarios["juridica"], exp, "no_procedente", "Constancia de posesión sin firmas del comisariado.")
    assert d.get_resultado_display() == "No procedente"


def test_hu_2_2_titular_en_el_listado_de_incumplidas_es_no_procedente(validada, usuarios):
    """Criterio 2: una solicitud cuyo titular está en el Listado es no procedente (se impide en el servicio)."""
    juridico.registrar_incumplida(usuarios["juridica"], nombre="Rogelio Bautista Núñez", curp="BANR600101HMCTXG09",
                                  motivo="No realizó las actividades de 2024")
    exp = validada(curp="BANR600101HMCTXG09", solicitante="R. Bautista")
    cotejo = juridico.cotejar(exp)
    assert cotejo and cotejo[0]["coincide_por"] == "CURP"
    with pytest.raises(ValidationError, match="No puede ser procedente"):
        juridico.dictaminar(usuarios["juridica"], exp, "procedente", "Todo en orden")
    assert not DictamenJuridico.objects.filter(expediente=exp).exists()
    d = juridico.dictaminar(usuarios["juridica"], exp, "no_procedente", "Está en el Listado de Incumplidas")
    assert d.cotejo[0]["catalogo"].startswith("Listado")


def test_hu_2_2_cotejo_por_nombre_sin_acentos(validada, usuarios):
    juridico.registrar_incumplida(usuarios["juridica"], nombre="José Pérez Ávila", motivo="Adeudo con PROBOSQUE")
    exp = validada(solicitante="JOSE PEREZ AVILA")
    assert juridico.cotejar(exp)[0]["coincide_por"] == "nombre"


def test_hu_2_2_predio_con_sancion_es_no_procedente(validada, usuarios):
    """Criterio 2 (predio): un predio con procedimiento o sanción tampoco puede quedar procedente."""
    exp = validada()
    juridico.registrar_predio_sancionado(usuarios["juridica"], predio=exp.predio, descripcion_predio=exp.predio.nombre,
                                         tipo="sancion", descripcion="Multa por aprovechamiento sin autorización")
    with pytest.raises(ValidationError):
        juridico.dictaminar(usuarios["juridica"], exp, "procedente", "x")
    PredioSancionado.objects.update(reintegro_realizado=True)  # con el reintegro deja de impedir (8.1.1.1 fr. III)
    assert juridico.cotejar(exp) == []


def test_hu_2_2_baja_del_listado_queda_en_el_historial(validada, usuarios):
    p = juridico.registrar_incumplida(usuarios["juridica"], nombre="Persona Baja", motivo="Incumplimiento")
    exp = validada(solicitante="Persona Baja")
    assert juridico.cotejar(exp)
    juridico.dar_de_baja(usuarios["juridica"], p, "Reintegró el recurso (acuerdo del Comité)")
    assert juridico.cotejar(exp) == []
    p.refresh_from_db()
    assert PersonaIncumplida.objects.filter(pk=p.pk).exists() and not p.activa
    assert p.history.count() == 2 and p.history.first().history_change_reason.startswith("Reintegró")


def test_hu_2_2_refrendo_tambien_lleva_dictamen_juridico(validada, usuarios):
    exp = validada(refrendo=True)
    d = juridico.dictaminar(usuarios["juridica"], exp, "procedente", "Refrendo con documentación vigente")
    assert "10.1 fr. IV" in dict(d.acuse.contenido["renglones"])["Refrendo"]


def test_hu_2_2_solo_la_unidad_juridica_dictamina_y_edita_el_listado(validada, usuarios):
    exp = validada()
    with pytest.raises(PermissionDenied):
        juridico.dictaminar(usuarios["dir_drff"], exp, "procedente", "x")
    with pytest.raises(PermissionDenied):
        juridico.registrar_incumplida(usuarios["dir_drff"], nombre="X", motivo="Y")


def test_hu_2_2_pantallas_de_dictamen_y_catalogo(validada, client, contrasena):
    exp = validada()
    client.login(username="juridica", password=contrasena)
    assert "Bandeja de Unidad Jurídica" in client.get("/bandeja/").content.decode()
    r = client.get(f"/dictamen/juridico/{exp.folio}/")
    assert r.status_code == 200 and "Cotejo automático" in r.content.decode()
    r = client.post("/dictamen/incumplidas/", {"catalogo": "persona", "persona-nombre": "Persona Solicitante M2",
                                               "persona-motivo": "Incumplimiento 2025", "persona-fecha_inscripcion": "2026-01-10"})
    assert r.status_code == 302
    r = client.post(f"/dictamen/juridico/{exp.folio}/", {"resultado": "procedente", "motivo": "Todo bien"})
    assert r.status_code == 200 and "No puede ser procedente" in r.content.decode()
    r = client.post(f"/dictamen/juridico/{exp.folio}/", {"resultado": "no_procedente", "motivo": "En el Listado"})
    assert r.status_code == 302
