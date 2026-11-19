"""Lleva a los documentos de la propuesta los cambios de las historias de usuario.

Fuente única: `sistema/especificacion/modelo.json` del repositorio (la que usan el sistema y sus pruebas).
Actualiza, dentro de propuesta/:

- `datos/modelo.json` (copia de la fuente);
- `CONTEXTO.md` (formato de historia y, por cada HU, sus líneas «Historia» y «Criterios»);
- `docs/Matriz_funciones_historias_PROBOSQUE.xlsx` (hoja «Historias de usuario»: forma, redacción y criterios);
- `docs/Propuesta_solucion_modular_PROBOSQUE_2026.pdf`: rehace las páginas de historias (11 a 15 y 21 a 22) con
  el mismo estilo y la misma paginación, y conserva intactas las demás.

Los originales del 12-13 de noviembre de 2026 están en `original/` y no se tocan: el PDF y la matriz se rehacen
siempre a partir de ellos. Se corre desde la raíz del repositorio, dentro de la imagen de pruebas del sistema
(trae Chromium); las bibliotecas que faltan se instalan al vuelo:

    wsl -e bash -lc "docker run --rm -v /mnt/c/Users/josh/Documents/GitHub/FEPI:/repo -w /repo \
        --entrypoint sh probosque-sistema-pruebas:0.1 -c 'pip install -q --root-user-action=ignore openpyxl pypdf; \
        python propuesta/herramientas/actualizar_propuesta.py'"
"""
import html
import io
import json
import pathlib
import re

import openpyxl
from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter

RAIZ = pathlib.Path(__file__).resolve().parents[2]
CARPETA = RAIZ / "propuesta"
ORIGINAL = CARPETA / "original"
FUENTE = RAIZ / "sistema" / "especificacion" / "modelo.json"
FORMATO = "«Como [rol], quiero [acción], para [beneficio]»"
TOTAL_PAGINAS = 26

modelo = json.loads(FUENTE.read_text(encoding="utf-8"))
historias = {h["id"]: h for h in modelo["historias"]}
assert len(historias) == 26


def criterios_texto(h, estilo):
    cs = h["criterios"]
    if len(cs) == 1:
        return cs[0]
    if estilo == "md":
        return " ".join(f"({i}) {c}" for i, c in enumerate(cs, 1))
    return " ".join(f"{i}) {c}" for i, c in enumerate(cs, 1))


# 1. datos/modelo.json
(CARPETA / "datos" / "modelo.json").write_text(FUENTE.read_text(encoding="utf-8"), encoding="utf-8")

# 2. CONTEXTO.md (contexto de la propuesta)
md = (ORIGINAL / "CONTEXTO.md").read_text(encoding="utf-8")
viejo_formato = "Formato de historia: «Como [rol], quiero [lo que desea], por lo que [lo que hace], para [la meta]»."
assert viejo_formato in md
md = md.replace(viejo_formato, f"Formato de historia: {FORMATO}, centrada en la acción del usuario.")
md = md.replace("- Historias en una sola frase con rol, lo que desea, lo que hace y la meta; describen la necesidad, no la solución.",
                f"- Historias en una sola frase {FORMATO}, enfocadas en la acción del usuario (nota del profesor del "
                "18-nov-2026 a la HU-1.1); describen la necesidad, no la solución.")
md = md.replace("- Criterios de aceptación como condiciones (\"Existe una solicitud asociada al predio y se genera su acuse…\"), nunca acciones.",
                "- Criterios de aceptación como condiciones, nunca acciones. HU-1.1 tiene un solo criterio por indicación del "
                "profesor: «Se genera un folio único para la solicitud».")
lineas = md.split("\n")
actual = None
for i, linea in enumerate(lineas):
    m = re.match(r"\*\*M\d\.\d · (HU-\d\.\d) · ", linea)
    if m:
        actual = historias[m.group(1)]
    elif actual and linea.startswith("- Historia: "):
        lineas[i] = f"- Historia: {actual['texto']}"
    elif actual and linea.startswith("- Criterios: "):
        lineas[i] = f"- Criterios: {criterios_texto(actual, 'md')}"
