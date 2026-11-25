"""HU-2.2 · Dictamen jurídico: documentación legal, propiedad o legal posesión del predio y cotejo."""
import hashlib
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from dictamen import documentos, juridico
from dictamen.models import DictamenJuridico, PersonaIncumplida, PredioSancionado, RevisionPropiedad
from nucleo.models import TipoDocumento

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def _dictaminar(usuarios, exp, resultado, motivo, **propiedad):
    return juridico.dictaminar(usuarios["juridica"], exp, resultado, motivo, propiedad=propiedad_en_regla(exp, **propiedad))


def test_hu_2_2_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-2.2")
    assert len(hu["criterios"]) == 4
    assert "documento PDF" in hu["criterios"][0]
    assert "propiedad o legal posesión" in hu["criterios"][1]
    assert "Listado de Personas Beneficiarias Incumplidas" in hu["criterios"][2]
    assert "trazabilidad" in hu["criterios"][3]
    assert "propiedad o legal posesión" in hu["desea"]
    assert "M2.2" in modelo["necesidad_a_funciones"]["CC-UJ-01"]


def test_hu_2_2_cada_solicitud_tiene_dictamen_juridico_con_motivo_y_documento(validada, usuarios):
    """Criterio 1: cada solicitud tiene un dictamen jurídico con su motivo, expedido como PDF y adjunto al expediente."""
    exp = validada()
    with pytest.raises(ValidationError, match="motivo"):
        _dictaminar(usuarios, exp, "procedente", "")
    d = _dictaminar(usuarios, exp, "procedente", "Escritura pública vigente y CURP actualizada.")
    assert d.resultado == "procedente" and d.motivo and d.cotejo == []
    assert d.folio == f"DJ-CC-{exp.ejercicio.anio}-0001"
    assert d.documento.expediente == exp and d.documento.tipo == TipoDocumento.DICTAMEN
    contenido = d.documento.archivo.open("rb").read()
    assert contenido[:4] == b"%PDF" and hashlib.sha256(contenido).hexdigest() == d.huella
    html = documentos.html_juridico(d, d.folio)
    for texto in ("DICTAMEN JURÍDICO", "Revisión de la documentación legal", "Acreditación de la propiedad",
                  "Se acredita la propiedad", "Cotejo con el Listado", "PROCEDENTE", exp.folio):
        assert texto in html
    assert exp.eventos.filter(tipo="dictamen_juridico", datos__folio=d.folio).exists()


def test_hu_2_2_no_procedente_con_motivo(validada, usuarios):
    exp = validada()
    d = _dictaminar(usuarios, exp, "no_procedente", "Constancia de posesión sin firmas del comisariado.")
    assert d.get_resultado_display() == "No procedente" and d.documento is not None


def test_hu_2_2_la_revision_de_la_propiedad_es_obligatoria(validada, usuarios):
    exp = validada()
    with pytest.raises(ValidationError, match="propiedad o legal posesión"):
        juridico.dictaminar(usuarios["juridica"], exp, "no_procedente", "Sin revisar la propiedad")


@pytest.mark.parametrize("cambios, motivo", [
    ({"titular_coincide": False, "titular_documento": "Otra Persona"}, "no está a nombre del titular"),
    ({"superficie_documento_ha": Decimal("2")}, "el documento ampara 2"),
    ({"superficie_documento_ha": None}, "no indica la superficie"),
    ({"tipo_documento": "constancia_posesion", "vigente_hasta": None}, "falta la fecha de vigencia"),
    ({"tipo_documento": "constancia_posesion", "vigente_hasta": timezone.localdate() - timedelta(days=1)}, "venció"),
    ({"tipo_documento": "usufructo", "fecha_documento": timezone.localdate() - timedelta(days=30),
      "vigente_hasta": timezone.localdate() + timedelta(days=365 * 7)}, "plazo máximo de 5 años"),
    ({"sin_conflicto": False}, "conflicto de propiedad"),
    ({"tipo_documento": "carpeta_basica"}, "no corresponde a persona física"),
])
def test_hu_2_2_sin_propiedad_acreditada_es_no_procedente(validada, usuarios, cambios, motivo):
    """Criterio 2: si no se acredita la propiedad o legal posesión (titular, superficie, vigencia, conflicto, tipo de
    documento), el dictamen no puede ser procedente; queda registrada la revisión con el motivo."""
    exp = validada()
    with pytest.raises(ValidationError, match="no se acredita la propiedad"):
        _dictaminar(usuarios, exp, "procedente", "Todo en orden", **cambios)
    assert not DictamenJuridico.objects.filter(expediente=exp).exists()
    d = _dictaminar(usuarios, exp, "no_procedente", "No se acredita la legal posesión", **cambios)
    assert not d.propiedad.acreditada and any(motivo in m for m in d.propiedad.motivos)


