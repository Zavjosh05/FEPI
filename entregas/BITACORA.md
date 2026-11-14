# Bitácora de decisiones y propuestas

Registro de lo que se propuso, por qué, y si se hizo o no, durante la construcción de los prototipos
(Sistema de programas en `sistema/` y Calculadora forestal en `src/` y `docs/`). El avance tarea por
tarea está en [AVANCE.md](AVANCE.md); aquí queda el porqué.

**Cómo leerla.** Cada renglón tiene un identificador que no cambia (`T-03`, `R-05`…), para poder citarlo
en un commit o en una entrega. La columna **Estado** usa siempre una de estas palabras:

| Estado | Significa |
| --- | --- |
| Hecho | Está en el repositorio y verificado; se indica el commit o el archivo. |
| Aceptado | Joshua lo aprobó; falta hacerlo (se indica en qué sprint). |
| Propuesto | Recomendación sin respuesta todavía. |
| Por decidir | Depende de Joshua o del cliente; se anota la recomendación. |
| Descartado | Se evaluó y no se hará; se dice por qué. |

Reglas de la bitácora: se agrega un renglón cuando se propone algo, no cuando ya está hecho; un renglón
no se borra, se le cambia el estado; y lo que contradiga a las Reglas de Operación se resuelve a favor de
las Reglas y se anota aquí.

---

## 1. Tecnologías y entorno (revisión de la propuesta del 12-nov-2026)

Veredicto: la pila de la propuesta se conserva completa. Los cambios son de entorno y de detalle.

| ID | Propuesta | Por qué | Estado |
| --- | --- | --- | --- |
| T-01 | Conservar Django + GeoDjango, PostgreSQL + PostGIS, HTMX, Bootstrap 5, Leaflet, WeasyPrint, django-simple-history, pytest + Playwright y Docker Compose. | Es una pila libre, madura y de un solo lenguaje; nada de lo revisado justificó cambiarla. | Hecho (13-nov, `6f6a11f`) |
| T-02 | Instalar Docker Engine dentro de WSL (Ubuntu 24.04) en el equipo de desarrollo. | El equipo no tenía Docker ni PostgreSQL, y GeoDjango, PostGIS y WeasyPrint son difíciles en Windows nativo; sin Docker no se puede verificar «levanta con `docker compose up`». | Hecho (13-nov; decisión de Joshua) |
| T-03 | Cambiar la pila a geometrías en GeoJSON + SQLite para no instalar nada. | Evitaba instalar, pero dejaba sin probar Docker, PostGIS y los PDF. | Descartado (Joshua eligió T-02) |
| T-04 | Copiar HTMX, Bootstrap, Leaflet y Leaflet-Geoman al proyecto (`estaticos/vendor/`) en lugar de usar CDN. | Conectividad de las Delegaciones; el sistema no debe depender de internet para verse. | Hecho (`6f6a11f`) |
| T-05 | Polígonos por carga de archivo (GeoJSON, KML, Shapefile en zip) además del dibujo en el mapa. | El polígono se levanta en campo con GPS; dibujarlo a mano es solo respaldo. | Hecho (`15e7511`) |
| T-06 | Playwright en su versión de Python. | Un solo lenguaje; no se agrega Node. | Hecho |
| T-07 | Servicio `plazos` como contenedor que corre `revisar_plazos` una vez al día, en lugar de un demonio cron. | Mismo efecto con una pieza menos. | Hecho (`6f6a11f`) |
| T-08 | Django 5.2 (versión de soporte extendido) con todas las versiones fijadas. | Un sistema de gobierno debe poder mantenerse años sin migrar de versión. | Hecho |
| T-09 | Imagen base Debian 13 en lugar de Debian 12. | Con GDAL 3.6 Django advierte de riesgo al leer archivos espaciales subidos por usuarios; con 3.10 no. | Hecho |
| T-10 | Código del sistema en la carpeta `sistema/` de este mismo repositorio. | La propuesta pide «repositorio en GitHub» sin más; un solo repositorio simplifica entregas y revisión. | Hecho |
| T-11 | Versionar la especificación que el sistema necesita (`modelo.json`, necesidades v12 y texto de las ROP) en `sistema/especificacion/`. | Las pruebas y las reglas deben poder correr con solo clonar el repositorio. | Hecho (`6f6a11f`) |
| T-12 | Servidor para las demostraciones (de PROBOSQUE o VPS). | Pendiente desde la propuesta. | Por decidir (cliente) |

