"""HU-3.4 · Entrega de planta (Vale de Planta, salida del vivero, vigencia y reposición)."""
from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from contrato import firma, planta
from contrato.models import SalidaPlanta, ValePlanta
from nucleo import dias_habiles
from nucleo.demo import archivo_demo

from .conftest import historia
from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def emitir(usuarios, exp, vivero, renglones, **kw):
    return planta.emitir_vale(delegado_de(usuarios, exp), exp, vivero, renglones, **kw)


def vencer(vale, dias=40):
    """El vale se entregó hace ``dias`` días y su vigencia ya pasó."""
    vale.entregado_en = timezone.now() - timedelta(days=dias)
    vale.vence_el = timezone.localdate() - timedelta(days=3)
    vale.save()
    vale.salidas.update(salido_en=timezone.now() - timedelta(days=dias - 1))


def test_hu_3_4_criterios_y_necesidades_vienen_del_modelo(modelo):
    hu = historia(modelo, "HU-3.4")
    assert "Vale de Planta vigente" in hu["criterios"][0] and "vencido no es válido" in hu["criterios"][2]
    assert len(hu["criterios"]) == 4
    assert "trazabilidad" in hu["criterios"][-1]
    funcion = next(f for m in modelo["modulos"] for f in m["funciones"] if f["id"] == "M3.4")
    assert {"PS-DRF-03", "PS-VIV-01", "RHF-DRF-03", "RHF-VIV-01"} <= set(funcion["necesidades"])


# ----------------------------------------------------------------------------- emisión del vale
@pytest.mark.pdf_real
def test_hu_3_4_el_vale_lleva_especie_cantidad_vivero_fecha_hora_acuse_y_hito(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    assert planta.propuesta(exp)["total"] == 4400  # 1,100 por hectárea × 4 ha
    antes = timezone.now()
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 3000), (esp["Oyamel"], 1400)])
    exp.refresh_from_db()
    assert exp.estado.clave == "vale_entregado" and vale.folio == "VP-PS-2026-0001"
    assert vale.entregado_en >= antes and vale.vivero == vivero and vale.total_autorizado == 4400
    assert {r.especie.nombre: r.cantidad for r in vale.renglones.all()} == {"Pino patula": 3000, "Oyamel": 1400}
    assert vale.acuse and vale.acuse.tipo == "entrega_vale" and vale.archivo.read().startswith(b"%PDF")
    assert exp.hitos.get(clave="entrega_vale").referencia == vale.folio
    assert exp.eventos.filter(tipo="vale_entregado", acuse=vale.acuse).exists()
    assert vale.situacion() == "vigente" and not vale.anticipado


def test_hu_3_4_ajustar_la_propuesta_exige_motivo(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    with pytest.raises(ValidationError, match="motivo del ajuste"):
        emitir(usuarios, exp, vivero, [(esp["Pino patula"], 1000)])
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 1000)], motivo_ajuste="Solo hay 1,000 en el vivero.")
    assert vale.propuesta_total == 4400 and "1,000" in vale.motivo_ajuste


