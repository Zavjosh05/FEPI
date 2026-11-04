# Estado de México, serie anual 2023 → 2024 → 2025

Serie de tres años de noviembre-diciembre, con el bosque encadenado año con año (`serie`, versión
0.7.0). Se corrió con `--bloques` el 4 de noviembre de 2026, con la zona forestal ampliada y el
clasificador del destino. Reemplaza las tres corridas directas de la zona anterior, que están en
`resultados/anteriores_0.5/`.

| Archivo | Qué es |
|---|---|
| `serie_2023_2025.csv` | Una fila por municipio, año y tipo de bosque (`Todos` es la suma): bosque, pérdidas, ganancia, destino y `bosque_sin_encadenar_ha` |
| `tendencia_2023_2025.csv` | Tendencia por mínimos cuadrados (ha/año, %/año, R²) por municipio y tipo; `Total` es el estado |
| `balance_<a>_<b>.csv` | Balance de cada comparación: 2023_2024, 2024_2025 y 2023_2025 |
| `cambio_<a>_<b>.tif` | uint8: 0 sin bosque, 1 estable, 2 pérdida por incendio, 3 otra pérdida, 4 ganancia |
| `vegetacion_<a>_<b>.csv`, `tipo_bosque_<a>_<b>.csv` | Desglose por clave de la Serie VII y por tipo de bosque |
| `destino_perdidas_<a>_<b>.csv`, `destino_<a>_<b>.tif` | Uso al que pasaron las otras pérdidas (0 no aplica, 1 agrícola, 2 pecuario, 3 urbano, 4 otro, 5 sin dato) |
| `destino_exactitud_2023_2024.csv`, `destino_exactitud_2024_2025.csv` | Exactitud del clasificador de cada año con las muestras reservadas |
| `bosque_por_anio.tif` | uint8: bit 0 = bosque en 2023, bit 1 = 2024, bit 2 = 2025 |
| `anio_perdida.tif` | uint8: año − 2000 de la última vez que el píxel dejó de ser bosque (24 o 25); 0 sin pérdida |
| `incendios_dnbr.csv` | Los 1,092 incendios con su columna `periodo` (1,085 de 2023_2024 y 7 de 2024_2025) |
| `incendios_dnbr_2023_2025.csv` | Los mismos incendios medidos contra el bosque de 2023 y de 2025 |
| `bloques_2023_2025.csv` | Cada bloque: escenas de cada año, segundos y RAM pico |
| `corrida_<a>_<b>.json`, `serie_2023_2025.json` | Parámetros y exactitud del clasificador |

## Comando

```bash
python src/prototipo_masa_forestal.py serie --aoi datos/edomex/estado_mexico.gpkg \
  --anios 2023 2024 2025 --umbral-ndvi 0.51 \
  --zona-forestal datos/edomex/usv_serie7_edomex.gpkg \
  --incendios datos/edomex/incendios_conafor_edomex.gpkg \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
  --bloques --salida resultados/edomex_serie_2023_2025
```

## Parámetros

- **Zona forestal:** `^(B|S|M|VSA/)`, 512,576 ha y 22 claves (antes `^(B|VSA/)`, 484,695 ha).
- **Imágenes:** nov-dic de 2023 (115 escenas), 2024 (213) y 2025 (202).
- **Umbral:** NDVI 0.51 fijo, el mismo de las corridas anteriores. Margen de cambio 0.10.
- **Incendios:** 1,085 del 1-nov-2023 al 31-oct-2024 y 7 del 1-nov-2024 al 31-oct-2025 (solo los
  de nov-dic de 2024: no hay capa de 2025).
- **Tiempo:** 1 h 59 min (84 bloques de ~68 s y los incendios en paralelo). RAM pico: 4.8 GB.

## Resultados

| | 2023 | 2024 | 2025 |
|---|---|---|---|
| Bosque | 473,148 ha | 467,955 | 466,058 |
| Pérdida por incendio | | 711 | 0 |
| Otras pérdidas | | 9,436 | 6,080 |
| Ganancia | | 4,954 | 4,183 |
| Cambio neto | | −5,194 (−1.1 %) | −1,897 (−0.4 %) |
| Bosque sin encadenar (solo el umbral) | 473,148 | 465,430 | 463,713 |