md = "\n".join(lineas)
assert md.count("por lo que") == 0 or "por lo que [lo que hace]" not in md
(CARPETA / "CONTEXTO.md").write_text(md, encoding="utf-8")

# 3. Matriz de Excel
wb = openpyxl.load_workbook(ORIGINAL / "docs" / "Matriz_funciones_historias_PROBOSQUE.xlsx")
ws = wb["Historias de usuario"]
ws["A2"].value = re.sub(r"Como \[rol\], quiero \[lo que desea\], por lo que \[lo que hace\], para \[[^\]]*\]",
                        "Como [rol], quiero [acción], para [beneficio]", ws["A2"].value)
cambiadas = 0
for fila in range(5, ws.max_row + 1):
    hu = ws.cell(fila, 1).value
    if hu in historias:
        h = historias[hu]
        ws.cell(fila, 5).value = h["texto"]
        for j in range(3):
            ws.cell(fila, 6 + j).value = h["criterios"][j] if j < len(h["criterios"]) else None
        cambiadas += 1
assert cambiadas == 26, cambiadas
wb.save(CARPETA / "docs" / "Matriz_funciones_historias_PROBOSQUE.xlsx")

# 4. PDF: páginas de historias con el mismo estilo y la misma paginación
MODULOS = {m["id"]: m["nombre"] for m in modelo["modulos"]}
ESTILO = """
@page { size: Letter; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "DejaVu Sans", sans-serif; color: #1c1c1c; font-size: 9.6pt; line-height: 1.42; }
.pagina { width: 8.5in; height: 11in; padding: 0.62in 0.6in 0.7in; position: relative; overflow: hidden;
          page-break-after: always; }
.pie { position: absolute; bottom: 0.3in; left: 0; right: 0; text-align: center; font-size: 6.6pt; color: #333; }
h2 { font-size: 15pt; color: #1e4d2b; margin: 0 0 8pt; padding-bottom: 4pt; border-bottom: 1px solid #b9c7bd; }
h2.barra { background: #eef1ee; border: none; border-left: 5px solid #1e4d2b; padding: 6pt 10pt; }
h3 { font-size: 12pt; color: #1e4d2b; margin: 12pt 0 3pt; }
p { margin: 0 0 6pt; }
ul { margin: 0 0 6pt; padding-left: 16pt; } li { margin-bottom: 3pt; }
table { width: 100%; border-collapse: collapse; font-size: 7.9pt; margin: 3pt 0 8pt; }
th { background: #1e4d2b; color: #fff; text-align: left; padding: 3pt 4pt; font-weight: bold; }
td { border: 1px solid #d5d9d6; padding: 3pt 4pt; vertical-align: top; }
td.id { color: #1e4d2b; font-weight: bold; white-space: nowrap; }
td.tit { font-weight: bold; } td.num { text-align: center; } td.pts { text-align: center; color: #1e4d2b; font-weight: bold; }
tr:nth-child(even) td { background: #fafbfa; }
td.m7 { background: #d6eadb !important; text-align: center; color: #1e4d2b; font-weight: bold; }
"""
ENC = ("<tr><th style='width:9%'>HU</th><th style='width:13%'>Título</th><th style='width:38%'>Historia de usuario</th>"
       "<th style='width:31%'>Criterios de aceptación</th><th style='width:9%'>Puntos</th></tr>")


def filas(ids):
    salida = []
    for i in ids:
        h = historias[i]
        salida.append(f"<tr><td class='id'>{i}</td><td class='tit'>{html.escape(h['titulo'])}</td>"
                      f"<td>{html.escape(h['texto'])}</td><td>{html.escape(criterios_texto(h, 'pdf'))}</td>"
                      f"<td class='pts'>{h['puntos']}</td></tr>")
    return "".join(salida)


def tabla(ids):
    return f"<table>{ENC}{filas(ids)}</table>"


def modulo(n):
    return f"<h3>Módulo {n}. {html.escape(MODULOS[f'M{n}'])}</h3>"


def pagina(numero, contenido):
    return (f"<section class='pagina' data-n='{numero}'>{contenido}"
            f"<div class='pie'>Propuesta de solución modular — PROBOSQUE 2026 · {numero} / {TOTAL_PAGINAS}</div></section>")