def test_hu_3_4_el_vale_valida_cantidades_especies_y_vivero(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    for malos, texto in (([], "al menos una especie"), ([(esp["Pino patula"], 0)], "mayor que cero"),
                         ([(esp["Pino patula"], 10), (esp["Pino patula"], 20)], "repetida")):
        with pytest.raises(ValidationError, match=texto):
            emitir(usuarios, exp, vivero, malos, motivo_ajuste="x")
    with pytest.raises(ValidationError, match="vivero"):
        emitir(usuarios, exp, None, [(esp["Pino patula"], 4400)])


def test_hu_3_4_solo_la_delegacion_del_expediente_entrega_el_vale(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    for quien in ("dir_drff", "vivero", "juridica", "del_valle"):
        with pytest.raises(PermissionDenied):
            planta.emitir_vale(usuarios[quien], exp, vivero, [(esp["Pino patula"], 4400)])


def test_hu_3_4_no_hay_vale_para_cc_ni_para_rhf_modalidad_uno(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (cc,) = contratadas("CC")
    with pytest.raises(ValidationError, match="no entrega planta con Vale"):
        emitir(usuarios, cc, vivero, [(esp["Pino patula"], 10)])
    _, (uno, dos) = contratadas("RHF", cuantas=2)
    assert planta.aplica(uno)[0] and uno.modalidad.clave == "rfi_modalidad_dos"
    from nucleo.models import Expediente, Modalidad
    Expediente.objects.filter(pk=dos.pk).update(modalidad=Modalidad.objects.get(ejercicio=dos.ejercicio, clave="rfi_modalidad_uno"))
    dos.refresh_from_db()
    ok, razon = planta.aplica(dos)
    assert not ok and "no recibe planta" in razon
    with pytest.raises(ValidationError, match="no recibe planta"):
        emitir(usuarios, dos, vivero, [(esp["Pino patula"], 10)])


def test_hu_3_4_un_expediente_con_vale_vigente_no_recibe_otro(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)])
    with pytest.raises(ValidationError, match="Ya tiene el vale VP-PS-2026-0001, vigente"):
        emitir(usuarios, exp, vivero, [(esp["Pino patula"], 10)], motivo_ajuste="x")


# ----------------------------------------------------------------------------- vigencia desde las reglas
def test_hu_3_4_vigencia_ps_30_dias_naturales_y_rhf_15_dias_habiles(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (ps,) = contratadas("PS")
    _, (rhf,) = contratadas("RHF")
    ahora = timezone.now()
    v_ps = emitir(usuarios, ps, vivero, [(esp["Pino patula"], 4400)], momento=ahora)
    v_rhf = emitir(usuarios, rhf, vivero, [(esp["Oyamel"], 1800)], momento=ahora)
    hoy = timezone.localdate()
    assert v_ps.vence_el == hoy + timedelta(days=30) and "30" in v_ps.vigencia_texto
    assert v_rhf.vence_el == dias_habiles.calcular_vencimiento(ahora, 15, "dias_habiles")
    assert "15" in v_rhf.vigencia_texto and v_rhf.vence_el > hoy + timedelta(days=14)


def test_hu_3_4_un_vale_con_fecha_de_entrega_pasada_ya_esta_vencido(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)], momento=timezone.now() - timedelta(days=40))
    assert vale.situacion() == "vencido" and not vale.vigente()


# ----------------------------------------------------------------------------- vale antes de la firma
def test_hu_3_4_antes_de_la_firma_el_vale_exige_la_carta_compromiso(en_delegacion, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = en_delegacion("PS")
    with pytest.raises(ValidationError, match="carta compromiso"):
        emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)])
    with pytest.raises(ValidationError, match="PDF, JPG o PNG"):
        emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)], carta=archivo_demo("carta.exe"))
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)], carta=archivo_demo("carta.pdf"))
    exp.refresh_from_db()
    assert vale.anticipado and vale.carta_compromiso and exp.estado.clave == "contrato_en_delegacion"
    assert exp.hitos.filter(clave="entrega_vale").exists()


def test_hu_3_4_al_firmar_un_contrato_con_vale_anticipado_pasa_a_vale_entregado_o_planta_entregada(
        en_delegacion, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (por_surtir, surtido) = en_delegacion("PS", cuantas=2)
    v1 = emitir(usuarios, por_surtir, vivero, [(esp["Pino patula"], 4400)], carta=archivo_demo("carta.pdf"))
    v2 = emitir(usuarios, surtido, vivero, [(esp["Pino patula"], 3300)], carta=archivo_demo("carta.pdf"))
    planta.registrar_salida(usuarios["vivero"], v2, esp["Pino patula"], 3300)
    surtido.refresh_from_db()
    assert surtido.estado.clave == "contrato_en_delegacion"  # el contrato aún no se firma: el estado no cambia
    for e in (por_surtir, surtido):
        firma.registrar_firma(delegado_de(usuarios, e), e, None, "persona", "X", archivo_demo("f.pdf"),
                              [p["clave"] for p in firma.puntos_de_verificacion(e)])
        e.refresh_from_db()
    assert por_surtir.estado.clave == "vale_entregado" and surtido.estado.clave == "planta_entregada"
    assert v1.situacion() == "vigente"


# ----------------------------------------------------------------------------- salida de planta
def test_hu_3_4_la_salida_tiene_especie_cantidad_fecha_hora_y_acuse(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 3000), (esp["Oyamel"], 1400)])
    antes = timezone.now()
    s = planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 1000, observaciones="Primer camión.")
    assert s.especie == esp["Pino patula"] and s.cantidad == 1000 and antes <= s.salido_en <= timezone.now()
    assert s.acuse.tipo == "salida_planta" and "Pino patula" in " ".join(v for _, v in s.acuse.contenido["renglones"])
    exp.refresh_from_db()
    assert exp.estado.clave == "vale_entregado" and exp.eventos.filter(tipo="salida_planta", acuse=s.acuse).exists()
    momento = s.salido_en + timedelta(milliseconds=5)
    planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 500, salido_en=momento, momento=momento)
    assert SalidaPlanta.objects.filter(vale=vale).count() == 2
    assert {r.especie.nombre: r.pendiente for r in vale.renglones.all()} == {"Pino patula": 1500, "Oyamel": 1400}


