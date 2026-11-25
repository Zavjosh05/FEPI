"""Genera el resumen en PDF de un sprint: entregas/sprint_N/Resumen_sprint_N.pdf.

El texto de cada sprint está en `entregas/sprint_N/resumen_contenido.html` (se escribe a mano) y sus
datos en `entregas/sprint_N/resumen_datos.json` (commits, cifras, estados del sprint). Lo demás se genera:

- las tablas de historias y de cobertura de necesidades, de `sistema/especificacion/modelo.json` y
  `necesidades_v12.json`; el número de pruebas se cuenta en los archivos de prueba;
- el diagrama de estados, de `sistema/datos/flujo_tramite.json` (solo los estados que lista el sprint);
- los diagramas entidad-relación, de `sistema/docs/modelo_datos.md`, reducidos a las tablas principales que lista
  el sprint en `er` (área, tablas y número de campos), para que se lean en una hoja;
- los diagramas escritos en el texto (`<pre class="mermaid" data-nombre="…" data-pie="…">`);
- el anexo de capturas, de `entregas/sprint_N/capturas/`.

Los diagramas se dibujan con Mermaid en el Chromium de Playwright (necesita internet para bajar Mermaid)
y quedan en `entregas/sprint_N/diagramas/`. Se corre con la imagen de pruebas del sistema, que trae
WeasyPrint y Playwright (desde la raíz del repositorio):

    wsl -e bash -lc "docker run --rm -v /mnt/c/Users/<usuario>/Documents/GitHub/FEPI:/repo -w /repo \
        --entrypoint python probosque-sistema-pruebas:sprint-1 entregas/generar_resumen.py 1"

Con `--html` deja también el HTML intermedio; con `--sin-diagramas` reutiliza los PNG ya dibujados.
"""
import html
import json
import os
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ESPEC = RAIZ / "sistema" / "especificacion"
# Sin internet, se puede apuntar a una copia local: MERMAID_JS=file:///ruta/mermaid.min.js
MERMAID_JS = os.environ.get("MERMAID_JS", "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js")
PROGRAMAS = {"CC": "Capturando Carbono", "MFS": "Manejo Forestal Sustentable", "PS": "Plantaciones Sustentables",
             "RHF": "Restauración Hidrológico-Forestal", "PSA": "PSAHEM", "PEG": "Guardabosques",
             "CF": "Calculadora forestal"}
UNIDADES = {"delegacion": "Delegación", "direccion": "Dirección", "juridica": "U. Jurídica",
            "secretaria_comite": "Secretaría Técnica", "admin_finanzas": "Adm. y Finanzas", "vivero": "Vivero",
            "fiduciaria": "Fiduciaria"}
# Los nombres de archivo de las capturas no llevan acentos: se reponen para los pies de imagen.
ACENTOS = {
    "delegacion": "Delegación", "direccion": "Dirección", "poligono": "polígono", "validacion": "validación",
    "notificacion": "notificación", "notificaciones": "notificaciones", "sesion": "sesión", "aprobacion": "aprobación",
    "publicacion": "publicación", "tecnico": "técnico", "tecnica": "Técnica", "juridico": "jurídico",
    "juridica": "Jurídica", "senalado": "señalado", "emision": "emisión", "envio": "envío", "remision": "remisión",
    "bitacora": "bitácora", "area": "área", "pagina": "página", "publica": "pública", "busqueda": "búsqueda",
    "comite": "Comité", "secretaria": "Secretaría", "administracion": "Administración", "reposicion": "reposición",
    "anio": "año", "anios": "años", "limite": "límite", "habiles": "hábiles", "verificacion": "verificación",
    "ministracion": "ministración", "ministraciones": "ministraciones", "instruccion": "instrucción",
    "fiduciaria": "Fiduciaria", "movil": "móvil", "cartografico": "cartográfico", "analisis": "análisis",
    "automatico": "automático", "autorizacion": "autorización", "evolucion": "evolución", "ubicacion": "ubicación",
    "dias": "días", "inicio": "inicio", "revision": "revisión", "elaboracion": "elaboración", "seguimiento": "seguimiento",
    "informacion": "información", "segun": "según", "ultimo": "último", "numero": "número", "psa": "PSAHEM",
    "ps": "PS", "peg": "Guardabosques", "psahem": "PSAHEM", "htmx": "(sin recargar)", "pdf": "PDF",
}