## 2. Calculadora forestal

| ID | Propuesta | Por qué | Estado |
| --- | --- | --- | --- |
| C-01 | Publicar la página como sitio por archivos (`docs/calculadora/`): índice, municipios en TopoJSON, un archivo por año y por comparación, cuadrículas en PNG. | Es la «opción A» de la propuesta; la carga inicial baja de 2.76 MB a 438 kB. | Hecho (HU-7.1, `d8b71ff`) |
| C-02 | Conservar además el archivo único `docs/mapa_edomex.html`. | La página por archivos usa `fetch` y ya no abre con doble clic; el archivo único sí. | Hecho (`d8b71ff`) |
| C-03 | Cuadrícula en PNG y no en COG. | El navegador no lee COG sin otra biblioteca; los GeoTIFF para QGIS ya salen del cálculo. | Hecho |
| C-04 | Corregir el total estatal de 2023: la página mostraba 473,149 ha y la suma es 473,148.48. | Doble redondeo heredado de la versión 0.7.0. Es la única cifra que cambia. | Hecho (`d8b71ff`) |
| C-05 | Tabla de equivalencias de identificadores: las necesidades v12 son CF-DEV-01 a 05; el README y el CHANGELOG hasta 0.7.0 usan una numeración anterior. | Sin la tabla, «CF-DEV-03» significa dos cosas distintas. | Hecho (README) |
| C-06 | No tocar el motor de cálculo en los tres sprints. | Las historias M7 piden consulta y publicación; el cálculo ya existe. | Aceptado |
| C-07 | Presentar el uso del suelo (HU-7.4) como estimación, con su exactitud (~55 %), año y fuente, y marcar los años sin dato oficial del INEGI. | El clasificador ya existe pero acierta poco; decirlo cumple los dos criterios sin aparentar precisión. | Aceptado (sprint 3) |
| C-08 | Adelantar al sprint 2 la investigación de los datos del INFyS para HU-7.5 (¿traen coordenadas?, ¿cómo se descargan?). | HU-7.2 y HU-7.3 están casi hechas y el sprint 3 es el más cargado. | Aceptado (sprint 2) |
| C-09 | Corregir en la propuesta el tiempo de proceso: dice «10 horas para 125 municipios»; la corrida estatal real tarda ~2 h. | Dato desactualizado del documento. | Propuesto (lo edita Joshua) |
| C-10 | Pendientes de método que deben seguir visibles en «Alcances»: selva baja que pierde 7–8 % al año (probable caída de hojas), 6 % de precisión contra Hansen, umbral NDVI sin calibrar. | No bloquean las historias, pero condicionan cómo se leen las cifras. | Propuesto |
| C-11 | Probar el sitio en GitHub Pages real y el modo `--fragmento`. | Solo se probó con un servidor local. | Por decidir (publicar es decisión de Joshua) |

## 3. Reglas de Operación: lo que se encontró

Las reglas de cada programa se guardan como datos (`sistema/reglas/<CLAVE>.json`), cada dato con su
numeral y la línea del texto de las ROP.

