"""Vuelve a generar los diagramas de `docs/modelo_datos.md` y el diagrama completo `docs/modelo_datos.mmd`.

Cada sección de `modelo_datos.md` tiene un bloque Mermaid de un área; este script toma las entidades que ya dibuja cada
bloque, le agrega las que se indiquen en NUEVAS (tablas que aparecieron después) y lo reemplaza con la salida de
`diagrama_er.py --resumen --entidades ...`. El texto de las secciones no se toca, salvo el número de tablas del
primer párrafo.

    docker compose --profile pruebas run --rm --no-deps --entrypoint python pruebas herramientas/regenerar_modelo_datos.py
"""
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DOC = RAIZ / "docs" / "modelo_datos.md"
MMD = RAIZ / "docs" / "modelo_datos.mmd"
ER = [sys.executable, str(RAIZ / "herramientas" / "diagrama_er.py")]
# título de la sección (inicio) -> entidades nuevas que se agregan a su diagrama
NUEVAS = {"## 2.": ["ObservacionValidacion"], "## 3.": ["RevisionPropiedad", "MovimientoListado"]}


def entidades_de(bloque):
    nombres = set()
    for linea in bloque.splitlines():
        linea = linea.strip()
        m = re.match(r"^(\w+)\s+[|}o][^ ]*\s+(\w+)\s*:", linea)
        if m:
            nombres.update(m.groups())
            continue
        m = re.match(r"^(\w+)\s*\{", linea)
        if m:
            nombres.add(m.group(1))
    nombres.discard("erDiagram")
    return sorted(nombres)


def generar(*args):
    return subprocess.run(ER + list(args), capture_output=True, text=True, check=True).stdout.strip("\n")


def main():
    texto = DOC.read_text(encoding="utf-8")
    partes = re.split(r"(?m)^(## .*)$", texto)
    salida = [partes[0]]
    for titulo, cuerpo in zip(partes[1::2], partes[2::2]):
        bloques = list(re.finditer(r"```mermaid\n(.*?)```", cuerpo, flags=re.S))
        if bloques:
            m = bloques[0]
            nombres = entidades_de(m.group(1))
            for prefijo, extra in NUEVAS.items():
                if titulo.startswith(prefijo):
                    nombres = sorted(set(nombres) | set(extra))
            nuevo = generar("--resumen", "--entidades", *nombres)
            cuerpo = cuerpo[:m.start()] + "```mermaid\n" + nuevo + "\n```" + cuerpo[m.end():]
        salida += [titulo, cuerpo]
    texto = "".join(salida)
    completo = generar()
    MMD.write_text(completo + "\n", encoding="utf-8")
    tablas = len(re.findall(r"(?m)^  \w+ \{", completo))
    texto = re.sub(r"\b\d+ tablas propias", f"{tablas} tablas propias", texto, count=1)
    DOC.write_text(texto, encoding="utf-8")
    print(f"{tablas} tablas")


if __name__ == "__main__":
    main()