CSS = """
@page { size: Letter; margin: 2.1cm 2cm 2.2cm 2cm;
  @bottom-left { content: "PROBOSQUE 2026 · Resumen del sprint __SPRINT__"; font-size: 8pt; color: #666; }
  @bottom-right { content: counter(page) " / " counter(pages); font-size: 8pt; color: #666; } }
@page :first { margin-top: 5cm; @bottom-left { content: ""; } @bottom-right { content: ""; } }
html { font-family: "DejaVu Sans", "Noto Sans", sans-serif; font-size: 9.6pt; line-height: 1.45; color: #1c1c1c; }
h1 { font-size: 24pt; line-height: 1.15; margin: 0 0 .3cm; color: #1f4d2e; }
h2 { font-size: 14pt; color: #1f4d2e; margin: .9cm 0 .25cm; padding-bottom: .12cm; border-bottom: 1.2pt solid #1f4d2e;
     break-after: avoid; }
h3 { font-size: 11pt; margin: .55cm 0 .15cm; color: #26382b; break-after: avoid; }
p { margin: 0 0 .22cm; } ul, ol { margin: 0 0 .25cm; padding-left: .55cm; } li { margin-bottom: .08cm; }
.portada p.sub { font-size: 12pt; color: #444; margin-bottom: .8cm; }
.portada table { width: auto; } .portada td { border: none; padding: .08cm .5cm .08cm 0; }
.caja { background: #eef4ee; border-left: 3pt solid #1f4d2e; padding: .25cm .35cm; margin: .3cm 0; break-inside: avoid; }
.aviso { background: #fbf3df; border-left: 3pt solid #b7791f; padding: .25cm .35cm; margin: .3cm 0; break-inside: avoid; }
table { width: 100%; border-collapse: collapse; margin: .2cm 0 .35cm; font-size: 8.4pt; }
th { background: #1f4d2e; color: #fff; text-align: left; padding: .12cm .16cm; font-weight: 600; }
td { padding: .11cm .16cm; border-bottom: .4pt solid #c9d3cb; vertical-align: top; }
tr { break-inside: avoid; } thead { display: table-header-group; }
td.n, th.n { text-align: right; white-space: nowrap; } code, .id { font-family: "DejaVu Sans Mono", monospace; font-size: 8pt; }
.id { white-space: nowrap; } .gris { color: #666; }
figure { margin: .3cm 0 .45cm; break-inside: avoid; } figcaption { font-size: 8pt; color: #555; margin-top: .1cm; }
figure img { width: 100%; border: .5pt solid #b8c2ba; }
figure.diagrama { text-align: center; } figure.diagrama img { border: none; width: auto; max-width: 100%; max-height: 21cm; }
figure.recorte div { height: 8.2cm; overflow: hidden; border: .5pt solid #b8c2ba; } figure.recorte img { border: none; }
.dos { display: flex; gap: .4cm; } .dos > * { flex: 1; min-width: 0; }
.anexo figure.recorte div { height: 9.4cm; } .anexo h3 { margin-top: .35cm; }
.flujo { font-size: 8.4pt; } .flujo span { display: inline-block; border: .6pt solid #1f4d2e; border-radius: 3pt;
  padding: .05cm .18cm; margin: .06cm .05cm; background: #fff; } .flujo span.alt { border-color: #b7791f; background: #fbf3df; }
.salto { break-before: page; }
"""


def e(texto):
    return html.escape(str(texto))


# ----------------------------------------------------------------------------- tablas
def contar_pruebas(rutas):
    total = 0
    for patron in rutas:
        for archivo in RAIZ.glob(patron):
            total += len(re.findall(r"^def test_", archivo.read_text(encoding="utf-8"), flags=re.M))
    return total


def historias_del(sprint, modelo):
    return [x for x in modelo["historias"] if x["sprint"] == sprint]


