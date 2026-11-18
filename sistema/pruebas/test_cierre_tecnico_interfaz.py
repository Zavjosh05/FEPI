"""Cierre técnico · pendientes de interfaz aceptados (P-33, P-36, P-37 y P-38).

* P-33: ningún texto visible dice «sprint» ni nombra historias (HU-x.y) ni quedan notas de «lo llenarán estas historias».
* P-36: las pestañas del expediente se acomodan (la prueba de navegador comprueba que caben a 1366 px).
* P-37: «Plazos de esta etapa» muestra la fecha límite que fijó el área en el aviso de omisiones.
* P-38: en el padrón público todas las fechas salen de lo registrado (mismo reloj); el botón de cierre concuerda en número.
"""
import re
from datetime import date

import pytest
from django.urls import NoReverseMatch, reverse

from ejecucion import verificacion
from nucleo import extensiones, reloj
from nucleo.models import Usuario
from recepcion.views import PESTANAS
from seguimiento import cierre, incumplimientos

from .fixtures_m2 import *  # noqa: F401,F403
from .fixtures_m3 import *  # noqa: F401,F403
from .fixtures_m3 import delegado_de
from .fixtures_m4 import *  # noqa: F401,F403
from .fixtures_m5 import *  # noqa: F401,F403
from .test_hu_4_2 import _archivo, _por_verificar
from .test_hu_6_3 import _concluida

pytestmark = pytest.mark.django_db
PROHIBIDO = re.compile(r"HU-\d|sprint|llenar[áa]n estas historias|por construir|django-simple-history|\bChanged\b|\bCreated\b", re.I)


def texto_visible(html):
    """El texto que ve la persona: sin scripts, estilos, comentarios ni atributos."""
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html)


def _sin_prohibidos(client, url, quien):
    r = client.get(url)
    if r.status_code != 200:
        return []
    texto = texto_visible(r.content.decode())
    return [f"{quien} {url}: …{texto[max(0, m.start() - 60): m.end() + 30]}…" for m in PROHIBIDO.finditer(texto)]


def test_p_33_ningun_texto_visible_dice_sprint_ni_nombra_historias(pagada, peg_contratado, entregado, cuenta_portal, usuarios,
                                                                   client):
    cc = _concluida(pagada, usuarios)                       # CC verificado y concluido
    with reloj.en("2026-09-01 10:00"):
        otro = pagada("PS")                                 # PS con la segunda ministración por verificar
        incumplimientos.avisar_omision(usuarios["dir_drff"], otro, "Falta la evidencia.", date(2026, 9, 15))
    peg = peg_contratado()
    psa, _ = entregado()
    persona = cuenta_portal(cc)
    claves = [c for c, _ in PESTANAS] + [p["clave"] for p in extensiones.PESTANAS_EXPEDIENTE]
    hallazgos = []
    for u in Usuario.objects.filter(cuenta_externa__isnull=True).exclude(username="admin"):
        client.force_login(u)
        paginas = [reverse("nucleo:bandeja")]
        for m in extensiones.MENU:
            try:
                paginas.append(reverse(m["url"]))
            except NoReverseMatch:
                pass
        for exp in (cc, otro, peg, psa):
            paginas += [reverse("recepcion:expediente", args=[exp.folio]) + f"?pestana={c}" for c in claves]
        for url in paginas:
            hallazgos += _sin_prohibidos(client, url, u.username)
    cierre.publicar_padron(usuarios["dir_drff"], cc.ejercicio)
    client.force_login(persona)
    hallazgos += _sin_prohibidos(client, reverse("portal:expediente", args=[cc.folio]), "portal")
    client.logout()
    for url in (reverse("padron:indice"), reverse("padron:programa", args=["CC", 2026]), "/contrato/resultados/",
                reverse("portal:entrar"), reverse("portal:consulta")):
        hallazgos += _sin_prohibidos(client, url, "público")
    assert not hallazgos, "\n".join(sorted(set(hallazgos))[:40])


