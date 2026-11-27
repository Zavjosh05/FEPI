"""Genera el «Diseño de la capa de persistencia» del Sistema de programas: entregas/diseno/Diseno_capa_de_persistencia.pdf.

El texto está en `persistencia_contenido.html` (se escribe a mano) y los datos en `persistencia_datos.json`, que saca
`extraer_persistencia.py` de los modelos de Django del sistema completo. Lo demás se genera aquí:

- el mapa de tablas por área y sprint, el diagrama entidad-relación de cada área (Mermaid, dibujado con el Chromium de
  Playwright), el diccionario de datos de las 78 tablas y la lista de tablas de historial;
- `fragmento_resumen.html` y `fragmento_planeacion.md`: el mapa de tablas por área y sprint para los resúmenes y las
  planeaciones de los sprints.

Pasos (desde `sistema/`, con la imagen de pruebas del sistema completo):

    docker compose --profile pruebas run --rm --no-deps --entrypoint python pruebas /entregas/diseno/extraer_persistencia.py
    docker compose --profile pruebas run --rm --no-deps --entrypoint python pruebas /entregas/diseno/generar_diseno_persistencia.py --preparar
    docker compose --profile pruebas run --rm --no-deps --entrypoint python pruebas /entregas/diseno/generar_diseno_persistencia.py

`--preparar` agrega a cada tabla su área (de `sistema/docs/modelo_datos.md`), el sprint desde el que la usan las
pantallas y servicios (`sprint`; de `nombres_sprint_1.txt` y `nombres_sprint_2.txt`: las tablas que usaban las historias de
las ramas `sprint-1` y `sprint-2` antes de programar en ellas la base completa) y la descripción de las tablas cuyo modelo
no la trae. Las 78 tablas están programadas desde el sprint 1 en las tres ramas. Con `--sin-diagramas` reutiliza los PNG ya dibujados.
"""
import html
import json
import os
import re
import sys
from pathlib import Path

CARPETA = Path(__file__).resolve().parent
RAIZ = CARPETA.parents[1]
DATOS = CARPETA / "persistencia_datos.json"
MERMAID_JS = os.environ.get("MERMAID_JS", "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js")

AREAS = [
    (1, "Reglas por programa y catálogos", "Núcleo: base de todas las historias"),
    (2, "Expediente y recepción", "M1 · HU-1.1 a HU-1.4"),
    (3, "Dictamen y Comité", "M2 · HU-2.1 a HU-2.4"),
    (4, "Publicación y contrato", "M3 · HU-3.1 a HU-3.4"),
    (5, "Pagos", "M5 · HU-5.1 a HU-5.3"),
    (6, "Portal de personas beneficiarias", "Apoyo a M4 y M6"),
    (7, "Ejecución y verificación", "M4 · HU-4.1 a HU-4.3"),
    (8, "Seguimiento y cierre", "M6 · HU-6.1 a HU-6.3"),
]
APP_MODULO = {"nucleo": "Núcleo", "recepcion": "M1", "dictamen": "M2", "contrato": "M3", "pagos": "M5",
              "portal": "Portal", "ejecucion": "M4", "seguimiento": "M6"}
