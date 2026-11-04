# Estado de México, 2023 → 2025

Balance de dos años de noviembre-diciembre, corrido directo (no sumando periodos) con `--bloques`
el 22 de octubre de 2026.

| Archivo | Qué es |
|---|---|
| `balance_2023_2025.csv` | Balance de los 125 municipios (hectáreas) |
| `incendios_dnbr.csv` | Los 1,092 incendios del 1-nov-2023 al 31-oct-2025 |
| `cambio_2023_2025.tif` | uint8: 0 sin bosque, 1 estable, 2 pérdida por incendio, 3 otra pérdida, 4 ganancia |
| `bloques_2023_2025.csv` | Cada bloque: escenas, segundos y RAM pico |
| `corrida_2023_2025.json` | Parámetros de la corrida |

## Comando

```bash
python src/prototipo_masa_forestal.py correr --aoi datos/edomex/estado_mexico.gpkg \
  --anio-base 2023 --anio 2025 --umbral-ndvi 0.51 \
  --zona-forestal datos/edomex/usv_serie7_edomex.gpkg \
  --incendios datos/edomex/incendios_conafor_edomex.gpkg \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
  --bloques --salida resultados/edomex_2023_2025
```

## Parámetros y resultados

- **Imágenes:** nov-dic 2023 (115 escenas) y nov-dic 2025 (202).
- **Umbral:** NDVI 0.51 fijo.
- **Bosque:** 459,262 → 454,634 ha (−4,628, −1.0 %). Pérdida por incendio: 245 ha. Otras
  pérdidas: 7,329 ha. Ganancia: 2,946 ha.
- **Incendios:** solo hay polígonos hasta 2024. La pérdida por incendio (245 ha) es menor que en
  2023 → 2024 (708 ha) porque parte de lo quemado en 2024 ya recuperó copa en 2025.
- **Coherencia:** parte del mismo bosque de 2023 que 2023 → 2024 (459,262 ha). Su cambio neto
  (−4,628 ha) casi iguala la suma de los dos periodos de un año (−5,812 + 1,182 = −4,630 ha).
- **Tiempo:** 43 min, con los 1,092 incendios en paralelo. RAM pico: 4.6 GB.
