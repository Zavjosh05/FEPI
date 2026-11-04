#!/usr/bin/env python3
"""
Muestra estratificada de puntos para fotointerpretar (CF-DEV-09)
================================================================

Sortea puntos dentro de la zona forestal, repartidos por estratos que salen del ráster de
cambio del prototipo y del ráster de coincidencia de `validar_hansen.py`. El CSV queda listo
para que alguien marque cada punto viendo imágenes (Sentinel-2 nov-dic, Google Earth, etc.) y
luego se use con `prototipo_masa_forestal.py calibrar --puntos`, que lee `lon`, `lat` y `clase`.

**Este script no etiqueta nada:** la columna `clase` sale vacía. Hay que llenarla con 1 (bosque)
o 0 (no bosque) en nov-dic del año `--anio-clase`, y borrar los renglones que no se puedan
interpretar antes de correr `calibrar` (un valor vacío se leería como bosque).

Estratos (cada píxel de 10 m cae en uno solo):

| Estrato | Qué es |
|---|---|
| bosque_estable | bosque en los dos años según el prototipo, sin pérdida de Hansen |
| perdida_incendio | pérdida por incendio del prototipo (clase 2) |
| otra_perdida_con_hansen | otra pérdida (clase 3) que Hansen también marca |
| otra_perdida_solo_prototipo | otra pérdida (clase 3) que Hansen no marca |
| perdida_solo_hansen | pérdida de Hansen donde el prototipo no ve pérdida |
| ganancia | ganancia del prototipo (clase 4) |
| sin_bosque_en_zona | zona forestal sin bosque en ninguno de los dos años |

Se sortea el mismo número de puntos por estrato (`--por-estrato`), así los estratos raros, que
son justo los que interesan, también quedan representados. `estratos_<periodo>.csv` guarda la
superficie de cada estrato para poder ponderar después (estimador estratificado): un punto de un
estrato chico "vale" menos hectáreas que uno de un estrato grande.

Uso (desde la raíz; antes hay que correr src/validar_hansen.py):
    python src/muestra_puntos.py
    python src/muestra_puntos.py --por-estrato 20 --semilla 7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SIN_BOSQUE, ESTABLE, PERD_INCENDIO, PERD_OTRA, GANANCIA = 0, 1, 2, 3, 4   # ráster de cambio
FUERA, ZONA, AMBOS, SOLO_PROTO, SOLO_HANSEN = 0, 1, 2, 3, 4               # ráster de coincidencia

ESTRATOS = ["bosque_estable", "perdida_incendio", "otra_perdida_con_hansen",
            "otra_perdida_solo_prototipo", "perdida_solo_hansen", "ganancia", "sin_bosque_en_zona"]


def estratos(cam: np.ndarray, coin: np.ndarray) -> np.ndarray:
    """0 = fuera de la muestra; 1..7 = posición en ESTRATOS + 1."""
    e = np.zeros(cam.shape, dtype=np.uint8)
    zona = coin != FUERA
    e[zona & (cam == ESTABLE)] = 1
    e[zona & (cam == SIN_BOSQUE)] = 7
    e[zona & (coin == SOLO_HANSEN)] = 5          # antes que ganancia/estable: lo marca Hansen
    e[cam == PERD_INCENDIO] = 2
    e[(cam == PERD_OTRA) & (coin == AMBOS)] = 3
    e[(cam == PERD_OTRA) & (coin != AMBOS)] = 4
    e[(cam == GANANCIA) & (coin != SOLO_HANSEN)] = 6
    return e


def main():
    p = argparse.ArgumentParser(description="Muestra estratificada de puntos para fotointerpretar")
    p.add_argument("--cambio", default="resultados/edomex_2023_2024/cambio_2023_2024.tif")
    p.add_argument("--coincidencia", help="ráster de validar_hansen.py (por defecto el del mismo periodo)")
    p.add_argument("--por-estrato", type=int, default=15, help="puntos por estrato (7 estratos)")
    p.add_argument("--anio-clase", type=int, help="año que describe la columna clase (por defecto el final)")
    p.add_argument("--semilla", type=int, default=2026)
    p.add_argument("--filas-bloque", type=int, default=2048)
    p.add_argument("--salida", default="resultados/validacion_hansen")
    p.add_argument("--sobrescribir", action="store_true")
    a = p.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    import rasterio
    from rasterio.windows import Window
    from rasterio.warp import transform as transformar

    periodo = Path(a.cambio).stem.removeprefix("cambio_")
    anio_base, anio = (int(x) for x in periodo.split("_"))
    anio_clase = a.anio_clase or anio
    coin_ruta = a.coincidencia or str(Path(a.salida) / f"coincidencia_{periodo}.tif")
    out = Path(a.salida)
    ruta_csv = out / f"muestra_puntos_{periodo}.csv"
    if ruta_csv.exists() and not a.sobrescribir:
        sys.exit(f"{ruta_csv} ya existe; usa --sobrescribir (cambia la muestra) u otra --salida.")
    if not Path(coin_ruta).exists():
        sys.exit(f"No existe {coin_ruta}; primero corre src/validar_hansen.py")

    with rasterio.open(a.cambio) as sc, rasterio.open(coin_ruta) as so:
        if sc.shape != so.shape or sc.transform != so.transform:
            sys.exit("El ráster de cambio y el de coincidencia no tienen la misma malla.")
        alto, ancho, paso = sc.height, sc.width, a.filas_bloque
        ventanas = [Window(0, r0, ancho, min(paso, alto - r0)) for r0 in range(0, alto, paso)]

        def leer(w):
            return estratos(sc.read(1, window=w), so.read(1, window=w))

        # 1.ª pasada: cuántos píxeles tiene cada estrato en cada franja
        cuentas = np.zeros((len(ventanas), len(ESTRATOS) + 1), dtype=np.int64)
        for i, w in enumerate(ventanas):
            cuentas[i] = np.bincount(leer(w).ravel(), minlength=len(ESTRATOS) + 1)
        total = cuentas.sum(axis=0)

        # Sorteo: para cada estrato, qué píxeles (por su número de orden dentro del estrato)
        rng = np.random.default_rng(a.semilla)
        elegidos = {}
        for k in range(1, len(ESTRATOS) + 1):
            m = min(a.por_estrato, int(total[k]))
            elegidos[k] = np.sort(rng.choice(total[k], size=m, replace=False)) if m else np.array([], int)

        # 2.ª pasada: ubicar los píxeles sorteados
        filas = []
        acum = np.zeros(len(ESTRATOS) + 1, dtype=np.int64)
        for i, w in enumerate(ventanas):
            e = leer(w)
            for k in range(1, len(ESTRATOS) + 1):
                sel = elegidos[k][(elegidos[k] >= acum[k]) & (elegidos[k] < acum[k] + cuentas[i, k])] - acum[k]
                if len(sel):
                    planos = np.flatnonzero(e.ravel() == k)[sel]
                    for r, c in zip(*np.unravel_index(planos, e.shape)):
                        x, y = sc.transform * (c + 0.5, w.row_off + r + 0.5)
                        filas.append({"estrato": ESTRATOS[k - 1], "x_utm": x, "y_utm": y})
            acum += cuentas[i]
        crs = sc.crs

    t = pd.DataFrame(filas)
    lon, lat = transformar(crs, "EPSG:4326", t["x_utm"].tolist(), t["y_utm"].tolist())
    t["lon"], t["lat"] = np.round(lon, 6), np.round(lat, 6)
    bosque_base = t["estrato"].isin(["bosque_estable", "perdida_incendio", "otra_perdida_con_hansen",
                                     "otra_perdida_solo_prototipo"])
    bosque_act = t["estrato"].isin(["bosque_estable", "ganancia"])
    t[f"prototipo_bosque_{anio_base}"] = bosque_base.astype(int)
    t[f"prototipo_bosque_{anio}"] = bosque_act.astype(int)
    # Los de "solo Hansen" pueden ser bosque estable o sin bosque para el prototipo
    t.loc[t["estrato"] == "perdida_solo_hansen", [f"prototipo_bosque_{anio_base}", f"prototipo_bosque_{anio}"]] = -1
    t = t.sample(frac=1, random_state=a.semilla).reset_index(drop=True)  # orden al azar: sin pistas al interpretar
    t.insert(0, "id", np.arange(1, len(t) + 1))
    t["clase"] = ""
    t["notas"] = ""
    cols = ["id", "lon", "lat", "clase", "notas", "estrato", f"prototipo_bosque_{anio_base}",
            f"prototipo_bosque_{anio}", "x_utm", "y_utm"]
    out.mkdir(parents=True, exist_ok=True)
    t[cols].to_csv(ruta_csv, index=False)

    resumen = pd.DataFrame({"estrato": ESTRATOS, "superficie_ha": total[1:] * 0.01,
                            "puntos": [len(elegidos[k]) for k in range(1, len(ESTRATOS) + 1)]})
    resumen["ha_por_punto"] = resumen["superficie_ha"] / resumen["puntos"].replace(0, np.nan)
    resumen.to_csv(out / f"estratos_{periodo}.csv", index=False, float_format="%.2f")
    print(resumen.to_string(index=False))
    print(f"\n{len(t)} puntos en {ruta_csv}")
    print(f"Llenar 'clase' con 1 (bosque) o 0 (no bosque) en nov-dic {anio_clase}; los de "
          f"prototipo_bosque_* = -1 dependen de lo que se vea. Luego:\n"
          f"  python src/prototipo_masa_forestal.py calibrar --aoi <zona> --anio {anio_clase} "
          f"--puntos {ruta_csv.as_posix()} --salida {out.as_posix()}\n"
          "Ojo: calibrar arma el compuesto NDVI de toda la --aoi de una sola vez; con el estado entero "
          "no cabe en memoria. Hasta que lea por bloques, usar una --aoi más chica (los puntos fuera "
          "de ella se ignoran).")


if __name__ == "__main__":
    main()
