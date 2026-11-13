"""Núcleo: tabla de transiciones (un solo punto que cambia el estado) y permisos por unidad."""
import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError

from nucleo.models import (
    Estado, Evento, Programa, TipoUnidad, Transicion, TransicionNoPermitida, Usuario, bandeja, expedientes_visibles,
)

pytestmark = pytest.mark.django_db


def test_nucleo_transicion_permitida_cambia_estado_y_escribe_bitacora(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    exp.cambiar_estado("desechada", usuarios["del_amecameca"], motivo="Prueba")
    exp.refresh_from_db()
    assert exp.estado.clave == "desechada"
    ev = exp.eventos.filter(tipo="cambio_estado").first()
    assert ev.estado_origen.clave == "recibida" and ev.estado_destino.clave == "desechada"
    assert ev.usuario == usuarios["del_amecameca"] and ev.motivo == "Prueba"


def test_nucleo_transicion_fuera_de_la_tabla_se_rechaza(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    with pytest.raises(TransicionNoPermitida):
        exp.cambiar_estado("validada", usuarios["del_amecameca"])
    exp.refresh_from_db()
    assert exp.estado.clave == "recibida"


def test_nucleo_transicion_de_otra_unidad_se_rechaza(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    # La Dirección no puede enviar a sí misma lo que aún está en la Delegación.
    with pytest.raises(TransicionNoPermitida):
        exp.cambiar_estado("enviada_direccion", usuarios["dir_drff"])


def test_nucleo_transicion_que_pide_motivo(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    with pytest.raises(ValidationError):
        exp.cambiar_estado("desechada", usuarios["del_amecameca"], motivo=" ")


def test_nucleo_transicion_por_programa(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    otra = Programa.objects.get(clave="PEG")
    Transicion.objects.create(programa=otra, origen=Estado.objects.get(clave="recibida"),
                              destino=Estado.objects.get(clave="validada"), tipo_unidad=TipoUnidad.DELEGACION,
                              accion="Solo PEG")
    with pytest.raises(TransicionNoPermitida):
        exp.cambiar_estado("validada", usuarios["del_amecameca"])


def test_nucleo_delegacion_solo_ve_sus_expedientes(nueva_solicitud, usuarios):
    propio = nueva_solicitud()
    ajeno = nueva_solicitud(usuario="del_toluca", municipio="Toluca")
    visibles = set(expedientes_visibles(usuarios["del_amecameca"]))
    assert propio in visibles and ajeno not in visibles
    with pytest.raises(TransicionNoPermitida):
        ajeno.cambiar_estado("desechada", usuarios["del_amecameca"], motivo="x")


def test_nucleo_direccion_ve_los_expedientes_de_sus_programas(nueva_solicitud, usuarios):
    exp = nueva_solicitud()
    assert exp in expedientes_visibles(usuarios["dir_drff"])        # DRFF es Instancia Ejecutora de CC
    assert exp not in expedientes_visibles(usuarios["dir_dpf"])     # DPF solo PEG
    assert exp not in expedientes_visibles(usuarios["juridica"])    # aún no le toca


def test_nucleo_bandeja_muestra_lo_que_toca_atender(nueva_solicitud, usuarios, pdf):
    exp = nueva_solicitud()
    assert exp in bandeja(usuarios["del_amecameca"])
    assert exp not in bandeja(usuarios["dir_drff"])


def test_nucleo_grupo_del_usuario_sigue_el_tipo_de_su_unidad(usuarios):
    u = usuarios["del_amecameca"]
    assert list(u.groups.values_list("name", flat=True)) == [TipoUnidad.DELEGACION.label]
    u.unidad = usuarios["dir_drff"].unidad
    u.save()
    assert list(Usuario.objects.get(pk=u.pk).groups.values_list("name", flat=True)) == [TipoUnidad.DIRECCION.label]
    assert Group.objects.filter(name=TipoUnidad.FIDUCIARIA.label).exists()


def test_nucleo_vistas_protegidas_por_unidad(client, nueva_solicitud, usuarios, contrasena):
    exp = nueva_solicitud()
    client.login(username="del_toluca", password=contrasena)
    assert client.get(f"/recepcion/expediente/{exp.folio}/").status_code == 404
    acuse = exp.acuses.first()
    assert client.get(f"/acuses/{acuse.folio}/").status_code == 404
    client.login(username="del_amecameca", password=contrasena)
    assert client.get(f"/recepcion/expediente/{exp.folio}/").status_code == 200
    assert client.get(f"/acuses/{acuse.folio}/").status_code == 200


def test_nucleo_inicio_de_sesion_y_bandeja(client, catalogos, contrasena):
    assert client.get("/bandeja/").status_code == 302
    r = client.post("/entrar/", {"username": "dir_drff", "password": contrasena})
    assert r.status_code == 302
    r = client.get("/bandeja/")
    assert "Dirección de Restauración y Fomento Forestal" in r.content.decode()


def test_nucleo_filtros_de_bandeja_por_htmx(client, nueva_solicitud, contrasena):
    nueva_solicitud(nombre="Predio Alfa")
    nueva_solicitud(nombre="Predio Beta")
    client.login(username="del_amecameca", password=contrasena)
    r = client.get("/bandeja/?q=Alfa", HTTP_HX_REQUEST="true", HTTP_HX_TARGET="tabla-bandeja")
    html = r.content.decode()
    assert "Predio Alfa" in html and "Predio Beta" not in html and "<nav" not in html


def test_nucleo_revisar_plazos_senala_vencidos_una_vez(nueva_solicitud, usuarios, pdf):
    from datetime import timedelta

    from django.core.management import call_command
    from django.utils import timezone

    exp = nueva_solicitud()
    r = exp.revisiones.first()
    from recepcion import servicios
    servicios.revisar_requisito(usuarios["del_amecameca"], r, "faltante")
    futuro = (timezone.localdate() + timedelta(days=30)).isoformat()
    call_command("revisar_plazos", fecha=futuro)
    call_command("revisar_plazos", fecha=futuro)
    assert exp.eventos.filter(tipo="plazo_vencido").count() == 1
