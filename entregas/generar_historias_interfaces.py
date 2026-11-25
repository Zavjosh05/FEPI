"""Genera tres documentos con las 26 historias de usuario, su cotejo con los 7 módulos, el código y las pantallas:

- `completa`: entregas/interfaces/Historias_e_interfaces.pdf, el documento de trabajo, con todo lo que se notó;
- `profesor`: Historias_de_usuario_e_interfaces.pdf (raíz del repositorio), para exponer: historias, cotejo e
  interfaz, sin las observaciones de problemas;
- `cambios`: Registro_de_cambios_historias_e_interfaces.pdf (raíz del repositorio): qué se agregó, qué se modificó,
  qué se notó y qué falta en la revisión del 19-nov;
- `observaciones`: Registro_de_cambios_observaciones_23_nov.pdf (raíz del repositorio): los cambios por las
  observaciones del profesor del 23-nov (documentos, vistas, código, base de datos y pruebas).

Lee:
- `sistema/especificacion/modelo.json` (módulos, funciones e historias);
- `entregas/interfaces/cotejo.json` (resultado del cotejo de cada historia y ajustes; se escribe a mano);
- `entregas/interfaces/capturas.json` (pie de cada captura nueva) y las capturas de `entregas/interfaces/capturas/`;
- las capturas de los recorridos del sprint 1 en `entregas/sprint_1/capturas/`.

Usa el mismo estilo que el resumen del sprint (`generar_resumen.py`). Se corre igual que ese script, con la imagen de
pruebas del sistema (trae WeasyPrint):

    python entregas/generar_historias_interfaces.py [completa|profesor|cambios|todas]   (por omisión, todas)
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generar_resumen import CSS, ESPEC, RAIZ, e, funciones, pie_de  # noqa: E402

CARPETA = RAIZ / "entregas" / "interfaces"
SPRINT1 = RAIZ / "entregas" / "sprint_1" / "capturas"
VERSIONES = {
    "completa": {"titulo": "Historias de usuario e interfaces", "contenido": "contenido.html",
                 "salida": CARPETA / "Historias_e_interfaces.pdf", "notas": True},
    "profesor": {"titulo": "Historias de usuario e interfaces", "contenido": "contenido_profesor.html",
                 "salida": RAIZ / "Historias_de_usuario_e_interfaces.pdf", "notas": False},
    "cambios": {"titulo": "Registro de cambios: historias e interfaces", "contenido": "contenido_cambios.html",
                "salida": RAIZ / "Registro_de_cambios_historias_e_interfaces.pdf", "notas": True, "lote": "19-nov"},
    "observaciones": {"titulo": "Registro de cambios: observaciones del 23 de noviembre",
                      "contenido": "contenido_observaciones.html",
                      "salida": RAIZ / "Registro_de_cambios_observaciones_23_nov.pdf", "notas": True, "lote": "23-nov"},
}

CSS_EXTRA = """
.hu td { font-size: 8.3pt; } .hu td.t { width: 13%; } .hu td.h { width: 38%; } .hu td.c { width: 39%; }
.ok { color: #1f6b35; font-weight: 600; } .aj { color: #8a5a00; font-weight: 600; } .pend { color: #555; font-weight: 600; }
.cap { margin: .25cm 0 .4cm; break-inside: avoid; } .cap img { width: 100%; border: .5pt solid #b8c2ba; }
.par .cap img { width: auto; max-width: 100%; max-height: 20.5cm; }
.cap figcaption { font-size: 7.8pt; color: #444; margin-top: .08cm; } .cap .ruta { color: #888; font-family: "DejaVu Sans Mono", monospace; font-size: 6.8pt; }
table.par { table-layout: fixed; margin: 0; } table.par td { width: 50%; border: none; padding: .1cm .18cm .1cm 0; }
table.par tr.tit { break-after: avoid; page-break-after: avoid; } table.par tr.tit td { padding: 0; }
table.par td + td { padding: .1cm 0 .1cm .18cm; } table.par .cap { margin: 0 0 .15cm; }
.antes { color: #6b2a1f; } .ahora { color: #1f4d2e; }
"""


def criterios_txt(crit):
    if len(crit) == 1:
        return e(crit[0])
    return " ".join(f"{i}) {e(c)}" for i, c in enumerate(crit, 1))


# ----------------------------------------------------------------------------- tablas
def tabla_modulos(modelo):
    hu_de = {h["funcion"]: h for h in modelo["historias"]}
    estado = {1: "Construida", 2: "Sprint 2", 3: "Sprint 3"}
    filas = []
    for m in modelo["modulos"] + [modelo["calculadora"]]:
        hus = [hu_de[f["id"]] for f in m["funciones"]]
        sprints = sorted({h["sprint"] for h in hus})
        filas.append(
            f"<tr><td class='id'>{e(m['id'])}</td><td><b>{e(m['nombre'])}</b><br><span class='gris'>{e(m['descripcion'])}</span></td>"
            f"<td class='n'>{len(m['funciones'])}</td><td class='id' style='white-space:normal'>{e(', '.join(h['id'] for h in hus))}</td>"
            f"<td class='n'>{sum(h['puntos'] for h in hus)}</td><td>{e(', '.join(estado[s] for s in sprints))}</td></tr>")
    total = len(modelo["historias"])
    return ("<table><thead><tr><th>Módulo</th><th>Nombre y alcance</th><th class='n'>Funciones</th><th>Historias</th>"
            "<th class='n'>Puntos</th><th>Situación</th></tr></thead><tbody>" + "".join(filas) +
            f"<tr><td></td><td><b>Total</b></td><td class='n'><b>{total}</b></td><td><b>{total} historias</b></td>"
            f"<td class='n'><b>{sum(h['puntos'] for h in modelo['historias'])}</b></td><td></td></tr></tbody></table>")


def comprobar_correspondencia(modelo):
    """Cada función tiene exactamente una historia y cada historia una función que existe."""
    fun = funciones(modelo)
    por_funcion = {}
    for h in modelo["historias"]:
        por_funcion.setdefault(h["funcion"], []).append(h["id"])
    sin_historia = [f for f in fun if f not in por_funcion]
    repetidas = {f: hs for f, hs in por_funcion.items() if len(hs) > 1}
    sin_funcion = [h for f, hs in por_funcion.items() for h in hs if f not in fun]
    numeracion = [h["id"] for h in modelo["historias"] if h["id"].replace("HU-", "M") != h["funcion"]]
    return sin_historia, repetidas, sin_funcion, numeracion


def tabla_cotejo(modelo, cotejo, notas=True):
    fun = funciones(modelo)
    marcas = {"empata": "<span class='ok'>Empata</span>", "ajustada": "<span class='aj'>Ajustada</span>",
              "sin_codigo": "<span class='pend'>Sin código aún</span>"}
    filas = []
    for h in modelo["historias"]:
        c = dict(cotejo["historias"][h["id"]])
        if not notas:                              # versión para exponer: el estado vigente, sin observaciones
            c["nota"] = ""
            c["resultado"] = "empata" if c["resultado"] == "ajustada" else c["resultado"]
            c["funcion"] = c.get("funcion_vigente", c["funcion"])
            c["codigo"] = c.get("codigo_vigente", c["codigo"])
        filas.append(
            f"<tr><td><span class='id'>{e(h['id'])}</span><br><b>{e(h['titulo'])}</b><br><span class='gris'>Función {e(h['funcion'])} · sprint {h['sprint']}</span></td>"
            f"<td>{e(c['funcion'])}</td><td>{e(c['codigo'])}</td><td>{marcas[c['resultado']]}"
            f"{'<br><span class=gris>' + e(c['nota']) + '</span>' if c.get('nota') else ''}</td></tr>")
    return ("<table><thead><tr><th style='width:15%'>Historia</th><th style='width:27%'>Contra su función del módulo</th>"
            "<th style='width:38%'>Contra el código y las pantallas</th><th>Resultado</th></tr></thead><tbody>"
            + "".join(filas) + "</tbody></table>")


def tabla_ajustes(cotejo, lote=None):
    """Ajustes a las historias (antes y ahora); ``lote`` = «19-nov» o «23-nov» para solo los de esa revisión."""
    partes = []
    for a in cotejo["ajustes"]:
        if lote and a.get("lote", "19-nov") != lote:
            continue
        filas = "".join(f"<tr><td>{e(x['parte'])}</td><td class='antes'>{e(x['antes'])}</td><td class='ahora'>{e(x['ahora'])}</td></tr>"
                        for x in a["cambios"])
        partes.append(f"<h3>{e(a['historia'])}</h3><p>{e(a['motivo'])}</p>"
                      "<table><thead><tr><th style='width:12%'></th><th style='width:44%'>Antes</th><th>Ahora</th></tr></thead>"
                      f"<tbody>{filas}</tbody></table>")
    return "".join(partes)


def tablas_historias(modelo):
    partes = []
    hu_de = {h["funcion"]: h for h in modelo["historias"]}
    for m in modelo["modulos"] + [modelo["calculadora"]]:
        num = m["id"][1:]
        filas = []
        for f in m["funciones"]:
            h = hu_de[f["id"]]
            filas.append(f"<tr><td class='id'>{e(h['id'])}</td><td class='t'>{e(h['titulo'])}</td><td class='h'>{e(h['texto'])}</td>"
                         f"<td class='c'>{criterios_txt(h['criterios'])}</td><td class='n'>{h['puntos']}</td></tr>")
        partes.append(f"<h3>Módulo {num}. {e(m['nombre'])}</h3><table class='hu'><thead><tr><th>HU</th><th>Título</th>"
                      "<th>Historia de usuario</th><th>Criterios de aceptación</th><th class='n'>Puntos</th></tr></thead>"
                      f"<tbody>{''.join(filas)}</tbody></table>")
    return "".join(partes)


# ----------------------------------------------------------------------------- capturas
def _ruta(nombre):
    if (CARPETA / "capturas" / nombre).exists():
        return f"capturas/{nombre}", f"interfaces/capturas/{nombre}"
    if (SPRINT1 / nombre).exists():
        return f"../sprint_1/capturas/{nombre}", f"sprint_1/capturas/{nombre}"
    sys.exit(f"No existe la captura {nombre}")


PROPORCION_MAXIMA = 2.6     # alto / ancho; las más altas se recortan a su parte superior
ANCHO_MAXIMO = 1300
TEMPORAL = None


def preparar(nombre):
    """Copia de la captura para el PDF: JPEG, a lo más ANCHO_MAXIMO de ancho y recortada si es muy alta.
    Las capturas originales (PNG) no se tocan. Devuelve (ruta absoluta, se recortó)."""
    global TEMPORAL
    import tempfile
    from PIL import Image
    if TEMPORAL is None:
        TEMPORAL = Path(tempfile.mkdtemp(prefix="historias_interfaces_"))
    src, _ = _ruta(nombre)
    with Image.open(CARPETA / src) as im:
        im = im.convert("RGB")
        recorte = im.height / im.width > PROPORCION_MAXIMA
        if recorte:
            im = im.crop((0, 0, im.width, int(im.width * PROPORCION_MAXIMA)))
        if im.width > ANCHO_MAXIMO:
            im = im.resize((ANCHO_MAXIMO, round(im.height * ANCHO_MAXIMO / im.width)), Image.LANCZOS)
        destino = TEMPORAL / (Path(nombre).stem + ".jpg")
        im.save(destino, quality=84, optimize=True)
    return destino, recorte


def figuras(nombres, pies, encabezado=""):
    """Capturas de dos en dos, cada una a media hoja y sin pasar de una hoja de alto."""
    partes = []

    def fig(nombre):
        archivo, recorte = preparar(nombre)
        _, mostrar = _ruta(nombre)
        pie = pies.get(nombre) or pie_de(nombre)
        if recorte:
            pie += " (parte superior de la pantalla)"
        return (f"<figure class='cap'><img src='{archivo.as_uri()}' alt=''><figcaption>{e(pie)} "
                f"<span class='ruta'>{e(mostrar)}</span></figcaption></figure>")

    for i in range(0, len(nombres), 2):
        celdas = "".join(f"<td>{fig(n)}</td>" for n in nombres[i:i + 2])
        if len(nombres[i:i + 2]) == 1:
            celdas += "<td></td>"
        partes.append(f"<tr>{celdas}</tr>")
    titulo = f"<tr class='tit'><td colspan='2'>{encabezado}</td></tr>" if encabezado else ""
    return "<table class='par'>" + titulo + "".join(partes) + "</table>"


def grupos_interfaz(cotejo, version):
    """Grupos de capturas de la versión: la de exponer quita las capturas y los textos que señalan problemas."""
    if version == "cambios":
        return cotejo.get("evidencia", [])
    if version == "observaciones":
        return cotejo.get("evidencia_23nov", [])
    ajustes = cotejo.get("profesor", {}) if version == "profesor" else {}
    fuera = set(ajustes.get("sin_capturas", []))
    textos = ajustes.get("textos", {})
    grupos = []
    for g in cotejo["interfaz"]:
        capturas = [n for n in g["capturas"] if n not in fuera]
        if capturas:
            grupos.append({**g, "capturas": capturas, "texto": textos.get(g["titulo"], g.get("texto", ""))})
    return grupos


def apartado_interfaz(grupos, pies):
    partes = []
    for g in grupos:
        encabezado = f"<h3>{e(g['titulo'])}</h3>" + (f"<p>{g['texto']}</p>" if g.get("texto") else "")
        partes.append(figuras(g["capturas"], pies, encabezado))
    return "".join(partes)


# ----------------------------------------------------------------------------- documento
def generar(version):
    conf = VERSIONES[version]
    titulo = conf["titulo"]
    modelo = json.loads((ESPEC / "modelo.json").read_text(encoding="utf-8"))
    cotejo = json.loads((CARPETA / "cotejo.json").read_text(encoding="utf-8"))
    pies = json.loads((CARPETA / "capturas.json").read_text(encoding="utf-8"))
    if version == "profesor":
        pies.update(cotejo.get("profesor", {}).get("pies", {}))
    cuerpo = (CARPETA / conf["contenido"]).read_text(encoding="utf-8")

    sin_historia, repetidas, sin_funcion, numeracion = comprobar_correspondencia(modelo)
    if sin_historia or repetidas or sin_funcion or numeracion:
        sys.exit(f"La correspondencia función-historia no es uno a uno: {sin_historia} {repetidas} {sin_funcion} {numeracion}")

    grupos = grupos_interfaz(cotejo, version)
    usadas = [n for g in grupos for n in g["capturas"]]
    todas = [n for g in cotejo["interfaz"] for n in g["capturas"]]
    cifras = {
        "historias": len(modelo["historias"]),
        "funciones": len(funciones(modelo)),
        "capturas": len(usadas),
        "capturas_nuevas": sum(1 for n in usadas if (CARPETA / "capturas" / n).exists()),
        "capturas_previas": sum(1 for n in usadas if not (CARPETA / "capturas" / n).exists()),
        "capturas_completa": len(todas),
        "capturas_completa_nuevas": sum(1 for n in todas if (CARPETA / "capturas" / n).exists()),
        "construidas": sum(1 for h in modelo["historias"] if cotejo["historias"][h["id"]]["resultado"] != "sin_codigo"),
        "empatan": sum(1 for c in cotejo["historias"].values() if c["resultado"] == "empata"),
        "ajustadas": sum(1 for c in cotejo["historias"].values() if c["resultado"] == "ajustada"),
        "sin_codigo": sum(1 for c in cotejo["historias"].values() if c["resultado"] == "sin_codigo"),
        **cotejo.get("cifras", {}),
    }
    for marca, valor in {
        "<!--TABLA_MODULOS-->": tabla_modulos(modelo),
        "<!--TABLA_COTEJO-->": tabla_cotejo(modelo, cotejo, conf["notas"]),
        "<!--TABLA_AJUSTES-->": tabla_ajustes(cotejo, conf.get("lote")),
        "<!--TABLAS_HISTORIAS-->": tablas_historias(modelo),
        "<!--INTERFAZ-->": apartado_interfaz(grupos, pies),
    }.items():
        cuerpo = cuerpo.replace(marca, valor)
    for clave, valor in cifras.items():
        cuerpo = cuerpo.replace("{{" + clave + "}}", e(valor))
    pendientes = re.findall(r"\{\{[^}]+\}\}|<!--[A-Z_]+-->", cuerpo)
    if pendientes:
        sys.exit(f"Quedaron marcas sin llenar: {sorted(set(pendientes))}")

    css = CSS.replace("Resumen del sprint __SPRINT__", titulo) + CSS_EXTRA
    documento = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><title>{titulo}</title>"
                 f"<style>{css}</style></head><body>{cuerpo}</body></html>")
    salida = conf["salida"]
    if "--html" in sys.argv:
        salida.with_suffix(".html").write_text(documento, encoding="utf-8")
    from weasyprint import HTML

    HTML(string=documento, base_url=str(CARPETA)).write_pdf(str(salida), optimize_images=True, jpeg_quality=84, dpi=200)
    print(f"{salida} ({salida.stat().st_size / 1024:.0f} kB, {len(usadas)} capturas)")


def main():
    pedidas = [a for a in sys.argv[1:] if not a.startswith("--")] or ["todas"]
    for version in (list(VERSIONES) if pedidas == ["todas"] else pedidas):
        if version not in VERSIONES:
            sys.exit(f"Versión desconocida: {version}. Use {', '.join(VERSIONES)} o todas.")
        generar(version)


if __name__ == "__main__":
    main()