AREA_EXTRA = {"Consecutivo": 1, "Prorroga": 8}
# Descripción de las tablas cuyo modelo no trae docstring.
DESCRIPCIONES = {
    "DiaInhabil": "Días inhábiles del calendario oficial, con su fuente; cuentan para los plazos en días hábiles.",
    "Documento": "Archivo del expediente (requisito entregado, dictamen u otro): tipo, requisito al que responde, nombre, "
                 "ruta en el almacén de archivos, fecha de entrega, quién lo registró y su unidad.",
    "Formato": "Formato oficial de un programa-ejercicio (clave FO-PB-…, nombre, para qué se usa y línea de las ROP).",
    "Modalidad": "Modalidad o concepto de apoyo de un programa-ejercicio: clave, nombre, fundamento y si la persona "
                 "solicitante puede elegirla.",
    "Municipio": "Municipio del Estado de México con su geometría (PostGIS) y la Delegación Regional Forestal que lo atiende.",
    "Plazo": "Plazo de las reglas de un programa-ejercicio: cantidad y unidad (días hábiles, naturales o meses) o fecha "
             "límite, desde cuándo corre, responsable, fundamento y línea de las ROP.",
    "Programa": "Programa de PROBOSQUE (CC, MFS, PS, RHF, PSAHEM y PEG), con su nombre y si usa polígono del predio.",
    "Requisito": "Requisito de un programa-ejercicio (clave CC-REQ-NN…): texto, si aplica en refrendo, si es documento "
                 "legal, si es opcional o condicional, su formato y fundamento; se liga a los tipos de persona y "
                 "modalidades a los que aplica.",
    "TipoPersona": "Tipo de persona solicitante que admite un programa-ejercicio (física, jurídica colectiva, núcleo "
                   "agrario…), con su fundamento.",
    "Usuario": "Cuenta de acceso de una persona servidora pública (o, en el portal, de una persona beneficiaria), con la "
               "unidad a la que pertenece y su cargo.",
    "Poligono": "Polígono del predio levantado en campo (MultiPolygon en EPSG:4326) con su superficie calculada en "
                "EPSG:32614, quién lo levantó, su origen (archivo o dibujo), su ubicación respecto del municipio y el "
                "polígono anterior al que sustituye (corrección o cambio de lugar).",
    "RevisionRequisito": "Revisión de cada requisito del expediente en la Delegación: entregado, faltante o no aplica, "
                         "con su documento, fecha y observaciones.",
    "Validacion": "Validación del expediente por la Dirección: resultado, faltantes con su observación, plazo para "
                  "completar, acuse y notificación del aviso.",
    "Acuerdo": "Acuerdo de una sesión del Comité (incidente, reasignación, instrucción de pago…): causa, expedientes, "
               "unidad que lo cumple, montos liberado y reasignado, y su cumplimiento.",
    "DictamenJuridico": "Dictamen jurídico de la Unidad Jurídica: procedente o no procedente, motivo, cotejo con los "
                        "catálogos, revisión de la documentación y su documento en PDF (folio DJ-… y huella SHA-256).",
    "DictamenTecnico": "Dictamen técnico del área responsable: factible o no factible, superficie factible, verificación "
                       "de criterios, análisis cartográfico, plazo y su documento en PDF (folio DT-… y huella SHA-256).",
    "DocumentoSesion": "Documento de una sesión del Comité (convocatoria, acta u otro), con su archivo.",
    "SesionComite": "Sesión del Comité (de aprobación o de seguimiento): número, fecha y hora, lugar, orden del día, "
                    "integrantes, presupuesto, acta y si autoriza publicar los listados.",
    "VersionModelo": "Versión del texto de un modelo de contrato y su revisión por la Unidad Jurídica (validada o "
                     "devuelta, con fecha, quién y observaciones).",
    "Consecutivo": "Último número usado de cada serie de folios (solicitudes, acuses, dictámenes, contratos…); se lee "
                   "con bloqueo de fila para que dos usuarios no tomen el mismo folio.",
    "Prorroga": "Prórroga solicitada para un plazo del expediente: causa, plazo original y solicitado, resolución y el "
                "adendum que la formaliza.",
}
TIPOS_CORTOS = {"BigAutoField": "id", "AutoField": "id", "CharField": "texto", "TextField": "texto", "SlugField": "texto",
                "EmailField": "texto", "BooleanField": "bool", "DateField": "fecha", "DateTimeField": "fecha_hora",
                "DecimalField": "decimal", "IntegerField": "entero", "PositiveIntegerField": "entero",
                "PositiveSmallIntegerField": "entero", "SmallIntegerField": "entero", "FloatField": "decimal",
                "JSONField": "json", "FileField": "archivo", "ImageField": "archivo", "MultiPolygonField": "geometria",
                "PolygonField": "geometria", "PointField": "geometria", "GeometryField": "geometria",
                "BinaryField": "binario", "UUIDField": "uuid"}
AL_BORRAR = {"CASCADE": "en cascada", "PROTECT": "protegida", "SET_NULL": "a nulo", "RESTRICT": "restringida",
             "DO_NOTHING": "sin acción"}

