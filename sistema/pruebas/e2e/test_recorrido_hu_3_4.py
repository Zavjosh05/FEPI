"""HU-3.4 · Recorrido del Vale de Planta (Delegación), la validación y las salidas del vivero, el vale vencido y la
reposición en RHF."""
from datetime import timedelta

from django.utils import timezone
from playwright.sync_api import expect

from contrato import planta
from contrato.models import ValePlanta
from pruebas.fixtures_m3 import aprobadas, catalogo_planta, contratadas, delegado_de, en_delegacion, modelo_validado, notificadas  # noqa: F401


def test_hu_3_4_recorrido_vale_salidas_vencido_y_reposicion(  # noqa: F811
        datos_e2e, contratadas, catalogo_planta, usuarios, page, live_server, entrar, captura):
    vivero, esp = catalogo_planta
    _, (ps,) = contratadas("PS")
    _, (rhf,) = contratadas("RHF")

    # La Delegación entrega el Vale de Planta (PS): propuesta por hectárea y vigencia de las reglas.
    entrar(delegado_de(usuarios, ps).username)
    expect(page.locator("[data-prueba=panel-vales-por-entregar]")).to_be_visible()
    captura("hu_3_4_01_bandeja_de_la_delegacion_vales_por_entregar")
    page.goto(f"{live_server.url}/contrato/vales/emitir/{ps.folio}/")
    expect(page.locator("[data-prueba=propuesta-planta]")).to_contain_text("4400")
    page.select_option("#id_vivero", label=vivero.nombre)
    page.fill(f"#id_esp_{esp['Pino patula'].pk}", "3000")
    page.fill(f"#id_esp_{esp['Oyamel'].pk}", "1400")
    captura("hu_3_4_02_emision_del_vale_con_propuesta_y_vigencia")
    page.click("button:has-text('Entregar el vale')")
    expect(page.locator("[data-prueba=vigencia]")).to_contain_text("hasta el")
    captura("hu_3_4_03_vale_entregado_con_vigencia_y_acuse")
    page.goto(f"{live_server.url}/recepcion/expediente/{ps.folio}/?pestana=contrato")
    expect(page.locator("[data-prueba=vale]")).to_be_visible()
    captura("hu_3_4_04_pestana_contrato_con_el_vale")
    vale_ps = ValePlanta.objects.get(expediente=ps)

    # El vivero valida el vale y registra salidas parciales; una cantidad mayor a la autorizada se rechaza.
    entrar("vivero")
    expect(page.locator("[data-prueba=panel-vales-por-surtir]")).to_be_visible()
    page.goto(f"{live_server.url}/contrato/vivero/")
    page.fill("#folio", vale_ps.folio)
    captura("hu_3_4_05_bandeja_del_vivero")
    page.click("button:has-text('Validar el vale')")
    expect(page.locator("#form-salida")).to_be_visible()
    page.select_option("#id_especie", label=str(esp["Pino patula"]))
    page.fill("#id_cantidad", "1200")
    page.click("button:has-text('Registrar la salida')")
    expect(page.locator("[data-prueba=salidas]")).to_contain_text("1200")
    page.select_option("#id_especie", label=str(esp["Oyamel"]))
    page.fill("#id_cantidad", "9999")
    page.click("button:has-text('Registrar la salida')")
    expect(page.locator(".alert-danger")).to_contain_text("no se entrega más de lo autorizado")
    captura("hu_3_4_06_salida_parcial_y_exceso_rechazado")

    # Un vale de RHF vence: no es válido para el vivero y la Delegación lo repone por lo no entregado.
    vale = planta.emitir_vale(delegado_de(usuarios, rhf), rhf, vivero, [(esp["Oyamel"], 1800)])
    planta.registrar_salida(usuarios["vivero"], vale, esp["Oyamel"], 500)
    vale.entregado_en = timezone.now() - timedelta(days=40)
    vale.vence_el = timezone.localdate() - timedelta(days=5)
    vale.save()
    vale.salidas.update(salido_en=timezone.now() - timedelta(days=39))
    page.goto(f"{live_server.url}/contrato/vivero/?folio={vale.folio}")
    expect(page.locator("[data-prueba=vale-no-valido]")).to_contain_text("vencido no es válido")
    captura("hu_3_4_07_vale_vencido_no_es_valido")
    entrar(delegado_de(usuarios, rhf).username)
    page.goto(f"{live_server.url}/contrato/vales/{vale.folio}/")
    captura("hu_3_4_08_vale_vencido_en_la_delegacion")
    page.click("a:has-text('Reponer el vale')")
    expect(page.locator("[data-prueba=propuesta-planta]")).to_contain_text("1300")
    page.select_option("#id_vivero", label=vivero.nombre)
    page.fill(f"#id_esp_{esp['Oyamel'].pk}", "1300")
    page.check("#id_planta_disponible")
    captura("hu_3_4_09_reposicion_solo_de_lo_no_entregado")
    page.click("button:has-text('Reponer el vale')")
    expect(page.locator("[data-prueba=datos-vale]")).to_contain_text(vale.folio)
    captura("hu_3_4_10_vale_de_reposicion")