def test_hu_2_2_propiedad_acreditada_y_vigente(validada, usuarios):
    exp = validada(ha=6)
    d = _dictaminar(usuarios, exp, "procedente", "Constancia de posesión vigente del comisariado",
                    tipo_documento="constancia_posesion", superficie_documento_ha=Decimal("6.5"),
                    vigente_hasta=timezone.localdate() + timedelta(days=200))
    p = RevisionPropiedad.objects.get(dictamen=d)
    assert p.acreditada and p.vigente and p.superficie_suficiente and p.titular_coincide and p.motivos == []
    assert p.superficie_predio_ha == exp.poligonos.get(vigente=True).superficie_ha


def test_hu_2_2_documento_legal_no_valido_impide_procedente(validada, usuarios):
    exp = validada()
    legal = next(r for r in juridico.documentos_legales(exp) if r.estado == "entregado")
    marcas = {legal.requisito.clave: {"valido": False, "observacion": ""}}
    with pytest.raises(ValidationError, match="por qué no es válido"):
        juridico.dictaminar(usuarios["juridica"], exp, "no_procedente", "x", propiedad=propiedad_en_regla(exp),
                            documentacion=marcas)
    marcas[legal.requisito.clave]["observacion"] = "Copia ilegible"
    with pytest.raises(ValidationError, match="documentos legales no válidos"):
        juridico.dictaminar(usuarios["juridica"], exp, "procedente", "x", propiedad=propiedad_en_regla(exp),
                            documentacion=marcas)
    with pytest.raises(ValidationError, match="Marque como válido"):
        juridico.dictaminar(usuarios["juridica"], exp, "no_procedente", "x", propiedad=propiedad_en_regla(exp),
                            documentacion=marcas, exigir_revision=True)
    d = juridico.dictaminar(usuarios["juridica"], exp, "no_procedente", "Documento ilegible",
                            propiedad=propiedad_en_regla(exp), documentacion=marcas)
    fila = next(x for x in d.documentacion if x["clave"] == legal.requisito.clave)
    assert fila["valido"] is False and fila["observacion"] == "Copia ilegible"
    assert all(x["aplica"] is False for x in d.documentacion if x["estado"] == "No aplica")


def test_hu_2_2_titular_en_el_listado_de_incumplidas_es_no_procedente(validada, usuarios):
    """Criterio 3: una solicitud cuyo titular está en el Listado es no procedente (se impide en el servicio)."""
    juridico.registrar_incumplida(usuarios["juridica"], nombre="Rogelio Bautista Núñez", curp="BANR600101HMCTXG09",
                                  motivo="No realizó las actividades de 2024")
    exp = validada(curp="BANR600101HMCTXG09", solicitante="R. Bautista")
    cotejo = juridico.cotejar(exp)
    assert cotejo and cotejo[0]["coincide_por"] == "CURP"
    with pytest.raises(ValidationError, match="No puede ser procedente"):
        _dictaminar(usuarios, exp, "procedente", "Todo en orden")
    assert not DictamenJuridico.objects.filter(expediente=exp).exists()
    d = _dictaminar(usuarios, exp, "no_procedente", "Está en el Listado de Incumplidas")
    assert d.cotejo[0]["catalogo"].startswith("Listado")


def test_hu_2_2_cotejo_por_nombre_sin_acentos(validada, usuarios):
    juridico.registrar_incumplida(usuarios["juridica"], nombre="José Pérez Ávila", motivo="Adeudo con PROBOSQUE")
    exp = validada(solicitante="JOSE PEREZ AVILA")
    assert juridico.cotejar(exp)[0]["coincide_por"] == "nombre"


