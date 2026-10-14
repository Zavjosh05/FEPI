# Registro de cambios

Los cambios importantes del proyecto se anotan aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[Versionado Semántico](https://semver.org/lang/es/). Mientras sea prototipo, se queda en 0.x.

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