CSS = """
@page { size: Letter; margin: 2cm 1.8cm 2.1cm 1.8cm;
  @bottom-left { content: "PROBOSQUE 2026 · Diseño de la capa de persistencia"; font-size: 8pt; color: #666; }
  @bottom-right { content: counter(page) " / " counter(pages); font-size: 8pt; color: #666; } }
@page :first { margin-top: 4.5cm; @bottom-left { content: ""; } @bottom-right { content: ""; } }
html { font-family: "DejaVu Sans", "Noto Sans", sans-serif; font-size: 9.4pt; line-height: 1.42; color: #1c1c1c; }
h1 { font-size: 24pt; line-height: 1.15; margin: 0 0 .3cm; color: #1f4d2e; }
h2 { font-size: 14pt; color: #1f4d2e; margin: .9cm 0 .25cm; padding-bottom: .12cm; border-bottom: 1.2pt solid #1f4d2e;
     break-after: avoid; }
h3 { font-size: 11pt; margin: .55cm 0 .15cm; color: #26382b; break-after: avoid; }
h4 { font-size: 9.6pt; margin: .45cm 0 .08cm; color: #1f4d2e; break-after: avoid; }
p { margin: 0 0 .22cm; } ul, ol { margin: 0 0 .25cm; padding-left: .55cm; } li { margin-bottom: .08cm; }
.portada p.sub { font-size: 12pt; color: #444; margin-bottom: .8cm; }
.portada table { width: auto; } .portada td { border: none; padding: .08cm .5cm .08cm 0; }
.caja { background: #eef4ee; border-left: 3pt solid #1f4d2e; padding: .25cm .35cm; margin: .3cm 0; break-inside: avoid; }
table { width: 100%; border-collapse: collapse; margin: .15cm 0 .3cm; font-size: 8.2pt; }
th { background: #1f4d2e; color: #fff; text-align: left; padding: .1cm .14cm; font-weight: 600; }
td { padding: .09cm .14cm; border-bottom: .4pt solid #c9d3cb; vertical-align: top; }
tr { break-inside: avoid; } thead { display: table-header-group; }
code, .mono { font-family: "DejaVu Sans Mono", monospace; font-size: 7.8pt; }
.gris { color: #666; } .meta { font-size: 8pt; color: #444; margin-bottom: .1cm; }
table.dic td:first-child { white-space: nowrap; } table.dic { font-size: 7.6pt; }
figure { margin: .3cm 0 .45cm; break-inside: avoid; text-align: center; } figcaption { font-size: 8pt; color: #555; }
figure img { width: auto; max-width: 100%; max-height: 20.5cm; }
.salto { break-before: page; }
.s1, .s2, .s3 { display: inline-block; border-radius: 3pt; padding: .02cm .14cm; margin: .03cm .04cm .03cm 0;
  font-family: "DejaVu Sans Mono", monospace; font-size: 7.4pt; }
.s1 { background: #dcebdf; border: .6pt solid #1f4d2e; } .s2 { background: #dde7f5; border: .6pt solid #2b5797; }
.s3 { background: #fbf0d9; border: .6pt solid #b7791f; }
table.mapa td { width: 27%; } table.mapa td:first-child { width: 19%; }
"""


def e(texto):
    return html.escape(str(texto), quote=True)


def doc(texto):
    """Texto de un docstring o help_text: escapado, con ``código`` y **negritas** convertidos."""
    t = re.sub(r"``(.+?)``", r"<code>\1</code>", e(texto))
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)


# ----------------------------------------------------------------------------- preparar
def preparar():
    datos = json.loads(DATOS.read_text(encoding="utf-8"))
    ruta = RAIZ / "sistema" / "docs" / "modelo_datos.md"
    if not ruta.exists():                        # en el contenedor de pruebas, sistema/ es el directorio de trabajo
        ruta = Path.cwd() / "docs" / "modelo_datos.md"
    md = ruta.read_text(encoding="utf-8")
    area, textos = {}, {}
    for seccion in re.split(r"^## ", md, flags=re.M)[1:]:
        numero = int(seccion.split(".", 1)[0])
        texto = seccion.split("\n", 1)[1].split("```mermaid", 1)[0]
        textos[numero] = " ".join(texto.split())
        for bloque in re.findall(r"```mermaid\n(.*?)```", seccion, flags=re.S):
            for nombre in re.findall(r"^\s*(\w+) \{$", bloque, flags=re.M):
                area.setdefault(nombre, numero)
    s1 = set((CARPETA / "nombres_sprint_1.txt").read_text(encoding="utf-8").split())
    s2 = set((CARPETA / "nombres_sprint_2.txt").read_text(encoding="utf-8").split())
    for t in datos["tablas"]:
        clave = f"{t['app']}.{t['modelo']}"
        t["area"] = area.get(t["modelo"]) or AREA_EXTRA[t["modelo"]]
        t["sprint"] = 1 if clave in s1 else 2 if clave in s2 else 3
        if not t["doc"]:
            t["doc"] = DESCRIPCIONES[t["modelo"]]
    datos["areas"] = [{"numero": n, "titulo": titulo, "modulo": modulo, "texto": textos.get(n, "")}
                      for n, titulo, modulo in AREAS]
    DATOS.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{DATOS}: áreas y sprints agregados")


