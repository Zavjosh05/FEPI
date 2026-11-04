# Registro de cambios

Los cambios importantes del proyecto se anotan aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[Versionado Semántico](https://semver.org/lang/es/). Mientras sea prototipo, se queda en 0.x.

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