def tabla_historias(sprint, modelo, datos):
    filas = []
    for h in historias_del(sprint, modelo):
        a, b = h["id"].split("-")[1].split(".")
        if a == "7":
            pruebas = contar_pruebas([f"pruebas/calculadora/test_hu_{a}_{b}_*.py"])
        else:
            pruebas = contar_pruebas([f"sistema/pruebas/test_hu_{a}_{b}.py", f"sistema/pruebas/e2e/test_recorrido_hu_{a}_{b}.py"])
            if not pruebas:                                  # los recorridos del sprint 1 van en un solo archivo
                pruebas = contar_pruebas([f"sistema/pruebas/test_hu_{a}_{b}.py"])
        d = datos["historias"].get(h["id"], {})
        filas.append(
            f"<tr><td class='id'>{e(h['id'])}</td><td>{e(h['titulo'])}<br><span class='gris'>{e(h['rol'].capitalize())}</span></td>"
            f"<td class='n'>{h['puntos']}</td><td class='n'>{len(h['criterios'])}</td><td class='n'>{pruebas}</td>"
            f"<td class='id'>{e(d.get('commit', ''))}</td><td>{e(d.get('estado', 'Hecha'))}</td></tr>")
    return ("<table><thead><tr><th>Historia</th><th>Título y rol</th><th class='n'>Puntos</th><th class='n'>Criterios</th>"
            "<th class='n'>Pruebas</th><th>Commit</th><th>Estado</th></tr></thead><tbody>" + "".join(filas) + "</tbody></table>")


def funciones(modelo):
    todas = {}
    for mod in modelo["modulos"] + [modelo["calculadora"]]:
        for f in mod["funciones"]:
            todas[f["id"]] = f
    return todas


def tabla_cobertura(sprint, modelo, datos):
    """Por historia: su función, las necesidades que cubre, cómo se cubrió y con qué se comprueba."""
    fun = funciones(modelo)
    filas = []
    for h in historias_del(sprint, modelo):
        f = fun[h["funcion"]]
        d = datos["historias"].get(h["id"], {})
        criterios = "".join(f"<li>{e(c)}</li>" for c in h["criterios"])
        filas.append(
            f"<tr><td><span class='id'>{e(h['id'])}</span><br><b>{e(h['titulo'])}</b><br><span class='gris'>Función {e(f['id'])}</span></td>"
            f"<td><ol>{criterios}</ol></td><td>{d.get('como', '')}</td>"
            f"<td class='id' style='white-space:normal'>{e(', '.join(f['necesidades']))}</td></tr>")
    return ("<table><thead><tr><th style='width:17%'>Historia</th><th style='width:27%'>Criterios de aceptación</th>"
            "<th style='width:36%'>Cómo se cubrió</th><th>Necesidades que atiende</th></tr></thead><tbody>"
            + "".join(filas) + "</tbody></table>")


def tabla_necesidades(sprint, modelo, necesidades, datos):
    """Anexo: cada necesidad tocada por el sprint, con su nombre, sus funciones y su situación por programa."""
    del_sprint = {h["funcion"] for h in historias_del(sprint, modelo)}
    sprint_de = {h["funcion"]: h["sprint"] for h in modelo["historias"]}
    situacion = datos.get("situacion_programa", {})
    filas, resumen = [], {}
    for clave, nec in necesidades.items():
        todas = modelo["necesidad_a_funciones"].get(clave, [])
        aqui = [f for f in todas if f in del_sprint]
        if not aqui:
            continue
        prog = clave.split("-")[0]
        faltan = [f"{f} (sprint {sprint_de[f]})" for f in todas if f not in del_sprint and sprint_de[f] > sprint]
        resumen.setdefault(prog, [0, 0])
        resumen[prog][0] += 1
        resumen[prog][1] += 0 if faltan else 1
        nombre = nec.get("nombre_corto") or nec["texto"].split(":")[0].replace("Mecanismo de soporte para ", "").capitalize()
        filas.append(f"<tr><td class='id'>{e(clave)}</td><td>{e(nombre)}</td><td class='id'>{e(', '.join(aqui))}</td>"
                     f"<td>{e(', '.join(faltan)) or 'Completa con este sprint'}</td><td>{e(situacion.get(prog, ''))}</td></tr>")
    cab = ("<table><thead><tr><th>Necesidad</th><th>Nombre</th><th>Funciones de este sprint</th>"
           "<th>Funciones que faltan</th><th>Situación del programa</th></tr></thead><tbody>")
    total = {p: sum(1 for k in necesidades if k.split('-')[0] == p) for p in PROGRAMAS}
    res = "".join(f"<tr><td>{e(PROGRAMAS[p])}</td><td class='n'>{total[p]}</td><td class='n'>{v[0]}</td><td class='n'>{v[1]}</td></tr>"
                  for p, v in resumen.items())
    res = ("<table style='width:70%'><thead><tr><th>Programa</th><th class='n'>Necesidades</th>"
           "<th class='n'>Atendidas en este sprint</th><th class='n'>De ellas, completas</th></tr></thead><tbody>" + res + "</tbody></table>")
    return res, cab + "".join(filas) + "</tbody></table>"


