"""HU-3.1 · Publicación y notificaciones."""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from contrato import publicacion
from contrato.models import Publicacion, ResultadoPublicado
from nucleo import notificaciones, plazos
from nucleo.models import Notificacion, Plazo

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def test_hu_3_1_criterios_y_necesidades_vienen_del_modelo(modelo):
    hu = historia(modelo, "HU-3.1")
    assert len(hu["criterios"]) == 3 and "publicados en la fecha de la convocatoria" in hu["criterios"][0]
    assert "acuse" in hu["criterios"][1]
    assert "trazabilidad" in hu["criterios"][-1]


# ----------------------------------------------------------------------------- criterio 1: publicación
def test_hu_3_1_listados_autorizados_quedan_publicados_con_fecha_hora_acuse_y_hito(aprobadas, usuarios):
    """Criterio 1: los listados autorizados por el Comité quedan publicados; cada solicitud tiene su hito y estado."""
    sesion, exps = aprobadas("CC", presupuesto=12000, no_factible=True)   # beneficiaria, lista de espera, no factible
    resultados = {e.folio: e.resoluciones_comite.get().resultado for e in exps}
    assert sorted(resultados.values()) == ["beneficiaria", "lista_espera", "no_factible"]
    antes = timezone.now()
    pub = publicacion.publicar(usuarios["dir_drff"], sesion)
    assert antes <= pub.publicada_en <= timezone.now() and pub.publicada_por == usuarios["dir_drff"]
    assert pub.acuse.archivo.open("rb").read(4) == b"%PDF" and pub.acuse.tipo == "publicacion_resultados"
    assert dict(pub.acuse.contenido["renglones"])["Fecha y hora de la publicación"]
    for e in exps:
        e.refresh_from_db()
        hito = e.hitos.get(clave="publicacion_resultados")
        assert hito.fecha_hora == pub.publicada_en and hito.usuario == usuarios["dir_drff"]
        assert e.eventos.filter(tipo="publicacion_resultados", acuse=pub.acuse).exists()
        esperado = {"beneficiaria": "publicada", "lista_espera": "lista_espera", "no_factible": "no_factible"}
        assert e.estado.clave == esperado[resultados[e.folio]]
    assert pub.renglones.count() == 3


def test_hu_3_1_no_se_publica_sin_autorizacion_ni_antes_del_acta(aprobadas, usuarios, cc):
    sesion, exps = aprobadas("CC", autoriza=False)
    with pytest.raises(ValidationError, match="no autorizó la publicación"):
        publicacion.publicar(usuarios["dir_drff"], sesion)
    assert not Publicacion.objects.exists() and not exps[0].hitos.filter(clave="publicacion_resultados").exists()
    assert all(e.estado.clave == "aprobada" for e in exps if e.resoluciones_comite.get().resultado == "beneficiaria")
    # Una sesión autorizada, pero con la fecha de publicación anterior al acta.
    sesion2, _ = aprobadas("PS")
    with pytest.raises(ValidationError, match="anterior al acta"):
        publicacion.publicar(usuarios["dir_drff"], sesion2, momento=sesion2.acta_fecha - timedelta(minutes=1))
    # Sin acta (sesión convocada): no hay listados aprobados que publicar.
    from dictamen import sesiones
    from dictamen.models import TipoSesion
    sin_acta = sesiones.crear_sesion(usuarios["comite"], cc, TipoSesion.APROBACION, fecha_sesion(6), "Sala", "Quórum")
    with pytest.raises(ValidationError, match="no tiene acta"):
        publicacion.publicar(usuarios["dir_drff"], sin_acta)


def test_hu_3_1_solo_el_area_responsable_publica_y_una_sola_vez(aprobadas, usuarios):
    sesion, _ = aprobadas("CC")
    for quien in ("del_amecameca", "comite", "juridica"):
        with pytest.raises(PermissionDenied):
            publicacion.publicar(usuarios[quien], sesion)
    with pytest.raises(PermissionDenied, match="Instancia Ejecutora"):
        publicacion.publicar(usuarios["dir_dpf"], sesion)   # Protección Forestal no es Instancia Ejecutora de CC
    publicacion.publicar(usuarios["dir_drff"], sesion)
    with pytest.raises(ValidationError, match="ya se publicaron"):
        publicacion.publicar(usuarios["dir_drff"], sesion)


