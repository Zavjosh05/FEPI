# Registro de cambios

Los cambios importantes del proyecto se anotan aquí. El formato sigue
[Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y las versiones siguen
[Versionado Semántico](https://semver.org/lang/es/). Mientras sea prototipo, se queda en 0.x.

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
