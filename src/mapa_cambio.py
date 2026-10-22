#!/usr/bin/env python3
"""
Mapa de una corrida de la calculadora de masa forestal
======================================================

Dibuja en un PNG el resultado de `prototipo_masa_forestal.py correr`:

  - Izquierda: el ráster de cambio (bosque estable, pérdida por incendio, otra pérdida y
    ganancia) con los límites de las unidades.
  - Derecha (si se dan unidades): el cambio neto de bosque de cada unidad, en porcentaje.

En zonas grandes cada celda del mapa junta varios píxeles de 10 m. Para que las pérdidas y
ganancias, que son manchas pequeñas, no desaparezcan, la celda toma la clase de mayor
prioridad que contenga: pérdida por incendio > otra pérdida > ganancia > bosque estable.
Eso las hace ver más grandes de lo que son; las hectáreas reales están en el balance y en
la leyenda.

Uso (desde la raíz del repositorio):
    python src/mapa_cambio.py resultados/edomex_2023_2024 \
        --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
        --titulo "Estado de México"
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SIN_BOSQUE, ESTABLE, PERD_INCENDIO, PERD_OTRA, GANANCIA = 0, 1, 2, 3, 4

# Colores (validados para daltonismo: todos los pares distinguibles)
SUPERFICIE = "#fcfcfb"
TINTA, TINTA_2, TINTA_TENUE = "#0b0b0b", "#52514e", "#898781"
FONDO_SIN_BOSQUE = "#e6e5df"
COLOR_CLASE = {ESTABLE: "#1baf7a", PERD_INCENDIO: "#a3221d", PERD_OTRA: "#eb6834", GANANCIA: "#2a78d6"}

# Cambio neto por unidad: rojo (pierde) - gris (casi igual) - azul (gana)
CORTES_PCT = [-np.inf, -5, -2, -0.5, 0.5, 2, np.inf]
COLORES_PCT = ["#a8201a", "#e34948", "#f09a96", "#ebeae5", "#86b6ef", "#2a78d6"]
ETIQUETAS_PCT = ["Pierde más de 5 %", "Pierde 2–5 %", "Pierde 0.5–2 %", "Casi igual (±0.5 %)",
                 "Gana 0.5–2 %", "Gana más de 2 %"]
BOSQUE_MINIMO_HA = 500  # con menos bosque, el porcentaje engaña: se marca aparte


def leer_cambio_agregado(ruta, ancho_px):
    """Ráster de cambio reducido a ~ancho_px columnas, con prioridad a pérdidas y ganancias.

    Lee por franjas para no cargar todo el ráster (el del estado son 450 M píxeles).
    Regresa (arreglo, factor, límites) con límites = (izq, abajo, der, arriba) en metros.
    """
    import rasterio
    from rasterio.windows import Window

    with rasterio.open(ruta) as src:
        alto, ancho = src.height, src.width
        f = max(1, math.ceil(ancho / ancho_px))
        h, w = math.ceil(alto / f), math.ceil(ancho / f)
        salida = np.zeros((h, w), dtype=np.uint8)
        paso = f * max(1, 4096 // f)
        for r0 in range(0, alto, paso):
            r1 = min(r0 + paso, alto)
            a = src.read(1, window=Window(0, r0, ancho, r1 - r0))
            filas = math.ceil((r1 - r0) / f)
            a = np.pad(a, ((0, filas * f - (r1 - r0)), (0, w * f - ancho)))
            celdas = a.reshape(filas, f, w, f)
            cat = np.zeros((filas, w), dtype=np.uint8)
            for clase in (ESTABLE, GANANCIA, PERD_OTRA, PERD_INCENDIO):  # de menor a mayor prioridad
                cat[(celdas == clase).any(axis=(1, 3))] = clase
            salida[r0 // f:r0 // f + filas] = cat
        b = src.bounds
        # Límites de la malla reducida (la última fila/columna puede salirse un poco del ráster)
        res_x, res_y = src.transform.a * f, -src.transform.e * f
        limites = (b.left, b.top - h * res_y, b.left + w * res_x, b.top)
        crs = src.crs
    return salida, f, limites, crs


def barra_escala(ax, limites):
    """Barra de escala de ~1/5 del ancho, redondeada a 1, 2 o 5 × 10^n km."""
    izq, abajo, der, arriba = limites
    objetivo = (der - izq) / 5
    n = 10 ** math.floor(math.log10(objetivo))
    largo = max(m * n for m in (1, 2, 5) if m * n <= objetivo)
    x0, y0 = izq + (der - izq) * 0.04, abajo + (arriba - abajo) * 0.04
    ax.plot([x0, x0 + largo], [y0, y0], color=TINTA, lw=2, solid_capstyle="butt")
    km = largo / 1000
    ax.text(x0 + largo / 2, y0 + (arriba - abajo) * 0.012, f"{km:g} km", ha="center", va="bottom",
            fontsize=8, color=TINTA_2)


def main():
    p = argparse.ArgumentParser(description="Mapa PNG de una corrida de la calculadora")
    p.add_argument("carpeta", help="carpeta de resultados de correr")
    p.add_argument("--periodo", help="sufijo de los archivos, p. ej. 2023_2024 (se deduce si hay uno)")
    p.add_argument("--unidades", help="polígonos de las unidades del balance (p. ej. municipios)")
    p.add_argument("--campo-unidad", default="NOM_MUN")
    p.add_argument("--titulo", default="", help="nombre de la zona para el título")
    p.add_argument("--ancho-px", type=int, default=1800, help="resolución del mapa de cambio")
    p.add_argument("--etiquetar", type=int, default=5,
                   help="cuántas unidades con más pérdida neta (ha) rotular en el mapa de la derecha")
    p.add_argument("--salida", help="PNG de salida (por defecto <carpeta>/mapa_cambio_<periodo>.png)")
    p.add_argument("--sobrescribir", action="store_true")
    a = p.parse_args()

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import ListedColormap
    from matplotlib.patches import Patch
    import matplotlib.patheffects as pe

    carpeta = Path(a.carpeta)
    if a.periodo:
        periodo = a.periodo
    else:
        candidatos = sorted(carpeta.glob("cambio_*.tif"))
        if len(candidatos) != 1:
            sys.exit(f"Hay {len(candidatos)} rásters cambio_*.tif en {carpeta}; indica --periodo.")
        periodo = candidatos[0].stem.removeprefix("cambio_")
    ruta_cambio = carpeta / f"cambio_{periodo}.tif"
    ruta_balance = carpeta / f"balance_{periodo}.csv"
    salida = Path(a.salida) if a.salida else carpeta / f"mapa_cambio_{periodo}.png"
    if salida.exists() and not a.sobrescribir:
        sys.exit(f"{salida} ya existe; usa --sobrescribir u otra --salida.")
    anio_base, anio = periodo.split("_")

    balance = pd.read_csv(ruta_balance)
    tot = balance.sum(numeric_only=True)
    umbral = float(balance["umbral_ndvi"].iloc[0])

    print(f"Leyendo {ruta_cambio.name}")
    cambio, f, limites, crs = leer_cambio_agregado(ruta_cambio, a.ancho_px)
    celda_m = round(10 * f)

    uni = None
    if a.unidades:
        import geopandas as gpd
        uni = gpd.read_file(a.unidades).to_crs(crs)
        uni = uni[uni[a.campo_unidad].astype(str).isin(balance["unidad"].astype(str))].copy()

    plt.rcParams.update({"font.family": ["Segoe UI", "DejaVu Sans"], "text.color": TINTA,
                         "axes.edgecolor": SUPERFICIE})
    dos = uni is not None and len(uni) > 0
    fig, ejes = plt.subplots(1, 2 if dos else 1, figsize=(15, 8) if dos else (9, 8.6),
                             facecolor=SUPERFICIE, layout="constrained")
    ejes = np.atleast_1d(ejes)

    # --- Izquierda: ráster de cambio -------------------------------------------------
    ax = ejes[0]
    if dos:  # fondo gris debajo del ráster (zorder), límites encima
        uni.plot(ax=ax, color=FONDO_SIN_BOSQUE, linewidth=0, zorder=1)
    colores = [(0, 0, 0, 0)] + [COLOR_CLASE[c] for c in (ESTABLE, PERD_INCENDIO, PERD_OTRA, GANANCIA)]
    izq, abajo, der, arriba = limites
    ax.imshow(cambio, cmap=ListedColormap(colores), vmin=0, vmax=4, interpolation="nearest",
              extent=(izq, der, abajo, arriba), zorder=2)
    if dos:
        uni.boundary.plot(ax=ax, color=TINTA_TENUE, linewidth=0.25, zorder=3)
        uni.dissolve().boundary.plot(ax=ax, color=TINTA_2, linewidth=0.8, zorder=3)
    ax.set_xlim(izq, der)
    ax.set_ylim(abajo, arriba)
    ax.set_axis_off()
    barra_escala(ax, limites)
    detalle = (f"cada celda de {celda_m} m muestra la pérdida o ganancia si la hay" if f > 1
               else "píxeles de 10 m")
    ax.set_title(f"Cambio de cobertura ({detalle})", loc="left", fontsize=10, color=TINTA_2)
    leyenda = [
        Patch(color=COLOR_CLASE[ESTABLE], label=f"Bosque estable"),
        Patch(color=COLOR_CLASE[PERD_INCENDIO], label=f"Pérdida por incendio ({tot.perdida_incendio_ha:,.0f} ha)"),
        Patch(color=COLOR_CLASE[PERD_OTRA], label=f"Otra pérdida, por verificar ({tot.otras_perdidas_ha:,.0f} ha)"),
        Patch(color=COLOR_CLASE[GANANCIA], label=f"Ganancia ({tot.ganancia_ha:,.0f} ha)"),
        Patch(color=FONDO_SIN_BOSQUE, label="Sin bosque o fuera de la zona forestal"),
    ]
    ax.legend(handles=leyenda, loc="upper left", bbox_to_anchor=(0, 0), ncol=3, fontsize=8.5,
              frameon=False, labelcolor=TINTA)  # debajo del mapa, para no tapar ninguna zona

    # --- Derecha: cambio neto por unidad ---------------------------------------------
    if dos:
        ax = ejes[1]
        b = balance.set_index(balance["unidad"].astype(str))
        uni["base"] = uni[a.campo_unidad].astype(str).map(b["bosque_base_ha"])
        uni["neto"] = uni[a.campo_unidad].astype(str).map(b["cambio_neto_ha"])
        poco = uni["base"] < BOSQUE_MINIMO_HA
        uni["pct"] = np.where(poco, np.nan, uni["neto"] / uni["base"] * 100)
        clase = pd.cut(uni["pct"], CORTES_PCT, labels=False, right=False)
        handles = []
        for k, (color, etiqueta) in enumerate(zip(COLORES_PCT, ETIQUETAS_PCT)):
            sel = uni[(clase == k) & ~poco]
            if len(sel):
                sel.plot(ax=ax, color=color, edgecolor=SUPERFICIE, linewidth=0.4)
            handles.append(Patch(facecolor=color, label=f"{etiqueta} ({len(sel)})"))
        if poco.any():
            uni[poco].plot(ax=ax, facecolor=SUPERFICIE, edgecolor="#c3c2b7", hatch="////", linewidth=0.3)
            handles.append(Patch(facecolor=SUPERFICIE, edgecolor="#c3c2b7", hatch="////",
                                 label=f"Menos de {BOSQUE_MINIMO_HA} ha de bosque ({int(poco.sum())})"))
        uni.dissolve().boundary.plot(ax=ax, color=TINTA_2, linewidth=0.8)
        # Rótulos: las unidades con más pérdida neta en hectáreas
        for _, fila in uni.nsmallest(a.etiquetar, "neto").iterrows():
            if not fila["neto"] < 0:
                continue
            pt = fila.geometry.representative_point()
            ax.annotate(f"{fila[a.campo_unidad]}\n{fila['neto']:,.0f} ha", (pt.x, pt.y), ha="center",
                        va="center", fontsize=7.5, color=TINTA,
                        path_effects=[pe.withStroke(linewidth=2.5, foreground=SUPERFICIE)])
        ax.set_xlim(izq, der)
        ax.set_ylim(abajo, arriba)
        ax.set_axis_off()
        ax.set_title("Cambio neto de bosque por unidad (% de su bosque base); rótulos: mayor pérdida en ha",
                     loc="left", fontsize=10, color=TINTA_2)
        ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0, 0), ncol=3, fontsize=8.5,
                  frameon=False, labelcolor=TINTA)

    neto = tot.bosque_actual_ha - tot.bosque_base_ha
    zona = f" · {a.titulo}" if a.titulo else ""
    fig.suptitle(f"Masa forestal {anio_base} → {anio}{zona} (prototipo)", x=0.01, ha="left",
                 fontsize=15, color=TINTA)
    fig.text(0.01, 0.935 if dos else 0.94,
             f"Bosque {tot.bosque_base_ha:,.0f} → {tot.bosque_actual_ha:,.0f} ha ({neto:+,.0f} ha, "
             f"{neto / tot.bosque_base_ha * 100:+.1f} %).  Sentinel-2 L2A nov-dic; bosque = NDVI ≥ "
             f"{umbral:.2f} dentro de la zona forestal INEGI Serie VII; cambio mínimo de NDVI 0.10; "
             f"quemado = dNBR ≥ 0.27.  Contiene datos modificados de Copernicus Sentinel {anio_base}–{anio}; "
             "Fuente: INEGI, CONAFOR.", fontsize=8.5, color=TINTA_2, wrap=True)
    fig.get_layout_engine().set(rect=(0, 0, 1, 0.92))
    fig.savefig(salida, dpi=150, facecolor=SUPERFICIE)
    print(f"Mapa en {salida.resolve()}")


if __name__ == "__main__":
    main()
