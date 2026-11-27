"""Regenera los diagramas de ``docs/modelo_datos.md`` (cada bloque ``mermaid`` con las entidades que ya dibuja) y el
completo ``docs/modelo_datos.mmd`` con ``herramientas/diagrama_er.py``. El texto de cada sección se escribe a mano; los
diagramas, no.

    docker compose --profile pruebas run --rm --no-deps --entrypoint python pruebas herramientas/regenerar_modelo_datos.py
"""
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
MD = RAIZ / "docs" / "modelo_datos.md"
HERRAMIENTA = [sys.executable, str(RAIZ / "herramientas" / "diagrama_er.py")]
BLOQUE = re.compile(r"```mermaid\nerDiagram\n(.*?)```", re.S)


def diagrama(*args):
    return subprocess.run(HERRAMIENTA + list(args), check=True, capture_output=True, text=True, cwd=RAIZ).stdout


def main():
    texto = MD.read_text(encoding="utf-8")

    def nuevo(m):
        entidades = re.findall(r"^  (\w+) \{$", m.group(1), re.M)
        return "```mermaid\n" + diagrama("--resumen", "--entidades", *entidades) + "```"

    MD.write_text(BLOQUE.sub(nuevo, texto), encoding="utf-8")
    (RAIZ / "docs" / "modelo_datos.mmd").write_text(diagrama(), encoding="utf-8")


if __name__ == "__main__":
    main()