def test_hu_3_4_nunca_se_entrega_mas_de_lo_autorizado_por_especie(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 3000), (esp["Oyamel"], 1400)])
    with pytest.raises(ValidationError, match="solo quedan 3000"):
        planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 3001)
    with pytest.raises(ValidationError, match="no está autorizada"):
        planta.registrar_salida(usuarios["vivero"], vale, esp["Encino"], 1)
    with pytest.raises(ValidationError, match="mayor que cero"):
        planta.registrar_salida(usuarios["vivero"], vale, esp["Oyamel"], 0)
    planta.registrar_salida(usuarios["vivero"], vale, esp["Oyamel"], 1400)
    with pytest.raises(ValidationError, match="solo quedan 0"):
        planta.registrar_salida(usuarios["vivero"], vale, esp["Oyamel"], 1)
    assert not SalidaPlanta.objects.filter(cantidad__gt=3000).exists()


def test_hu_3_4_la_fecha_de_la_salida_no_es_futura_ni_anterior_al_vale(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)])
    with pytest.raises(ValidationError, match="futuras"):
        planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 10, salido_en=timezone.now() + timedelta(hours=3))
    with pytest.raises(ValidationError, match="anterior a la entrega"):
        planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 10, salido_en=vale.entregado_en - timedelta(hours=1))


def test_hu_3_4_solo_el_vivero_del_vale_registra_la_salida(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)])
    for quien in ("del_amecameca", "dir_drff", "juridica"):
        with pytest.raises(PermissionDenied):
            planta.registrar_salida(usuarios[quien], vale, esp["Pino patula"], 10)
    from nucleo.models import Unidad, Usuario
    otra = Unidad.objects.create(clave="VIV-OTRO", nombre="Otro vivero", tipo="vivero")
    intruso = Usuario.objects.create_user(username="vivero_otro", password="x", unidad=otra)
    with pytest.raises(PermissionDenied, match="no en su vivero"):
        planta.registrar_salida(intruso, vale, esp["Pino patula"], 10)


def test_hu_3_4_al_completarse_el_vale_el_expediente_pasa_a_planta_entregada(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)])
    planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 4000)
    exp.refresh_from_db()
    assert exp.estado.clave == "vale_entregado"
    planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 400)
    exp.refresh_from_db()
    vale.refresh_from_db()
    assert exp.estado.clave == "planta_entregada" and vale.surtido and vale.situacion() == "surtido"
    with pytest.raises(ValidationError, match="ya se surtió completo"):
        planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 1)


# ----------------------------------------------------------------------------- vale vencido y reposición
def test_hu_3_4_un_vale_vencido_no_es_valido_y_el_vivero_no_registra_salida(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("RHF")
    vale = emitir(usuarios, exp, vivero, [(esp["Oyamel"], 1800)])
    vencer(vale)
    with pytest.raises(ValidationError, match="un vale vencido no es válido"):
        planta.registrar_salida(usuarios["vivero"], vale, esp["Oyamel"], 10)
    with pytest.raises(ValidationError, match="vencido no es válido"):
        planta.validar_vale(usuarios["vivero"], vale)
    assert not SalidaPlanta.objects.exists()


def test_hu_3_4_en_rhf_el_vale_vencido_se_repone_solo_por_lo_no_entregado_y_si_hay_planta(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("RHF")
    viejo = emitir(usuarios, exp, vivero, [(esp["Oyamel"], 1000), (esp["Encino"], 800)])
    planta.registrar_salida(usuarios["vivero"], viejo, esp["Oyamel"], 400)
    assert planta.situacion_para_emitir(exp)["motivo"].startswith("Ya tiene el vale")  # vigente: no se repone
    vencer(viejo)
    assert planta.situacion_para_emitir(exp)["tipo"] == "reposicion"
    with pytest.raises(ValidationError, match="planta disponible"):
        emitir(usuarios, exp, vivero, [(esp["Oyamel"], 600)], planta_disponible=False)
    with pytest.raises(ValidationError, match="solo faltan por entregar 600"):
        emitir(usuarios, exp, vivero, [(esp["Oyamel"], 700), (esp["Encino"], 800)], motivo_ajuste="x")
    with pytest.raises(ValidationError, match="no estaba en el vale"):
        emitir(usuarios, exp, vivero, [(esp["Aile"], 10)], motivo_ajuste="x")
    nuevo = emitir(usuarios, exp, vivero, [(esp["Oyamel"], 600), (esp["Encino"], 800)])  # coincide con lo pendiente: sin motivo
    viejo.refresh_from_db()
    assert nuevo.repone == viejo and nuevo.propuesta_total == 1400 and nuevo.situacion() == "vigente"
    assert viejo.situacion() == "repuesto" and nuevo.vence_el > timezone.localdate()
    assert exp.eventos.filter(tipo="vale_repuesto").exists()
    with pytest.raises(ValidationError, match="fue repuesto por el"):
        planta.registrar_salida(usuarios["vivero"], viejo, esp["Oyamel"], 1)
    planta.registrar_salida(usuarios["vivero"], nuevo, esp["Oyamel"], 600)
    planta.registrar_salida(usuarios["vivero"], nuevo, esp["Encino"], 800)
    exp.refresh_from_db()
    assert exp.estado.clave == "planta_entregada"


def test_hu_3_4_en_ps_las_rop_no_preven_reposicion_y_el_sistema_lo_dice_citando_la_regla(contratadas, catalogo_planta, usuarios):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)])
    vencer(vale)
    situacion = planta.situacion_para_emitir(exp)
    assert not situacion["puede"] and "8.1.7 inciso e" in situacion["motivo"] and "5931" in situacion["motivo"]
    with pytest.raises(ValidationError, match="no prevén reposición"):
        emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)])
    assert planta.config_vale(exp)["reposicion"] is False  # es un dato por programa, no código


