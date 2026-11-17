"""Portal de personas beneficiarias (S3-02c; decisión S2-05): cuenta creada por la Delegación al registrar la firma
(usuario = CURP, primer acceso con código de un solo uso impreso en el acuse), respaldo con folio + código, y un externo
que solo ve SUS expedientes y ninguna pantalla interna."""
import re

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from contrato import firma
from nucleo.demo import archivo_demo
from portal import cuentas
from portal.models import CodigoConsulta, CuentaExterna

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de, elementos_propios

pytestmark = pytest.mark.django_db
CONTRASENA = "Bosque-Seguro-2026"


def _firmar(usuarios, exp):
    return firma.registrar_firma(delegado_de(usuarios, exp), exp, None, "persona", exp.beneficiaria.nombre,
                                 archivo_demo("firmado.pdf"), [p["clave"] for p in firma.puntos_de_verificacion(exp)],
                                 elementos_propios(exp))


def _codigos(acuse):
    texto = str(acuse.contenido)
    return re.findall(r"[A-Z2-9]{4}-[A-Z2-9]{4}", texto)


@pytest.fixture
def firmado(en_delegacion, usuarios):
    """``firmado("CC", curp=...)`` → expediente con el contrato firmado y el acceso al portal ya emitido."""
    def _crear(programa="CC", curp="LAPB800101MMCRNT05", cuantas=1, indice=0):
        _, exps = en_delegacion(programa, cuantas=cuantas)
        exp = exps[indice]
        if curp and programa != "PEG":
            exp.solicitante.curp = curp
            exp.solicitante.save()
        _firmar(usuarios, exp)
        exp.refresh_from_db()
        return exp
    return _crear


def _activar(exp):
    acuse = exp.acuses.get(tipo="alta_portal")
    acceso, consulta = _codigos(acuse)
    return acuse, acceso, consulta


# ----------------------------------------------------------------------------- alta al firmar
def test_portal_la_firma_crea_la_cuenta_con_la_curp_y_el_codigo_impreso_en_el_acuse(firmado):
    exp = firmado("CC")
    cuenta = CuentaExterna.objects.get(persona=exp.beneficiaria)
    assert cuenta.usuario.username == "LAPB800101MMCRNT05" and cuenta.usuario.unidad_id is None
    assert not cuenta.usuario.has_usable_password() and cuenta.activada_en is None
    acuse, acceso, consulta = _activar(exp)
    assert acuse.archivo and "LAPB800101MMCRNT05" in str(acuse.contenido)
    assert acceso not in cuenta.codigo_hash and cuenta.codigo_hash          # en la base, cifrado
    assert exp.eventos.filter(tipo="alta_portal").exists()


def test_portal_en_peg_la_cuenta_es_del_guardabosque(firmado):
    exp = firmado("PEG")
    cuenta = CuentaExterna.objects.get()
    assert cuenta.persona == exp.persona_beneficiaria and cuenta.usuario.username == "SARM800101HMCNZR09"


def test_portal_sin_curp_no_hay_cuenta_pero_si_folio_y_codigo(firmado):
    exp = firmado("PS", curp="")
    assert not CuentaExterna.objects.exists() and CodigoConsulta.objects.filter(expediente=exp).exists()
    (consulta,) = _codigos(exp.acuses.get(tipo="alta_portal"))
    assert cuentas.consultar(exp.folio, consulta) == exp
    assert cuentas.consultar(exp.folio, "AAAA-BBBB") is None


def test_portal_solo_la_delegacion_del_expediente_da_acceso(firmado, usuarios):
    exp = firmado("CC")
    for quien in ("dir_drff", "del_valle", "juridica"):
        with pytest.raises(PermissionDenied):
            cuentas.dar_acceso(usuarios[quien], exp)


# ----------------------------------------------------------------------------- primer acceso
def test_portal_primer_acceso_con_codigo_de_un_solo_uso(firmado, client):
    exp = firmado("CC")
    _, acceso, _ = _activar(exp)
    with pytest.raises(ValidationError):
        cuentas.primer_acceso("LAPB800101MMCRNT05", "ZZZZ-ZZZZ", CONTRASENA)
    r = client.post("/portal/primer-acceso/", {"curp": "lapb800101mmcrnt05", "codigo": acceso.lower(),
                                                "contrasena": CONTRASENA, "confirmacion": CONTRASENA})
    assert r.status_code == 302 and r["Location"] == "/portal/"
    cuenta = CuentaExterna.objects.get()
    assert cuenta.activada_en and cuenta.usuario.check_password(CONTRASENA) and not cuenta.codigo_hash
    with pytest.raises(ValidationError, match="ya se usó"):
        cuentas.primer_acceso("LAPB800101MMCRNT05", acceso, "Otra-Contrasena-99")
    client.post("/portal/salir/")
    assert client.post("/portal/entrar/", {"curp": "LAPB800101MMCRNT05", "contrasena": CONTRASENA}).status_code == 302


