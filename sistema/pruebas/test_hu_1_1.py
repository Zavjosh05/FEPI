"""HU-1.1 · Registro de la solicitud (criterios tomados de modelo.json)."""
import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from nucleo.models import Expediente, Municipio, Predio
from recepcion import servicios

from .conftest import historia

pytestmark = pytest.mark.django_db


def test_hu_1_1_criterios_y_necesidades_vienen_del_modelo(modelo, necesidades):
    hu = historia(modelo, "HU-1.1")
    assert hu["criterios"] == ["Se genera un folio único para la solicitud."]
    assert "CC-DRF-01" in modelo["necesidad_a_funciones"] and "M1.1" in modelo["necesidad_a_funciones"]["CC-DRF-01"]
    assert "municipio que atiende la Delegación" in necesidades["CC-DRF-01"]["texto"]


def test_hu_1_1_genera_folio_unico(nueva_solicitud):
    """Criterio: se genera un folio único para la solicitud (programa, ejercicio, Delegación y consecutivo)."""
    from django.db import IntegrityError, transaction

    exps = [nueva_solicitud(nombre=f"Predio {i}") for i in range(3)]
    exps.append(nueva_solicitud(usuario="del_toluca", municipio="Toluca", nombre="Predio de Toluca"))
    folios = [e.folio for e in exps]
    assert len(set(folios)) == len(folios)
    assert all(f.startswith("CC-2026-AME-") for f in folios[:3]) and folios[3].startswith("CC-2026-TOL-")
    # El consecutivo es del programa y ejercicio: no se repite aunque cambie la Delegación.
    numeros = [int(f.rsplit("-", 1)[1]) for f in folios]
    assert numeros == sorted(numeros) and len(set(numeros)) == len(numeros)
    # La base de datos tampoco admite dos expedientes con el mismo folio.
    exps[1].folio = exps[0].folio
    with pytest.raises(IntegrityError), transaction.atomic():
        exps[1].save(update_fields=["folio"])


@pytest.mark.pdf_real
def test_hu_1_1_existe_solicitud_asociada_al_predio_con_acuse(nueva_solicitud, usuarios):
    """Regla del registro: la solicitud queda asociada al predio y se emite su acuse con fecha y hora de recepción."""
    exp = nueva_solicitud(nombre="Predio El Pino")
    assert exp.predio.nombre == "Predio El Pino" and exp.predio.folio.startswith("PRED-")
    assert exp.estado.clave == "recibida"
    assert exp.delegacion == usuarios["del_amecameca"].unidad
    acuse = exp.acuses.get(tipo="recepcion")
    assert acuse.folio.startswith("AC-")
    assert acuse.fecha_hora == exp.fecha_recepcion or abs((acuse.fecha_hora - exp.fecha_recepcion).total_seconds()) < 5
    contenido = acuse.archivo.open("rb").read()
    assert contenido.startswith(b"%PDF") and len(acuse.huella) == 64
    assert any("Fecha y hora de recepción" == r[0] for r in acuse.contenido["renglones"])
    assert exp.eventos.filter(tipo="registro", acuse=acuse).exists()


def test_hu_1_1_acuse_pdf_lleva_folio_fecha_y_hora(nueva_solicitud):
    exp = nueva_solicitud()
    acuse = exp.acuses.get(tipo="recepcion")
    renglones = dict(acuse.contenido["renglones"])
    assert renglones["Fecha y hora de recepción"] == servicios.fmt_fecha_hora(exp.fecha_recepcion)
    assert acuse.folio in acuse.archivo.name and acuse.archivo.name.endswith(".pdf")


def test_hu_1_1_predio_en_municipio_que_atiende_la_delegacion(nueva_solicitud):
    """Regla del registro (ROP CC 8.1.3): el predio está en un municipio que atiende la Delegación."""
    exp = nueva_solicitud(municipio="Tlalmanalco")
    assert exp.predio.municipio.delegacion == exp.delegacion


def test_hu_1_1_municipio_de_otra_delegacion_se_rechaza_y_dice_cual_corresponde(nueva_solicitud):
    antes = Expediente.objects.count()
    with pytest.raises(ValidationError) as e:
        nueva_solicitud(municipio="Toluca")
    assert "Delegación Regional Forestal Toluca" in str(e.value)
    assert Expediente.objects.count() == antes and not Predio.objects.filter(nombre="Predio de prueba").exists()


def test_hu_1_1_solo_la_delegacion_registra(cc, usuarios):
    datos = servicios.DatosSolicitud(
        ejercicio=cc, municipio=Municipio.objects.get(nombre="Amecameca"), nombre_predio="X",
        tipo_persona=cc.tipos_persona.first(), solicitante_nombre="Y", solicitante_tipo="fisica",
    )
    with pytest.raises(PermissionDenied):
        servicios.registrar_solicitud(usuarios["dir_drff"], datos)


def test_hu_1_1_programa_sin_reglas_no_recibe_solicitudes(catalogos, usuarios):
    """Los seis programas ya tienen reglas 2026; un ejercicio sin su archivo de reglas (2027) no recibe solicitudes."""
    from nucleo.models import Ejercicio, Programa

    sin_reglas = Ejercicio.objects.create(programa=Programa.objects.get(clave="PEG"), anio=2027)
    assert not sin_reglas.tiene_reglas
    datos = servicios.DatosSolicitud(
        ejercicio=sin_reglas, municipio=Municipio.objects.get(nombre="Amecameca"), nombre_predio="X",
        tipo_persona=None, solicitante_nombre="Y", solicitante_tipo="fisica",
    )
    with pytest.raises(ValidationError):
        servicios.registrar_solicitud(usuarios["del_amecameca"], datos)


def test_hu_1_1_predio_ya_registrado_conserva_su_folio(nueva_solicitud, cc, usuarios):
    primero = nueva_solicitud()
    datos = servicios.DatosSolicitud(
        ejercicio=cc, municipio=primero.predio.municipio, nombre_predio="", tipo_persona=primero.tipo_persona,
        modalidad=primero.modalidad, solicitante_nombre="", solicitante_tipo="fisica",
        predio_existente=primero.predio, es_refrendo=True,
    )
    segundo = servicios.registrar_solicitud(usuarios["del_amecameca"], datos)
    assert segundo.predio == primero.predio and segundo.folio != primero.folio


def test_hu_1_1_pantalla_de_registro(client, cc, contrasena):
    client.login(username="del_amecameca", password=contrasena)
    form = client.get("/recepcion/registrar/")
    assert form.status_code == 200 and "Registro de la solicitud" in form.content.decode()
    tp = cc.tipos_persona.get(clave="fisica")
    mod = cc.modalidades.get(clave="reforestacion")
    datos = {"ejercicio": cc.pk, "tipo_persona": tp.pk, "modalidad": mod.pk,
             "municipio": Municipio.objects.get(nombre="Toluca").pk, "nombre_predio": "Predio Web",
             "solicitante_nombre": "Persona Web"}
    r = client.post("/recepcion/registrar/", datos)
    assert r.status_code == 200 and "Delegación Regional Forestal Toluca" in r.content.decode()
    datos["municipio"] = Municipio.objects.get(nombre="Ayapango").pk
    r = client.post("/recepcion/registrar/", datos)
    assert r.status_code == 302
    assert Expediente.objects.filter(predio__nombre="Predio Web").exists()