# ----------------------------------------------------------------------------- diagramas
def mermaid_estados(datos):
    """Diagrama de estados del trámite con los estados que lista el sprint (`estados` y `estados_nuevos`)."""
    flujo = json.loads((RAIZ / "sistema" / "datos" / "flujo_tramite.json").read_text(encoding="utf-8"))
    elegidos = datos.get("estados") or [x["clave"] for x in flujo["estados"]]
    nuevos = set(datos.get("estados_nuevos", []))
    por_clave = {x["clave"]: x for x in flujo["estados"]}
    lineas = ["flowchart TD"]
    for clave in elegidos:
        est = por_clave[clave]
        nombre = est["nombre"].replace('"', "'")
        if est.get("flujo_alterno"):
            nombre += f"<br/><i>flujo alterno {est['flujo_alterno']}</i>"
        forma = f'(["{nombre}"])' if est.get("final") else f'["{nombre}"]'
        lineas.append(f"  {clave}{forma}")
    vistos = {}
    for t in flujo["transiciones"]:
        if t["origen"] in elegidos and t["destino"] in elegidos:
            quien = UNIDADES.get(t["tipo_unidad"], t["tipo_unidad"])
            if t.get("programas"):
                quien += " · " + ", ".join(t["programas"])
            vistos.setdefault((t["origen"], t["destino"]), []).append(quien)
    for (origen, destino), quienes in vistos.items():
        lineas.append(f'  {origen} -->|"{" / ".join(dict.fromkeys(quienes))}"| {destino}')
    alternos = [c for c in elegidos if por_clave[c].get("flujo_alterno")]
    lineas.append("  classDef alterno fill:#fbf3df,stroke:#b7791f,color:#3a2a06;")
    lineas.append("  classDef nuevo fill:#dcebdf,stroke:#1f4d2e,stroke-width:2px;")
    if alternos:
        lineas.append("  class " + ",".join(alternos) + " alterno;")
    if nuevos - set(alternos):
        lineas.append("  class " + ",".join(c for c in elegidos if c in nuevos and c not in alternos) + " nuevo;")
    return "\n".join(lineas)


def mermaid_er(area, entidades, campos=4):
    """Diagrama entidad-relación de un área de modelo_datos.md, reducido a las tablas `entidades` (las principales)
    y a los primeros `campos` campos de cada una, para que se pueda leer en una hoja."""
    md = (RAIZ / "sistema" / "docs" / "modelo_datos.md").read_text(encoding="utf-8")
    bloque = re.findall(r"```mermaid\n(.*?)```", md, flags=re.S)[area - 1]
    lineas, pares = ["erDiagram"], set()
    for linea in bloque.splitlines():
        m = re.match(r"\s*(\w+) (\S+) (\w+) : (.+)", linea)
        if m and m.group(1) in entidades and m.group(3) in entidades and (m.group(1), m.group(3)) not in pares:
            pares.add((m.group(1), m.group(3)))
            lineas.append(f"  {m.group(1)} {m.group(2)} {m.group(3)} : {m.group(4)}")
    for nombre, cuerpo in re.findall(r"^\s*(\w+) \{\n(.*?)^\s*\}", bloque, flags=re.S | re.M):
        if nombre in entidades:
            filas = [f for f in cuerpo.splitlines() if f.strip()][:campos]
            lineas += [f"  {nombre} {{"] + filas + ["  }"]
    return "\n".join(lineas)


