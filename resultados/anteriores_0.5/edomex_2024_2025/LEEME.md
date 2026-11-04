# Estado de México, 2024 → 2025

Balance más reciente de noviembre-diciembre, corrido con `--bloques` el 21 de octubre de 2026.

| Archivo | Qué es |
|---|---|
| `balance_2024_2025.csv` | Balance de los 125 municipios (hectáreas) |
| `incendios_dnbr.csv` | Los 7 incendios de nov-dic 2024 que caen en el periodo |
| `cambio_2024_2025.tif` | uint8: 0 sin bosque, 1 estable, 2 pérdida por incendio, 3 otra pérdida, 4 ganancia |
| `bloques_2024_2025.csv` | Cada bloque: escenas, segundos y RAM pico |
| `corrida_2024_2025.json` | Parámetros. Se escribió a mano a partir de la bitácora, porque esta corrida arrancó antes de que el script generara este archivo |

## Comando

```bash
python src/prototipo_masa_forestal.py correr --aoi datos/edomex/estado_mexico.gpkg \
  --anio-base 2024 --anio 2025 --umbral-ndvi 0.51 \
  --zona-forestal datos/edomex/usv_serie7_edomex.gpkg \
  --incendios datos/edomex/incendios_conafor_edomex.gpkg \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
  --bloques --salida resultados/edomex_2024_2025
```

## Parámetros y resultados

- **Imágenes:** nov-dic 2024 (213 escenas) y nov-dic 2025 (202), en 9 teselas.
- **Umbral:** NDVI 0.51 fijo, el mismo de 2023 → 2024, para que los dos periodos se puedan comparar.
- **Bosque:** 450,768 → 451,950 ha (+1,182, +0.3 %). Otras pérdidas: 3,336 ha. Ganancia: 4,519 ha.
- **Incendios:** CONAFOR todavía no publica los polígonos de 2025. Solo entran los 7 incendios
  de nov-dic 2024, que no dejaron pérdida de bosque. Lo que se quemó en la temporada de 2025 está
  dentro de "otras pérdidas".
- **Tiempo:** 49 min. RAM pico: 3.5 GB.