def test_hu_3_1_sin_fecha_en_las_reglas_se_dice_asi(aprobadas, usuarios):
    """Las ROP no fijan fecha ni días para publicar (R-05): no se inventa una fecha."""
    sesion, _ = aprobadas("PS")
    pub = publicacion.publicar(usuarios["dir_drff"], sesion)
    assert pub.fecha_limite is None and pub.dentro_de_fecha is None
    assert "Sin fecha en las reglas" in pub.situacion_fecha
    assert "Sin fecha en las reglas" in dict(pub.acuse.contenido["renglones"])["Fecha de la convocatoria"]


@pytest.mark.parametrize("dias,dentro", [(2, True), (-2, False)])
def test_hu_3_1_con_fecha_en_las_reglas_dice_si_se_publico_dentro_de_la_fecha(aprobadas, usuarios, dias, dentro):
    sesion, _ = aprobadas("RHF")
    Plazo.objects.filter(ejercicio=sesion.ejercicio, clave="publicacion_resultados").update(
        fecha_fin=timezone.localdate() + timedelta(days=dias))
    pub = publicacion.publicar(usuarios["dir_drff"], sesion)
    assert pub.dentro_de_fecha is dentro and pub.fecha_limite == timezone.localdate() + timedelta(days=dias)
    assert ("Dentro de la fecha" if dentro else "Fuera de la fecha") in pub.situacion_fecha


# ----------------------------------------------------------------------------- criterio 2: avisos
def test_hu_3_1_cada_aviso_tiene_acuse_fecha_hora_de_envio_y_de_notificacion(aprobadas, usuarios):
    """Criterio 2: cada aviso tiene su acuse y la fecha y la hora de envío y de notificación."""
    sesion, exps = aprobadas("CC", cuantas=2)
    pub = publicacion.publicar(usuarios["dir_drff"], sesion)
    avisos = Notificacion.objects.filter(datos__publicacion=pub.pk)
    assert avisos.count() == 2 and set(avisos.values_list("tipo", flat=True)) == {"resultados"}
    for n in avisos:
        assert n.enviada_en == pub.publicada_en and n.acuse_envio.archivo.open("rb").read(4) == b"%PDF"
        assert n.notificada_en is None and n.delegacion == n.expediente.delegacion
    n = avisos.get(expediente=exps[0])
    deleg = usuarios["del_amecameca"]
    assert n in publicacion.por_entregar(deleg) and n not in publicacion.por_entregar(usuarios["del_toluca"])
    acuse = publicacion.registrar_entrega(deleg, n, "correo", observaciones="Se envió al correo registrado.")
    n.refresh_from_db()
    assert n.notificada_en and n.notificada_en >= n.enviada_en and n.medio == "correo" and n.acuse_notificacion == acuse
    assert acuse.archivo.open("rb").read(4) == b"%PDF" and dict(acuse.contenido["renglones"])["Medio"]
    assert n.expediente.eventos.filter(tipo="notificacion", acuse=acuse).exists()
    assert n not in publicacion.por_entregar(deleg)


def test_hu_3_1_notificar_a_la_persona_beneficiaria_pasa_el_expediente_a_notificada_y_arranca_el_plazo(aprobadas, usuarios):
    sesion, exps = aprobadas("CC", cuantas=1)
    exp = exps[0]
    publicacion.publicar(usuarios["dir_drff"], sesion)
    exp.refresh_from_db()
    assert exp.estado.clave == "publicada"
    assert plazos.vencimiento(exp, "firma_liberacion").fecha_evento is None   # CC: corre desde la notificación
    n = exp.notificaciones.get(tipo="resultados")
    cuando = n.enviada_en + timedelta(milliseconds=1)
    publicacion.registrar_entrega(usuarios["del_amecameca"], n, "personal", fecha_hora=cuando)
    exp.refresh_from_db()
    assert exp.estado.clave == "notificada"
    assert exp.eventos.filter(estado_origen__clave="publicada", estado_destino__clave="notificada").exists()
    assert plazos.vencimiento(exp, "firma_liberacion").fecha_evento == cuando
    assert notificaciones.ultima_notificada(exp, "resultados") == n


