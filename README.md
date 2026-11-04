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
- **Bosque:** NDVI ≥ umbral **dentro de la zona forestal** de INEGI Serie VII: bosques (`B*`),
  selva baja caducifolia (`SBC`), matorrales (`MC`, `MDR`) y vegetación secundaria arbórea
  (`VSA/*`). Ver [Zona forestal ampliada](#zona-forestal-ampliada).
- **Desglose:** el balance sale también por clave de la Serie VII y por tipo de bosque (coníferas,
  encino, mesófilo, selva baja caducifolia, zonas semiáridas y otro).
- **Cambio:** un píxel solo cambia de clase si, además de cruzar el umbral, su NDVI varió ≥ 0.10.
- **Quemado:** dNBR ≥ 0.27 (USGS, moderada-baja o mayor) dentro de los polígonos de incendio de
  CONAFOR. La pérdida en un píxel quemado se atribuye al incendio; si no, va a "otras pérdidas".
- **Destino de las otras pérdidas:** cada píxel se clasifica como agrícola, pecuario, urbano u otro
  con un clasificador entrenado con Sentinel-2 y las zonas no forestales de la Serie VII
  (ver [Uso al que pasó el terreno](#uso-al-que-pasó-el-terreno-cf-dev-07-opción-a)).
- **Reforestación:** recuperación **esperada** (polígonos de PS/RHF/CC × sobrevivencia) contra la
  **observada** por el satélite.

## Estructura

```
FEPI/
├── src/
│   ├── prototipo_masa_forestal.py   Calculadora (subcomandos demo, calibrar, correr)
│   ├── descargar_capas.py           Descarga las capas del Estado de México desde IDEFOR
│   ├── comparar_resultados.py       Compara dos corridas (balance, incendios, ráster de cambio)
│   ├── mapa_cambio.py               Dibuja el mapa PNG de una corrida
│   ├── mapa_interactivo.py          Arma la página HTML interactiva (con plantilla_mapa.html)
│   ├── plantilla_mapa.html          Diseño y código de esa página
│   ├── validar_hansen.py            Compara la pérdida con Hansen GFC v1.13 (CF-DEV-09)
│   └── muestra_puntos.py            Puntos estratificados para fotointerpretar
├── docs/
│   └── mapa_edomex.html             Página interactiva del estado (todos los periodos)
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
Solo necesita internet. No hay caché en disco (el equipo tiene poco espacio): cada corrida vuelve
a leer los píxeles.

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
# 1. Probar la lógica con datos inventados (no descarga nada; el balance debe dar 516 ha y
#    procesar por bloques debe dar lo mismo que de una sola vez). Tarda unos segundos
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

Para todo el estado se agrega `--bloques` (ver [Cobertura geográfica](#cobertura-geográfica)):

```bash
python src/prototipo_masa_forestal.py correr --aoi datos/edomex/estado_mexico.gpkg \
  --anio-base 2023 --anio 2024 --umbral-ndvi auto \
  --zona-forestal datos/edomex/usv_serie7_edomex.gpkg \
  --incendios datos/edomex/incendios_conafor_edomex.gpkg \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
  --bloques --salida resultados/edomex_2023_2024
```

`--umbral-ndvi auto` usa el umbral de Otsu, que es provisional. Con un valor calibrado se pasa el
número (por ejemplo `--umbral-ndvi 0.55`). `python src/prototipo_masa_forestal.py correr -h` muestra
todas las opciones.

`--ventana INICIO FIN` cambia los días del año de los compuestos (por defecto `11-01 12-31`).
Sirve para lo más reciente cuando todavía no llega noviembre-diciembre. Por ejemplo, el preliminar
de 2026 compara del 1 de septiembre al 20 de octubre de 2025 y de 2026:

```bash
python src/prototipo_masa_forestal.py correr --aoi datos/edomex/estado_mexico.gpkg \
  --anio-base 2025 --anio 2026 --ventana 09-01 10-20 --umbral-ndvi auto \
  --zona-forestal datos/edomex/usv_serie7_edomex.gpkg \
  --incendios datos/edomex/incendios_conafor_edomex.gpkg \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
  --bloques --salida resultados/edomex_2025_2026_sepoct
```

En otra temporada el verdor cambia: en lluvias, pastos y cultivos se ven verdes. Por eso las
hectáreas de otra ventana no se comparan con las de noviembre-diciembre. Lo que sí vale es el
cambio entre los dos años de la misma ventana.

Salidas de `correr`, todas en EPSG:32614 (UTM 14N):

| Archivo | Contenido |
|---|---|
| `balance_<base>_<actual>.csv` | Balance por unidad (hectáreas) |
| `incendios_dnbr.csv` | Cada incendio: superficie del polígono contra lo quemado según el dNBR |
| `cambio_<base>_<actual>.tif` | uint8 comprimido: 0 sin bosque, 1 estable, 2 pérdida por incendio, 3 otra pérdida, 4 ganancia |
| `vegetacion_<base>_<actual>.csv` | Por unidad y clave de la Serie VII (CF-DEV-03): zona forestal, bosque inicial, pérdida por incendio, otras pérdidas, ganancia, bosque final y cambio neto. Suma lo mismo que el balance |
| `tipo_bosque_<base>_<actual>.csv` | Lo mismo por unidad y tipo de bosque (CF-DEV-04) |
| `destino_perdidas_<base>_<actual>.csv` | Otras pérdidas de cada unidad según el uso al que pasó el terreno (CF-DEV-07): agrícola, pecuario, urbano, otro y sin dato |
| `destino_exactitud_<base>_<actual>.csv` | Exactitud del clasificador con las muestras reservadas: matriz de confusión, exactitud de productor y de usuario por clase, global y kappa |
| `destino_<base>_<actual>.tif` | uint8 comprimido: 0 no aplica, 1 agrícola, 2 pecuario, 3 urbano, 4 otro, 5 sin dato |
| `corrida_<base>_<actual>.json` | Parámetros de la corrida, zona forestal y resumen del clasificador (muestras, exactitud, importancia de cada rasgo) |
| `bloques_<base>_<actual>.csv` | Cada bloque: escenas leídas, segundos y RAM pico del proceso |
| `ndvi_<año>.tif`, `dnbr.tif` | Índices en float32. Se guardan por defecto solo de una sola vez; con `--bloques` hay que pedirlos con `--guardar-indices` (~1.5 GB cada uno para el estado) |

Para comparar dos corridas (por ejemplo, con y sin `--bloques`):

```bash
python src/comparar_resultados.py resultados/piloto_2023_2024 resultados/otra_corrida
```

Compara valor por valor el balance (por unidad), los incendios (por clave) y el ráster de cambio
(píxeles distintos), y dice si todo es idéntico. Si las dos carpetas tienen los desgloses y el
destino, también los compara; si solo una los tiene (las corridas anteriores a 0.6.0), los omite.

Para dibujar el mapa de una corrida (`correr` no lo hace):

```bash
python src/mapa_cambio.py resultados/edomex_2023_2024 \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN --titulo "Estado de México"
```

Deja `mapa_cambio_<base>_<actual>.png` en la carpeta de la corrida, con dos paneles:

- **Izquierda:** el ráster de cambio. En zonas grandes, cada celda junta varios píxeles y muestra
  la pérdida o ganancia si la hay, así que se ven más grandes de lo que son; las hectáreas reales
  van en la leyenda.
- **Derecha:** el cambio neto de bosque de cada unidad, en porcentaje.

No sobrescribe un mapa que ya exista, a menos que se use `--sobrescribir`.

### Página interactiva

[`docs/mapa_edomex.html`](docs/mapa_edomex.html) se abre directo en el navegador, sin servidor.
Solo necesita internet para cargar la librería D3. Permite:

- acercar y arrastrar el mapa, o buscar un municipio por nombre;
- ver el ráster de cambio, con cada clase como capa que se prende y apaga, o el cambio neto por
  municipio;
- ver las cifras de un municipio al pasar el cursor, y su detalle en todos los periodos al
  elegirlo;
- ver el desglose por tipo de bosque del periodo elegido: del estado cuando no hay municipio
  elegido y del municipio cuando sí. Solo aparece en las corridas que traen
  `tipo_bosque_<base>_<actual>.csv` (desde 0.6.0);
- comparar años con un selector **Desde → Hasta**: 2023 → 2024, 2024 → 2025, 2023 → 2025 o
  2025 → 2026. El de 2026 es el preliminar de septiembre-octubre, va marcado así y avisa que es
  otra temporada. Las combinaciones sin corrida dicen "sin datos"; si eliges una, el otro año se
  ajusta al más cercano que sí tiene;
- ordenar la tabla de municipios.

Se adapta al tema claro u oscuro y a pantallas de teléfono. Para regenerarla con todas las
corridas:

```bash
python src/mapa_interactivo.py resultados/edomex_2023_2024 resultados/edomex_2024_2025 \
  resultados/edomex_2023_2025 resultados/edomex_2025_2026_sepoct \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
  --titulo "Estado de México" --salida docs/mapa_edomex.html
```

Cada comparación es su propia corrida de `correr`; la página no las suma. Las corridas deben ser de
la misma zona (mismo `--aoi`). Como está en `docs/`, se puede publicar
con GitHub Pages si el repositorio es público.

## Cobertura geográfica

El script **no tiene ninguna zona fija**: calcula sobre el polígono que se le pase en `--aoi`.
La proyección (UTM 14N) cubre todo el Estado de México y las capas de `datos/edomex/` cubren el
estado completo. Hay dos modos:

- **De una sola vez** (el de siempre): carga cada capa completa en memoria. Sirve para municipios
  o Delegaciones. El piloto (dos municipios, unas 34,000 ha) tarda unos 5 minutos.
- **Por bloques** (`--bloques`): para zonas grandes, como todo el estado (2.23 millones de ha,
  125 municipios, 9 teselas Sentinel-2). De una sola vez no cabría: el rectángulo del estado son
  21,211 × 21,215 píxeles de 10 m (450 millones), ~1.8 GB por capa float32 más las máscaras.

Los dos modos dan **exactamente el mismo resultado**: mismo balance, mismo ráster de cambio y una
fila por incendio. El modo `demo` lo comprueba con datos inventados (bloques que se saltan,
incendios que cruzan bloques o se enciman, umbral fijo y automático, corridas interrumpidas).
**Con datos reales también se comprobó** (14-oct-2026), es decir con las mismas fuentes del
proyecto (Sentinel-2 de Earth Search y capas de IDEFOR), no con datos adicionales:

- El piloto da idéntico de una sola vez, por bloques y contra el piloto guardado: mismo balance,
  mismos 14 incendios y 0 píxeles distintos.
- Un cuadro de 12 km en la esquina donde se juntan 4 teselas (14QLF, 14QLG, 14QMF, 14QMG; x =
  399,960, y = 2,100,000) también da idéntico de las dos formas. Son 4 bloques, uno por tesela,
  con 8 incendios.

El estado completo ya se corrió: ver [Resultados del estado](#resultados-del-estado-2023--2024).

### Cómo funciona el modo por bloques

- **Bloques en memoria.** La zona se divide en bloques de hasta 2,048 × 2,048 píxeles (20.48 km;
  se cambia con `--tam-bloque`). Cada bloque lee sus compuestos, calcula, suma al balance y
  libera la memoria. Los bloques no se enciman, así que cada píxel cuenta una sola vez, y los que
  no tocan la zona se saltan: para el estado son 84 de los 144 que tiene el rectángulo.
- **Alineados a la malla de los COG.** Earth Search guarda cada banda en bloques internos de
  10.24 km (1,024 px en B04 y B08, 512 px en B8A, B12 y SCL) que arrancan en el origen de cada
  tesela (`proj:transform`). Un bloque de 20 km sin alinear toca hasta 3 × 3 bloques internos y
  lee más del doble de lo que usa; uno alineado de 20.48 km toca exactamente 2 × 2. Como las
  teselas vecinas tienen la malla desfasada, la zona se reparte en un "dominio" por tesela,
  cortado en los orígenes de las teselas (cada 100 km), y dentro de cada dominio los bloques
  siguen la malla de su tesela. Solo se releen, en las costuras, los bloques internos de la tesela
  vecina que se mete en el dominio (las teselas se traslapan ~10 km y esa franja siempre se lee
  de las dos). La SCL además lee un píxel de más en cada borde (así remuestrea `odc-stac`), lo que
  alcanza a los bloques internos vecinos; pesa muy poco frente a B04 y B08.
- **Incendios.** El dNBR de cada incendio se calcula igual que antes, una sola vez y en su propia
  ventana (polígono + 200 m), antes de los bloques. Su máscara de quemado se reparte entre los
  bloques que toca, así que un incendio que cruza bloques sigue siendo una fila.
- **Umbral automático.** Con `--umbral-ndvi auto` primero se leen los compuestos del año base de
  todos los bloques y se guarda en memoria solo el NDVI dentro del estado (0.83 GB); con eso se
  calcula Otsu y luego se lee el año actual bloque por bloque. Con un umbral numérico no hace
  falta: cada bloque lee sus dos años y termina.
- **Solo salidas pequeñas.** En disco quedan los CSV y el ráster de cambio (uint8 comprimido). Los
  rásters de NDVI y dNBR (~1.5 GB cada uno para el estado) solo se guardan con `--guardar-indices`.
- **Reanudar.** Mientras corre, `<salida>/progreso_<base>_<actual>/` guarda cada incendio y cada
  bloque terminado (pocos KB por renglón, más el pedazo del ráster de cambio de cada bloque, que en
  total pesa lo mismo que el ráster final). Si la corrida se corta, se repite el mismo comando y
  sigue desde el último bloque. Con umbral automático, si se corta antes de terminar de leer el
  año base, esa lectura empieza de nuevo. Si cambian los parámetros o las escenas del catálogo, el
  script se niega a mezclar corridas: `--reiniciar` empieza de cero. Al terminar, la carpeta se
  borra.
- **Leer menos.** `--nubes-max` (60 % por defecto) descarta escenas más nubladas, también en el
  dNBR. `--escenas-max N` deja las N escenas menos nubladas de cada tesela para cada compuesto
  anual. Los valores por defecto dan el resultado de siempre.

### Tiempos

Medidos en el equipo de Joshua (15.7 GB de RAM, conexión de ~5–8 MB/s), 14-oct-2026, con el
código anterior (bloques de 20 km sin alinear):

| Qué | Tiempo | Datos leídos |
|---|---|---|
| Compuesto nov-dic 2023 de un bloque de 20 × 20 km cerca del Nevado de Toluca (x = 425,000, y = 2,120,000), 9 escenas | 51 s | 253 MB |
| Compuesto nov-dic 2024 del mismo bloque, 18 escenas | 69 s | 542 MB |
| dNBR de un incendio | ~8.5 s | ~22 MB |

En el periodo 2023-11 a 2024-10 hay 1,085 incendios en el estado. Escalando esas mediciones, el
estado completo tardaría ~6–7 h y leería ~110 GB (compuestos ~3.7 h, incendios ~2.6 h).

Medidos el mismo día con `--bloques` (bloques alineados, umbral automático):

| Corrida | Tiempo | RAM pico |
|---|---|---|
| Piloto: 2 municipios, 1 tesela, 4 bloques, 14 incendios | 2 min 12 s | 1.2 GB |
| Amanalco, Coatepec Harinas y Villa Guerrero: 73,700 ha, 4 teselas, 7 bloques, 72 incendios | 9 min 51 s | 2.0 GB |
| Estado completo: 9 teselas, 84 bloques, 1,085 incendios | ~2 h 08 min | 4.2 GB |

En el estado, los 84 bloques sumaron 34 minutos (mediana de 23 s por bloque, máximo 53 s con
60 + 113 escenas) y los incendios el resto. La RAM pico (4.2 GB) incluye los 0.83 GB del umbral
automático.

En la de 3 municipios, cada bloque tardó de 13 a 47 s (~23.5 s en promedio, con los dos años),
según cuántas escenas lo cubren: hasta 36 + 72 donde se traslapan dos teselas. Cada incendio tardó
~5.5 s. Escalado a los 84 bloques y 1,085 incendios del estado, serían **~2–2.5 h** (compuestos
~35 min, incendios ~1.7 h) con una RAM de ~2 GB, más 0.83 GB del umbral automático.

La velocidad de la conexión cambia mucho: ese mismo día el piloto tardó 11 min en un momento y
2 min en otro. Con una conexión lenta, el estado podría tardar varias horas más.
`bloques_<base>_<actual>.csv` registra los segundos y la RAM pico de cada bloque.

**Incendios en paralelo.** El dNBR es la parte más lenta, y casi todo ese tiempo se va en esperar
respuestas del servidor, no en bajar datos. Por eso el script:

- lee varios incendios a la vez (`--hilos-incendios`, 6 por defecto);
- busca las escenas de todos los incendios en una sola consulta al catálogo;
- guarda en RAM, no en disco, los pedazos de imagen ya bajados, porque los incendios cercanos
  comparten bloques.

Cada incendio se procesa y guarda en su orden, así que el resultado es el mismo que uno por uno.
Con los 72 incendios de los 3 municipios, la corrida bajó de 9 min 51 s a 7 min 9 s, aun
compartiendo la conexión con otra corrida. Paralelizar los bloques no ayuda: ahí el límite es la
conexión, y solo subiría la RAM.

## Resultados del piloto (Amecameca y Tlalmanalco, 2023 → 2024)

| Municipio | Bosque 2023 | Pérdida por incendio | Otras pérdidas | Ganancia | Bosque 2024 |
|---|---|---|---|---|---|
| Amecameca | 7,123 ha | 50 | 223 | 50 | 6,900 |
| Tlalmanalco | 9,592 ha | 3 | 149 | 22 | 9,462 |

CONAFOR reportó 14 incendios con 1,810 ha en total. De ellas, 699 ha tienen dNBR ≥ 0.27; 225 ha
estaban en bosque, y solo 54 ha seguían sin copa al cierre. Las "otras pérdidas" están por
verificar (tala, plaga, nieve o ruido). Detalles en
[`resultados/piloto_2023_2024/LEEME.md`](resultados/piloto_2023_2024/LEEME.md).

## Resultados del estado (2023 → 2024)

Corrida con `--bloques` el 14–15 de octubre de 2026. Usó umbral NDVI 0.51 (Otsu sobre todo el
estado, provisional), 115 y 213 escenas, 9 teselas y 1,085 incendios.

| | Hectáreas |
|---|---|
| Bosque 2023 | 459,262 |
| Pérdida por incendio | 708 |
| Otras pérdidas (por verificar) | 7,788 |
| Ganancia | 2,684 |
| **Bosque 2024** | **453,450** (−5,812, −1.3 %) |

- **Incendios:** CONAFOR reportó 52,325 ha de polígonos. De ellas, 16,214 ha tienen dNBR ≥ 0.27;
  8,388 ha estaban en bosque, y solo 708 ha seguían sin copa al cierre. En 258 incendios el dNBR
  no detectó nada quemado: probablemente fueron superficiales o pequeños.
- **Mayor pérdida neta:** Tlatlaya (−633 ha), Luvianos (−590), Atlautla (−461), Ocuilan (−440),
  Temascaltepec (−404) y Santo Tomás (−378, el 19 % de su bosque). Casi todo son "otras
  pérdidas", que hay que verificar (tala, plaga, nieve o ruido).
- **El umbral automático cambia con la zona que se corre** (0.50 en el piloto, 0.51 en el
  estado). Por eso Amecameca da 7,051 ha de bosque en esta corrida y 7,123 ha en el piloto. Para
  comparar corridas conviene fijar un umbral numérico.

Mapa: [`resultados/edomex_2023_2024/mapa_cambio_2023_2024.png`](resultados/edomex_2023_2024/mapa_cambio_2023_2024.png).
Detalles en [`resultados/edomex_2023_2024/LEEME.md`](resultados/edomex_2023_2024/LEEME.md).

## Todas las comparaciones del estado

Cada fila es su propia corrida con `--bloques`, del 21 al 22 de octubre de 2026. Se exploran en
[`docs/mapa_edomex.html`](docs/mapa_edomex.html).

| Comparación | Bosque inicial | Pérdida por incendio | Otras pérdidas | Ganancia | Bosque final | Cambio neto |
|---|---|---|---|---|---|---|
| 2023 → 2024 | 459,262 | 708 | 7,788 | 2,684 | 453,450 | −5,812 (−1.3 %) |
| 2024 → 2025 | 450,768 | 0 ¹ | 3,336 | 4,519 | 451,950 | +1,182 (+0.3 %) |
| 2023 → 2025 | 459,262 | 245 ¹ | 7,329 | 2,946 | 454,634 | −4,628 (−1.0 %) |
| 2025 → 2026, sep-oct (preliminar) ² | 434,687 | 0 ¹ | 20,758 | 17,897 | 431,826 | −2,861 (−0.7 %) |

Hectáreas. Las tres primeras usan noviembre-diciembre y el umbral fijo 0.51.

¹ Todavía no hay polígonos de incendios de 2025 ni de 2026, así que esa pérdida cae en "otras
pérdidas". En 2023 → 2025 solo cuentan los incendios hasta octubre de 2024.

² Compara del 1 de septiembre al 20 de octubre de 2025 con lo mismo de 2026, las imágenes más
recientes. Es el final de las lluvias, con más nubes y vegetación que cambia de verdor. Por eso
sus pérdidas y ganancias son varias veces mayores que en noviembre-diciembre, y en algunos
municipios se ven exageradas: en Valle de Bravo daría −13.6 %. Sirve para ver dónde revisar, no
como cifra final, y no se compara con las otras filas.

Las cifras son coherentes entre sí:

- 2023 → 2025 parte del mismo bosque de 2023 que 2023 → 2024.
- Sumar los dos periodos de un año (−5,812 + 1,182 = −4,630 ha) da casi lo mismo que la corrida
  directa de dos años (−4,628 ha).
- El bosque final de un balance no es igual al inicial del siguiente (453,450 contra 450,768 ha
  en 2024). El final conserva el bosque de 2023 que bajó del umbral por menos de 0.10 de NDVI,
  mientras que el balance siguiente mide 2024 desde cero.

Tiempos: 2024 → 2025 tardó 49 min, el preliminar 25 min y 2023 → 2025 43 min, con 1,092 incendios
en paralelo. La RAM pico fue de 3.5 a 4.6 GB.

## Validación contra Hansen GFC (CF-DEV-09)

`src/validar_hansen.py` compara la pérdida del prototipo con la de Hansen Global Forest Change
v1.13, la única versión que trae 2025. Sin argumentos compara 2023 → 2024 con la pérdida de
Hansen 2024, y 2024 → 2025 con la de 2025. Tarda ~2 min.

- **Lectura:** baja por ventanas solo la parte del estado (~100 MB de internet) y deja recortes de
  22 MB en `datos/edomex/hansen/`, que git ignora.
- **Mallas:** lleva Hansen a la malla de 10 m del prototipo por vecino más cercano, para que las
  hectáreas del prototipo no cambien.
- **Salidas:** en `resultados/validacion_hansen/` quedan dos CSV (municipios y estatal), los
  rásters de coincidencia, `mapa_coincidencia.png` y un
  [LEEME](resultados/validacion_hansen/LEEME.md) con el método, la licencia (CC BY 4.0) y la cita.

Hansen no es la verdad de campo: es otro mapa satelital, de Landsat a 30 m, que solo marca
remoción de copa.

| | 2023 → 2024 | 2024 → 2025 |
|---|---|---|
| Pérdida del prototipo | 8,496 ha | 3,336 ha |
| Pérdida de Hansen (zona forestal) | 1,883 ha | 1,340 ha |
| Coinciden | 580 ha | 156 ha |
| Precisión (exacta / con 30 m de tolerancia) | 7 % / 10 % | 5 % / 8 % |
| Exhaustividad (exacta / con 30 m de tolerancia) | 31 % / 69 % | 12 % / 36 % |

- Casi todo el desacuerdo está en las "otras pérdidas", que coinciden solo 4 %. La pérdida por
  incendio coincide 40 %.
- Hay municipios con desacuerdo casi total: Atlautla, Santo Tomás, Amecameca y Tlalmanalco. Son
  los primeros lugares que conviene fotointerpretar.
- Donde hay un evento grande, como en San Simón de Guerrero en 2024, las dos fuentes lo ven.

`src/muestra_puntos.py` arma una muestra estratificada de 105 puntos (15 en cada uno de 7
estratos de cambio y Hansen) para fotointerpretar. Su CSV,
`resultados/validacion_hansen/muestra_puntos_2023_2024.csv`, es compatible con `calibrar --puntos`
y trae la columna `clase` vacía.

## Decisiones de diseño

Tomadas el 3 de noviembre de 2026 para cubrir las necesidades CF-DEV-03, 04 y 07 del Módulo 13
de la propuesta. **Programadas en la versión 0.6.0.** Los resultados del estado que aparecen
arriba siguen siendo de la zona anterior hasta que se vuelvan a correr los balances.

### Zona forestal ampliada

Las claves de la zona forestal pasan de `^(B|VSA/)` a `^(B|S|M|VSA/)`, para incluir los cinco
tipos que pide CF-DEV-04: coníferas, encino, mesófilo de montaña, selva baja caducifolia y
vegetación de zonas semiáridas.

| | Claves de la Serie VII en el Estado de México | Hectáreas |
|---|---|---|
| Antes | Bosques (`B*`) y vegetación secundaria arbórea (`VSA/*`) | 484,695 |
| Ahora | Lo anterior más selva baja caducifolia (`SBC`) y matorrales (`MC`, `MDR`) | 512,577 |

- **Por qué:** antes quedaba fuera la selva baja caducifolia primaria (13,818 ha), aunque su
  vegetación secundaria arbórea (28,751 ha) sí entraba. También quedaba fuera la vegetación
  semiárida.
- **Qué sigue fuera:** la vegetación secundaria arbustiva (`VSa/*`) y herbácea (`VSh/*`), porque
  no es cobertura arbórea.
- **Efecto:** cambian los totales de todos los balances, así que hay que volver a correrlos.
- **Cautela:** la selva baja caducifolia empieza a tirar hojas en noviembre-diciembre, y el
  matorral casi nunca llega al umbral de NDVI. El umbral único de 0.51 sigue siendo provisional y
  quizá necesite valores por tipo (CF-DEV-09).
- **En el código:** es el valor por defecto de `--clases-forestales`. Para repetir una corrida
  anterior se pasa `--clases-forestales "^(B|VSA/)"`.

### Cruce con la Serie VII y tipo de bosque (CF-DEV-03 y 04)

La clave (`CLAVE`) de la Serie VII se rasteriza en cada bloque junto con la zona forestal (son los
mismos píxeles, solo cambia el valor que se escribe). El balance se cuenta por unidad y clave,
bloque por bloque, y sale en `vegetacion_<base>_<actual>.csv`. Agrupando las claves sale
`tipo_bosque_<base>_<actual>.csv`. Los dos suman lo mismo que el balance. Los píxeles de una
reforestación fuera de la zona forestal van como "(reforestación fuera de la zona forestal)",
tipo "Otro".

Agrupación propuesta de los cinco tipos que pide CF-DEV-04:

| Tipo | Claves de la Serie VII | Hectáreas en el estado |
|---|---|---|
| Coníferas | `BA`, `BP`, `BPQ`, `BJ`, `BB`, `BG` y sus `VSA/` | 299,156 |
| Encino | `BQ`, `BQP` y sus `VSA/` | 133,464 |
| Mesófilo de montaña | `BM` y `VSA/BM` | 11,358 |
| Selva baja caducifolia | `SBC` y `VSA/SBC` | 42,569 |
| Vegetación de zonas semiáridas | `MC`, `MDR` | 14,064 |
| Otro | `BC` (bosque cultivado) y lo que no encaje | 11,965 |
| **Total** | `^(B\|S\|M\|VSA/)` | **512,577** |

Notas sobre la propuesta:
- `BPQ` (pino-encino) va con coníferas porque domina el pino; `BQP` (encino-pino), con encino.
- `BG` (bosque de galería, 212 ha) no es de coníferas, pero es muy poco; se dejó ahí como pedía
  la propuesta. Se puede mover cambiando `TIPOS_BOSQUE` en el script.
- Se agregó `VSA/BM` (743 ha) a mesófilo, aunque la propuesta solo decía `BM`: es la vegetación
  secundaria arbórea del mismo bosque.
- Las hectáreas son de la zona forestal (polígonos de la Serie VII), no del bosque medido.

### Uso al que pasó el terreno (CF-DEV-07): opción A

La Serie VII es un mapa fijo anterior a 2023. Dentro de la zona forestal todos sus píxeles son
vegetación, así que por sí sola no dice en qué se convirtió un píxel que perdió bosque.

**Opción elegida (A):** clasificar el terreno perdido con Sentinel-2, el mismo año en que se
perdió. El clasificador se entrena con las zonas que la Serie VII marca fuera del bosque:
agricultura (`TA*`, `TR*`) para agrícola, pastizales (`PI`, `PC`) para pecuario y asentamientos
(`AH`) para urbano. Usa solo las fuentes que ya tiene el proyecto. Sus limitaciones: las
etiquetas del INEGI son de antes de 2023, y el resultado es una estimación con su propia
exactitud, que hay que reportar.

Cómo quedó programada (se activa sola con `--zona-forestal`; `--no-clasificar-destino` la apaga):

- **Qué se clasifica:** cada píxel de "otra pérdida" (código 3 del ráster de cambio), con su
  cobertura del año actual. La pérdida por incendio no se clasifica.
- **Rasgos:** mediana del compuesto del año actual (la misma ventana, nov-dic por defecto) de
  B03, B04, B08, B8A, B11 y B12, más NDVI (B08, B04), NBR (B8A, B12), NDBI (B11, B08) y MNDWI
  (B03, B11). Las bandas de 20 m pasan a 10 m por vecino más cercano. Solo se leen los píxeles
  que hacen falta (las pérdidas y las muestras), no se guarda ninguna imagen; aun así, cada bloque
  lee 6 bandas más del año actual.
- **Etiquetas:** las zonas no forestales de la Serie VII. Agrícola: `T*` (temporal), `R*` (riego)
  y `HA` (humedad); pecuario: `PI` y `PC`; urbano: `AH`; otro: todo lo demás (vegetación
  secundaria arbustiva y herbácea, pastizal halófilo, pradera de alta montaña, agua, sin
  vegetación, tular...). La indicación decía "TA\* y TR\*"; en la Serie VII la agricultura de riego
  es `R*` (no hay claves `TR`), así que se tomaron `T*` y `R*`.
- **Muestreo:** una retícula de 250 m sobre la malla total, solo fuera de la zona forestal y
  dentro de la zona de interés. Como la retícula es de la malla total, da los mismos puntos con o
  sin bloques. Se balancea con un máximo de 1,500 muestras por clase en cada región de 100 km (la
  malla de las teselas Sentinel-2), elegidas al azar con semilla fija.
- **Clasificador:** bosque aleatorio de scikit-learn (200 árboles, clases balanceadas, semilla
  fija). Se entrena uno solo para toda la corrida, al final, con las muestras de todos los bloques
  ordenadas por posición. Por eso da lo mismo por bloques (el `demo` lo comprueba).
- **Exactitud:** las muestras de 1 de cada 5 celdas de 5 km quedan fuera del entrenamiento y sirven
  de prueba. Es una prueba espacial, porque las muestras vecinas se parecen y medirían de más.
  `destino_exactitud_<base>_<actual>.csv` trae la matriz de confusión, la exactitud de productor y
  de usuario por clase, la global y kappa. **Mide el acuerdo con la Serie VII, cuyas etiquetas son
  anteriores a 2023**: una parcela que cambió de uso después cuenta como error aunque el
  clasificador acierte.
- **Sin dato:** si a un píxel le falta algún rasgo (ninguna escena válida en alguna banda), queda
  como código 5.
- **Ganancia por programa (CF-DEV-05):** pendiente, faltan los polígonos de PROBOSQUE. La función
  `ganancia_por_programa` del script marca dónde se conecta.

### Verificación de 0.6.0 (3-nov-2026)

- **`demo`:** pasa. Por bloques, de una sola vez, con incendios en paralelo y en corridas
  interrumpidas da los mismos desgloses, el mismo clasificador y el mismo destino.
- **Piloto con la zona anterior** (`--clases-forestales "^(B|VSA/)"`, de una sola vez): balance,
  incendios y ráster de cambio IDÉNTICOS a `resultados/piloto_2023_2024`.
- **Piloto con la zona nueva, por bloques:** también IDÉNTICO al guardado, porque Amecameca y
  Tlalmanalco no tienen claves `S*` ni `M*`: la ampliación no les cambia nada. Contra la corrida de
  una sola vez, todas las salidas nuevas (vegetación, tipo, destino, exactitud y ráster de destino)
  dan IDÉNTICO.
  - Por tipo: coníferas 14,051 ha de bosque inicial y −329 ha de cambio neto; encino 2,664 ha y
    −24 ha.
  - Destino de las 372 ha de otras pérdidas: agrícola 115, pecuario 58, urbano 5 y otro 194.
  - Clasificador: exactitud 67 % (kappa 0.40) con 743 muestras de prueba. Pecuario se quedó sin
    muestras de prueba: el pastizal del piloto cae en pocas celdas de 5 km.
- **Efecto de la zona nueva**, en Otzoloapan (selva baja) y Tequixquiac (matorral crasicaule),
  2023 → 2024, umbral 0.51, por bloques:

  | | Zona anterior | Zona nueva | Diferencia |
  |---|---|---|---|
  | Zona forestal | 3,326 ha | 6,567 ha | +3,241 |
  | Bosque 2023, Otzoloapan | 3,229 | 4,762 | +1,532 (selva baja) |
  | Bosque 2023, Tequixquiac | 0 | 166 | +166 (de 1,581 ha de matorral) |
  | Otras pérdidas, Otzoloapan | 124 | 312 | +188 |

  - El matorral casi no llega al umbral: solo 166 de sus 1,581 ha cuentan como bosque.
  - La selva baja perdió el 11 % de su bosque inicial en "otras pérdidas" (291 de 2,568 ha),
    contra 1 % en coníferas. Lo más probable es que sea la caída de hojas de noviembre-diciembre,
    no pérdida real. Confirma la cautela de arriba: la selva baja necesita su propio umbral o su
    propia ventana.
  - Clasificador en esta zona: exactitud 48 % (kappa 0.21). Confunde sobre todo pecuario con otro
    (pastizal inducido contra vegetación secundaria arbustiva). Es baja: si en el estado sale
    parecida, conviene revisar los rasgos (por ejemplo, agregar otra temporada) o pasar a la
    opción B.
- **Costo:** con `--no-clasificar-destino` el balance y los desgloses salen idénticos. El
  clasificador no subió la RAM pico (3.6 GB en las dos corridas), pero los bloques tardaron unas
  2.6 veces más (356 s contra 138 s; la corrida con clasificador compartía la conexión con otra).
  Los incendios no cambian.
- Las corridas de prueba están en `resultados/verificacion/` (git las ignora).

**Opción guardada (B), por si se llega a requerir:** usar un mapa de cobertura del suelo ya
hecho, como fuente nueva:

- **ESA WorldCover:** 10 m, años 2020 y 2021, licencia CC BY 4.0. Solo sirve para el estado
  previo, no para 2024 o 2025.
- **Dynamic World:** 10 m, casi en tiempo real, licencia CC BY 4.0. Se distribuye sobre todo por
  Google Earth Engine, que el proyecto no usa en operación.

Convendría cambiar a B si la exactitud de A resulta baja, o si PROBOSQUE pide una clasificación
reconocida externamente en lugar de una propia.

## Pendientes

1. Calibrar el umbral de NDVI con ~100 puntos de referencia. Mientras tanto, `auto` cambia según
   la zona que se corre, así que conviene fijar un umbral numérico para comparar corridas.
2. Conseguir los polígonos de reforestación de PS, RHF y CC, con año de plantación, sobrevivencia
   y programa. Con el programa se completa la ganancia por programa (CF-DEV-05).
3. Volver a correr los balances del estado con la zona ampliada (0.6.0), para tener los desgloses
   por clave y tipo, el destino de las otras pérdidas y la página con el desglose por tipo.
   Revisar la exactitud del clasificador de destino a escala estatal.
4. Verificar las "otras pérdidas" del estado (7,788 ha), empezando por Tlatlaya, Luvianos,
   Atlautla, Ocuilan, Temascaltepec y Santo Tomás. El destino de las otras pérdidas (0.6.0) ayuda
   a elegir qué revisar, pero sus etiquetas son del INEGI, anteriores a 2023.
5. Bajar el tiempo de los incendios (~1.7–2.6 h para el estado, según la conexión). Es la parte
   más lenta y no cambió con los bloques.
6. Validación (CF-DEV-09): la comparación con Hansen ya está hecha. Falta:
   - fotointerpretar los 105 puntos de `resultados/validacion_hansen/muestra_puntos_2023_2024.csv`;
   - hacer que `calibrar` lea el NDVI por bloques o solo en los puntos, porque hoy arma el
     compuesto de toda la `--aoi` de una vez y con el estado no cabe en memoria;
   - repetir la validación cuando se vuelvan a correr los balances con la zona ampliada;
   - comparar con las verificaciones de campo de los programas, cuando existan.
7. Agregar los incendios de 2025 al balance 2024 → 2025 cuando CONAFOR publique su capa, y correr
   el balance 2025 → 2026 en enero de 2027, cuando exista el compuesto de noviembre-diciembre
   de 2026.
8. Escenarios de recuperación y ampliar la página interactiva como tablero para la Dirección
   General y las áreas responsables.

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
