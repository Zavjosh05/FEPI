# Estado de México, 2023 → 2024

Primera corrida del balance para todo el estado, con `--bloques`, el 14–15 de octubre de 2026.

## Contenido

| Archivo | Qué es |
|---|---|
| `balance_2023_2024.csv` | Balance de los 125 municipios (hectáreas); 91 tienen bosque |
| `incendios_dnbr.csv` | Los 1,085 incendios del periodo: superficie del polígono contra lo quemado según el dNBR |
| `cambio_2023_2024.tif` | uint8: 0 sin bosque, 1 estable, 2 pérdida por incendio, 3 otra pérdida, 4 ganancia (EPSG:32614) |
| `bloques_2023_2024.csv` | Cada bloque: escenas, segundos y RAM pico |

No se guardaron los rásters de NDVI ni de dNBR; pesarían ~1.5 GB cada uno.

## Comando usado

Desde la raíz del repositorio, con las capas de `datos/edomex/` (ver `src/descargar_capas.py`):

```bash
python src/prototipo_masa_forestal.py correr --aoi datos/edomex/estado_mexico.gpkg \
  --anio-base 2023 --anio 2024 --umbral-ndvi auto \
  --zona-forestal datos/edomex/usv_serie7_edomex.gpkg \
  --incendios datos/edomex/incendios_conafor_edomex.gpkg \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
  --bloques --salida resultados/edomex_2023_2024
```

## Parámetros

- **Imágenes:** Sentinel-2 L2A Colección 1 (Earth Search) en 9 teselas (14QLF, 14QLG, 14QLH,
  14QMF, 14QMG, 14QMH, 14QNF, 14QNG, 14QNH). 115 escenas en nov-dic 2023 y 213 en nov-dic 2024.
- **Bloques:** 84 de los 144 del rectángulo tocan el estado. Miden 2,048 px (20.48 km) y están
  alineados a la malla interna de los COG.
- **Bosque:** NDVI ≥ 0.51 (Otsu sobre todo el estado, **provisional**), dentro de la zona
  forestal de la Serie VII (484,692 ha). El margen de cambio es 0.10.
- **Quemado:** dNBR ≥ 0.27. Incendios del 1-nov-2023 al 31-oct-2024: 1,085. Los 7 posteriores
  quedan para el periodo siguiente.

## Resultados

| | Hectáreas |
|---|---|
| Bosque 2023 | 459,262 |
| Pérdida por incendio | 708 |
| Otras pérdidas (por verificar) | 7,788 |
| Ganancia | 2,684 |
| **Bosque 2024** | **453,450** (−5,812, −1.3 %) |

- **Incendios:** 52,325 ha de polígonos CONAFOR. De ellas, 16,214 ha tienen dNBR ≥ 0.27; 8,388 ha
  estaban en bosque, y 708 ha seguían sin copa al cierre. En 258 incendios el dNBR no detectó nada
  quemado.
- **Mayor pérdida neta:**

  | Municipio | Hectáreas |
  |---|---|
  | Tlatlaya | −633 |
  | Luvianos | −590 |
  | Atlautla | −461 |
  | Ocuilan | −440 |
  | Temascaltepec | −404 |
  | Santo Tomás | −378 (19 % de su bosque) |
  | Tejupilco | −324 |
  | Amecameca | −230 |

  Casi todo son "otras pérdidas", que están **por verificar** (tala, plaga, nieve o ruido).
- **Mayor pérdida por incendio:** Tejupilco (93 ha), Jilotzingo (66), Valle de Bravo (63),
  Tlatlaya (59) y Amecameca (51).
- **El umbral automático depende de la zona que se corre.** Con 0.51 (estado) contra 0.50 (piloto),
  Amecameca da 7,051 ha de bosque base en lugar de 7,123. Además, aquí sus píxeles pueden usar
  escenas de las teselas vecinas. Para comparar corridas conviene fijar un umbral numérico.

## Tiempo y recursos

- **Tiempo:** arrancó a las 23:09 y escribió los resultados a la 01:18, unas 2 h 08 min. Los
  bloques sumaron 34 min (mediana de 23 s, máximo 53 s con 60 + 113 escenas); los incendios, el
  resto.
- **RAM pico:** 4.2 GB, incluidos los 0.83 GB del umbral automático.
- **Disco:** ~3 MB de resultados.
- **Suspensión:** el equipo entró en suspensión moderna (Modern Standby) a las 00:44, con la
  pantalla apagada, aunque el proceso había pedido no suspender. Siguió avanzando y terminó a la
  01:18, pero el proceso no se cerró hasta que el equipo despertó a las 03:19.

## Abrir en QGIS

Arrastrar `cambio_2023_2024.tif` (EPSG:32614) y `datos/edomex/municipios_edomex.gpkg`.
`balance_2023_2024.csv` se puede unir a los municipios por `NOM_MUN`.