# ----------------------------------------------------------------------------- piezas
def chip(t):
    return f"<span class='s{t['sprint']}' title='{e(t['tabla'])}'>{e(t['modelo'])}</span>"


def mapa_html(datos, con_leyenda=True):
    """Tabla área × sprint con las tablas de cada celda."""
    filas = []
    for a in datos["areas"]:
        celdas = []
        for s in (1, 2, 3):
            ts = [t for t in datos["tablas"] if t["area"] == a["numero"] and t["sprint"] == s]
            celdas.append(" ".join(chip(t) for t in ts) or "<span class='gris'>—</span>")
        filas.append(f"<tr><td><b>{a['numero']}. {e(a['titulo'])}</b><br><span class='gris'>{e(a['modulo'])}</span></td>"
                     + "".join(f"<td>{c}</td>" for c in celdas) + "</tr>")
    cuenta = {s: sum(1 for t in datos["tablas"] if t["sprint"] == s) for s in (1, 2, 3)}
    leyenda = (f"<p class='meta'>Cada cuadro es una tabla (el nombre del modelo de Django; la tabla en PostgreSQL es "
               "<code>&lt;app&gt;_&lt;modelo&gt;</code>). Las {len(datos['tablas'])} están programadas desde el sprint 1; el "
               "color dice desde qué sprint las usan las pantallas y servicios: <span class='s1'>sprint 1</span> "
               "<span class='s2'>sprint 2</span> <span class='s3'>sprint 3</span></p>") if con_leyenda else ""
    return (leyenda + "<table class='mapa'><thead><tr><th>Área</th>"
            f"<th>Se usan desde el sprint 1 ({cuenta[1]} tablas)</th><th>Desde el sprint 2 ({cuenta[2]})</th>"
            f"<th>Desde el sprint 3 ({cuenta[3]})</th></tr>"
            "</thead><tbody>" + "".join(filas) + "</tbody></table>")


def mapa_md(datos):
    cuenta = {s: sum(1 for t in datos["tablas"] if t["sprint"] == s) for s in (1, 2, 3)}
    filas = ["| Área | Se usan desde el sprint 1 (" + str(cuenta[1]) + " tablas) | Desde el sprint 2 (" + str(cuenta[2])
             + ") | Desde el sprint 3 (" + str(cuenta[3]) + ") |", "| --- | --- | --- | --- |"]
    for a in datos["areas"]:
        celdas = []
        for s in (1, 2, 3):
            ts = [t["modelo"] for t in datos["tablas"] if t["area"] == a["numero"] and t["sprint"] == s]
            celdas.append(", ".join(ts) or "—")
        filas.append(f"| {a['numero']}. {a['titulo']} ({a['modulo']}) | " + " | ".join(celdas) + " |")
    return "\n".join(filas)