lista = "".join(
    f"<tr><td class='id'>{h['id']}</td><td>{html.escape(h['titulo'])}</td><td>{html.escape(h['rol'][0].upper() + h['rol'][1:])}</td>"
    f"<td class='num'>{h['puntos']}</td><td class='num'>{h['sprint']}</td></tr>" for h in modelo["historias"])
p11 = f"""<h2>4. Historias de usuario</h2>
<p>Cada función tiene una historia de usuario, y cada historia corresponde a una sola función: HU-1.1 corresponde a la
función M1.1. Cada historia tiene un título y es una sola frase centrada en la acción del usuario, con tres partes:
{FORMATO}. Las historias describen lo que hace el usuario en el proceso, no cómo lo resuelve el sistema.</p>
<p>Los criterios de aceptación son condiciones que deben cumplirse para dar por terminada la historia; no describen
acciones. En cada envío o entrega existe la fecha y la hora. La columna Puntos da la complejidad en la escala Fibonacci
(1, 2, 3, 5 y 8), explicada en la sección 7.</p>
<h3>Lista de historias</h3><p>Lista completa de las 26 historias para consulta rápida, con su sprint (sección 8).</p>
<table><tr><th style='width:10%'>HU</th><th style='width:31%'>Título</th><th>Rol</th><th style='width:9%'>Puntos</th>
<th style='width:9%'>Sprint</th></tr>{lista}</table>"""
p12 = modulo(1) + tabla(["HU-1.1", "HU-1.2", "HU-1.3", "HU-1.4"]) + modulo(2) + tabla(["HU-2.1", "HU-2.2", "HU-2.3"])
p13 = tabla(["HU-2.4"]) + modulo(3) + tabla(["HU-3.1", "HU-3.2", "HU-3.3", "HU-3.4"]) + modulo(4) + tabla(["HU-4.1"])
p14 = tabla(["HU-4.2", "HU-4.3"]) + modulo(5) + tabla(["HU-5.1", "HU-5.2", "HU-5.3"]) + modulo(6) + tabla(["HU-6.1"])
p15 = tabla(["HU-6.2", "HU-6.3"])
p21 = """<h2 class='barra'>6. Módulo independiente: Calculadora forestal</h2>
<p>La Calculadora forestal se propone como un módulo aparte de los 6 anteriores. No forma parte del trámite de ningún
programa ni comparte datos con él: la construye, alimenta y mantiene el equipo desarrollador, y el personal de PROBOSQUE
consulta sus resultados.</p>
<h3>Módulo 7. Calculadora forestal</h3>
<p>Permite conocer cuánta masa forestal hay en el Estado de México y en cada municipio, cómo cambia entre años, qué se
perdió por incendios, a qué uso pasó el terreno y qué especies hay.</p>
<ul><li><b>Qué mide:</b> la superficie con masa forestal (cobertura arbórea), en hectáreas, a partir de imágenes de
satélite. No mide biomasa ni carbono.</li>
<li><b>Dónde:</b> los 125 municipios del Estado de México y el total estatal.</li>
<li><b>Cuándo:</b> una cifra por año con imágenes de noviembre-diciembre de 2023, 2024 y 2025; 2026 entra cuando haya
imágenes de fin de año.</li>
<li><b>Lo que depende de datos externos:</b> los incendios de 2025 (CONAFOR aún no los publica), el uso del suelo de
los años recientes (el más reciente del INEGI es la Serie VII, de 2021) y las especies (inventario forestal de CONAFOR
de 2015 a 2020).</li></ul>
<p>Sus 5 necesidades se atienden con 5 funciones y 5 historias de usuario: una función y una historia por necesidad.</p>
<table><tr><th style='width:8%'>ID</th><th>Función</th><th style='width:13%'>Necesidad que cubre</th></tr>
<tr><td class='id'>M7.1</td><td>Masa forestal de cada año por municipio y para el Estado, y su evolución año con año.</td><td>CF-DEV-01</td></tr>
<tr><td class='id'>M7.2</td><td>Balance entre un año inicial y uno final: masa forestal perdida, ganada y cambio neto, con su histograma.</td><td>CF-DEV-02</td></tr>
<tr><td class='id'>M7.3</td><td>Ubicación y fecha de los incendios forestales y masa forestal perdida por ellos.</td><td>CF-DEV-03</td></tr>
<tr><td class='id'>M7.4</td><td>Uso del suelo al que pasó el terreno donde se perdió masa forestal, en los años con datos.</td><td>CF-DEV-04</td></tr>
<tr><td class='id'>M7.5</td><td>Especies forestales registradas en el bosque de cada municipio.</td><td>CF-DEV-05</td></tr></table>
<h3>Historias de usuario de la Calculadora</h3>
<p>Cada función del Módulo 7 tiene una historia de usuario (HU-7.1 corresponde a M7.1), con la misma forma y la misma
escala de puntos que las de los módulos 1 a 6.</p>""" + tabla(["HU-7.1"])
p22 = tabla(["HU-7.2", "HU-7.3", "HU-7.4", "HU-7.5"]) + """<h3>Matriz de la Calculadora forestal</h3>
<p>Cada necesidad la cubre una sola función, con una sola historia. La columna Prototipo indica si el primer prototipo
ya la cumple: 1 cumplida, 1 cumplida en parte y 3 pendientes.</p>
<table><tr><th style='width:13%'>ID</th><th>Necesidad</th><th style='width:10%'>M7</th><th style='width:35%'>Prototipo</th></tr>
<tr><td>CF-DEV-01</td><td>Cuantificación de la masa forestal</td><td class='m7'>M7.1</td><td>Cumplida en parte (calcula la superficie de cada año; falta mostrar su evolución)</td></tr>
<tr><td>CF-DEV-02</td><td>Balance entre dos años</td><td class='m7'>M7.2</td><td>Pendiente (ya da las cifras entre dos años; falta el histograma)</td></tr>
<tr><td>CF-DEV-03</td><td>Ubicación de incendios</td><td class='m7'>M7.3</td><td>Cumplida (falta 2025, que CONAFOR aún no publica)</td></tr>
<tr><td>CF-DEV-04</td><td>Cambio de uso del suelo</td><td class='m7'>M7.4</td><td>Pendiente</td></tr>
<tr><td>CF-DEV-05</td><td>Identificación de especies</td><td class='m7'>M7.5</td><td>Pendiente</td></tr></table>"""