def test_hu_3_1_solo_la_delegacion_del_expediente_registra_la_entrega(aprobadas, usuarios):
    sesion, exps = aprobadas("CC", cuantas=1)
    publicacion.publicar(usuarios["dir_drff"], sesion)
    n = exps[0].notificaciones.get()
    for quien in ("del_toluca", "dir_drff"):
        with pytest.raises(PermissionDenied):
            publicacion.registrar_entrega(usuarios[quien], n, "personal")
    with pytest.raises(ValidationError, match="futura"):
        publicacion.registrar_entrega(usuarios["del_amecameca"], n, "personal", fecha_hora=timezone.now() + timedelta(days=1))
    with pytest.raises(ValidationError, match="anterior a su envío"):
        publicacion.registrar_entrega(usuarios["del_amecameca"], n, "personal", fecha_hora=n.enviada_en - timedelta(hours=1))
    publicacion.registrar_entrega(usuarios["del_amecameca"], n, "personal")
    with pytest.raises(ValidationError, match="ya se registró"):
        publicacion.registrar_entrega(usuarios["del_amecameca"], n, "personal")


def test_hu_3_1_lista_de_espera_y_no_factible_tambien_reciben_su_aviso_sin_cambiar_de_estado(aprobadas, usuarios):
    sesion, exps = aprobadas("CC", presupuesto=12000, no_factible=True)
    publicacion.publicar(usuarios["dir_drff"], sesion)
    for e in exps:
        n = e.notificaciones.get(tipo="resultados")
        renglones = dict(n.acuse_envio.contenido["renglones"])
        assert renglones["Resultado"] and n.acuse_envio.destinatario.endswith(e.delegacion.nombre)
        publicacion.registrar_entrega(usuarios[{"Amecameca": "del_amecameca", "Zinacantepec": "del_toluca",
                                                 "Amanalco": "del_valle"}[e.predio.municipio.nombre]], n, "estrados")
    for e in exps:
        e.refresh_from_db()
    estados = sorted(e.estado.clave for e in exps)
    assert estados == ["lista_espera", "no_factible", "notificada"]


def test_hu_3_1_ps_la_delegacion_cita_a_firma_en_5_dias_habiles_desde_la_publicacion(aprobadas, usuarios):
    """PS (10.1 inciso h): la Delegación notifica y cita a firma en 5 días hábiles tras la publicación."""
    sesion, exps = aprobadas("PS", cuantas=1)
    pub = publicacion.publicar(usuarios["dir_drff"], sesion)
    cita = exps[0].notificaciones.get(tipo="cita_firma")
    v = publicacion.vencimiento_de(cita)
    assert v.plazo.clave == "cita_firma_contrato" and v.fecha_evento == pub.publicada_en
    from nucleo import dias_habiles
    assert v.vencimiento == dias_habiles.calcular_vencimiento(pub.publicada_en, 5, "dias_habiles")
    assert "5 días hábiles" in v.texto
    assert exps[0].notificaciones.filter(tipo="resultados").exists()


def test_hu_3_1_en_cc_no_hay_cita_a_firma_aparte(aprobadas, usuarios):
    sesion, exps = aprobadas("CC", cuantas=1)
    publicacion.publicar(usuarios["dir_drff"], sesion)
    assert not exps[0].notificaciones.filter(tipo="cita_firma").exists()


@pytest.mark.parametrize("tipo", ["omision", "devolucion", "cita_firma", "otro"])
def test_hu_3_1_quedan_listos_los_avisos_de_omisiones_y_devolucion(aprobadas, usuarios, tipo):
    sesion, exps = aprobadas("RHF", cuantas=1)
    publicacion.publicar(usuarios["dir_drff"], sesion)
    n = publicacion.enviar_aviso(usuarios["dir_drff"], exps[0], tipo, "Aviso de prueba", observaciones="Detalle")
    assert n.tipo == tipo and n.enviada_en and n.acuse_envio.folio
    with pytest.raises(PermissionDenied):
        publicacion.enviar_aviso(usuarios["del_amecameca"], exps[0], tipo, "No debe poder")
    with pytest.raises(ValidationError):
        publicacion.enviar_aviso(usuarios["dir_drff"], exps[0], "inventado", "x")
    publicacion.registrar_entrega(usuarios["del_amecameca"], n, "telefono")
    assert exps[0].estado.clave == "publicada"   # solo el aviso de resultados cambia el estado


