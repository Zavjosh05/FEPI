# Registro de cambios

Los cambios importantes del proyecto se anotan aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[Versionado Semántico](https://semver.org/lang/es/). Mientras sea prototipo, se queda en 0.x.

## [0.7.0] - 2026-11-04

Serie anual y tendencia (CF-DEV-08), consulta de un año (CF-DEV-10), capa de pérdida por año
(CF-DEV-12) y documentación de alcances (CF-DEV-14).

### Agregado

- **Subcomando `serie --anios 2023 2024 2025 ...`** (mismas opciones que `correr`).
  - En cada bloque lee una sola vez el compuesto de cada año y encadena el bosque: el primer año es
    NDVI ≥ umbral dentro de la zona; en cada año siguiente un píxel solo cambia si cruza el umbral
    y su NDVI cambió al menos 0.10 respecto del año anterior (`mascaras_serie`).
  - Cada incendio cuenta en su periodo (1-nov a 31-oct) con el dNBR en paralelo de siempre.
  - Arma todas las comparaciones entre los años pedidos, cada una con las salidas de `correr`; la
    de años no consecutivos compara el bosque del primer año con el del último, así que la cifra
    de cada año es la misma en todas.
  - Un clasificador de destino por año, entrenado con el compuesto de ese año.
  - Salidas nuevas: `serie_<a0>_<aN>.csv` (por unidad, año y tipo de bosque, con el destino y el
    bosque sin encadenar), `tendencia_<a0>_<aN>.csv` (ha/año y %/año por mínimos cuadrados, y R²),
    `bosque_por_anio.tif` (bit *t* = bosque en el año *t*), `anio_perdida.tif` (año − 2000 de la
    última pérdida), `serie_<a0>_<aN>.json` e `incendios_dnbr_<a>_<b>.csv` de las comparaciones
    largas.
- **Página:** modo "Un año" (mapa del bosque de ese año por densidad, cifras, tabla por municipio
  y por tipo de bosque, destino de las otras pérdidas), capa "Año de pérdida", vista de tendencia
  por municipio, gráfica de la serie con su recta de tendencia en el detalle y sección "Alcances".
  Los colores nuevos son rampas ordinales de un solo tono validadas en los dos temas.
  `mapa_interactivo.py` acepta carpetas con varias comparaciones y `--validacion`.
- `demo` comprueba también la serie: de 3 y de 4 años, de una sola vez, por bloques, con incendios
  en paralelo e interrumpida y reanudada, contra una referencia escrita aparte; y que con dos años
  `mascaras_serie` es la regla de `correr`. Se probó que detecta cuatro fallas inyectadas.

### Cambiado

- `correr` usa el mismo motor que `serie` (es la serie de dos años). Sus salidas no cambian: en el
  piloto da IDÉNTICO a la corrida 0.6.0 en todos los archivos, y `serie --anios 2023 2024` da
  IDÉNTICO a `correr`. El avance guardado (`progreso_*`) tiene otro formato: una corrida 0.6.0
  interrumpida no se reanuda con 0.7.0.
- `incendios_dnbr.csv` trae la columna `periodo`. `bloques_*.csv` de una serie trae
  `escenas_<año>` en lugar de `escenas_base` y `escenas_actual`.
- `comparar_resultados.py` compara también `serie_*.csv`, `tendencia_*.csv`, `bosque_por_anio.tif`
  y `anio_perdida.tif`, y con `--periodo` filtra los incendios por su columna `periodo`.
- `validar_hansen.py`: por defecto usa la zona `^(B|S|M|VSA/)` y las comparaciones de un año de
  `resultados/edomex_serie_2023_2025`.
- Las comparaciones nov-dic de la página salen de la serie y ya no de corridas directas. Las
  corridas estatales de la zona anterior pasaron a `resultados/anteriores_0.5/`.

### Resultados (corridas estatales del 4-nov-2026, zona `^(B|S|M|VSA/)`)

- **Serie 2023 → 2025** (`resultados/edomex_serie_2023_2025/`, umbral 0.51, 1 h 59 min, 4.8 GB):
  bosque 473,148 → 467,955 → 466,058 ha; −3,545 ha/año (−0.75 %/año). Dentro de la zona anterior,
  2023 → 2024 da IDÉNTICO a la corrida de octubre; 2024 vale 453,450 ha en todas las comparaciones
  (antes 453,450 y 450,768), así que 2024 → 2025 pasa de +1,182 a +826 y 2023 → 2025 de −4,628 a
  −4,986.
- **Selva baja caducifolia:** pierde 7.8 % y 7.1 % al año en nov-dic, casi sin ganancia, y Hansen
  casi no lo ve (Luvianos: precisión 1 % y 0.1 %). Probable caída de hojas; pendiente de decidir.
- **Destino:** el clasificador acierta 54.9 % y 54.6 % (kappa 0.39) contra la Serie VII; pecuario
  es la clase más confundida.
- **Preliminar sep-oct 2025 → 2026** (`resultados/edomex_2025_2026_sepoct/`, umbral auto 0.51):
  458,667 → 454,334 ha (−4,332). Clasificador 52.3 % (kappa 0.35).
- **Hansen** (`resultados/validacion_hansen/`): precisión 6 % y 3 %, exhaustividad 31 % y 12 %
  (antes 7 % y 5 %, 31 % y 12 %). La muestra de 105 puntos sigue en
  `resultados/anteriores_0.5/validacion_hansen/`.

## [0.6.0] - 2026-11-03

Programa las decisiones de diseño del 3 de noviembre (CF-DEV-03, CF-DEV-04 y CF-DEV-07, opción A).

### Cambiado

- La zona forestal por defecto (`--clases-forestales`) pasa de `^(B|VSA/)` a `^(B|S|M|VSA/)`:
  agrega selva baja caducifolia (`SBC`) y matorrales (`MC`, `MDR`). En el Estado de México son
  512,577 ha en lugar de 484,695. Los balances estatales guardados son de la zona anterior y hay
  que volver a correrlos. Para repetir una corrida anterior: `--clases-forestales "^(B|VSA/)"`.
- `src/comparar_resultados.py` compara también los desgloses, el destino y su ráster cuando las
  dos carpetas los tienen; si solo una los tiene (corridas anteriores), los omite sin fallar.

### Agregado

- **Cruce con la Serie VII (CF-DEV-03):** la clave (`CLAVE`) se rasteriza por bloque y
  `vegetacion_<base>_<actual>.csv` da, por unidad y clave, la zona forestal, el bosque inicial, la
  pérdida por incendio, las otras pérdidas, la ganancia y el bosque final. Suma lo mismo que el
  balance.
- **Tipo de bosque (CF-DEV-04):** `tipo_bosque_<base>_<actual>.csv`, por unidad y tipo: coníferas
  (BA, BP, BPQ, BJ, BB, BG y sus VSA/), encino (BQ, BQP y sus VSA/), mesófilo de montaña (BM y
  VSA/BM), selva baja caducifolia (SBC, VSA/SBC), vegetación de zonas semiáridas (MC, MDR) y otro
  (BC, bosque cultivado, y lo que no encaje).
- **Uso al que pasó el terreno (CF-DEV-07, opción A):** cada píxel de "otra pérdida" se clasifica
  como agrícola, pecuario, urbano u otro.
  - Bosque aleatorio (scikit-learn, 200 árboles) con la mediana nov-dic del año actual de B03,
    B04, B08, B8A, B11, B12, NDVI, NBR, NDBI y MNDWI.
  - Etiquetas de las zonas no forestales de la Serie VII: `T*`, `R*` y `HA` agrícola; `PI` y `PC`
    pecuario; `AH` urbano; lo demás, otro. Muestras en una retícula de 250 m, como máximo 1,500
    por clase y región de 100 km.
  - Exactitud con las muestras de 1 de cada 5 celdas de 5 km, reservadas
    (`destino_exactitud_<base>_<actual>.csv`). Mide el acuerdo con la Serie VII, anterior a 2023.
  - Salidas `destino_perdidas_<base>_<actual>.csv` por unidad y `destino_<base>_<actual>.tif`
    (uint8). Se desactiva con `--no-clasificar-destino`; las clases de entrenamiento se cambian
    con `--clases-agricola`, `--clases-pecuario` y `--clases-urbano`.
  - Lee 6 bandas más del año actual, solo en los píxeles que necesita.
- La ganancia por programa (CF-DEV-05) queda pendiente: `ganancia_por_programa` marca el punto de
  conexión para cuando lleguen los polígonos de PROBOSQUE.
- `demo`: comprueba que el desglose por clave y tipo, el clasificador, la tabla de destino y su
  ráster salen idénticos por bloques, de una sola vez, con incendios en paralelo y en corridas
  interrumpidas y reanudadas.
- Página interactiva: desglose por tipo de bosque del periodo elegido, del estado (sin municipio
  elegido) y de cada municipio. Las corridas sin `tipo_bosque_*.csv` lo dicen.
- `requirements.txt`: scikit-learn 1.9.1.

### Verificado

- El piloto con `--clases-forestales "^(B|VSA/)"` da IDÉNTICO a `resultados/piloto_2023_2024`. Con
  la zona nueva también, porque el piloto no tiene claves `S*` ni `M*`. Por bloques y de una sola
  vez, todas las salidas nuevas dan IDÉNTICO.
- En Otzoloapan y Tequixquiac la zona nueva agrega 3,241 ha de zona forestal y 1,698 ha de bosque
  2023. La selva baja pierde 11 % en "otras pérdidas", probablemente por la caída de hojas.
- Exactitud del clasificador de destino: 67 % (kappa 0.40) en el piloto y 48 % (kappa 0.21) en
  Otzoloapan y Tequixquiac. No sube la RAM, pero los bloques tardan ~2.6 veces más.
- Los balances estatales todavía no se vuelven a correr con la zona nueva.

## [0.5.0] - 2026-11-03

### Agregado

- `src/validar_hansen.py`: compara la pérdida de bosque del prototipo con Hansen Global Forest
  Change v1.13 (CF-DEV-09). Lee por ventanas solo la parte del estado de `lossyear` y
  `treecover2000` (~100 MB de internet; recortes de 22 MB en `datos/edomex/hansen/`).
  - Lleva Hansen a la malla de 10 m por vecino más cercano.
  - Calcula, por municipio y para el estado: coincidencias, lo que solo marca cada fuente,
    precisión y exhaustividad (exactas y con 30 m de tolerancia) y la pérdida que Hansen pone un
    año antes o después.
  - Salidas en `resultados/validacion_hansen/`. Tarda ~2 min.
- `src/muestra_puntos.py`: muestra estratificada de puntos (7 estratos de cambio y Hansen) para
  fotointerpretar. Su CSV es compatible con `calibrar --puntos`; la columna `clase` sale vacía.
- README: sección de validación con los resultados.
  - 2023 → 2024: el prototipo marca 8,496 ha, Hansen 1,883 ha y coinciden 580 ha (precisión 7 %,
    exhaustividad 31 %). La pérdida por incendio coincide 40 % y las "otras pérdidas" solo 4 %.
  - 2024 → 2025: precisión 5 % y exhaustividad 12 %.
- README: sección "Decisiones de diseño".
  - La zona forestal se amplía a `^(B|S|M|VSA/)`, de 484,695 a 512,577 ha.
  - El uso al que pasó el terreno (CF-DEV-07) se resolverá con la opción A: clasificar con
    Sentinel-2, entrenando con las clases no forestales del INEGI.
  - La opción B, ESA WorldCover o Dynamic World, queda como nota.
  - Las dos decisiones están documentadas, pero todavía no programadas.

## [0.4.1] - 2026-10-22

### Cambiado

- Página interactiva: los botones de comparación se cambiaron por un selector de años **Desde →
  Hasta**. Las combinaciones sin corrida dicen "sin datos"; si eliges una, el otro año se ajusta
  al más cercano que sí tiene. 2026 aparece como "sep-oct (preliminar)" y solo se compara con 2025.

## [0.4.0] - 2026-10-22

### Agregado

- `src/mapa_cambio.py`: dibuja el mapa PNG de una corrida, con el ráster de cambio y el cambio
  neto por unidad. En zonas grandes, cada celda muestra la pérdida o ganancia si la hay. Los
  colores están validados para daltonismo.
- `resultados/edomex_2023_2024/mapa_cambio_2023_2024.png`: el mapa del estado.
- `matplotlib` en `requirements.txt` (solo para el mapa).
- `src/mapa_interactivo.py` y `src/plantilla_mapa.html`: página HTML interactiva de una o varias
  corridas. Ofrece zoom, capas que se prenden y apagan, cambio neto por municipio, búsqueda,
  detalle por periodo y tabla ordenable, con tema claro y oscuro. Queda en `docs/mapa_edomex.html`.
  - Selector "Comparar" para pasar de una comparación a otra: 2023 → 2024, 2024 → 2025,
    2023 → 2025 y el preliminar de 2026, que va aparte.
- `correr --ventana INICIO FIN` (MM-DD; por defecto 11-01 12-31): días del año de los compuestos.
  El periodo de incendios arranca en el inicio de la ventana.
- El dNBR de los incendios se lee en paralelo (`--hilos-incendios`, 6 por defecto). Las escenas
  de todos los incendios se buscan en una sola consulta al catálogo, y GDAL guarda en RAM (512 MB,
  nada en disco) los pedazos de imagen ya bajados. El resultado es idéntico: el piloto y los 3
  municipios dan igual que antes, y el demo lo comprueba. Con 72 incendios, la corrida bajó de
  9 min 51 s a 7 min 9 s, aun compartiendo la conexión con otra corrida.
- Límites de espera en las conexiones: GDAL corta si no conecta en 30 s o si deja de recibir
  datos por 60 s, y cada consulta al catálogo tiene un límite de 120 s. Antes, una conexión
  colgada podía dejar la corrida esperando para siempre; ahora falla con error y se reanuda con el
  mismo comando.
- `corrida_<base>_<actual>.json` en cada corrida: ventana, umbral, escenas, número de incendios y
  fecha.
- `resultados/edomex_2023_2025/`: balance 2023 → 2025 corrido directo, con umbral fijo 0.51.
- `resultados/edomex_2025_2026_sepoct/`: preliminar de 2026. Compara del 1 de septiembre al 20 de
  octubre de 2025 con lo mismo de 2026, las imágenes más recientes, con umbral automático. Es otra
  temporada, así que sus hectáreas no se comparan con las de los balances de noviembre-diciembre.
- `resultados/edomex_2024_2025/`: balance del estado 2024 → 2025, el más reciente posible. Usa
  imágenes de noviembre-diciembre de 2025 y el umbral fijo 0.51 del periodo anterior, para que
  los dos periodos se puedan comparar. Todavía no hay polígonos de incendios de 2025, así que esas
  pérdidas quedan en "otras pérdidas".

## [0.3.1] - 2026-10-15

### Agregado

- `resultados/edomex_2023_2024/`: balance, incendios, ráster de cambio, tiempos por bloque y
  `LEEME.md` de la primera corrida del estado completo. `.gitignore` ahora versiona esa carpeta,
  sin las bitácoras (`*.log`).

### Cambiado

- README: resultados de las pruebas de `--bloques` con datos reales (Sentinel-2 e IDEFOR).
  - El piloto da idéntico de una sola vez, por bloques y contra el piloto guardado.
  - Un cuadro en la esquina de 4 teselas da idéntico de las dos formas.
  - Tiempos y RAM medidos: piloto en 2 min 12 s con 1.2 GB; 3 municipios en 9 min 51 s con
    2.0 GB.
  - Nuevo estimado para el estado: ~2–2.5 h.
- README: primera corrida del estado completo (2023 → 2024), con su `LEEME.md` en
  `resultados/edomex_2023_2024/`.
  - Bosque: 459,262 → 453,450 ha (−1.3 %); 708 ha perdidas por incendio, 7,788 por otras causas
    (por verificar) y 2,684 ganadas.
  - Tardó ~2 h 08 min con 4.2 GB de RAM.
- README: el umbral automático cambia según la zona que se corre; se recomienda fijar uno numérico
  para comparar corridas.

## [0.3.0] - 2026-10-14

### Agregado

- `correr --bloques`: procesa la zona por bloques en memoria para cubrir todo el estado sin
  pasar de ~4 GB de RAM. Los resultados son los mismos que de una sola vez: no cambia el umbral
  NDVI, el margen 0.10, el dNBR 0.27 ni el periodo de incendios.
  - Bloques de 20.48 km (`--tam-bloque`, en píxeles, múltiplo de 1024), alineados a la malla
    interna de los COG de cada tesela Sentinel-2 para no releer datos. Se saltan los que no tocan
    la zona (84 de 144 para el estado).
  - Cada incendio se calcula una sola vez y da una sola fila aunque cruce bloques.
  - Con `--umbral-ndvi auto`, el histograma de Otsu se arma por bloques y es idéntico al de
    todos los valores juntos.
  - Reanudar: si la corrida se corta, el mismo comando sigue desde el último bloque. El avance
    vive en `<salida>/progreso_<base>_<actual>/` (KB, más los pedazos del ráster de cambio) y se
    borra al terminar. `--reiniciar` lo descarta.
- `--nubes-max` (60 por defecto) y `--escenas-max` (máximo de escenas menos nubladas por tesela en
  los compuestos anuales; sin tope por defecto), también en `calibrar`.
- `--guardar-indices` / `--no-guardar-indices` para los rásters de NDVI y dNBR.
- `bloques_<base>_<actual>.csv`: escenas, segundos y RAM pico de cada bloque.
- El modo `demo` comprueba que por bloques da exactamente lo mismo que de una sola vez.
- `src/comparar_resultados.py`: compara dos corridas (balance por unidad, incendios por clave y
  píxeles distintos del ráster de cambio).

### Cambiado

- Las escenas de cada año se buscan una sola vez para toda la zona; cada bloque usa las que se
  traslapan con él.
- Los rásters de NDVI y dNBR ya solo se guardan por defecto de una sola vez. Con `--bloques` hay
  que pedirlos.
- `cambio_<base>_<actual>.tif` se escribe en mosaicos de 512 px (antes en tiras); los valores no
  cambian.
- README: secciones "Uso", "Cobertura geográfica" (con los tiempos medidos) y "Pendientes".

## [0.2.0] - 2026-10-14

### Agregado

- `src/descargar_capas.py`: descarga del WFS de IDEFOR (CONAFOR) las capas del Estado de México:
  - el límite estatal;
  - los 125 municipios;
  - la Serie VII de INEGI recortada al estado;
  - los incendios 2019–2024 en una sola capa.

  Verifica que lleguen todos los polígonos y registra fecha y filtros en `descarga.json`.
- `requirements.txt` con las versiones probadas (Python 3.13 en Windows).
- `.gitignore`: ignora el venv, los datos descargados, las corridas nuevas en `resultados/` (salvo
  el piloto) y los auxiliares de QGIS y GDAL.
- `README.md`: instalación, datos, uso, cobertura geográfica, resultados del piloto, pendientes,
  y de dónde sale cada dato y si es de uso libre, con los créditos que hay que poner.
- `CHANGELOG.md`.

### Cambiado

- Estructura del repositorio: el contenido de `piloto_masa_forestal/` se repartió en `src/`,
  `datos/piloto/` y `resultados/piloto_2023_2024/`.
- `LEEME.txt` del piloto pasó a `resultados/piloto_2023_2024/LEEME.md`, con las rutas nuevas.
  También anota que en nov-dic 2023 no hubo incendios en la zona del piloto, así que usar solo la
  capa 2024 no dejó nada fuera.

### Corregido

- Las fechas de la capa de incendios 2020 vienen con hora y zona (`2020-04-03T12:00:00Z`).
  Mezcladas con las de otros años rompían la lectura de fechas del prototipo. Ahora se guardan
  como `AAAA-MM-DD` al descargar.

## [0.1.0] - prototipo y piloto

La fecha no quedó registrada; el proyecto se agregó al repositorio el 2026-10-14.

### Agregado

- `prototipo_masa_forestal.py`, con los subcomandos `demo`, `calibrar` y `correr`. El cálculo usa:
  - un balance de superficie arbórea con compuestos NDVI de Sentinel-2 de noviembre-diciembre;
  - la zona forestal de INEGI Serie VII;
  - un margen de cambio de NDVI de 0.10;
  - quemado por dNBR ≥ 0.27;
  - la recuperación esperada contra la observada.
- Piloto en Amecameca y Tlalmanalco, 2023 → 2024, con sus datos de entrada y resultados.
