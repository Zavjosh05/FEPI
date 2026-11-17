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
- **Serie anual (CF-DEV-08):** con `serie`, el bosque de cada año se encadena: el primer año es el
  que pasa el umbral y cada año siguiente parte del anterior con la misma regla del margen. Así un
  año vale lo mismo en todas las comparaciones. Da además la tendencia (ha/año y %/año por mínimos
  cuadrados), el bosque de cada año (`bosque_por_anio.tif`) y el año de pérdida (`anio_perdida.tif`,
  CF-DEV-12). Ver [Serie anual](#serie-anual-cf-dev-08-10-y-12).

## Estructura

```
FEPI/
├── src/
│   ├── prototipo_masa_forestal.py   Calculadora (subcomandos demo, calibrar, correr, serie)
│   ├── descargar_capas.py           Descarga las capas del Estado de México desde IDEFOR
│   ├── comparar_resultados.py       Compara dos corridas (balance, incendios, rásters, serie)
│   ├── mapa_cambio.py               Dibuja el mapa PNG de una corrida
│   ├── mapa_interactivo.py          Arma la página HTML interactiva (con plantilla_mapa.html)
│   ├── plantilla_mapa.html          Diseño y código de esa página
│   ├── validar_hansen.py            Compara la pérdida con Hansen GFC v1.13 (CF-DEV-09)
│   └── muestra_puntos.py            Puntos estratificados para fotointerpretar
├── docs/
│   ├── mapa_edomex.html             Página interactiva del estado, en un solo archivo
│   └── calculadora/                 La misma página como sitio estático (index.html + datos/)
├── pruebas/calculadora/             Pruebas de la página (pytest + Playwright)
├── entregas/sprint_1/capturas/      Capturas de las pruebas de HU-7.1
├── datos/
│   ├── piloto/                      Recortes usados en el piloto (versionados)
│   └── edomex/                      Capas estatales descargadas (no se versionan)
├── resultados/                      Cada carpeta con su LEEME.md
│   ├── piloto_2023_2024/            Salidas del piloto
│   ├── edomex_serie_2023_2025/      Serie estatal nov-dic 2023 → 2024 → 2025
│   ├── edomex_2025_2026_sepoct/     Preliminar septiembre-octubre 2025 → 2026
│   ├── validacion_hansen/           Comparación con Hansen GFC
│   └── anteriores_0.5/              Corridas estatales con la zona anterior
├── requirements.txt
├── requirements-dev.txt             pytest y Playwright, solo para las pruebas
├── CHANGELOG.md                     Registro de cambios
└── README.md
```

Las corridas nuevas conviene guardarlas en `resultados/<nombre>/`. Git las ignora, salvo las que
están en la lista de arriba (`.gitignore` las habilita una por una).

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
# 1. Probar la lógica con datos inventados (no descarga nada; el balance debe dar 516 ha,
#    procesar por bloques debe dar lo mismo que de una sola vez y la serie de 2 años lo mismo
#    que correr). Tarda unos 30 segundos
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

Desde 0.7.0, `incendios_dnbr.csv` trae además la columna `periodo` (`<base>_<actual>`).

### Serie anual (CF-DEV-08, 10 y 12)

`serie` lee una sola vez, en cada bloque, el compuesto de cada año y arma todas las comparaciones
entre ellos. Para el estado:

```bash
python src/prototipo_masa_forestal.py serie --aoi datos/edomex/estado_mexico.gpkg   --anios 2023 2024 2025 --umbral-ndvi 0.51   --zona-forestal datos/edomex/usv_serie7_edomex.gpkg   --incendios datos/edomex/incendios_conafor_edomex.gpkg   --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN   --bloques --salida resultados/edomex_serie_2023_2025
```

- **Bosque encadenado:** el bosque del primer año es NDVI ≥ umbral dentro de la zona. En cada año
  siguiente, un píxel solo cambia de clase si cruza el umbral y además su NDVI cambió al menos 0.10
  respecto del año anterior. Con dos años es exactamente `correr` (el demo y el piloto lo
  comprueban); `correr` es, de hecho, la serie de dos años.
- **Incendios:** cada uno cuenta en su periodo, del 1-nov de un año al 31-oct del siguiente, y
  en las comparaciones largas que lo incluyen.
- **Comparaciones:** todas las de los años pedidos (con 2023, 2024 y 2025: 2023→2024, 2024→2025 y
  2023→2025), cada una con las mismas salidas de `correr` (`balance_`, `cambio_`, `vegetacion_`,
  `tipo_bosque_`, `destino_perdidas_`, `destino_`, `corrida_`). Una comparación larga compara el
  bosque del primer año con el del último: su balance cuadra píxel por píxel y la cifra de cada
  año es la misma en todas. Su pérdida es "por incendio" si el píxel se quemó en alguno de sus
  periodos; el destino de una otra pérdida es el que le dio el clasificador del año en que el
  píxel dejó de ser bosque por última vez.
- **Clasificador de destino:** uno por año, entrenado con el compuesto de ese año
  (`destino_exactitud_<año anterior>_<año>.csv`).
- `--umbral-ndvi auto` usa Otsu sobre el primer año. Hasta 8 años (un bit por año).

Salidas propias de `serie`:

| Archivo | Contenido |
|---|---|
| `serie_<a0>_<aN>.csv` | Por unidad, año y tipo de bosque (`Todos` = la unidad completa): zona forestal, bosque, y desde el año anterior la pérdida por incendio, las otras pérdidas, la ganancia y el cambio neto. Las filas `Todos` traen además el destino de las otras pérdidas y `bosque_sin_encadenar_ha` (el bosque de ese año con solo el umbral, como lo tomaría una comparación directa que empezara ahí) |
| `tendencia_<a0>_<aN>.csv` | Por unidad (y `Total`) y tipo: pendiente por mínimos cuadrados en ha/año y en % del bosque del primer año por año, y R² (desde 3 años) |
| `bosque_por_anio.tif` | uint8: bit *t* = bosque en el año *t* (bit 0 = primer año) |
| `anio_perdida.tif` | uint8: 0 sin pérdida; si no, año − 2000 del último año en que el píxel dejó de ser bosque (por incendio u otra causa) |
| `serie_<a0>_<aN>.json` | Parámetros, escenas e incendios por año, y resumen de cada clasificador |
| `incendios_dnbr_<a>_<b>.csv` | Incendios de una comparación de años no consecutivos, con sus cifras contra el bosque de esa comparación |

Con tres años, la tendencia por mínimos cuadrados es (último − primero) / 2: solo con más años dice
algo que el cambio total no diga.

Para comparar dos corridas (por ejemplo, con y sin `--bloques`, o `serie` contra `correr`):

```bash
python src/comparar_resultados.py resultados/piloto_2023_2024 resultados/otra_corrida
python src/comparar_resultados.py resultados/edomex_serie_2023_2025 otra_serie --periodo 2024_2025
```

Compara valor por valor el balance (por unidad), los incendios (por clave; con `periodo`, solo los
de ese periodo) y el ráster de cambio (píxeles distintos), y dice si todo es idéntico. Si las dos
carpetas tienen los desgloses, el destino o las salidas de la serie, también los compara; si solo
una los tiene, los omite.

Para dibujar el mapa de una corrida (`correr` no lo hace):

```bash
python src/mapa_cambio.py resultados/anteriores_0.5/edomex_2023_2024 \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN --titulo "Estado de México"
```

Deja `mapa_cambio_<base>_<actual>.png` en la carpeta de la corrida, con dos paneles:

- **Izquierda:** el ráster de cambio. En zonas grandes, cada celda junta varios píxeles y muestra
  la pérdida o ganancia si la hay, así que se ven más grandes de lo que son; las hectáreas reales
  van en la leyenda.
- **Derecha:** el cambio neto de bosque de cada unidad, en porcentaje.

No sobrescribe un mapa que ya exista, a menos que se use `--sobrescribir`.

### Página interactiva

La misma página sale de dos formas, con la misma plantilla (`src/plantilla_mapa.html`), el mismo
código y los mismos archivos de datos:

- **Archivo único** ([`docs/mapa_edomex.html`](docs/mapa_edomex.html), `--salida`): trae todos los
  datos dentro (~2.6 MB) y se abre directo en el navegador, sin servidor. Con `--fragmento` sale
  sin `<html>/<head>/<body>`, para publicarla como Artifact.
- **Sitio estático** ([`docs/calculadora/`](docs/calculadora/), `--sitio`, desde 0.8.0): la página
  sin datos (`index.html`) y los datos en archivos separados que pide con `fetch` solo cuando se
  consultan. Al abrirla baja ~0.45 MB (la página, el índice, los municipios, la comparación
  inicial y su cuadrícula) en vez de 2.6 MB. Necesita servirse por HTTP (GitHub Pages sirve
  `docs/`); abierta como archivo, avisa que no puede leer `datos/`.

Las dos necesitan internet para cargar D3 y TopoJSON (cdnjs). Tiene dos modos:

- **Comparar años** (Desde → Hasta): 2023 → 2024, 2024 → 2025, 2023 → 2025 y el preliminar
  2025 → 2026 de septiembre-octubre, marcado así porque es otra temporada. Las comparaciones
  nov-dic salen de la serie, así que la cifra de cada año es la misma en todas. Las combinaciones
  sin datos dicen "sin datos"; si eliges una, el otro año se ajusta al más cercano que sí tiene.
- **Un año** (CF-DEV-10): el bosque de ese año en el mapa (cada celda según qué parte de ella tiene
  bosque), sus cifras (bosque, % de la zona forestal, cambio desde el año anterior y sus partes,
  tendencia), la tabla de municipios de ese año y, en el panel, el bosque por tipo con su
  tendencia y el uso al que pasaron las otras pérdidas.

En los dos:

- **Evolución del bosque** (CF-DEV-01 de las Tablas v12, M7.1): arriba del mapa, siempre a la
  vista, la gráfica del bosque del Estado de cada año de la serie (un punto y su cifra por año, con
  la recta de tendencia) y una tabla con el bosque, el % de la zona forestal y el cambio respecto
  del año anterior. «ver» abre ese año en el modo "Un año". La de cada municipio está en su detalle.
- **Balance del periodo** (HU-7.2, CF-DEV-02 de las Tablas v12; solo en "Comparar años"): la
  cascada del balance (pérdida por incendio, otras pérdidas, ganancia y cambio neto, en hectáreas)
  del Estado o del municipio elegido, y el histograma de los municipios con 500 ha o más de bosque
  inicial según su cambio neto en % (intervalos de 2 puntos, de −10 a +10, abiertos en los
  extremos), con el municipio elegido resaltado. Cada gráfica trae su tabla equivalente.
- **Incendios** (HU-7.3, CF-DEV-03; solo en "Comparar años"): vista «Incendios» del mapa (un punto
  por incendio, con clave, fecha, municipio y hectáreas) y tarjeta con la pérdida por incendio por
  año y la tabla ordenable de incendios. Un año sin capa de CONAFOR se señala («CONAFOR aún no
  publica los incendios de 2025»): el periodo parcial lleva † y el que no tiene incendios
  publicados dice «sin dato», nunca 0. Sus datos están en `datos/incendios/<periodo>.json` y
  `mapa_interactivo.py` los arma con `--incendios` (por defecto `datos/edomex/incendios_conafor_edomex.gpkg`).
- **A qué uso pasó el terreno perdido** (HU-7.4, CF-DEV-04; solo en "Comparar años"): tarjeta con
  las otras pérdidas del Estado o del municipio elegido repartidas en agrícola, pecuario, urbano,
  otro y sin dato (hectáreas y %, con tabla equivalente) y vista «Destino de la pérdida» del mapa
  (cuadrícula de 90 m, clase más frecuente de cada celda). Es una **estimación** con la exactitud
  del clasificador a la vista (global y kappa, del archivo `destino_exactitud_*.csv`), el año de las
  imágenes (el final del periodo) y la fuente (Sentinel-2 entrenado con la Serie VII, 2021). Un año
  o periodo sin clasificación dice «sin dato», no cero; la pérdida por incendio va aparte. Sus
  datos están en `datos/destino/<periodo>.json` y `datos/cuadriculas/destino_<periodo>.png`.
- **Año de pérdida** (CF-DEV-12): capa con el último año en que cada celda perdió bosque, un tono
  por año (violeta, de claro a oscuro), con cada año como capa que se prende y apaga. En "Comparar
  años" muestra los años de la comparación elegida.
- **Serie y tendencia** (CF-DEV-08) en el detalle: al elegir un municipio, una gráfica de su
  bosque de cada año con la recta de tendencia.
- Ráster de cambio con sus clases como capas, cambio neto por municipio o tendencia por municipio
  (%/año); cifras al pasar el cursor; tabla ordenable; desglose por tipo de bosque.
- **Alcances** (CF-DEV-14): qué mide, dónde, cuándo, con qué fuentes, cómo se arma la serie y qué
  no puede afirmar todavía.

Pruebas de la página: `python -m pytest pruebas/calculadora -q`. Guardan capturas en
`entregas/sprint_N/capturas/` solo si existe la variable de entorno `CAPTURAS=1`
(`CAPTURAS=1 python -m pytest pruebas/calculadora/test_hu_7_3_perdida_por_incendios.py`), para que
una corrida normal no reescriba las capturas versionadas.

Los colores nuevos (densidad de bosque y año de pérdida) son rampas de un solo tono validadas con
el validador del skill dataviz (`--ordinal`, contra el fondo sin bosque) en el tema claro y en el
oscuro. Se adapta al tema y a pantallas de teléfono. Para regenerar las dos (unos 30 s; lee
`resultados/` y `datos/edomex/municipios_edomex.gpkg`, no descarga nada):

```bash
python src/mapa_interactivo.py resultados/edomex_serie_2023_2025 resultados/edomex_2025_2026_sepoct \
  --unidades datos/edomex/municipios_edomex.gpkg --campo-unidad NOM_MUN \
  --titulo "Estado de México" --validacion resultados/validacion_hansen \
  --salida docs/mapa_edomex.html --sitio docs/calculadora
```

Se puede pedir solo una de las dos (`--salida` o `--sitio`). Cada carpeta puede ser de `correr`
(una comparación) o de `serie` (varias, más el modo "Un año" y la evolución). Si dos carpetas traen
el mismo par de años y temporada, gana la de la serie. Todas deben ser de la misma zona (mismo
`--aoi`). `--validacion` agrega a "Alcances" la precisión contra Hansen. `--sitio` borra y vuelve a
escribir la carpeta `datos/` del sitio.

**Probarla en local.** El sitio no abre como archivo (el navegador no deja leer `datos/` desde
`file://`); hay que servirlo:

```bash
python -m http.server 8766 --bind 127.0.0.1 --directory docs/calculadora
# y abrir http://127.0.0.1:8766/
```


**Archivos del sitio** (todo JSON compacto en UTF-8; las hectáreas, con 2 decimales por municipio y
1 en el Estado):

```
docs/calculadora/
├── index.html                       La página, sin datos (~80 kB)
└── datos/
    ├── indice.json                  Lo mínimo para arrancar: título, malla (CRS, origen, tamaño de
    │                                celda), tipos, campos, años, comparaciones (metadatos y banderas
    │                                preliminar / fuego_incompleto), umbral, totales del Estado por
    │                                año y tipo (`serie.tot`), evolucion_estatal, tendencia del
    │                                Estado, validación y la lista de archivos
    ├── municipios.topojson          125 municipios (`municipios`) y el contorno (`estado`), en
    │                                EPSG:32614, con arcos compartidos y simplificados a 45 m
    ├── anios/AAAA.json              Un año: por municipio y tipo de bosque [zona, bosque, incendio,
    │                                otras pérdidas, ganancia, neto] (los cambios, respecto del año
    │                                anterior; None en el primero), destino de las otras pérdidas,
    │                                bosque sin encadenar, escenas, y lo mismo para el Estado
    ├── tendencias.json              Tendencia de la serie (ha/año, %/año) por municipio y tipo
    ├── comparaciones/<id>.json      Una comparación: filas por municipio, totales, incendios, notas
    │                                y desglose por tipo. <id> = <base>_<actual>; los preliminares
    │                                llevan además su ventana (2025_2026_0901_1020)
    └── cuadriculas/                 Cuadrícula de 90 m como PNG en gris (clase × paso):
                                     bosque_AAAA.png, cambio_<id>.png, anio_perdida.png
```

La página pide al abrir solo `indice.json`, `municipios.topojson`, la comparación inicial y su
cuadrícula; un año, la tendencia, otra comparación o una cuadrícula se piden al consultarlos (con
"Cargando…" sobre el mapa y, si un archivo falla, un mensaje con "Reintentar"). Los municipios se
dibujan con `d3.geoIdentity` usando la malla del índice, la misma transformación de la cuadrícula,
así que quedan alineados con ella. Las cuadrículas son PNG y no COG porque el navegador no lee COG
sin otra librería; los GeoTIFF para QGIS siguen en `resultados/`. La estructura deja lugar para el
histograma del balance, los incendios, el uso del suelo y las especies (M7.2–M7.5) como archivos
nuevos en `datos/` listados en el índice.

**Pruebas de la página** (HU-7.1, en `pruebas/calculadora/`): necesitan las dependencias de
desarrollo y Chromium de Playwright, y prueban lo que ya está en `docs/` (no lo regeneran):

```bash
pip install -r requirements-dev.txt
python -m playwright install chromium
python -m pytest pruebas/calculadora -q
```

Revisan que cada año del índice tenga su archivo con los 125 municipios y el Estado, que sus
hectáreas coincidan con `serie_2023_2025.csv` (y la suma de los municipios con el Estado), que la
página abra sin errores con la evolución a la vista (un punto por año), que la carga sea diferida,
que el contorno y la cuadrícula estén alineados y que el archivo único traiga los mismos datos que
el sitio. Dejan capturas en `entregas/sprint_1/capturas/`.

**Identificadores.** Las Tablas de necesidades v12 renumeraron las necesidades de la Calculadora a
CF-DEV-01…05: 01 masa forestal por año (M7.1), 02 balance entre dos años con histograma (M7.2),
03 incendios (M7.3), 04 cambio de uso del suelo (M7.4) y 05 especies (M7.5). El resto de este README
y el CHANGELOG hasta 0.7.0 usan la numeración anterior: CF-DEV-03 vegetación (clave de la Serie
VII), 04 tipo de bosque, 07 destino de las pérdidas, 08 serie, 09 validación con Hansen, 10 consulta
de un año, 12 año de pérdida y 14 alcances.

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

## Resultados del estado: serie 2023 → 2025

Serie de noviembre-diciembre corrida con `serie --bloques` el 4 de noviembre de 2026 (versión
0.7.0): zona forestal `^(B|S|M|VSA/)` (512,576 ha), umbral NDVI fijo 0.51, 115, 213 y 202 escenas,
9 teselas y 1,092 incendios. Tardó 1 h 59 min con 4.8 GB de RAM pico. Se explora en
[`docs/mapa_edomex.html`](docs/mapa_edomex.html); detalles en
[`resultados/edomex_serie_2023_2025/LEEME.md`](resultados/edomex_serie_2023_2025/LEEME.md).

| Comparación | Bosque inicial | Pérdida por incendio | Otras pérdidas | Ganancia | Bosque final | Cambio neto |
|---|---|---|---|---|---|---|
| 2023 → 2024 | 473,148 | 711 | 9,436 | 4,954 | 467,955 | −5,194 (−1.1 %) |
| 2024 → 2025 | 467,955 | 0 ¹ | 6,080 | 4,183 | 466,058 | −1,897 (−0.4 %) |
| 2023 → 2025 | 473,148 | 361 ¹ | 11,475 | 4,745 | 466,058 | −7,091 (−1.5 %) |
| 2025 → 2026, sep-oct (preliminar) ² | 458,667 | 0 ¹ | 22,475 | 18,143 | 454,334 | −4,332 (−0.9 %) |

Hectáreas. ¹ Todavía no hay polígonos de incendios de 2025 ni de 2026, así que esa pérdida cae en
"otras pérdidas". En 2023 → 2025 solo cuentan los incendios hasta octubre de 2024, y la pérdida
por incendio es menor que en 2023 → 2024 porque parte de lo quemado ya recuperó copa.

² Corrida aparte (`correr --ventana 09-01 10-20 --umbral-ndvi auto`, umbral 0.51), en
[`resultados/edomex_2025_2026_sepoct/`](resultados/edomex_2025_2026_sepoct/LEEME.md). Es el final
de las lluvias, con más nubes y vegetación que cambia de verdor: sus pérdidas y ganancias son de 3
a 5 veces las de noviembre-diciembre y en algunos municipios se ven exageradas (Valle de Bravo
daría −13.6 %). Sirve para ver dónde revisar, no se compara con las otras filas.

- **Tendencia:** −3,545 ha/año (−0.75 %/año). Con 3 años es casi el cambio total entre 2; todavía
  no separa una tendencia de la variación de un año.
- **Por tipo** (ha/año): selva baja caducifolia −2,645 (−6.5 %/año), coníferas −764, encino −749,
  mesófilo −25, otro +26 y zonas semiáridas +612 (el matorral casi no llega al umbral y oscila).
- **Municipios:** Luvianos −1,662 ha/año (−6.9 %), Otzoloapan −449 (−9.4 %), Santo Tomás −334
  (−13.8 %), Tlatlaya −311 y Ocuilan −188. Los cuatro primeros son de selva baja.
- **Incendios 2023 → 2024:** CONAFOR reportó 52,325 ha de polígonos; 16,214 ha tienen dNBR ≥ 0.27,
  8,395 ha estaban en bosque y 711 seguían sin copa en nov-dic 2024.
- **Destino de las otras pérdidas:** 2023 → 2024 agrícola 2,834 ha, pecuario 4,921, urbano 432 y
  otro 1,250; 2024 → 2025 agrícola 1,195, pecuario 3,124, urbano 272 y otro 1,490. El
  clasificador acierta 54.9 % y 54.6 % (kappa 0.39) contra la Serie VII: urbano separa bien
  (68 %), pecuario mal (43–44 %). Es bajo; ver la opción B en
  [Decisiones de diseño](#uso-al-que-pasó-el-terreno-cf-dev-07-opción-a).
- **Selva baja caducifolia:** pierde 7.8 % de su bosque en 2023 → 2024 y 7.1 % en 2024 → 2025, y
  casi no gana. Hansen casi no ve pérdida ahí (en Luvianos, precisión de 1 % y 0.1 %). Lo más
  probable es la caída de hojas de nov-dic, que cambia de fecha cada año; falta decidir si se le
  da otra ventana, su propio umbral o se saca de la zona.

### Contra las corridas directas anteriores

Las corridas de octubre de 2026 (zona `^(B|VSA/)`, cada par por separado) están en
[`resultados/anteriores_0.5/`](resultados/anteriores_0.5/LEEME.md). Dentro de esa zona:

| Zona anterior | Corrida directa | Serie encadenada |
|---|---|---|
| 2023 → 2024 | 459,262 → 453,450 (−5,812) | idéntico |
| 2024 → 2025 | 450,768 → 451,950 (+1,182) | 453,450 → 454,276 (+826) |
| 2023 → 2025 | 459,262 → 454,634 (−4,628) | 459,262 → 454,276 (−4,986) |

Antes el 2024 tenía dos valores: 453,450 ha como año final de 2023 → 2024 (conserva el bosque que
bajó del umbral por menos de 0.10 de NDVI) y 450,768 como año base de 2024 → 2025 (medido desde
cero). Con la serie cada año tiene un solo valor y los cambios se suman exactamente. La diferencia
con el bosque de solo el umbral es de 2,525 ha en 2024 y 2,345 en 2025 (0.5 %;
`bosque_sin_encadenar_ha`). La zona ampliada agrega 13,886 ha de bosque en 2023: 12,748 de SBC,
1,062 de MC y 76 de MDR.

## Validación contra Hansen GFC (CF-DEV-09)

`src/validar_hansen.py` compara la pérdida del prototipo con la de Hansen Global Forest Change
v1.13, la única versión que trae 2025. Sin argumentos compara 2023 → 2024 de la serie con la
pérdida de Hansen 2024, y 2024 → 2025 con la de 2025, dentro de la zona `^(B|S|M|VSA/)`. Tarda
~2 min la primera vez y menos de 1 min después.

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
| Pérdida del prototipo | 10,147 ha | 6,080 ha |
| Pérdida de Hansen (zona forestal) | 1,890 ha | 1,342 ha |
| Coinciden | 583 ha | 156 ha |
| Precisión (exacta / con 30 m de tolerancia) | 6 % / 8 % | 3 % / 4 % |
| Exhaustividad (exacta / con 30 m de tolerancia) | 31 % / 69 % | 12 % / 36 % |

- Casi todo el desacuerdo está en las "otras pérdidas", que coinciden solo 3 %. La pérdida por
  incendio coincide 40 %.
- Con la zona anterior la precisión era de 7 % y 5 %. Bajó porque la selva baja y el matorral
  agregan pérdida que Hansen no marca; Hansen solo agrega 9 ha.
- Desacuerdo casi total en la selva baja (Luvianos, Otzoloapan, Santo Tomás) y en las laderas de
  los volcanes (Atlautla, Amecameca, Tlalmanalco). Son los primeros lugares que conviene
  fotointerpretar.
- Donde hay un evento grande, como en San Simón de Guerrero en 2024, las dos fuentes lo ven.

`src/muestra_puntos.py` arma una muestra estratificada de 105 puntos (15 en cada uno de 7
estratos de cambio y Hansen) para fotointerpretar. La muestra se sorteó con la zona anterior y
está en `resultados/anteriores_0.5/validacion_hansen/muestra_puntos_2023_2024.csv`. Es compatible
con `calibrar --puntos` y trae la columna `clase` vacía. No cubre la selva baja ni el matorral.

## Decisiones de diseño

Tomadas el 3 de noviembre de 2026 para cubrir las necesidades CF-DEV-03, 04 y 07 del Módulo 13
de la propuesta. **Programadas en la versión 0.6.0** y usadas en la serie estatal de 0.7.0.

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
- **Efecto:** cambian los totales de todos los balances. En la serie estatal agrega 13,886 ha de
  bosque en 2023.
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
reconocida externamente en lugar de una propia. **En el estado, A acierta 55 % (kappa 0.39)
en 2024 y 2025, y 52 % (kappa 0.35) en el preliminar sep-oct**: más que en la prueba de Otzoloapan
y Tequixquiac (48 %), pero bajo. Pecuario es la clase más confundida (con agrícola y con otro).
Antes de pasar a B se pueden probar rasgos de otra temporada.

## Pendientes

1. Calibrar el umbral de NDVI con ~100 puntos de referencia. Mientras tanto, `auto` cambia según
   la zona que se corre, así que conviene fijar un umbral numérico para comparar corridas.
2. Conseguir los polígonos de reforestación de PS, RHF y CC, con año de plantación, sobrevivencia
   y programa. Con el programa se completa la ganancia por programa (CF-DEV-05).
3. Decidir cómo tratar la selva baja caducifolia, que pierde ~7 % al año en nov-dic y casi no
   coincide con Hansen: otra ventana, su propio umbral o dejarla fuera de la zona.
4. Mejorar el clasificador del destino (55 %, kappa 0.39 en el estado): probar rasgos de otra
   temporada o pasar a la opción B.
5. Verificar las "otras pérdidas" del estado (9,436 ha en 2023 → 2024 y 6,080 en 2024 → 2025),
   empezando por Luvianos, Tlatlaya, Temascaltepec, Atlautla, Ocuilan y Santo Tomás.
6. Bajar el tiempo de los incendios. Es la parte más lenta y no cambió con los bloques.
7. Validación (CF-DEV-09): la comparación con Hansen ya está hecha con la zona ampliada. Falta:
   - fotointerpretar los 105 puntos de
     `resultados/anteriores_0.5/validacion_hansen/muestra_puntos_2023_2024.csv` y sortear puntos
     en la selva baja y el matorral;
   - hacer que `calibrar` lea el NDVI por bloques o solo en los puntos, porque hoy arma el
     compuesto de toda la `--aoi` de una vez y con el estado no cabe en memoria;
   - comparar con las verificaciones de campo de los programas, cuando existan.
8. Agregar los incendios de 2025 a la serie cuando CONAFOR publique su capa, y agregar 2026 a la
   serie en enero de 2027, cuando exista el compuesto de noviembre-diciembre de 2026.
9. Escenarios de recuperación y ampliar la página interactiva como tablero para la Dirección
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