- **2023 → 2025:** −7,091 ha (−1.5 %). Pérdida por incendio 361 ha, otras 11,475, ganancia 4,745.
  Como el bosque está encadenado, el cambio directo es exactamente la suma de los dos años
  (−5,194 − 1,897 = −7,091).
- **Tendencia del estado:** −3,545 ha/año (−0.75 %/año, R² 0.93 con 3 puntos).
- **Por tipo de bosque** (2023 → 2025, ha/año): selva baja caducifolia −2,645 (−6.5 %/año),
  coníferas −764, encino −749, mesófilo −25, otro +26 y zonas semiáridas +612 (el matorral pasa
  de 1,139 a 3,297 y 2,363 ha: casi no llega al umbral en nov-dic y oscila mucho).
- **Municipios con más pérdida** (tendencia): Luvianos −1,662 ha/año (−6.9 %), Otzoloapan −449
  (−9.4 %), Santo Tomás −334 (−13.8 %), Tlatlaya −311 y Ocuilan −188. Los cuatro primeros son de
  selva baja caducifolia.
- **Destino de las otras pérdidas:**

  | | Agrícola | Pecuario | Urbano | Otro |
  |---|---|---|---|---|
  | 2023 → 2024 | 2,834 ha | 4,921 | 432 | 1,250 |
  | 2024 → 2025 | 1,195 | 3,124 | 272 | 1,490 |

  Un clasificador por año. Exactitud con las muestras reservadas: 54.9 % (kappa 0.39, 7,500
  muestras) y 54.6 % (kappa 0.39, 7,471). Urbano es la clase que mejor separa (productor 68 %);
  pecuario la peor (43–44 %), confundida con agrícola y con otro. Es acuerdo con la Serie VII, no
  verificación de campo.

### Selva baja caducifolia

Pierde 3,154 ha en 2023 → 2024 (7.8 % de sus 40,394 ha) y 2,654 en 2024 → 2025 (7.1 %), y casi
no gana (172 y 354 ha). La clave SBC sola pierde 12 % y 17 %. Se concentra en Luvianos (3,274 ha en
los dos años), Otzoloapan (896), Tlatlaya (796) y Santo Tomás (648). Hansen casi no ve pérdida
ahí: en Luvianos la precisión es de 1 % en 2024 y 0.1 % en 2025 (ver
`resultados/validacion_hansen/`). Lo más probable es la caída de hojas en nov-dic, que cambia de
fecha cada año, y no pérdida real. Falta decidir cómo tratarla: otra ventana para la selva, un
umbral propio o dejarla fuera de la zona.

## Diferencias con las corridas directas anteriores

Dentro de la zona anterior (`^(B|VSA/)`), la comparación 2023 → 2024 da **idéntico** a
`anteriores_0.5/edomex_2023_2024` (459,262 → 453,450 ha; incendio 708, otras 7,788, ganancia
2,684): con dos años encadenar no cambia nada.

Las otras dos sí cambian, porque ahora 2024 y 2025 parten del año anterior:

| Zona anterior | Corrida directa | Serie encadenada |
|---|---|---|
| Bosque 2024 en 2024 → 2025 | 450,768 ha (solo el umbral) | 453,450 (el mismo de 2023 → 2024) |
| 2024 → 2025 | +1,182 (otras 3,336, ganancia 4,519) | +826 (otras 3,253, ganancia 4,079) |
| 2023 → 2025 | 454,634 (−4,628) | 454,276 (−4,986) |

Antes el 2024 tenía dos valores: 453,450 ha como año actual de 2023 → 2024 y 450,768 como año base
de 2024 → 2025. Con la serie, cada año tiene un solo valor en todas las comparaciones y los
cambios se suman exactamente. La diferencia entre el bosque encadenado y el de solo el umbral
(`bosque_sin_encadenar_ha`) es de 2,525 ha en 2024 y 2,345 en 2025 (0.5 %): son píxeles cerca del
umbral cuyo NDVI no cambió 0.10.

La zona ampliada agrega en 2023 12,748 ha de SBC, 1,062 de MC y 76 de MDR (13,886 ha en total).