def test_hu_3_4_la_reposicion_es_un_dato_por_programa(contratadas, catalogo_planta, usuarios):
    cfg = planta.datos_contrato()["vale_de_planta"]
    assert cfg["RHF"]["reposicion"] is True and cfg["PS"]["reposicion"] is False
    assert "3280" in cfg["RHF"]["reposicion_texto"] and "5931" in cfg["PS"]["reposicion_texto"]


# ----------------------------------------------------------------------------- pantallas
def test_hu_3_4_pantallas_de_la_delegacion_emision_pestana_y_pdf(contratadas, catalogo_planta, usuarios, client, contrasena):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    assert "Entregar el Vale de Planta" in client.get(f"/recepcion/expediente/{exp.folio}/").content.decode()
    assert 'data-prueba="panel-vales-por-entregar"' in client.get("/bandeja/").content.decode()
    html = client.get(f"/contrato/vales/emitir/{exp.folio}/").content.decode()
    assert 'id="form-vale"' in html and "4400" in html and "30 días" in html and "Pino patula" in html
    r = client.post(f"/contrato/vales/emitir/{exp.folio}/", {"vivero": vivero.pk, f"esp_{esp['Pino patula'].pk}": 4400}, follow=True)
    vale = ValePlanta.objects.get()
    html = r.content.decode()
    assert vale.folio in html and "Vigente" in html and "Ver el vale en PDF" in html
    pestana = client.get(f"/recepcion/expediente/{exp.folio}/?pestana=contrato").content.decode()
    assert 'data-prueba="vale"' in pestana and vale.folio in pestana and "HU-3.4" in pestana
    assert "por-construir" not in pestana
    pdf = client.get(f"/contrato/vales/{vale.folio}/pdf/")
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    assert vale.folio in client.get("/contrato/vales/").content.decode()
    client.login(username="comite", password=contrasena)
    assert client.get("/contrato/vales/").status_code == 403