def er_area(datos, numero, max_campos=3):
    """Diagrama entidad-relación de un área: sus tablas con llave, llaves foráneas y algunos campos, y las tablas de
    otras áreas a las que apuntan (sin campos). No dibuja las relaciones hacia Usuario ni Unidad (quién y qué unidad
    registró: casi todas las tablas las tienen)."""
    propias = {t["modelo"]: t for t in datos["tablas"] if t["area"] == numero}
    externas, relaciones, lineas = set(), set(), ["erDiagram"]
    omitir = {"Usuario", "Unidad", "Group", "Permission"} - set(propias)   # Group y Permission: tablas de Django
    for t in propias.values():
        for c in t["columnas"]:
            fk = c.get("fk")
            if not fk or fk["modelo"] in omitir:
                continue
            card = "||--o|" if fk["uno_a_uno"] else ("|o--o{" if c["nulo"] else "||--o{")
            relaciones.add(f"  {fk['modelo']} {card} {t['modelo']} : {c['nombre']}")
            if fk["modelo"] not in propias:
                externas.add(fk["modelo"])
        for m in t["muchos_a_muchos"]:
            if m["modelo"] not in omitir:
                relaciones.add(f"  {t['modelo']} }}o--o{{ {m['modelo']} : {m['nombre']}")
                if m["modelo"] not in propias:
                    externas.add(m["modelo"])
    lineas += sorted(relaciones)
    for nombre, t in sorted(propias.items()):
        filas, otros = [], 0
        for c in t["columnas"]:
            fk = c.get("fk")
            if fk:
                if fk["modelo"] not in omitir:
                    filas.append(f"    id {c['nombre']}_id FK")
                continue
            marca = " PK" if c["pk"] else (" UK" if c["unico"] else "")
            if not marca:
                otros += 1
                if otros > max_campos:
                    continue
            filas.append(f"    {TIPOS_CORTOS.get(c['tipo_django'], 'otro')} {c['nombre']}{marca}")
        lineas += [f"  {nombre} {{"] + filas + ["  }"]
    for nombre in sorted(externas):
        lineas += [f"  {nombre} {{", "    id id PK", "  }"]
    return "\n".join(lineas)


def descripcion_columna(c):
    partes = []
    if c["descripcion"]:
        partes.append(doc(c["descripcion"].rstrip(". ")))
    elif c.get("fk"):
        partes.append(e(c["verbose"].capitalize().rstrip(". ")))
    if c.get("opciones"):
        ops = c["opciones"]
        partes.append("Opciones: " + ", ".join(f"<code>{e(o)}</code>" for o in ops[:12]) + (" …" if len(ops) > 12 else ""))
    if c.get("srid"):
        partes.append(f"SRID {c['srid']}")
    if "omision" in c and c["omision"] not in ("", None):
        partes.append(f"Por omisión: <code>{e(c['omision'])}</code>")
    return ". ".join(partes) + ("." if partes else "")


def llave(c):
    if c["pk"]:
        return "PK"
    if c.get("fk"):
        fk = c["fk"]
        return (f"FK{' 1:1' if fk['uno_a_uno'] else ''} → <code>{e(fk['tabla'])}</code>"
                f"<br><span class='gris'>borrado {AL_BORRAR.get(fk['al_borrar'], fk['al_borrar'])}</span>")
    if c["unico"]:
        return "UK"
    if c.get("indice"):
        return "índice"
    return ""


def diccionario(datos):
    partes = []
    for a in datos["areas"]:
        tablas = sorted((t for t in datos["tablas"] if t["area"] == a["numero"]), key=lambda t: (t["sprint"], t["modelo"]))
        partes.append(f"<h3 class='salto'>6.{a['numero']} {e(a['titulo'])} <span class='gris'>({e(a['modulo'])})</span></h3>")
        for t in tablas:
            meta = [f"app <code>{t['app']}</code> ({APP_MODULO[t['app']]})", "programada en el sprint 1",
                    f"se usa desde el sprint {t['sprint']}"]
            meta.append(f"historial en <code>{t['tabla_historial']}</code>" if t["historial"] else "sin historial")
            if t["orden"]:
                meta.append("orden: " + ", ".join(f"<code>{e(o)}</code>" for o in t["orden"]))
            filas = "".join(
                f"<tr><td><code>{e(c['columna'])}</code></td><td><code>{e(c['tipo_bd'])}</code></td>"
                f"<td>{'sí' if c['nulo'] else 'no'}</td><td>{llave(c)}</td><td>{descripcion_columna(c)}</td></tr>"
                for c in t["columnas"])
            for m in t["muchos_a_muchos"]:
                filas += (f"<tr><td><code>{e(m['nombre'])}</code></td><td colspan='2'>muchos a muchos</td>"
                          f"<td>→ <code>{e(m['tabla'])}</code></td><td>Tabla intermedia "
                          f"<code>{e(m['tabla_intermedia'])}</code></td></tr>")
            extra = []
            for r in t["restricciones"]:
                texto = f"{e(r['tipo']).capitalize()}"
                if r.get("campos"):
                    texto += " (" + ", ".join(f"<code>{e(x)}</code>" for x in r["campos"]) + ")"
                if r.get("condicion"):
                    texto += f" cuando <code>{e(r['condicion'])}</code>"
                extra.append(texto)
            for i in t["indices"]:
                extra.append("Índice (" + ", ".join(f"<code>{e(x)}</code>" for x in i) + ")")
            partes.append(
                f"<h4><code>{e(t['tabla'])}</code> · {e(t['verbose'].capitalize())}</h4>"
                f"<p class='meta'>{' · '.join(meta)}</p><p>{doc(t['doc'])}</p>"
                "<table class='dic'><thead><tr><th>Columna</th><th>Tipo (PostgreSQL)</th><th>Nulo</th><th>Llave</th>"
                f"<th>Descripción</th></tr></thead><tbody>{filas}</tbody></table>"
                + (f"<p class='meta'>Restricciones: {'; '.join(extra)}.</p>" if extra else ""))
    return "".join(partes)