documento = ("<!doctype html><html lang='es'><head><meta charset='utf-8'><style>" + ESTILO + "</style></head><body>"
             + pagina(11, p11) + pagina(12, p12) + pagina(13, p13) + pagina(14, p14) + pagina(15, p15)
             + pagina(21, p21) + pagina(22, p22) + "</body></html>")
with sync_playwright() as p:
    navegador = p.chromium.launch()
    pag = navegador.new_page()
    pag.set_content(documento)
    desbordadas = pag.evaluate("[...document.querySelectorAll('.pagina')].filter(s => s.scrollHeight > s.clientHeight)"
                               ".map(s => s.dataset.n)")
    assert not desbordadas, f"Páginas que no caben: {desbordadas}"
    nuevas = pag.pdf(format="Letter", print_background=True, prefer_css_page_size=True)
    navegador.close()

generadas = PdfReader(io.BytesIO(nuevas))
assert len(generadas.pages) == 7, len(generadas.pages)
original = PdfReader(ORIGINAL / "docs" / "Propuesta_solucion_modular_PROBOSQUE_2026.pdf")
assert len(original.pages) == TOTAL_PAGINAS
salida = PdfWriter()
reemplazo = {10: 0, 11: 1, 12: 2, 13: 3, 14: 4, 20: 5, 21: 6}
for i, pagina_original in enumerate(original.pages):
    salida.add_page(generadas.pages[reemplazo[i]] if i in reemplazo else pagina_original)
salida.add_metadata({"/Title": "Propuesta de solución modular — PROBOSQUE 2026",
                     "/Subject": "Historias de usuario actualizadas (ver CAMBIOS_HU.md)"})
with open(CARPETA / "docs" / "Propuesta_solucion_modular_PROBOSQUE_2026.pdf", "wb") as f:
    salida.write(f)
print("propuesta actualizada:", len(original.pages), "páginas; reemplazadas 11-15 y 21-22")