def test_hu_3_4_pantallas_del_vivero_validacion_y_salida(contratadas, catalogo_planta, usuarios, client, contrasena):
    vivero, esp = catalogo_planta
    _, (exp, otro) = contratadas("PS", cuantas=2)
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 3000), (esp["Oyamel"], 1400)])
    viejo = emitir(usuarios, otro, vivero, [(esp["Pino patula"], 3300)])
    vencer(viejo)
    client.login(username="vivero", password=contrasena)
    assert 'data-prueba="panel-vales-por-surtir"' in client.get("/bandeja/").content.decode()
    html = client.get("/contrato/vivero/").content.decode()
    assert vale.folio in html and viejo.folio not in html.split('data-prueba="otros-vales"')[0]
    assert client.get("/contrato/vales/").status_code == 302  # el vivero va a su bandeja
    # vale vencido: no es válido
    r = client.get("/contrato/vivero/", {"folio": viejo.folio})
    assert 'data-prueba="vale-no-valido"' in r.content.decode() and "vencido no es válido" in r.content.decode()
    r = client.get("/contrato/vivero/", {"folio": "VP-NO-EXISTE"})
    assert "No hay un vale" in r.content.decode()
    # vale vigente: valida y abre el detalle
    r = client.get("/contrato/vivero/", {"folio": vale.folio.lower()}, follow=True)
    assert 'id="form-salida"' in r.content.decode()
    # la salida
    r = client.post(f"/contrato/vales/{vale.folio}/salida/", {"especie": esp["Pino patula"].pk, "cantidad": 1000}, follow=True)
    assert "Salida registrada" in r.content.decode() and 'data-prueba="salidas"' in r.content.decode()
    r = client.post(f"/contrato/vales/{vale.folio}/salida/", {"especie": esp["Oyamel"].pk, "cantidad": 9999}, follow=True)
    assert "no se entrega más de lo autorizado" in r.content.decode()
    assert SalidaPlanta.objects.filter(vale=vale).count() == 1
    # el vale vencido en el detalle no deja registrar
    html = client.get(f"/contrato/vales/{viejo.folio}/").content.decode()
    assert 'id="form-salida"' not in html and 'data-situacion="vencido"' in html
    # un vivero no ve los vales de otro
    from nucleo.models import Unidad, Usuario
    otra = Unidad.objects.create(clave="VIV-OTRO", nombre="Otro vivero", tipo="vivero")
    Usuario.objects.create_user(username="vivero_otro", password=contrasena, unidad=otra)
    client.login(username="vivero_otro", password=contrasena)
    assert client.get(f"/contrato/vales/{vale.folio}/").status_code == 404


def test_hu_3_4_la_pantalla_de_un_vale_vencido_de_ps_cita_que_no_hay_reposicion(contratadas, catalogo_planta, usuarios, client, contrasena):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 4400)])
    vencer(vale)
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    html = client.get(f"/contrato/vales/{vale.folio}/").content.decode()
    assert 'data-prueba="sin-reposicion"' in html and "5931" in html and "Reponer el vale" not in html
    assert 'data-prueba="vales-vencidos"' in client.get("/contrato/vales/").content.decode()


def test_hu_3_4_la_pantalla_de_un_vale_vencido_de_rhf_ofrece_reponerlo(contratadas, catalogo_planta, usuarios, client, contrasena):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("RHF")
    vale = emitir(usuarios, exp, vivero, [(esp["Oyamel"], 1800)])
    vencer(vale)
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    assert "Reponer el vale" in client.get(f"/contrato/vales/{vale.folio}/").content.decode()
    html = client.get(f"/contrato/vales/emitir/{exp.folio}/").content.decode()
    assert "Repone al vale" in html and "planta disponible" in html
    r = client.post(f"/contrato/vales/emitir/{exp.folio}/", {"vivero": vivero.pk, f"esp_{esp['Oyamel'].pk}": 1800,
                                                            "planta_disponible": "on"}, follow=True)
    assert ValePlanta.objects.count() == 2 and ValePlanta.objects.get(repone=vale)
    assert "repone al" in r.content.decode().lower() or "Repone al vale" in r.content.decode()


@pytest.mark.parametrize("programa", ["PS", "RHF"])
def test_hu_3_4_el_recorrido_corre_en_ps_y_rhf(contratadas, catalogo_planta, usuarios, programa):
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas(programa)
    total = planta.propuesta(exp)["total"] or 1000
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], total)], motivo_ajuste="demo")
    planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], total)
    exp.refresh_from_db()
    assert exp.estado.clave == "planta_entregada"


def _filas_de(exp, registro):
    from nucleo.trazabilidad import historial_expediente

    return [f for f in historial_expediente(exp) if f["registro"] == registro]


def test_hu_3_4_trazabilidad_del_vale_y_de_la_salida(contratadas, catalogo_planta, usuarios):
    """Criterio 4: el vale (Delegación) y cada salida de planta (vivero) quedan en el historial con su usuario."""
    vivero, esp = catalogo_planta
    _, (exp,) = contratadas("PS")
    vale = emitir(usuarios, exp, vivero, [(esp["Pino patula"], 3000), (esp["Oyamel"], 1400)])
    assert vale.history.get(history_type="+").history_user == delegado_de(usuarios, exp)
    planta.registrar_salida(usuarios["vivero"], vale, esp["Pino patula"], 1000)
    salida = SalidaPlanta.objects.get(vale=vale)
    assert salida.history.get(history_type="+").history_user == usuarios["vivero"]
    assert any(f["usuario"] == usuarios["vivero"] for f in _filas_de(exp, "Salida de planta"))
    assert len(_filas_de(exp, "Renglón del vale")) >= 2