def dibujar(diagramas, carpeta):
    """Dibuja cada diagrama de Mermaid a PNG con el Chromium de Playwright."""
    from playwright.sync_api import sync_playwright

    carpeta.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 2200, "height": 1200}, device_scale_factor=2)
        if MERMAID_JS.startswith("file://"):
            pagina.goto(MERMAID_JS)   # con origen file:// la página puede cargar la copia local de Mermaid
        for nombre, codigo in diagramas.items():
            pagina.set_content(
                "<html><body style='margin:0;background:#fff'>"
                f"<pre class='mermaid' id='d' style='margin:0;display:inline-block'>{html.escape(codigo)}</pre>"
                f"<script src='{MERMAID_JS}'></script><script>mermaid.initialize({{startOnLoad: true, theme: 'neutral', "
                "fontFamily: 'DejaVu Sans, sans-serif', flowchart: {htmlLabels: true, curve: 'basis', useMaxWidth: false}, "
                "er: {useMaxWidth: false}, sequence: {mirrorActors: false, useMaxWidth: false}});</script></body></html>")
            pagina.wait_for_selector("#d svg", timeout=90000)
            pagina.wait_for_timeout(400)
            pagina.locator("#d svg").screenshot(path=str(carpeta / f"{nombre}.png"))
            print(f"  diagrama {nombre}.png")
        navegador.close()


def figura(nombre, pie):
    return f"<figure class='diagrama'><img src='diagramas/{nombre}.png' alt='{e(pie)}'><figcaption>{e(pie)}</figcaption></figure>"


# ----------------------------------------------------------------------------- capturas
def pie_de(nombre_archivo):
    base = re.sub(r"^(hu_\d+_\d+|recorrido_sprint_\d+(_ps|_psa)?|s\d+_\d+)_(\d+_)?", "", nombre_archivo.removesuffix(".png"))
    palabras = [ACENTOS.get(p, p) for p in base.split("_")]
    texto = " ".join(palabras)
    return texto[:1].upper() + texto[1:]


def elegir(archivos, cuantos):
    """`cuantos` capturas repartidas a lo largo del recorrido (siempre la primera y la última)."""
    if len(archivos) <= cuantos:
        return archivos
    pasos = [round(i * (len(archivos) - 1) / (cuantos - 1)) for i in range(cuantos)]
    return [archivos[i] for i in dict.fromkeys(pasos)]


def anexo_capturas(sprint, modelo, datos, carpeta):
    capturas = carpeta / "capturas"
    por_historia = datos.get("capturas_por_historia", 4)
    grupos = []
    for h in historias_del(sprint, modelo):
        a, b = h["id"].split("-")[1].split(".")
        archivos = sorted(f.name for f in capturas.glob(f"hu_{a}_{b}_*.png")
                          if "oscuro" not in f.name and "movil" not in f.name)
        if archivos:
            grupos.append((f"{h['id']} · {h['titulo']}", elegir(archivos, por_historia)))
    for titulo, patron, cuantos in datos.get("capturas_extra", []):
        archivos = sorted(f.name for f in capturas.glob(patron))
        if archivos:
            grupos.append((titulo, elegir(archivos, cuantos)))
    partes = []
    for titulo, archivos in grupos:
        partes.append(f"<h3>{e(titulo)}</h3>")
        for i in range(0, len(archivos), 2):
            par = "".join(
                f"<figure class='recorte'><div><img src='capturas/{e(a)}' alt=''></div><figcaption>{e(pie_de(a))}</figcaption></figure>"
                for a in archivos[i:i + 2])
            if len(archivos[i:i + 2]) == 1:
                par += "<figure class='recorte' style='visibility:hidden'><div></div></figure>"
            partes.append(f"<div class='dos'>{par}</div>")
    total = sum(len(a) for _, a in grupos)
    todas = len(list(capturas.glob("*.png")))
    return (f"<p>Se muestran {total} de las {todas} capturas del sprint, tomadas por los recorridos de navegador; cada una "
            f"se recorta a la parte alta de la pantalla. Todas están en <code>entregas/sprint_{sprint}/capturas/</code>, "
            "nombradas por historia y por paso.</p><div class='anexo'>" + "".join(partes) + "</div>")