| ID | Hallazgo o propuesta | Consecuencia | Estado |
| --- | --- | --- | --- |
| R-01 | Extraer las reglas de Capturando Carbono a datos: 26 requisitos, 23 plazos, 2 montos, 3 ministraciones, 8 formatos. | Ningún requisito ni plazo está escrito en el código. | Hecho (`6f6a11f`) |
| R-02 | La Convocatoria sí dice qué municipios atiende cada Delegación (9 Delegaciones, 125 municipios). | Se usa tal cual, mostrado como «por confirmar con el cliente»; ya no hizo falta una asignación provisional. | Hecho; confirmación: Por decidir (cliente) |
| R-03 | Firma del contrato en 10 días hábiles: la Convocatoria los cuenta desde la publicación de resultados y el numeral 8.1.9 b) fr. IV desde la notificación. | El evento que arranca el plazo será un parámetro del programa. | Aceptado (sprint 2); cuál prevalece: Por decidir (cliente) |
| R-04 | Los «15 días hábiles de verificación» de CC son para entregar el Informe Final o la minuta, no para hacer la visita. | HU-4.2 debe medir la entrega del informe. | Aceptado (sprint 3) |
| R-05 | Las ROP no dan plazo en días para publicar resultados, pagar ni reintegrar. | Esos plazos quedan sin vencimiento calculado; solo se registra fecha y hora. | Por decidir (cliente) |
| R-06 | CC habla de «puntaje más alto» pero no trae tabla de puntos. | El orden propuesto al Comité es: reforestaciones, luego refrendos, y desempate por fecha de registro; el Comité puede ajustarlo dejando constancia. | Hecho (`40ac657`); la regla: Por decidir (cliente) |
| R-07 | Ni el texto ni el PDF traen los formatos FO-PB-509-A y 520-B, el modelo de Contrato de Adhesión ni el oficio de solicitud de pago. | Ver S2-04. | Por decidir (cliente) |
| R-08 | Las ROP no listan días inhábiles. | Calendario de demostración 2026 (11 días), editable. | Hecho |
| R-09 | El polígono se levanta después de entregar el expediente (CC 10.1 fr. III). | No es condición para enviar el expediente a la Dirección. | Hecho (`2c92b2c`) |
| R-10 | Los listados, incluidas las solicitudes no factibles, los aprueba el Comité (CC 10.1 fr. VI y VII; 9.4.3). | Se quitó el paso directo de «validada» a «no factible»; los dictámenes solo forman el listado preliminar. | Hecho (`50269bf`) |
| R-11 | El plazo de dictaminación de CC es una fecha límite (30-jun-2026), no una cantidad de días. | En la demostración los dictámenes de CC aparecen vencidos; es correcto con la fecha de hoy. Ver P-03. | Hecho |
| R-12 | Aviso de faltantes: 5 días hábiles, pero no dice si corren desde el aviso o desde la notificación. | Hoy corren desde el aviso. | Por decidir (cliente) |

## 4. Sprint 1: decisiones de diseño

| ID | Decisión | Por qué | Estado |
| --- | --- | --- | --- |
| D-01 | Estados del trámite como tabla de transiciones (`datos/flujo_tramite.json`) y un solo punto del código que cambia el estado, valida la unidad y escribe la bitácora. | Lo pide la propuesta (sin librería de estados) y hace que cada sprint agregue estados sin tocar lo anterior. | Hecho (`6f6a11f`) |
| D-02 | Cada envío o entrega registra quién, fecha y hora, y genera un acuse en PDF con folio. | Lineamiento del profesor y de las ROP. | Hecho |
| D-03 | Permisos por unidad: una Delegación solo ve sus expedientes; una Dirección, los de sus programas; los archivos no tienen dirección pública. | Datos personales y documentos legales. | Hecho |
| D-04 | Regla de envío a la Dirección: todos los requisitos revisados, ninguno faltante y cada entregado con su archivo (o documentación vigente en refrendo). | ROP CC 8.1.1.2 fr. XIV pide documentación completa. | Hecho (`2c92b2c`) |
| D-05 | Un módulo de código por historia desde M2 (`dictamen/tecnico.py`, `vistas/tecnico.py`…) y un registro de extensiones en el núcleo. | En M1 el código de las cuatro historias quedó mezclado y el commit por historia no salió limpio. | Hecho (`50269bf`); sigue en M3–M6 |
| D-06 | Commits: uno «base» por módulo con lo compartido y uno por historia. | Un commit de historia no arranca sin su base; se dice en el mensaje. | Hecho |
| D-07 | Diagrama entidad-relación generado desde los modelos (`herramientas/diagrama_er.py`), no dibujado a mano. | Un diagrama a mano deja de ser cierto al primer cambio. | Hecho (`68dc445`) |
| D-08 | Prueba del recorrido completo: una sola solicitud del registro al acta, comprobando en cada relevo estado, bandeja, acuse y bitácora. | Las pruebas por historia no demuestran que el relevo entre unidades funcione. | Hecho (`68dc445`) |

## 5. Problemas detectados al revisar el sprint 1

