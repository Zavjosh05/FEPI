"""Convierte documentos Markdown del proyecto a PDF (con diagramas de Mermaid e imágenes).

Se corre dentro de la imagen de pruebas del sistema (trae Chromium por Playwright); la biblioteca `markdown` se
instala al vuelo porque la imagen no la trae:

    wsl -e bash -lc "docker run --rm -v /mnt/c/.../FEPI:/repo -w /repo --entrypoint sh probosque-sistema-pruebas:sprint-2 \
        -c 'pip install -q markdown && python entregas/md_a_pdf.py ARCHIVO.md [ARCHIVO2.md ...]'"

Cada PDF queda junto a su Markdown, con el mismo nombre. Las rutas de imágenes se resuelven desde la carpeta del
Markdown. Los bloques ```mermaid se dibujan con Mermaid en el navegador antes de imprimir.
"""
import html
import os
import pathlib
import re
import sys

import markdown
from playwright.sync_api import sync_playwright

# Sin internet, se puede apuntar a una copia local: MERMAID_JS=file:///ruta/mermaid.min.js
MERMAID_JS = os.environ.get("MERMAID_JS", "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js")
ESTILO = """
@page { size: Letter; margin: 1.8cm 1.7cm 1.9cm 1.7cm; }
html { font-family: "DejaVu Sans", "Noto Sans", sans-serif; font-size: 9.4pt; line-height: 1.45; color: #1c1c1c; }
h1 { font-size: 19pt; color: #1e4d2b; margin: 0 0 .3em; }
h2 { font-size: 13.5pt; color: #1e4d2b; border-bottom: 1.5px solid #1e4d2b; padding-bottom: 2px; margin-top: 1.4em;
     break-after: avoid; }
h3 { font-size: 11pt; margin-top: 1.1em; break-after: avoid; }
h4 { font-size: 10pt; margin-top: .9em; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: .5em 0 .9em; font-size: 8.4pt; break-inside: auto; }
th { background: #1e4d2b; color: #fff; text-align: left; padding: 4px 6px; }
td { border-bottom: 1px solid #ddd; padding: 4px 6px; vertical-align: top; }
tr { break-inside: avoid; }
code { font-family: "DejaVu Sans Mono", monospace; font-size: 8pt; background: #f2f2f2; padding: 0 2px; }
pre { background: #f5f5f5; padding: 6px 8px; font-size: 7.8pt; white-space: pre-wrap; break-inside: avoid; }
pre.mermaid { background: none; text-align: center; }
pre.mermaid svg { width: 100% !important; max-width: 100% !important; height: auto; max-height: 18cm; }
blockquote { border-left: 3px solid #c99a2e; background: #fdf7e8; margin: .6em 0; padding: .3em .8em; }
img { max-width: 100%; max-height: 15cm; display: block; margin: .4em auto; border: 1px solid #ddd; }
hr { border: none; border-top: 1px solid #ccc; margin: 1.2em 0; }
.salto { break-before: page; }
"""


def convertir(md_path, pagina):
    md_path = pathlib.Path(md_path).resolve()
    texto = md_path.read_text(encoding="utf-8")
    # Bloques de Mermaid: se sacan antes de convertir y se reponen como <pre class="mermaid">.
    bloques = []

    def guardar(m):
        bloques.append(m.group(1))
        return f"\n\nMERMAID{len(bloques) - 1}FIN\n\n"

    texto = re.sub(r"```mermaid\n(.*?)```", guardar, texto, flags=re.S)
    # GitHub anida listas con 2 espacios; la biblioteca `markdown` pide 4.
    texto = re.sub(r"^  ((?:[-*]|\d+\.) )", r"    \1", texto, flags=re.M)
    cuerpo = markdown.markdown(texto, extensions=["tables", "fenced_code", "sane_lists", "toc"])
    for i, codigo in enumerate(bloques):
        cuerpo = cuerpo.replace(f"<p>MERMAID{i}FIN</p>", f"<pre class='mermaid'>{html.escape(codigo)}</pre>")
    cuerpo = cuerpo.replace("<p>[[SALTO]]</p>", "<div class='salto'></div>")
    documento = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><base href='{md_path.parent.as_uri()}/'>"
                 f"<style>{ESTILO}</style></head><body>{cuerpo}"
                 f"<script src='{MERMAID_JS}'></script>"
                 "<script>mermaid.initialize({startOnLoad:false, theme:'neutral'});"
                 "mermaid.run().then(()=>{document.body.dataset.listo='1'});</script></body></html>")
    temporal = md_path.with_suffix(".tmp.html")
    temporal.write_text(documento, encoding="utf-8")
    try:
        pagina.goto(temporal.as_uri())
        if bloques:
            pagina.wait_for_selector("body[data-listo='1']", timeout=60000)
        else:
            pagina.wait_for_load_state("networkidle")
        destino = md_path.with_suffix(".pdf")
        pagina.pdf(path=str(destino), format="Letter", print_background=True, prefer_css_page_size=True,
                   display_header_footer=True, header_template="<span></span>",
                   footer_template="<div style='font-size:7pt;width:100%;text-align:center;color:#777'>"
                                   f"{html.escape(md_path.stem.replace('_', ' '))} · "
                                   "<span class='pageNumber'></span> / <span class='totalPages'></span></div>")
        print(destino, f"({destino.stat().st_size // 1024} kB)")
    finally:
        temporal.unlink(missing_ok=True)


if __name__ == "__main__":
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        pagina = navegador.new_page()
        for archivo in sys.argv[1:]:
            convertir(archivo, pagina)
        navegador.close()
