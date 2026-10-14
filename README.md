# FEPI: Calculadora de masa forestal (PROBOSQUE)

Repositorio para la materia de FEPI. Contiene el prototipo de la **Calculadora de masa forestal**,
una propuesta para PROBOSQUE (Protectora de Bosques del Estado de México) dentro del levantamiento
de necesidades de sus programas 2026. La calculadora estima cómo cambia la superficie de bosque con
los incendios y las reforestaciones, usando imágenes satelitales y datos públicos de libre uso.

> **Estado: prototipo.** El umbral de NDVI es provisional (falta calibrarlo con puntos de
> referencia) y todavía no se tienen los polígonos de reforestación de los programas.

## Qué calcula

**Masa forestal = superficie con cobertura arbórea (ha)**, no biomasa. El balance se hace por
unidad (predio, municipio o Delegación):

```
bosque_actual = bosque_base − pérdida_por_incendio − otras_pérdidas + ganancia
```

- **Cobertura anual:** compuesto Sentinel-2 L2A (10 m) de noviembre-diciembre: ya pasaron las
  lluvias, las parcelas están secas y aún no empieza la temporada de incendios.
- **Bosque:** NDVI ≥ umbral **dentro de la zona forestal** de INEGI Serie VII (claves `B*` y `VSA/*`).
- **Cambio:** un píxel solo cambia de clase si, además de cruzar el umbral, su NDVI varió ≥ 0.10.
- **Quemado:** dNBR ≥ 0.27 (USGS, moderada-baja o mayor) dentro de los polígonos de incendio de
  CONAFOR. La pérdida en un píxel quemado se atribuye al incendio; si no, va a "otras pérdidas".
- **Reforestación:** recuperación **esperada** (polígonos de PS/RHF/CC × sobrevivencia) contra la
  **observada** por el satélite.

## Estructura

```
FEPI/
├── src/
│   ├── prototipo_masa_forestal.py   Calculadora (subcomandos demo, calibrar, correr)
│   └── descargar_capas.py           Descarga las capas del Estado de México desde IDEFOR
├── datos/
│   ├── piloto/                      Recortes usados en el piloto (versionados)
│   └── edomex/                      Capas estatales descargadas (no se versionan)
├── resultados/
│   └── piloto_2023_2024/            Salidas del piloto, con su LEEME.md
├── requirements.txt
├── CHANGELOG.md                     Registro de cambios
└── README.md
```

Las corridas nuevas conviene guardarlas en `resultados/<nombre>/`. Git las ignora, salvo el piloto.

## Instalación

Requiere Python 3.10 o superior (probado con 3.13 en Windows).

```bash
python -m venv .venv
.venv\Scripts\activate             # Windows (PowerShell o cmd)
# source .venv/bin/activate        # Linux o macOS
pip install -r requirements.txt
```

## Datos