def areas_html(datos):
    partes = []
    for a in datos["areas"]:
        tablas = sorted((t for t in datos["tablas"] if t["area"] == a["numero"]), key=lambda t: (t["sprint"], t["modelo"]))
        lista = "".join(f"<tr><td><code>{e(t['tabla'])}</code></td><td>{t['sprint']}</td><td>{doc(t['doc'])}</td></tr>"
                        for t in tablas)
        partes.append(
            f"<h3 class='salto'>5.{a['numero']} {e(a['titulo'])} <span class='gris'>({e(a['modulo'])})</span></h3>"
            f"<p>{e(a['texto'])}</p>" if a["texto"] else
            f"<h3 class='salto'>5.{a['numero']} {e(a['titulo'])} <span class='gris'>({e(a['modulo'])})</span></h3>")
        partes.append(f"<!--FIG:er_area_{a['numero']}|Entidad-relación del área {a['numero']}: {e(a['titulo'])}-->")
        partes.append("<table><thead><tr><th>Tabla</th><th>Se usa desde</th><th>Qué guarda</th></tr></thead>"
                      f"<tbody>{lista}</tbody></table>")
    return "".join(partes)


def historial_html(datos):
    filas = "".join(f"<tr><td><code>{e(t['tabla'])}</code></td><td><code>{e(t['tabla_historial'])}</code></td>"
                    f"<td>{t['sprint']}</td></tr>" for t in datos["tablas"] if t["historial"])
    return ("<table><thead><tr><th>Tabla</th><th>Tabla de historial</th><th>Se usa desde</th></tr></thead>"
            f"<tbody>{filas}</tbody></table>")


# ----------------------------------------------------------------------------- dibujo y documento
def dibujar(diagramas, carpeta):
    from playwright.sync_api import sync_playwright

    carpeta.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page(viewport={"width": 2400, "height": 1400}, device_scale_factor=2)
        for nombre, codigo in diagramas.items():
            pagina.set_content(
                "<html><body style='margin:0;background:#fff'>"
                f"<pre class='mermaid' id='d' style='margin:0;display:inline-block'>{html.escape(codigo)}</pre>"
                f"<script src='{MERMAID_JS}'></script><script>mermaid.initialize({{startOnLoad: true, theme: 'neutral', "
                "fontFamily: 'DejaVu Sans, sans-serif', flowchart: {htmlLabels: true, curve: 'basis', useMaxWidth: false}, "
                "er: {useMaxWidth: false}});</script></body></html>")
            pagina.wait_for_selector("#d svg", timeout=90000)
            pagina.wait_for_timeout(400)
            pagina.locator("#d svg").screenshot(path=str(carpeta / f"{nombre}.png"))
            print(f"  diagrama {nombre}.png")
        navegador.close()