# ----------------------------------------------------------------------------- página pública
def test_hu_3_1_pagina_publica_sin_iniciar_sesion_muestra_los_listados_cuidando_los_datos(aprobadas, usuarios, client):
    sesion, exps = aprobadas("CC", presupuesto=12000, no_factible=True)
    for e in exps:   # datos que NO deben salir
        e.solicitante.curp, e.solicitante.rfc = f"CURPZ{e.pk:06d}HMCXXX", f"RFCZ{e.pk:06d}XX"
        e.solicitante.save()
    pub = publicacion.publicar(usuarios["dir_drff"], sesion)
    indice = client.get("/contrato/resultados/")
    assert indice.status_code == 200 and "Capturando Carbono" in indice.content.decode()
    r = client.get("/contrato/resultados/CC/2026/")
    html = r.content.decode()
    assert r.status_code == 200 and "Lista de Personas Beneficiarias" in html and "Lista de espera" in html and "No factibles" in html
    por_resultado = {x.resultado: x for x in ResultadoPublicado.objects.filter(publicacion=pub)}
    assert por_resultado["beneficiaria"].persona in html          # el padrón de beneficiarias sí
    for malo in (por_resultado["lista_espera"], por_resultado["no_factible"]):
        assert malo.persona == "" and malo.expediente.solicitante.nombre not in html
        assert malo.folio in html and malo.predio in html and malo.municipio in html
    assert "CURP" not in html.replace("Buscar", "") and "RFC" not in html
    assert not any(e.solicitante.curp in html or e.solicitante.rfc in html for e in exps)
    assert "documento" not in html.lower().replace("documentos", "")


def test_hu_3_1_pagina_publica_busca_por_folio_y_dice_si_no_hay(aprobadas, usuarios, client):
    sesion, exps = aprobadas("CC", presupuesto=12000)
    publicacion.publicar(usuarios["dir_drff"], sesion)
    html = client.get("/contrato/resultados/CC/2026/", {"folio": exps[1].folio}).content.decode()
    assert exps[1].folio in html and exps[0].folio not in html and exps[2].folio not in html
    vacio = client.get("/contrato/resultados/CC/2026/", {"folio": "CC-2026-XXX-9999"}).content.decode()
    assert 'data-prueba="sin-resultados"' in vacio


def test_hu_3_1_pagina_publica_solo_de_lo_publicado(aprobadas, client):
    aprobadas("PS")   # aprobada pero sin publicar
    assert client.get("/contrato/resultados/PS/2026/").status_code == 404
    assert client.get("/contrato/resultados/XX/2026/").status_code == 404
    assert "Todavía no se publican resultados" in client.get("/contrato/resultados/").content.decode()


def test_hu_3_1_pantalla_de_inicio_de_sesion_enlaza_a_la_pagina_publica(client):
    html = client.get("/entrar/").content.decode()
    assert 'data-prueba="enlace-resultados"' in html and "/contrato/resultados/" in html


# ----------------------------------------------------------------------------- pantallas
def test_hu_3_1_pantallas_de_personal_piden_iniciar_sesion(client, aprobadas):
    for url in ("/contrato/publicacion/", "/contrato/notificaciones/"):
        r = client.get(url)
        assert r.status_code == 302 and "/entrar/" in r["Location"]


