"""P-21: el menú de la barra superior va agrupado por módulo. A 1366 px el nombre de la persona, su unidad y «Salir»
quedan visibles y dentro de la ventana, y cada enlace del menú lleva a su pantalla."""
import pytest
from playwright.sync_api import expect

from pruebas.e2e.conftest import ir_a

UNIDADES = ["del_amecameca", "dir_drff", "dir_dpf", "juridica", "comite", "finanzas", "vivero", "fiduciaria", "admin"]


def _dentro_de_la_ventana(page, selector):
    caja = page.locator(selector).first.bounding_box()
    ancho = page.viewport_size["width"]
    assert caja is not None, f"{selector} no está visible"
    assert caja["x"] >= 0 and caja["x"] + caja["width"] <= ancho + 0.5, f"{selector} se sale de la ventana: {caja}"


def _enlaces_del_menu(page):
    return page.eval_on_selector_all(
        "nav.barra-probosque #menu a.nav-link, nav.barra-probosque #menu a.dropdown-item",
        "els => els.map(e => e.textContent.trim())")


@pytest.mark.parametrize("usuario", UNIDADES)
def test_p_21_a_1366_px_el_nombre_y_salir_quedan_visibles_y_cada_enlace_lleva_a_su_pantalla(
        page, datos_e2e, entrar, usuario):
    page.set_viewport_size({"width": 1366, "height": 900})
    entrar(usuario)
    barra = page.locator("nav.barra-probosque")
    expect(barra.locator(".usuario-barra .fw-semibold")).to_be_visible()
    expect(barra.get_by_role("button", name="Salir")).to_be_visible()
    for selector in ("nav.barra-probosque .usuario-barra .fw-semibold", "nav.barra-probosque [data-prueba=unidad]",
                     "nav.barra-probosque .usuario-barra button"):
        _dentro_de_la_ventana(page, selector)
    # La barra cabe en una sola línea y la página no se desplaza a los lados.
    assert barra.bounding_box()["height"] < 80
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    # Los enlaces de módulo van en grupos desplegables, no sueltos
    grupos = barra.locator("button.dropdown-toggle").all_inner_texts()
    assert all(g.strip() for g in grupos)
    nombres = [n for n in _enlaces_del_menu(page) if n not in ("Bandeja", "Catálogos") and n not in grupos]
    for nombre in dict.fromkeys(nombres):
        with page.expect_navigation() as nav:
            ir_a(page, nombre)
        assert nav.value.status == 200, f"{usuario}: «{nombre}» respondió {nav.value.status}"
        expect(page.locator("nav.barra-probosque .usuario-barra button")).to_be_visible()
        assert "Server Error" not in page.title()


def test_p_21_la_direccion_ve_sus_grupos_en_el_orden_de_los_modulos(page, datos_e2e, entrar, captura):
    page.set_viewport_size({"width": 1366, "height": 900})
    entrar("dir_drff")
    grupos = [g.strip() for g in page.locator("nav.barra-probosque button.dropdown-toggle").all_inner_texts()]
    # «Pagos» es un solo enlace para la Dirección; «Ejecución y verificación» es grupo desde la evaluación de reportes y
    # «Seguimiento y cierre» desde el cierre del ejercicio (Seguimiento y Cierre del ejercicio).
    assert grupos == ["Dictamen y Comité", "Listados", "Publicación y contrato", "Ejecución y verificación",
                      "Seguimiento y cierre"]
    expect(page.locator("nav.barra-probosque a.nav-link:text-is('Pagos')")).to_be_visible()
    page.click("button.dropdown-toggle:text-is('Publicación y contrato')")
    expect(page.locator("a.dropdown-item:text-is('Contratos')")).to_be_visible()
    captura("s2_14_menu_direccion")


def test_p_21_la_delegacion_y_la_secretaria_tecnica_solo_ven_lo_suyo(page, datos_e2e, entrar, captura):
    page.set_viewport_size({"width": 1366, "height": 900})
    entrar("del_amecameca")
    barra = page.locator("nav.barra-probosque")
    expect(barra.locator("a.nav-link", has_text="Registrar solicitud")).to_be_visible()
    expect(barra.locator("a.dropdown-item", has_text="Modelos")).to_have_count(0)
    page.click("button.dropdown-toggle:text-is('Publicación y contrato')")
    captura("s2_14_menu_delegacion")
    entrar("comite")
    assert [g.strip() for g in barra.locator("button.dropdown-toggle").all_inner_texts()] == ["Dictamen y Comité", "Listados",
                                                                                              "Seguimiento y cierre"]
    page.click("button.dropdown-toggle:text-is('Dictamen y Comité')")
    captura("s2_14_menu_secretaria_tecnica")


def test_p_21_en_movil_el_menu_va_colapsado_y_se_usa_con_teclado(page, datos_e2e, entrar, captura):
    page.set_viewport_size({"width": 375, "height": 812})
    entrar("dir_drff")
    expect(page.locator("button.navbar-toggler")).to_be_visible()
    expect(page.locator("#menu")).not_to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.click("button.navbar-toggler")
    expect(page.locator("#menu")).to_be_visible()
    expect(page.get_by_role("button", name="Salir")).to_be_visible()
    _dentro_de_la_ventana(page, "nav.barra-probosque .usuario-barra button")
    page.click("button.dropdown-toggle:text-is('Dictamen y Comité')")
    captura("s2_14_menu_movil")
    # Con teclado: el grupo se abre con Enter y se recorre con Tab hasta el enlace
    page.locator("button.dropdown-toggle:text-is('Publicación y contrato')").focus()
    page.keyboard.press("Enter")
    expect(page.locator("a.dropdown-item:text-is('Contratos')")).to_be_visible()
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.classList.contains('dropdown-item')")
