# Estado de México, preliminar 2026 (septiembre-octubre)

Compara del 1 de septiembre al 20 de octubre de 2025 con lo mismo de 2026, las imágenes más
recientes que había. Se corrió con `--bloques` el 4 de noviembre de 2026, con la zona forestal
ampliada y el clasificador del destino (versión 0.6.0, commit 2286a7e; `correr` de 0.7.0 da las
mismas salidas).

> **Preliminar.** Es otra temporada que la de los balances anuales (noviembre-diciembre) y usa su
> propio umbral, así que sus hectáreas no se comparan ni se suman con las de esos balances.

| Archivo | Qué es |
|---|---|
| `balance_2025_2026.csv` | Balance de los 125 municipios (hectáreas) |
| `cambio_2025_2026.tif` | uint8: 0 sin bosque, 1 estable, 2 pérdida por incendio, 3 otra pérdida, 4 ganancia |
| `vegetacion_2025_2026.csv`, `tipo_bosque_2025_2026.csv` | Desglose por clave de la Serie VII y por tipo de bosque |
| `destino_perdidas_2025_2026.csv`, `destino_2025_2026.tif` | Uso al que pasaron las otras pérdidas (0 no aplica, 1 agrícola, 2 pecuario, 3 urbano, 4 otro, 5 sin dato) |
| `destino_exactitud_2025_2026.csv` | Exactitud del clasificador con las muestras reservadas |
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

- **Zona forestal:** `^(B|S|M|VSA/)`, 512,576 ha (antes `^(B|VSA/)`, 484,695 ha).
- **Imágenes:** 1-sep al 20-oct de 2025 (122 escenas) y de 2026 (108).
- **Umbral:** automático (Otsu sobre septiembre-octubre de 2025); salió 0.51.
- **Bosque:** 458,667 → 454,334 ha (−4,332, −0.9 %). Otras pérdidas: 22,475 ha. Ganancia:
  18,143 ha. Por tipo: coníferas −3,596, zonas semiáridas −1,360, otro −761, selva baja −40,
  encino +626, mesófilo +797.
- **Incendios:** no hay polígonos de 2025 ni de 2026, así que toda la pérdida aparece como
  "otras pérdidas".
- **Destino de las otras pérdidas:** agrícola 9,859 ha, pecuario 4,945, urbano 1,779, otro 5,892.
  Exactitud del clasificador 52.3 % (kappa 0.35, 7,507 muestras reservadas): confunde sobre todo
  pecuario con agrícola y con otro. Es acuerdo con la Serie VII, no verificación de campo.
- **Cautela:**
  - Las pérdidas y ganancias son de 3 a 5 veces las de noviembre-diciembre. Es el final de las
    lluvias: más nubes y sombras, y vegetación que cambia de verdor.
  - Algunos municipios se ven exagerados: Valle de Bravo daría −2,986 ha (−13.6 %), Tlalmanalco
    −1,540 (−19.9 %), Zinacantepec −1,407 y Amecameca −783.
  - Sirve para ver dónde revisar, no como cifra final.
- **Contra la corrida anterior (zona `^(B|VSA/)`, 21-oct-2026):** 434,687 → 431,826 ha
  (−2,861). Las claves nuevas agregan 23,981 ha de bosque base: selva baja caducifolia 13,696 y
  matorral crasicaule 10,156 (al final de las lluvias el matorral sí pasa el umbral; en
  noviembre-diciembre casi no). También agregan 1,472 ha de pérdida neta, casi toda de matorral
  (−1,356), que pierde verdor al secarse. Esa corrida está en
  `resultados/anteriores_0.5/edomex_2025_2026_sepoct/`.
- **Tiempo:** 52 min (con otra corrida estatal en paralelo). RAM pico: 4.1 GB.
