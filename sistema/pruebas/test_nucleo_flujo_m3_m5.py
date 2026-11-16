"""Núcleo · estados y transiciones de M3 (Publicación y contrato) y M5 (Pagos) (S2-02c). Solo la tabla:
las acciones con sus documentos y acuses las construyen las historias HU-3.x y HU-5.x."""
import json

import pytest
from django.conf import settings

from nucleo.models import (
    Ejercicio, Estado, Expediente, TipoUnidad, Transicion, TransicionNoPermitida, bandeja, expedientes_visibles,
)

pytestmark = pytest.mark.django_db

ESTADOS_M3_M5 = {
    "publicada", "notificada", "contrato_elaborado", "contrato_en_delegacion", "sin_firma_en_plazo",
    "recurso_liberado", "contratada", "vale_entregado", "planta_entregada", "ministracion_solicitada", "pagada",
    "remitida_fiduciaria", "cheque_emitido", "cheque_enviado", "cheque_entregado",
}


@pytest.fixture
def aprobada(nueva_solicitud):
    def _crear(programa="CC"):
        exp = nueva_solicitud()
        Expediente.objects.filter(pk=exp.pk).update(
            ejercicio=Ejercicio.objects.get(programa__clave=programa, anio=2026),
            estado=Estado.objects.get(clave="aprobada"))
        return Expediente.objects.get(pk=exp.pk)
    return _crear


def _pasar(exp, destino, usuario, motivo=""):
    exp.cambiar_estado(destino, usuario, motivo=motivo)
    exp.refresh_from_db()
    assert exp.estado.clave == destino
    assert exp.eventos.filter(estado_destino__clave=destino, usuario=usuario).exists()
    return exp


def _quien_atiende(exp, usuarios):
    return {n for n, u in usuarios.items() if u.unidad_id and exp in bandeja(u)}


def test_nucleo_estados_de_m3_y_m5_cargados_con_unidad_valida():
    datos = json.load(open(settings.DATOS_DIR / "flujo_tramite.json", encoding="utf-8"))
    claves = {e["clave"] for e in datos["estados"]}
    assert ESTADOS_M3_M5 <= claves
    tipos = set(TipoUnidad.values)
    for e in Estado.objects.all():
        assert set(e.tipos_bandeja) <= tipos, e.clave
        assert {t.strip() for t in e.visible_para.split(",") if t.strip()} <= tipos, e.clave
        if not e.final:
            # La lista de espera no se atiende: espera un acuerdo de reasignación del Comité.
            assert e.tipos_bandeja or e.clave == "lista_espera", f"{e.clave} no tiene quién lo atienda"
            assert e.salidas.exists(), f"{e.clave} no tiene salida"
    # Todo estado se alcanza desde «recibida».
    alcanzados, pendientes = {"recibida"}, ["recibida"]
    while pendientes:
        for t in Transicion.objects.filter(origen__clave=pendientes.pop()).select_related("destino"):
            if t.destino.clave not in alcanzados:
                alcanzados.add(t.destino.clave)
                pendientes.append(t.destino.clave)
    assert alcanzados == set(Estado.objects.values_list("clave", flat=True))


def test_nucleo_recorrido_cc_publicacion_contrato_y_dos_ministraciones(aprobada, usuarios):
    exp = aprobada("CC")
    u = usuarios
    assert _quien_atiende(exp, u) == {"dir_drff"}  # P-17: lo aprobado ya tiene bandeja
    pasos = [
        ("publicada", "dir_drff", {"del_amecameca"}),
        ("notificada", "del_amecameca", {"dir_drff"}),
        ("contrato_elaborado", "dir_drff", {"dir_drff"}),
        ("contrato_en_delegacion", "dir_drff", {"del_amecameca"}),
        ("contratada", "del_amecameca", {"dir_drff"}),
        ("ministracion_solicitada", "dir_drff", {"finanzas"}),
        ("pagada", "finanzas", {"dir_drff"}),
        ("ministracion_solicitada", "dir_drff", {"finanzas"}),  # segunda ministración
        ("pagada", "finanzas", {"dir_drff"}),
    ]
    for destino, quien, atienden in pasos:
        _pasar(exp, destino, u[quien])
        assert _quien_atiende(exp, u) == atienden, destino
    assert exp in expedientes_visibles(u["juridica"])
    with pytest.raises(TransicionNoPermitida):  # CC no pasa por la Fiduciaria
        Expediente.objects.filter(pk=exp.pk).update(estado=Estado.objects.get(clave="ministracion_solicitada"))
        exp.refresh_from_db()
        exp.cambiar_estado("remitida_fiduciaria", u["finanzas"])