**Imágenes Sentinel-2: no se descargan a mano.** El script las lee directo del catálogo
[Earth Search](https://earth-search.aws.element84.com/v1) (AWS Open Data), sin cuenta ni costo.
Solo necesita internet. Por ahora no hay caché: cada corrida vuelve a leer los píxeles.

**Capas vectoriales: deben estar en disco.** Para el piloto ya están en `datos/piloto/`. Las del
estado completo se bajan del WFS de [IDEFOR](https://idefor.cnf.gob.mx) (CONAFOR) con:

```bash
python src/descargar_capas.py
```

Tarda unos 4 minutos y deja en `datos/edomex/` (~23 MB):

| Archivo | Contenido |
|---|---|
| `estado_mexico.gpkg` | Límite estatal (INEGI 2025) |
| `municipios_edomex.gpkg` | 125 municipios (`NOM_ENT`, `NOM_MUN`) |
| `usv_serie7_edomex.gpkg` | INEGI Uso de suelo y vegetación Serie VII, recortada al estado (`CLAVE`, `DESCRIPCIO`) |
| `incendios_conafor_edomex.gpkg` | Incendios CONAFOR 2019–2024 que tocan el estado, en una sola capa (campo `ANIO_CAPA`). Un balance que cruza de año (1-nov a 31-oct) tiene así los incendios de ambos años |
| `descarga.json` | Fecha, capa de origen, filtro y número de polígonos de cada archivo |

Opciones: `--anios 2023 2024` para bajar solo algunos años de incendios y `--capas incendios`
para repetir solo una capa. IDEFOR todavía no publica la capa de incendios 2025.

Los **polígonos de reforestación** (PS, RHF, CC) son internos de PROBOSQUE y todavía no se tienen.

De dónde sale cada dato y en qué condiciones se puede usar: ver
[Fuentes de datos y licencias](#fuentes-de-datos-y-licencias).

## Uso

Todos los comandos se corren desde la raíz del repositorio, con el venv activado.

```bash
# 1. Probar la lógica con datos inventados (no descarga nada; el balance debe dar 516 ha)
python src/prototipo_masa_forestal.py demo

# 2. Calibrar el umbral de NDVI con un CSV lon,lat,clase (1 bosque, 0 no bosque)
python src/prototipo_masa_forestal.py calibrar --aoi zona.gpkg --anio 2024 --puntos puntos.csv

# 3. Repetir el piloto (unos 5 minutos)
python src/prototipo_masa_forestal.py correr --aoi datos/piloto/piloto_municipios.gpkg \
  --anio-base 2023 --anio 2024 --umbral-ndvi auto --margen-cambio 0.10 \
  --zona-forestal datos/piloto/usv7_piloto.geojson \
  --incendios datos/piloto/incendios_piloto_2024.gpkg \
  --unidades datos/piloto/piloto_municipios.gpkg --campo-unidad NOM_MUN \
  --salida resultados/piloto_2023_2024
```

Para otra zona, se usan las capas estatales y un polígono de la zona de interés. Por ejemplo, para
un municipio:

```bash
python -c "import geopandas as gpd; m = gpd.read_file('datos/edomex/municipios_edomex.gpkg'); m[m.NOM_MUN == 'Valle de Bravo'].to_file('datos/valle_de_bravo.gpkg')"

python src/prototipo_masa_forestal.py correr --aoi datos/valle_de_bravo.gpkg \
  --anio-base 2023 --anio 2024 --umbral-ndvi auto \
  --zona-forestal datos/edomex/usv_serie7_edomex.gpkg \
  --incendios datos/edomex/incendios_conafor_edomex.gpkg \
  --unidades datos/valle_de_bravo.gpkg --campo-unidad NOM_MUN \
  --salida resultados/valle_de_bravo_2023_2024
```

`--umbral-ndvi auto` usa el umbral de Otsu, que es provisional. Con un valor calibrado se pasa el
número (por ejemplo `--umbral-ndvi 0.55`). `python src/prototipo_masa_forestal.py correr -h` muestra
todas las opciones.

Salidas de `correr`: `balance_<base>_<actual>.csv`, `incendios_dnbr.csv`, `ndvi_<año>.tif`,
`dnbr.tif` y `cambio_<base>_<actual>.tif` (0 sin bosque, 1 estable, 2 pérdida por incendio,
3 otra pérdida, 4 ganancia). Todo está en EPSG:32614 (UTM 14N).

## Cobertura geográfica

El script **no tiene ninguna zona fija**: calcula sobre el polígono que se le pase en `--aoi`.
La proyección (UTM 14N) cubre todo el Estado de México y las capas de `datos/edomex/` cubren el
estado completo.

En la práctica, **solo se ha probado a escala municipal** (el piloto abarca dos municipios,
unas 34,000 ha). Correrlo de una vez sobre todo el estado (2.23 millones de ha) no es viable con
la versión actual:

- El rectángulo del estado a 10 m son ~450 millones de píxeles, y el script guarda cada capa
  completa en memoria: ~1.8 GB por capa de NDVI o dNBR, más las máscaras. Supera la RAM de un
  equipo de 16 GB.
- El estado abarca varias teselas Sentinel-2, que habría que releer en cada corrida porque no
  hay caché.
- Calcula el dNBR incendio por incendio: ~1,000 por año en el estado.

Mientras no se procese por bloques, lo recomendable es correr por municipio o por Delegación y
sumar los balances (las hectáreas se pueden sumar).

## Resultados del piloto (Amecameca y Tlalmanalco, 2023 → 2024)

| Municipio | Bosque 2023 | Pérdida por incendio | Otras pérdidas | Ganancia | Bosque 2024 |
|---|---|---|---|---|---|
| Amecameca | 7,123 ha | 50 | 223 | 50 | 6,900 |
| Tlalmanalco | 9,592 ha | 3 | 149 | 22 | 9,462 |

CONAFOR reportó 14 incendios con 1,810 ha en total. De ellas, 699 ha tienen dNBR ≥ 0.27; 225 ha
estaban en bosque, y solo 54 ha seguían sin copa al cierre. Las "otras pérdidas" están por
verificar (tala, plaga, nieve o ruido). Detalles en
[`resultados/piloto_2023_2024/LEEME.md`](resultados/piloto_2023_2024/LEEME.md).

## Pendientes

1. Calibrar el umbral de NDVI con ~100 puntos de referencia.
2. Conseguir los polígonos de reforestación de PS, RHF y CC, con año de plantación y sobrevivencia.
3. Caché de compuestos y procesamiento por bloques, para cubrir todo el estado.
4. Validar contra Hansen GFC y visitas de campo.
5. Escenarios de recuperación y un tablero para la Dirección General y las áreas responsables.

## Fuentes de datos y licencias

Ninguna fuente pide cuenta ni pago. Sus condiciones de uso son distintas:

| Dato | Quién lo produce | De dónde lo baja el proyecto | ¿Uso libre? |
|---|---|---|---|
| Imágenes Sentinel-2 L2A Colección 1 (NDVI, NBR) | ESA, programa Copernicus de la Unión Europea | Catálogo [Earth Search](https://earth-search.aws.element84.com/v1) de Element 84, con los archivos en el [Registry of Open Data de AWS](https://registry.opendata.aws/sentinel-2-l2a-cogs/) | **Sí.** Acceso libre, completo y abierto, incluso para uso comercial. Hay que citar la fuente (ver abajo) |
| Uso de suelo y vegetación, escala 1:250 000, Serie VII | INEGI | WFS de [IDEFOR](https://idefor.cnf.gob.mx), capa `cdv_usuev250svii_cnal_wgs84` | **Sí**, bajo los [Términos de Libre Uso de la Información del INEGI](https://www.inegi.org.mx/inegi/terminos.html). Hay que citar la fuente |
| Límite estatal (Áreas Geoestadísticas Estatales 2025) | INEGI | IDEFOR, capa `lim_estatal_inegi_2025` | **Sí**, mismos términos de INEGI |
| Límites municipales | No documentado: IDEFOR no publica metadatos de esta capa | IDEFOR, capa `municipios` | **Sin licencia declarada.** Para un uso formal conviene cambiarla por el Marco Geoestadístico de INEGI, que sí es de libre uso |
| Polígonos de incendios forestales ("Concentrado Nacional de Polígonos de Incendios Forestales", 2019–2024) | CONAFOR | IDEFOR, capas `_<año>_incendios_forestales` | **Públicos, pero sin licencia explícita.** IDEFOR los ofrece sin cuenta, pero sus metadatos dejan vacío el campo de restricciones. Para uso operativo, confirmar las condiciones con CONAFOR |
| Polígonos de reforestación (PS, RHF, CC) | PROBOSQUE | Internos; todavía no se tienen | **No.** Son información interna de PROBOSQUE |

**Créditos que se deben poner** al publicar mapas, tablas o datos derivados:

- Sentinel-2: `Contiene datos modificados de Copernicus Sentinel 2023–2024` (con los años
  usados). Así lo pide el
  [aviso legal de los datos Sentinel](https://sentinel.esa.int/documents/247904/690755/Sentinel_Data_Legal_Notice).
- INEGI: `Fuente: INEGI, Conjunto de datos vectoriales de uso del suelo y vegetación, escala
  1:250 000, serie VII`. También hay que aclarar que el análisis es propio y no una postura
  oficial del INEGI.
- CONAFOR: `Fuente: CONAFOR, Concentrado Nacional de Polígonos de Incendios Forestales <año>,
  vía IDEFOR`.

Los recortes de `datos/piloto/` se incluyen en el repositorio con esos mismos créditos.

No se usa Google Earth Engine, porque el uso gubernamental operativo requiere licencia comercial,
ni MODIS, porque Terra y Aqua se apagan en 2027.

## Licencia

El código está bajo la licencia MIT (ver [LICENSE](LICENSE)). Los datos no quedan bajo esa
licencia: cada uno conserva las condiciones de su fuente (ver la tabla anterior).