def test_hu_3_1_pantalla_de_publicacion_publica_y_avisa_en_la_bandeja_de_la_delegacion(aprobadas, usuarios, client, contrasena):
    sesion, exps = aprobadas("PS")
    client.login(username="dir_drff", password=contrasena)
    bandeja = client.get("/bandeja/").content.decode()
    assert 'data-prueba="panel-por-publicar"' in bandeja and sesion.numero in bandeja
    assert "Publicar los resultados" in client.get(f"/recepcion/expediente/{exps[0].folio}/").content.decode()
    detalle = client.get(f"/contrato/publicacion/{sesion.pk}/")
    assert detalle.status_code == 200 and "Sin fecha en las reglas" in detalle.content.decode()
    r = client.post(f"/contrato/publicacion/{sesion.pk}/", {"lugares": ""}, follow=True)
    html = r.content.decode()
    assert r.status_code == 200 and 'data-prueba="publicada"' in html and "AC-" in html
    assert Publicacion.objects.get(sesion=sesion).renglones.count() == 2
    client.login(username="del_amecameca", password=contrasena)
    assert 'data-prueba="panel-notificaciones"' in client.get("/bandeja/").content.decode()
    bandeja_n = client.get("/contrato/notificaciones/").content.decode()
    assert exps[0].folio in bandeja_n and "Cita a firma del contrato" in bandeja_n
    n = exps[0].notificaciones.get(tipo="resultados")
    r = client.post(f"/contrato/notificaciones/{n.pk}/entregar/", {f"n{n.pk}-medio": "personal", f"n{n.pk}-fecha_hora": "",
                                                                    f"n{n.pk}-observaciones": "En ventanilla"}, follow=True)
    assert "Notificación registrada" in r.content.decode()
    n.refresh_from_db()
    assert n.notificada_en and n.medio == "personal"


def test_hu_3_1_pestana_contrato_muestra_lo_publicado_y_lo_notificado(aprobadas, usuarios, client, contrasena):
    sesion, exps = aprobadas("PS", cuantas=1)
    publicacion.publicar(usuarios["dir_drff"], sesion)
    publicacion.registrar_entrega(usuarios["del_amecameca"], exps[0].notificaciones.get(tipo="resultados"), "personal")
    client.login(username="dir_drff", password=contrasena)
    html = client.get(f"/recepcion/expediente/{exps[0].folio}/?pestana=contrato").content.decode()
    assert 'data-prueba="resultado-publicado"' in html and 'data-prueba="notificaciones-exp"' in html
    assert "Cita a firma del contrato" in html and "Resultados (persona beneficiaria)" in html
    assert 'data-prueba="por-construir"' not in html   # ya no queda nada por construir en M3


def test_hu_3_1_actas_sin_autorizacion_se_ven_pero_no_se_publican(aprobadas, usuarios, client, contrasena):
    sesion, _ = aprobadas("CC", autoriza=False)
    client.login(username="dir_drff", password=contrasena)
    lista = client.get("/contrato/publicacion/").content.decode()
    assert 'data-prueba="sin-autorizacion"' in lista
    assert 'data-prueba="por-publicar"' in lista and "No hay listados autorizados por publicar" in lista
    detalle = client.get(f"/contrato/publicacion/{sesion.pk}/").content.decode()
    assert "no autorizó la publicación" in detalle and 'id="form-publicar"' not in detalle


def _filas_de(exp, registro):
    from nucleo.trazabilidad import historial_expediente

    return [f for f in historial_expediente(exp) if f["registro"] == registro]


# ----------------------------------------------------------------------------- criterio 3: trazabilidad
def test_hu_3_1_trazabilidad_de_la_publicacion_y_de_la_notificacion(aprobadas, usuarios):
    """Criterio 3: la publicación, su renglón y la notificación quedan en el historial con quién, cuándo y qué cambió."""
    sesion, (exp,) = aprobadas("CC", cuantas=1)
    pub = publicacion.publicar(usuarios["dir_drff"], sesion)
    assert pub.history.get(history_type="+").history_user == usuarios["dir_drff"]
    assert ResultadoPublicado.history.get(expediente_id=exp.pk).history_user == usuarios["dir_drff"]
    n = exp.notificaciones.get(tipo="resultados")
    publicacion.registrar_entrega(usuarios["del_amecameca"], n, "personal")
    cambio = n.history.filter(history_type="~").latest("history_date")
    assert cambio.history_user == usuarios["del_amecameca"] and cambio.notificada_en is not None
    assert any(f["usuario"] == usuarios["dir_drff"] for f in _filas_de(exp, "Publicación de resultados"))
    notif = _filas_de(exp, "Notificación")
    assert any(f["usuario"] == usuarios["del_amecameca"] and any(c["antes"] == "—" for c in f["cambios"]) for f in notif)