# ----------------------------------------------------------------------------- lo que ve un externo
def _entrar_externo(client, exp, curp):
    _, acceso, _ = _activar(exp)
    cuentas.primer_acceso(curp, acceso, CONTRASENA)
    assert client.post("/portal/entrar/", {"curp": curp, "contrasena": CONTRASENA}).status_code == 302


def test_portal_un_externo_ve_solo_sus_expedientes(firmado, usuarios, client):
    a = firmado("PEG", cuantas=2, indice=0)
    from nucleo.models import Expediente
    b = Expediente.objects.filter(ejercicio=a.ejercicio).exclude(pk=a.pk).get()
    _firmar(usuarios, b)                                      # el segundo Guardabosque también tiene cuenta
    _entrar_externo(client, a, "SARM800101HMCNZR09")
    html = client.get("/portal/").content.decode()
    assert a.folio in html and b.folio not in html
    assert client.get(f"/portal/expediente/{a.folio}/").status_code == 200
    assert client.get(f"/portal/expediente/{b.folio}/").status_code == 404          # lo ajeno no existe para él
    ajeno = b.acuses.exclude(tipo="alta_portal").first()
    assert client.get(f"/portal/expediente/{b.folio}/acuse/{ajeno.folio}/").status_code == 404
    propio = a.acuses.exclude(tipo="alta_portal").first()
    assert client.get(f"/portal/expediente/{a.folio}/acuse/{propio.folio}/").status_code == 200
    assert client.get(f"/portal/expediente/{a.folio}/acuse/{ajeno.folio}/").status_code == 404


@pytest.mark.parametrize("ruta", ["/bandeja/", "/recepcion/registrar/", "/pagos/", "/contrato/firmas/", "/admin/",
                                  "/dictamen/listado/"])
def test_portal_un_externo_no_entra_a_las_pantallas_internas(firmado, client, ruta):
    a = firmado("PEG")
    _entrar_externo(client, a, "SARM800101HMCNZR09")
    r = client.get(ruta)
    assert r.status_code == 302 and r["Location"] == "/portal/"
    assert client.get(f"/recepcion/expediente/{a.folio}/").status_code == 302         # ni su propio expediente interno
    assert client.post("/recepcion/registrar/", {}).status_code == 403


def test_portal_entradas_separadas_del_personal_y_de_las_personas(firmado, client, contrasena):
    a = firmado("PEG")
    _, acceso, _ = _activar(a)
    cuentas.primer_acceso("SARM800101HMCNZR09", acceso, CONTRASENA)
    r = client.post("/entrar/", {"username": "SARM800101HMCNZR09", "password": CONTRASENA})
    assert r.status_code == 200 and "_auth_user_id" not in client.session                  # no entra por la del personal
    r = client.post("/portal/entrar/", {"curp": "del_amecameca", "contrasena": contrasena})
    assert r.status_code == 200 and "_auth_user_id" not in client.session                  # el personal no entra al portal
    assert 'data-prueba="enlace-portal"' in client.get("/entrar/").content.decode()


def test_portal_consulta_sin_cuenta_muestra_solo_ese_expediente(firmado, usuarios, client):
    exp = firmado("PS", curp="", cuantas=2)
    from nucleo.models import Expediente
    otro = Expediente.objects.filter(ejercicio=exp.ejercicio).exclude(pk=exp.pk).get()
    (consulta,) = _codigos(exp.acuses.get(tipo="alta_portal"))
    assert client.post("/portal/consulta/", {"folio": exp.folio, "codigo": "XXXX-YYYY"}).status_code == 200
    r = client.post("/portal/consulta/", {"folio": exp.folio, "codigo": consulta})
    assert r.status_code == 302
    assert exp.estado.nombre in client.get(f"/portal/expediente/{exp.folio}/").content.decode()
    assert client.get(f"/portal/expediente/{otro.folio}/").status_code == 404
    assert client.get("/bandeja/").status_code == 302 and "/entrar/" in client.get("/bandeja/")["Location"]