def test_p_37_plazos_de_la_etapa_muestran_la_fecha_que_fijo_el_area(pagada, usuarios, client, contrasena):
    with reloj.en("2026-09-01 10:00"):
        exp, otro = pagada("CC", cuantas=2)
        aviso = incumplimientos.avisar_omision(usuarios["dir_drff"], exp, "Falta la evidencia.", date(2026, 9, 15))
    # El aviso vigente manda aunque el hito guarde otra fecha (por ejemplo, una corrección del aviso).
    type(aviso).objects.filter(pk=aviso.pk).update(vence=date(2026, 9, 11))
    client.login(username="dir_drff", password=contrasena)
    html = client.get(reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=seguimiento").content.decode()
    tabla = html[html.index('data-prueba="plazos-etapa"'):]
    tabla = texto_visible(tabla[: tabla.index("</table>")])
    assert "Subsanar las omisiones" in tabla and "11/09/2026 (fijada por el área responsable" in tabla
    assert "15/09/2026" not in tabla and "sin plazo en las reglas" not in tabla
    # Sin aviso: la fecha la fija el área al avisar (no «sin plazo en las reglas»).
    html = client.get(reverse("recepcion:expediente", args=[otro.folio]) + "?pestana=seguimiento").content.decode()
    assert "la fija el área responsable en el aviso de la omisión" in texto_visible(html)


def test_p_38_el_padron_usa_un_solo_reloj_y_el_boton_de_cierre_concuerda(pagada, usuarios, client, contrasena):
    exps = _por_verificar(pagada, usuarios, "CC", "2026-11-12 10:00", date(2026, 11, 11), ha=4, cuantas=2)
    with reloj.en("2026-11-20 10:00"):                       # el último movimiento (reloj simulado)
        for e in exps:
            verificacion.registrar_verificacion(delegado_de(usuarios, e), e, "informe_final_firmado", _archivo("i.pdf"),
                                                superficie_verificada="4")
            verificacion.dar_por_concluida(usuarios["dir_drff"], e)
    exp = exps[0]
    client.login(username="dir_drff", password=contrasena)
    html = client.get(reverse("seguimiento:cierre_detalle", args=[exp.ejercicio.pk])).content.decode()
    assert "Cerrar los 2 expedientes que ya cuadran" in html
    with reloj.en("2026-11-24 09:00"):
        cierre.cerrar_expediente(usuarios["dir_drff"], exps[1])
    html = client.get(reverse("seguimiento:cierre_detalle", args=[exp.ejercicio.pk])).content.decode()
    assert "Cerrar el expediente que ya cuadra" in html and "Cerrar los 1" not in html
    client.logout()
    with reloj.en("2026-11-24 09:15"):
        cierre.publicar_padron(usuarios["dir_drff"], exp.ejercicio)
    html = texto_visible(client.get(reverse("padron:programa", args=["CC", 2026])).content.decode())
    assert "Publicado el 24/11/2026 a las 09:15 h" in html and "actualizado al 24/11/2026 a las 09:00 h" in html
    assert "Consulta del" not in html                        # ninguna fecha del reloj del servidor junto a las registradas


def test_p_35_la_delegacion_da_acceso_al_prestador_y_este_envia_desde_el_portal(pagada, usuarios, client, contrasena):
    """MFS: la Delegación da acceso al portal al prestador de servicios forestales (RFN) desde la pestaña «Ejecución»; con el
    código del acuse define su contraseña, ve el expediente con el papel de prestador y entrega la Bitácora."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from ejecucion import comprobaciones
    from nucleo.demo import _pdf_demo
    from portal import cuentas
    from portal.models import RolAcceso

    from .fixtures_m4 import CONTRASENA_PORTAL, _codigos

    with reloj.en("2026-08-03 10:00"):
        exp = pagada("MFS")
    pestana = reverse("recepcion:expediente", args=[exp.folio]) + "?pestana=ejecucion"
    client.login(username="dir_drff", password=contrasena)
    assert 'data-prueba="dar-acceso-prestador"' not in client.get(pestana).content.decode()   # solo la Delegación
    client.login(username=delegado_de(usuarios, exp).username, password=contrasena)
    assert 'data-prueba="dar-acceso-prestador"' in client.get(pestana).content.decode()
    url = reverse("ejecucion:acceso_prestador", args=[exp.folio])
    client.post(url, {"nombre": "Ing. Tomás Ríos Peña", "curp": "CURP-MALA", "rfn": "RFN-MEX-0042"})
    assert not cuentas.prestadores_de(exp).exists()
    r = client.post(url, {"nombre": "Ing. Tomás Ríos Peña", "curp": "RIPT750101HMCSXM03", "rfn": "RFN-MEX-0042"}, follow=True)
    assert "Acceso al portal para el prestador" in r.content.decode()
    acceso = cuentas.prestadores_de(exp).get()
    assert acceso.rol == RolAcceso.PRESTADOR and acceso.cuenta.persona.rfn == "RFN-MEX-0042" and acceso.acuse.tipo == "alta_portal"
    html = texto_visible(client.get(pestana).content.decode())
    assert "Ing. Tomás Ríos Peña · RFN RFN-MEX-0042 · usuario RIPT750101HMCSXM03 · falta su primer acceso" in html
    codigo = _codigos(acceso.acuse)[0]
    prestador = cuentas.primer_acceso("RIPT750101HMCSXM03", codigo, CONTRASENA_PORTAL)
    client.logout()
    client.force_login(prestador)
    assert exp.folio in client.get(reverse("portal:inicio")).content.decode()
    assert 'id="form-envio-portal"' in client.get(reverse("portal:expediente", args=[exp.folio])).content.decode()
    with reloj.en("2026-10-01 10:00"):
        c = comprobaciones.registrar_envio(prestador, exp, "bitacora_etf",
                                           SimpleUploadedFile("bitacora.pdf", _pdf_demo("Bitácora"), content_type="application/pdf"))
    assert c.medio == "portal" and c.acuse.tipo == "comprobacion" and "Tomás Ríos" in c.persona_entrega