def main():
    if "--preparar" in sys.argv:
        preparar()
        return
    datos = json.loads(DATOS.read_text(encoding="utf-8"))
    cuerpo = (CARPETA / "persistencia_contenido.html").read_text(encoding="utf-8")
    cifras = {
        "tablas": len(datos["tablas"]),
        "columnas": sum(len(t["columnas"]) for t in datos["tablas"]),
        "historial": sum(1 for t in datos["tablas"] if t["historial"]),
        "fk": sum(1 for t in datos["tablas"] for c in t["columnas"] if c.get("fk")),
        "m2m": sum(len(t["muchos_a_muchos"]) for t in datos["tablas"]),
        "s1": sum(1 for t in datos["tablas"] if t["sprint"] == 1),
        "s2": sum(1 for t in datos["tablas"] if t["sprint"] == 2),
        "s3": sum(1 for t in datos["tablas"] if t["sprint"] == 3),
        "geom": sum(1 for t in datos["tablas"] for c in t["columnas"] if c.get("srid")),
    }
    for clave, valor in cifras.items():
        cuerpo = cuerpo.replace("{{" + clave + "}}", str(valor))
    pendientes = re.findall(r"\{\{[^}]+\}\}", cuerpo)       # antes de insertar lo generado (trae «{{campo}}» de los modelos)
    if pendientes:
        sys.exit(f"Quedaron cifras sin llenar: {sorted(set(pendientes))}")
    for marca, valor in {"<!--MAPA-->": mapa_html(datos), "<!--AREAS-->": areas_html(datos),
                         "<!--DICCIONARIO-->": diccionario(datos), "<!--HISTORIAL-->": historial_html(datos)}.items():
        cuerpo = cuerpo.replace(marca, valor)
    diagramas = {f"er_area_{a['numero']}": er_area(datos, a["numero"]) for a in datos["areas"]}
    for bloque, nombre, pie, codigo in re.findall(
            r"(<pre class=\"mermaid\" data-nombre=\"(.*?)\" data-pie=\"(.*?)\">(.*?)</pre>)", cuerpo, flags=re.S):
        diagramas[nombre] = html.unescape(codigo).strip()
        cuerpo = cuerpo.replace(bloque, f"<!--FIG:{nombre}|{pie}-->")
    for nombre, pie in re.findall(r"<!--FIG:(\w+)\|(.*?)-->", cuerpo):
        cuerpo = cuerpo.replace(f"<!--FIG:{nombre}|{pie}-->", f"<figure><img src='diagramas/{nombre}.png' alt='{pie}'>"
                                f"<figcaption>{pie}</figcaption></figure>")
    if "--sin-diagramas" not in sys.argv:
        dibujar(diagramas, CARPETA / "diagramas")
    pendientes = re.findall(r"<!--[A-Z_]+-->", cuerpo)
    if pendientes:
        sys.exit(f"Quedaron marcas sin llenar: {sorted(set(pendientes))}")
    # Para los resúmenes: la misma tabla con los estilos dentro (la hoja de estilos del resumen no trae estas clases).
    fragmento = mapa_html(datos)
    base = ("display:inline-block;border-radius:3pt;padding:.02cm .12cm;margin:.03cm .04cm .03cm 0;"
            "font-family:'DejaVu Sans Mono',monospace;font-size:7pt;")
    for clase, color in {"s1": "background:#dcebdf;border:.6pt solid #1f4d2e", "s2": "background:#dde7f5;border:.6pt solid #2b5797",
                         "s3": "background:#fbf0d9;border:.6pt solid #b7791f"}.items():
        fragmento = fragmento.replace(f"class='{clase}'", f"style=\"{base}{color}\"")
    fragmento = fragmento.replace("class='mapa'", "style='font-size:8pt'").replace("class='meta'", "style='font-size:8pt;color:#444'")
    (CARPETA / "fragmento_resumen.html").write_text(fragmento, encoding="utf-8")
    (CARPETA / "fragmento_planeacion.md").write_text(mapa_md(datos) + "\n", encoding="utf-8")
    documento = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>Diseño de la capa de persistencia"
                 f"</title><style>{CSS}</style></head><body>{cuerpo}</body></html>")
    from weasyprint import HTML

    salida = CARPETA / "Diseno_capa_de_persistencia.pdf"
    HTML(string=documento, base_url=str(CARPETA)).write_pdf(str(salida), optimize_images=True, jpeg_quality=85, dpi=200)
    print(f"{salida} ({salida.stat().st_size / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