def test_nucleo_sin_firma_en_plazo_y_liberacion_del_recurso(aprobada, usuarios):
    exp = aprobada("CC")
    _pasar(exp, "publicada", usuarios["dir_drff"])
    _pasar(exp, "notificada", usuarios["del_amecameca"])
    with pytest.raises(TransicionNoPermitida):  # lo señala la Dirección, no la Delegación
        exp.cambiar_estado("sin_firma_en_plazo", usuarios["del_amecameca"], motivo="x")
    _pasar(exp, "sin_firma_en_plazo", usuarios["dir_drff"], motivo="Venció el plazo de firma")
    assert _quien_atiende(exp, usuarios) == {"dir_drff", "comite"}
    _pasar(exp, "recurso_liberado", usuarios["comite"], motivo="Acuerdo del Comité")
    assert exp.estado.final and not _quien_atiende(exp, usuarios)


def test_nucleo_psahem_paga_con_cheque_de_la_fiduciaria(aprobada, usuarios):
    exp = aprobada("PSA")
    u = usuarios
    for destino, quien in [("publicada", "dir_drff"), ("notificada", "del_amecameca"),
                           ("contrato_elaborado", "dir_drff"), ("contrato_en_delegacion", "dir_drff"),
                           ("contratada", "del_amecameca"), ("ministracion_solicitada", "dir_drff")]:
        _pasar(exp, destino, u[quien])
    with pytest.raises(TransicionNoPermitida):  # en PSAHEM no paga Administración y Finanzas directamente
        exp.cambiar_estado("pagada", u["finanzas"])
    with pytest.raises(TransicionNoPermitida):  # ni la remite: se la solicita a la Fiduciaria la Secretaría Técnica (R-16)
        exp.cambiar_estado("remitida_fiduciaria", u["finanzas"])
    pasos = [
        ("remitida_fiduciaria", "comite", {"fiduciaria"}),  # R-16: la solicita la Secretaría Técnica (ROP PSAHEM 10.1 fr. X)
        ("cheque_emitido", "fiduciaria", {"fiduciaria"}),
        ("cheque_enviado", "fiduciaria", {"del_amecameca"}),
        ("cheque_entregado", "del_amecameca", {"dir_drff"}),
        ("ministracion_solicitada", "dir_drff", {"finanzas"}),
    ]
    for destino, quien, atienden in pasos:
        _pasar(exp, destino, u[quien])
        assert _quien_atiende(exp, u) == atienden, destino


def test_nucleo_vale_de_planta_solo_en_ps_y_rhf(aprobada, usuarios):
    u = usuarios
    for programa in ("PS", "RHF"):
        exp = aprobada(programa)
        Expediente.objects.filter(pk=exp.pk).update(estado=Estado.objects.get(clave="contratada"))
        exp.refresh_from_db()
        _pasar(exp, "vale_entregado", u["del_amecameca"])
        assert _quien_atiende(exp, u) == {"vivero"}
        _pasar(exp, "planta_entregada", u["vivero"])
        _pasar(exp, "ministracion_solicitada", u["dir_drff"])
    cc = aprobada("CC")
    Expediente.objects.filter(pk=cc.pk).update(estado=Estado.objects.get(clave="contratada"))
    cc.refresh_from_db()
    with pytest.raises(TransicionNoPermitida):
        cc.cambiar_estado("vale_entregado", u["del_amecameca"])


def test_nucleo_devolucion_de_la_solicitud_de_pago_pide_motivo(aprobada, usuarios):
    from django.core.exceptions import ValidationError

    exp = aprobada("RHF")
    Expediente.objects.filter(pk=exp.pk).update(estado=Estado.objects.get(clave="ministracion_solicitada"))
    exp.refresh_from_db()
    with pytest.raises(ValidationError):
        exp.cambiar_estado("contratada", usuarios["finanzas"], motivo="")
    _pasar(exp, "contratada", usuarios["finanzas"], motivo="Falta el oficio de solicitud de pago")
