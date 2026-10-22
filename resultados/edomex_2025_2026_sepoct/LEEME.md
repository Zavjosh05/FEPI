# Estado de México, preliminar 2026 (septiembre-octubre)

Compara del 1 de septiembre al 20 de octubre de 2025 con lo mismo de 2026, las imágenes más
recientes que había. Se corrió con `--bloques` el 21 de octubre de 2026.

> **Preliminar.** Es otra temporada que la de los balances anuales (noviembre-diciembre) y usa su
> propio umbral, así que sus hectáreas no se comparan ni se suman con las de esos balances.

| Archivo | Qué es |
|---|---|
| `balance_2025_2026.csv` | Balance de los 125 municipios (hectáreas) |
| `cambio_2025_2026.tif` | uint8: 0 sin bosque, 1 estable, 2 pérdida por incendio, 3 otra pérdida, 4 ganancia |
| `bloques_2025_2026.csv` | Cada bloque: escenas, segundos y RAM pico |
| `corrida_2025_2026.json` | Parámetros de la corrida |

## Comando

```bash
python src/prototipo_masa_forestal.py correr --aoi datos/edomex/estado_mexico.gpkg \
  --anio-base 2025 --anio 2026 --ventana 09-01 10-20 --umbral-ndvi auto \
  --zona-forestal datos/edomex/usv_serie7_edomex.gpkg \
  --incendios datos/edomex/incendios_conafor_edomex.gpkg \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
  --bloques --salida resultados/edomex_2025_2026_sepoct
```

## Parámetros y resultados

- **Imágenes:** 1-sep al 20-oct de 2025 (122 escenas) y de 2026 (108).
- **Umbral:** automático (Otsu sobre septiembre-octubre de 2025); salió 0.51.
- **Bosque:** 434,687 → 431,826 ha (−2,861, −0.7 %). Otras pérdidas: 20,758 ha. Ganancia:
  17,897 ha.
- **Incendios:** no hay polígonos de 2025 ni de 2026, así que toda la pérdida aparece como
  "otras pérdidas".
- **Cautela:**
  - Las pérdidas y ganancias son de 3 a 5 veces las de noviembre-diciembre. Es el final de las
    lluvias: más nubes y sombras, y vegetación que cambia de verdor.
  - Algunos municipios se ven exagerados: Valle de Bravo daría −2,986 ha (−13.6 %), Tlalmanalco
    −1,540 y Zinacantepec −1,407.
  - Sirve para ver dónde revisar, no como cifra final.
- **Tiempo:** 25 min. RAM pico: 4.0 GB.