| ID | Problema | Propuesta | Estado |
| --- | --- | --- | --- |
| P-01 | La lista de verificación del dictamen técnico viene con todo marcado «Cumple». | Que venga sin marcar y exigir que cada criterio se revise. | Hecho (ajuste A-1, `045feb7`) |
| P-02 | El acta se puede registrar antes de la fecha de la sesión. | Impedirlo en el servicio. | Hecho (ajuste A-2, `045feb7`) |
| P-03 | Todo en la demostración tiene fecha de «hoy», así que los plazos de CC salen vencidos. | Datos de demostración con el calendario de la convocatoria. Ver G-03. | Aceptado (sprint 2) |
| P-04 | La etiqueta «Ajustado» marca también las filas que solo se recorrieron de lugar. | Marcar solo la fila que el Comité movió. | Hecho (ajuste A-3, `045feb7`) |
| P-05 | Los montos salen sin separador de miles ($20500.00). | Formato de moneda en un solo filtro de plantilla. | Hecho (ajuste A-4, `045feb7`) |
| P-06 | Cada corrida de pruebas reescribe las 49 capturas y ensucia git. | Guardar capturas solo cuando se pida. | Hecho (ajuste A-5, `045feb7`) |
| P-07 | Las pruebas pasaron de 40 s a 133 s y seguirán creciendo. | Separar las rápidas de las de navegador. | Hecho (ajuste A-6, `045feb7`) |
| P-08 | El comando diario solo avisa de los faltantes vencidos; no desecha la solicitud. | Decidir si el desecho es automático o lo hace una persona. | Por decidir (cliente; recomendación: que lo haga una persona con un clic, por ser un acto con efectos legales) |
| P-09 | La cadena completa solo se probó a nivel de servicios; por la interfaz, historia por historia. | Un recorrido de navegador de punta a punta al cerrar cada sprint. | Aceptado (sprints 2 y 3) |
| P-10 | No se probó con dos usuarios sobre el mismo expediente, con volumen ni en navegadores distintos de Chromium. | Ver G-02 para el volumen; lo demás, al final del sprint 3. | Propuesto |
| P-11 | El mapa base (OpenStreetMap) no se probó; los mapas salen sin fondo. | Probarlo con el sitio levantado y documentar cómo configurar las teselas. | Propuesto |
| P-12 | Solo Capturando Carbono tiene reglas; los otros cinco programas no reciben solicitudes. | Ver S2-01. | Aceptado (sprint 2) |

## 6. Cambios al plan de los sprints 2 y 3

| ID | Cambio | Por qué | Estado |
| --- | --- | --- | --- |
| S2-01 | Empezar el sprint 2 extrayendo las reglas de PS, RHF y PSAHEM. | La entrega de planta (HU-3.4) es de PS y RHF y los cheques (HU-5.3) de PSAHEM: con solo CC no se pueden demostrar. La propuesta dejaba «los demás programas» para el sprint 3. | Aceptado (sprint 2) |
| S2-02 | Mover al núcleo la notificación por conducto de la Delegación que hoy vive en M1. | M3.1 la generaliza; duplicarla crearía dos formas de notificar. | Aceptado (sprint 2) |
| S2-03 | Parametrizar el evento que arranca cada plazo. | Ver R-03. | Aceptado (sprint 2) |
| S2-04 | El modelo de contrato se sube y lo valida la Unidad Jurídica; las plantillas propias se marcan como borrador. | HU-3.2 pide «modelo validado» y las ROP no traen el modelo (R-07). | Aceptado (sprint 2) |
| S2-05 | Decidir en el sprint 2 cómo se identifica una persona beneficiaria para la consulta pública y el portal. | La publicación (HU-3.1) es la primera pantalla sin sesión y el portal llega en el sprint 3. | Por decidir (recomendación: consulta pública por folio; cuenta del portal creada por la Delegación al firmar el contrato) |
| S2-06 | Conectar los acuerdos del Comité con los pagos y el seguimiento. | Hoy los acuerdos se registran pero no disparan nada. | Aceptado (sprints 2 y 3) |
| S3-01 | Reglas de MFS y PEG al inicio del sprint 3. | Guardabosques (HU-4.3) y la prórroga de MFS son de ese sprint. | Aceptado (sprint 3) |
| S3-02 | Aligerar el sprint 3 (39 puntos) adelantando la investigación del INFyS. | Ver C-08. | Aceptado |

## 7. Datos de prueba

