# Piloto: Amecameca y Tlalmanalco, 2023 → 2024

## Contenido

| Archivo | Qué es |
|---|---|
| `balance_2023_2024.csv` | Balance por municipio (hectáreas) |
| `incendios_dnbr.csv` | Cada incendio: superficie que reporta CONAFOR contra lo quemado según el dNBR |
| `cambio_2023_2024.tif` | 0 sin bosque, 1 estable, 2 pérdida por incendio, 3 otra pérdida, 4 ganancia |
| `ndvi_2023.tif`, `ndvi_2024.tif`, `dnbr.tif` | Índices en enteros int16: valor real = valor × 0.0001; sin dato = −32768. (El script actual los guarda como float32.) |
| `mapa_cambio_2023_2024.png` | Mapa del cambio |

Los datos de entrada están en [`datos/piloto/`](../../datos/piloto/):

- `piloto_municipios.gpkg`: límites municipales (IDEFOR, capa `municipios`).
- `incendios_piloto_2024.gpkg`: polígonos de incendio CONAFOR 2024 que tocan la zona.
- `usv7_piloto.geojson`: INEGI Uso de suelo y vegetación Serie VII (vía IDEFOR).

## Comando usado

Desde la raíz del repositorio:

```bash
python src/prototipo_masa_forestal.py correr --aoi datos/piloto/piloto_municipios.gpkg \
  --anio-base 2023 --anio 2024 --umbral-ndvi auto --margen-cambio 0.10 \
  --zona-forestal datos/piloto/usv7_piloto.geojson \
  --incendios datos/piloto/incendios_piloto_2024.gpkg \
  --unidades datos/piloto/piloto_municipios.gpkg --campo-unidad NOM_MUN \
  --salida resultados/piloto_2023_2024
```

## Parámetros

- **Imágenes:** Sentinel-2 L2A Colección 1 (Earth Search, AWS), tesela 14QNG. 7 escenas en nov-dic 2023 y 18 en nov-dic 2024.
- **Bosque:** NDVI ≥ 0.50 (Otsu, **provisional** hasta calibrar con puntos de referencia), dentro de las clases forestales de la Serie VII (claves `B*` y `VSA/*`).
- **Cambio:** solo cuenta si el NDVI cambió al menos 0.10, además de cruzar el umbral.
- **Quemado:** dNBR ≥ 0.27 (moderada-baja o mayor, USGS). Ventanas: 75–5 días antes y 10–70 días después.
- **Periodo de incendios:** del 1-nov-2023 al 31-oct-2024. El incendio 24-15-1259 (27-dic-2024) queda para el periodo siguiente. No hubo incendios en nov-dic 2023 dentro de la zona, así que usar solo la capa 2024 no dejó nada fuera.

## Abrir en QGIS

Arrastrar los `.tif` y `.gpkg`. Los rásters están en EPSG:32614 (UTM 14N) y los vectores de IDEFOR en EPSG:4326; QGIS los reproyecta solo.