def test_hu_2_2_predio_con_sancion_es_no_procedente(validada, usuarios):
    """Criterio 3 (predio): un predio con procedimiento o sanción tampoco puede quedar procedente."""
    exp = validada()
    juridico.registrar_predio_sancionado(usuarios["juridica"], predio=exp.predio, descripcion_predio=exp.predio.nombre,
                                         tipo="sancion", descripcion="Multa por aprovechamiento sin autorización")
    with pytest.raises(ValidationError):
        _dictaminar(usuarios, exp, "procedente", "x")
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
    assert p.history.first().history_user == usuarios["juridica"]


def test_hu_2_2_refrendo_tambien_lleva_dictamen_juridico(validada, usuarios):
    exp = validada(refrendo=True)
    d = _dictaminar(usuarios, exp, "procedente", "Refrendo con documentación vigente")
    assert "10.1 fr. IV" in documentos.html_juridico(d, d.folio)


def test_hu_2_2_solo_la_unidad_juridica_dictamina_y_edita_el_listado(validada, usuarios):
    exp = validada()
    with pytest.raises(PermissionDenied):
        juridico.dictaminar(usuarios["dir_drff"], exp, "procedente", "x", propiedad=propiedad_en_regla(exp))
    with pytest.raises(PermissionDenied):
        juridico.registrar_incumplida(usuarios["dir_drff"], nombre="X", motivo="Y")


def test_hu_2_2_trazabilidad(validada, usuarios):
    """Criterio 4: el dictamen, la revisión de la propiedad y el documento quedan en el historial con su usuario."""
    exp = validada()
    d = _dictaminar(usuarios, exp, "procedente", "Todo en orden")
    assert d.history.filter(history_type="+", history_user=usuarios["juridica"]).exists()
    assert d.history.filter(folio=d.folio, history_change_reason__startswith="Se expide").exists()
    assert d.propiedad.history.get().history_user == usuarios["juridica"]
    from nucleo.trazabilidad import historial_expediente
    registros = {f["registro"] for f in historial_expediente(exp) if f["usuario"] == usuarios["juridica"]}
    assert {"Dictamen jurídico", "Propiedad o posesión", "Documento"} <= registros


def _post_dictamen(exp, **extra):
    datos = {"tipo_documento": "escritura", "numero_documento": "123", "titular_documento": exp.solicitante.nombre,
             "titular_coincide": "si", "superficie_documento_ha": "50", "sin_conflicto": "si"}
    for r in juridico.documentos_legales(exp):
        if r.estado != "no_aplica":
            datos[f"doc_{r.requisito.clave}"] = "si"
    datos.update(extra)
    return datos


def test_hu_2_2_pantallas_de_dictamen_y_catalogo(validada, client, contrasena):
    exp = validada()
    client.login(username="juridica", password=contrasena)
    assert "Bandeja de Unidad Jurídica" in client.get("/bandeja/").content.decode()
    r = client.get(f"/dictamen/juridico/{exp.folio}/")
    html = r.content.decode()
    assert r.status_code == 200 and "Cotejo automático" in html and "Propiedad o legal posesión del predio" in html
    r = client.post("/dictamen/incumplidas/", {"catalogo": "persona", "persona-nombre": "Persona Solicitante M2",
                                               "persona-motivo": "Incumplimiento 2025", "persona-fecha_inscripcion": "2026-01-10"})
    assert r.status_code == 302
    r = client.post(f"/dictamen/juridico/{exp.folio}/", _post_dictamen(exp, resultado="procedente", motivo="Todo bien"))
    assert r.status_code == 200 and "No puede ser procedente" in r.content.decode()
    sin_marcar = _post_dictamen(exp, resultado="no_procedente", motivo="En el Listado")
    sin_marcar.pop(next(k for k in sin_marcar if k.startswith("doc_")))
    r = client.post(f"/dictamen/juridico/{exp.folio}/", sin_marcar)
    assert r.status_code == 200 and "Marque como válido" in r.content.decode()
    r = client.post(f"/dictamen/juridico/{exp.folio}/", _post_dictamen(exp, resultado="no_procedente", motivo="En el Listado"))
    assert r.status_code == 302
    d = DictamenJuridico.objects.get(expediente=exp)
    assert d.propiedad.acreditada and d.documento is not None
    html = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=dictamenes").content.decode()
    assert f"Documento del dictamen jurídico {d.folio}" in html and "acreditada" in html