| ID | Propuesta | Por qué | Estado |
| --- | --- | --- | --- |
| G-01 | Datos de demostración con `cargar_demo`: 12 solicitudes de CC en tres Delegaciones, en todos los estados, creadas con los mismos servicios que usa la interfaz. | Así los datos de demostración no pueden estar en un estado imposible. | Hecho |
| G-02 | Generador con semilla (`generar_datos --programa --n`) para cientos de solicitudes. | Probar bandejas, filtros y listados con volumen. | Aceptado (sprint 2) |
| G-03 | Calendario simulado: fechas según la convocatoria y pruebas en los bordes de cada plazo. | Ver P-03. | Aceptado (sprint 2) |
| G-04 | Polígonos difíciles: KML de GPS, Shapefile en otra proyección, multipolígonos, geometrías inválidas, predios entre dos municipios. | Los polígonos de hoy son cuadros sintéticos. | Aceptado (sprint 3, con la verificación en campo) |
| G-05 | Un escenario con nombre por flujo alterno (A a G). | Poder demostrar cada flujo sin armarlo a mano. | Aceptado (se completa en el sprint 3) |
| G-06 | Datos reales anonimizados: padrón 2025, polígonos y formatos. | Es lo único que valida el sistema contra la operación real. | Por decidir (cliente) |

## 8. Forma de trabajo

| ID | Regla | Por qué | Estado |
| --- | --- | --- | --- |
| W-01 | Rama `prototipos`; un commit local por historia verificada, con su identificador (`HU-3.3: …`). | Trazabilidad que pide la propuesta. | Hecho (decisión de Joshua, 13-nov) |
| W-02 | Se entrega un sprint y se revisa antes de empezar el siguiente. | Los sprints se construyen uno sobre otro; corregir pronto cuesta menos. | Hecho (decisión de Joshua, 13-nov) |
| W-03 | Al empezar un sprint se sube al repositorio remoto lo del anterior. | Que el trabajo revisado quede respaldado y a la vista antes de construir encima. | Aceptado (decisión de Joshua, 14-nov); primera vez al iniciar el sprint 2 |
| W-04 | Trabajo reanudable: tareas pequeñas (una historia o menos), commit en cuanto se verifican, y el tablero [AVANCE.md](AVANCE.md) con el «siguiente paso» siempre al día. | Si el trabajo se interrumpe a la mitad, se retoma desde el tablero sin rehacer nada. | Hecho (14-nov) |
| W-05 | Cada tarea delegada empieza de cero leyendo `sistema/README.md`, el modelo de datos y solo los archivos de su historia; no se reanuda una tarea que ya acumuló mucho historial. | El sprint 1 gastó entre 1.2 y 1.6 millones de unidades de proceso en tareas delegadas, cerca de un millón en una sola que se fue alargando. | Aceptado (desde el sprint 2) |
| W-06 | Extracción de reglas y ajustes pequeños con el modelo más económico; construcción de módulos con el más capaz. | Usar la capacidad donde hace falta. | Hecho en el sprint 1; sigue |
| W-07 | Durante la construcción se corren solo las pruebas de la historia; la batería completa, una vez al cerrar cada tarea. | La batería completa tarda más de dos minutos y crecerá. | Hecho (`045feb7`); sigue |
| W-08 | Nada se da por hecho con el informe de quien lo construyó: se vuelven a correr las pruebas y se revisan las capturas antes del commit. | En el sprint 1 esa revisión encontró el doble redondeo (C-04) y la dependencia de una carpeta fuera del repositorio (T-11). | Hecho; sigue |
| W-09 | Esta bitácora se actualiza en el mismo commit que el cambio que documenta, o en el siguiente cuando necesita citar su identificador. | Que la documentación no se quede atrás del código. | Hecho (14-nov) |
| W-10 | Después de cambiar código, el sitio se levanta con `docker compose up --build`. | Al verificar los ajustes se levantó sin reconstruir y corrió la imagen anterior: el sitio no respondió y la demostración mostraba datos viejos. Con `--build` responde en 39 s con una base nueva. | Hecho (14-nov; anotado en AVANCE.md) |
| W-11 | Los ajustes A-1 a A-6 se hicieron con una tarea delegada nueva y el modelo económico: unas 150 mil unidades de proceso, contra cerca de un millón del módulo más caro del sprint 1. | Primera aplicación de W-05 y W-06. | Hecho (`045feb7`) |