# ----------------------------------------------------------------------------- documento
def main():
    sprint = int(sys.argv[1])
    carpeta = RAIZ / "entregas" / f"sprint_{sprint}"
    modelo = json.loads((ESPEC / "modelo.json").read_text(encoding="utf-8"))
    necesidades = json.loads((ESPEC / "necesidades_v12.json").read_text(encoding="utf-8"))
    datos = json.loads((carpeta / "resumen_datos.json").read_text(encoding="utf-8"))
    cuerpo = (carpeta / "resumen_contenido.html").read_text(encoding="utf-8")

    diagramas = {}
    if "<!--DIAGRAMA_ESTADOS-->" in cuerpo:
        diagramas["estados"] = mermaid_estados(datos)
        cuerpo = cuerpo.replace("<!--DIAGRAMA_ESTADOS-->", figura("estados", datos.get(
            "pie_estados", "Estados del trámite y unidad que hace cada paso.")))
    for nombre, pie in re.findall(r"<!--DIAGRAMA_ER:(\w+)\|(.*?)-->", cuerpo):
        conf = datos["er"][nombre]
        diagramas[nombre] = mermaid_er(conf["area"], conf["entidades"], conf.get("campos", 4))
        cuerpo = cuerpo.replace(f"<!--DIAGRAMA_ER:{nombre}|{pie}-->", figura(nombre, pie))
    for bloque, nombre, pie, codigo in re.findall(
            r"(<pre class=\"mermaid\" data-nombre=\"(.*?)\" data-pie=\"(.*?)\">(.*?)</pre>)", cuerpo, flags=re.S):
        diagramas[nombre] = html.unescape(codigo).strip()
        cuerpo = cuerpo.replace(bloque, figura(nombre, pie))
    if diagramas and "--sin-diagramas" not in sys.argv:
        dibujar(diagramas, carpeta / "diagramas")

    resumen_nec, anexo_nec = tabla_necesidades(sprint, modelo, necesidades, datos)
    for marca, valor in {
        "<!--TABLA_HISTORIAS-->": tabla_historias(sprint, modelo, datos),
        "<!--TABLA_COBERTURA-->": tabla_cobertura(sprint, modelo, datos),
        "<!--RESUMEN_NECESIDADES-->": resumen_nec,
        "<!--ANEXO_NECESIDADES-->": anexo_nec,
        "<!--ANEXO_CAPTURAS-->": anexo_capturas(sprint, modelo, datos, carpeta),
    }.items():
        cuerpo = cuerpo.replace(marca, valor)
    for clave, valor in datos.get("cifras", {}).items():
        cuerpo = cuerpo.replace("{{" + clave + "}}", e(valor))
    pendientes = re.findall(r"\{\{[^}]+\}\}|<!--[A-Z_]+(:\w+)?(\|[^>]*)?-->|POR_ACTUALIZAR", cuerpo)
    if pendientes:
        sys.exit(f"Quedaron marcas sin llenar: {sorted(set(pendientes))}")
    documento = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Resumen del sprint {sprint}</title>"
                 f"<style>{CSS.replace('__SPRINT__', str(sprint))}</style></head><body>{cuerpo}</body></html>")
    if "--html" in sys.argv:
        (carpeta / f"Resumen_sprint_{sprint}.html").write_text(documento, encoding="utf-8")
    from weasyprint import HTML

    salida = carpeta / f"Resumen_sprint_{sprint}.pdf"
    HTML(string=documento, base_url=str(carpeta)).write_pdf(str(salida), optimize_images=True, jpeg_quality=85, dpi=200)
    print(f"{salida} ({salida.stat().st_size / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
