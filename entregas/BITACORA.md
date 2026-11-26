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
| R-03 | Firma del contrato en 10 días hábiles: la Convocatoria (base quinta, fr. V) los cuenta desde la publicación de resultados y el numeral 8.1.9 b) fr. IV, desde la notificación de ser persona beneficiaria con recurso disponible. La obligación de firmar (8.1.7 fr. IV) remite a «los tiempos establecidos en la Convocatoria». | **Decisión (14-nov, por encargo de Joshua): se llevan dos fechas.** La *fecha programada de firma* es publicación + 10 días hábiles y sirve para citar y alertar a la Delegación. El contrato queda «sin firma en plazo», para liberar el recurso, solo al vencer 10 días hábiles desde la *notificación con acuse*: la baja es una sanción y su regla se aplica en sus términos. Si la Delegación notifica el día de la publicación, las dos fechas coinciden. Las personas reasignadas cuentan desde su notificación, sin pasar del último día hábil de septiembre. Queda como parámetro por si la Instancia Normativa resuelve otra cosa (9.4.3 fr. VIII). | Aceptado (se aplica en S2-02 y HU-3.3) |
| R-04 | Los «15 días hábiles de verificación» de CC son para entregar el Informe Final o la minuta, no para hacer la visita. | HU-4.2 debe medir la entrega del informe. | Aceptado (sprint 3) |
| R-05 | Las ROP no dan plazo en días para publicar resultados, pagar ni reintegrar. | Esos plazos quedan sin vencimiento calculado; solo se registra fecha y hora. | Por decidir (cliente) |
| R-06 | CC habla de «puntaje más alto» pero no trae tabla de puntos. | El orden propuesto al Comité es: reforestaciones, luego refrendos, y desempate por fecha de registro; el Comité puede ajustarlo dejando constancia. | Hecho (`40ac657`); la regla: Por decidir (cliente) |
| R-07 | Ni el texto ni el PDF traen los formatos FO-PB-509-A y 520-B, el modelo de Contrato de Adhesión ni el oficio de solicitud de pago. | Ver S2-04. | Por decidir (cliente) |
| R-08 | Las ROP no listan días inhábiles. | Calendario de demostración 2026 (11 días), editable. | Hecho |
| R-09 | El polígono se levanta después de entregar el expediente (CC 10.1 fr. III). | No es condición para enviar el expediente a la Dirección. | Hecho (`2c92b2c`) |
| R-10 | Los listados, incluidas las solicitudes no factibles, los aprueba el Comité (CC 10.1 fr. VI y VII; 9.4.3). | Se quitó el paso directo de «validada» a «no factible»; los dictámenes solo forman el listado preliminar. | Hecho (`50269bf`) |
| R-11 | El plazo de dictaminación de CC es una fecha límite (30-jun-2026), no una cantidad de días. | En la demostración los dictámenes de CC aparecen vencidos; es correcto con la fecha de hoy. Ver P-03. | Hecho |
| R-12 | Faltantes: las ROP distinguen dos momentos. En ventanilla (8.1.1.2 fr. XIV) son 5 días hábiles **desde la recepción de la solicitud**, sin pasar de la fecha límite de recepción, y si no se complementa la solicitud «se tendrá por desechada». En la revisión posterior de la Dirección (10.1 fr. V) no hay número de días: se notifica dentro del plazo de evaluación. | Hoy el sistema cuenta 5 días hábiles desde el aviso de la Dirección: sirve para el segundo momento, pero es una decisión nuestra, y falta el plazo del primero (desde la recepción). Se corrige al parametrizar el evento que arranca cada plazo (S2-03). | Aceptado (S2-02); cuántos días da la Dirección: Por decidir (cliente) |

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
| P-08 | El comando diario solo avisa de los faltantes vencidos; no desecha la solicitud. | **Decisión de Joshua (14-nov): lo hace una persona.** Al vencer el plazo el sistema prepara la propuesta de desecho (fundamento, fechas y acuse de la notificación) y la persona la confirma con un clic. Variante automática evaluada: es viable técnicamente (ya existen los plazos en días hábiles, la tabla de transiciones, el comando diario y los acuses; faltarían un usuario «sistema», días de gracia y una reapertura con motivo) y la regla la respalda («se tendrá por desechada»). No se activa porque depende de tres cosas que hoy no se cumplen: calendario oficial de días inhábiles (R-08), captura al día de lo que se entrega en ventanilla y R-12 resuelto. | Aceptado (sprint 3, con plazos y avisos). Desecho automático: Descartado por ahora; queda como interruptor apagado |
| P-09 | La cadena completa solo se probó a nivel de servicios; por la interfaz, historia por historia. | Un recorrido de navegador de punta a punta al cerrar cada sprint. | Hecho para el sprint 1 (A-7, `450a5ac`): pasa completa, con seis tropiezos menores (P-13 a P-18). Sigue en los sprints 2 y 3 |
| P-10 | No se probó con dos usuarios sobre el mismo expediente, con volumen ni en navegadores distintos de Chromium. | Ver G-02 para el volumen; lo demás, al final del sprint 3. | Propuesto |
| P-11 | El mapa base (OpenStreetMap) no se probó; los mapas salen sin fondo. | Probarlo con el sitio levantado y documentar cómo configurar las teselas. | Propuesto |
| P-12 | Solo Capturando Carbono tiene reglas; los otros cinco programas no reciben solicitudes. | Ver S2-01. | Aceptado (sprint 2) |
| P-13 | Tras registrar la solicitud, ni el acuse ni la bandeja indican el siguiente paso (hay que saber ir a Requisitos). | Un botón del siguiente paso en cada pantalla del trámite («Revisar requisitos», «Levantar polígono», «Enviar a la Dirección»…). | Propuesto (se atiende en S2-02) |
| P-14 | La pestaña Requisitos deja enviar sin polígono (es correcto, R-09) pero no avisa que queda pendiente. | Aviso informativo en el panel de envío. | Propuesto (S2-02) |
| P-15 | El aviso de faltantes no enlaza al requisito que falta; la Delegación lo busca en la tabla. | Enlace directo del aviso al requisito. | Propuesto (S2-02) |
| P-16 | Desde un expediente dictaminado no hay cómo llegar a crear la sesión de aprobación; solo por el menú. | Acción «Llevar a sesión de aprobación» en la bandeja de la Secretaría Técnica. | Propuesto (S2-02) |
| P-17 | Un expediente aprobado desaparece de todas las bandejas «Por atender». | Se resuelve con el sprint 2 (publicación y contrato lo ponen en bandeja); mientras, el filtro «Todos los míos» más visible. | Propuesto (S2-02 y S2-03) |
| P-18 | Los acuses abren en pestaña nueva; la descarga real no se prueba. | Enlace de descarga además del de vista, y su prueba. | Propuesto (S2-02) |

## 6. Cambios al plan de los sprints 2 y 3

| ID | Cambio | Por qué | Estado |
| --- | --- | --- | --- |
| S2-01 | Empezar el sprint 2 extrayendo las reglas de PS, RHF y PSAHEM. | La entrega de planta (HU-3.4) es de PS y RHF y los cheques (HU-5.3) de PSAHEM: con solo CC no se pueden demostrar. La propuesta dejaba «los demás programas» para el sprint 3. | Aceptado (sprint 2) |
| S2-02 | Mover al núcleo la notificación por conducto de la Delegación que hoy vive en M1. | M3.1 la generaliza; duplicarla crearía dos formas de notificar. | Aceptado (sprint 2) |
| S2-03 | Parametrizar el evento que arranca cada plazo. | Ver R-03. | Aceptado (sprint 2) |
| S2-04 | El modelo de contrato se sube y lo valida la Unidad Jurídica; las plantillas propias se marcan como borrador. | HU-3.2 pide «modelo validado» y las ROP no traen el modelo (R-07). | Aceptado (sprint 2) |
| S2-05 | Identificación de personas externas. **Consulta pública de resultados:** sin cuenta; muestra los listados que el Comité autorizó publicar y permite buscar por folio. **Portal (sprint 3), opciones:** (1) cuenta creada por la Delegación al firmar el contrato, con la CURP como usuario y primer acceso con un código impreso en el acuse; (2) sin cuentas: folio más el código del acuse de cada expediente; (3) código de un solo uso por correo o SMS; (4) Llave MX o e.firma. | La consulta pública es lo que las ROP mandan publicar. Del portal: (1) aprovecha que la identidad ya se verifica en persona al firmar; (2) es lo más simple, pero el código se puede compartir; (3) depende de teléfono y señal; (4) es la más fuerte, pero requiere convenio y muchas personas no la tienen. En todas, la entrega en persona en la Delegación queda registrada igual. | Consulta pública: Aceptado (HU-3.1, sprint 2). Portal: Por decidir (recomendación: 1, con 2 como respaldo) |
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
| G-07 | Cada rama de sprint con su propio nombre de proyecto de Compose (`probosque_s1`) y sus propias imágenes (`probosque-sistema:sprint-1` y `probosque-sistema-pruebas:sprint-1`) (25-nov-2026). | Con el mismo nombre que `main`, reconstruir la imagen de una rama pisaba la de la otra, y la imagen del sistema lleva el código dentro. | Hecho: `docker-compose.yml`, guía y los comandos de `generar_resumen.py` y `md_a_pdf.py` |
| G-08 | `entregas/md_a_pdf.py` deja como texto los enlaces a archivos del repositorio (25-nov-2026). | Dentro del PDF esos enlaces quedaban como rutas `file:` del equipo donde se generó y no abrían nada. | Hecho: se regeneraron la planeación, las tareas por persona y la secuencia de prueba del sprint 1 |

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
| W-12 | Arranque desde Windows en la Guía de inicio (26-nov-2026). Al seguir la guía, el sistema no levantaba: el comando de PowerShell traía la ruta con el marcador `<usuario>` (copiado tal cual, bash lo toma como redirección: «usuario: No such file or directory») y el bloque `docker compose up` no sirve en PowerShell porque Docker está dentro de Ubuntu. La sección 1.3 ahora dice entrar a `sistema/` y escribir `wsl docker compose up --build` (WSL corre el comando en la misma carpeta, sin rutas `/mnt/c/...`), y que todos los comandos de la guía se escriben con `wsl` delante en PowerShell; «Si algo falla» suma esos dos errores, la distribución de WSL que no es Ubuntu, el servicio de Docker detenido y otra rama levantada en el puerto 8080. Lo mismo en `sistema/README.md` y en las secuencias de prueba (el script de casos del sprint 2 usa `<`, que PowerShell no acepta: `wsl sh -c "... < archivo"`). | Que cualquier integrante levante el sistema copiando la guía. | Hecho: `wsl docker compose up --build` desde PowerShell levanta el sistema y http://localhost:8080/entrar/ responde |
| W-13 | Mapa base bloqueado por OpenStreetMap (26-nov-2026). En la pestaña Ubicación (y en el análisis cartográfico del dictamen) las teselas salían como «403 Access blocked». Causa: Django envía `Referrer-Policy: same-origin`, así que el navegador pide las teselas a `tile.openstreetmap.org` sin Referer, y la política de uso de OSM bloquea esas peticiones (comprobado: la misma tesela sin Referer es la imagen de bloqueo y con `Referer: http://localhost:8080/` es el mapa). La capa de Leaflet de `mapa_poligono.js` y `mapa_dictamen.js` lleva `referrerPolicy: "strict-origin-when-cross-origin"`: solo las teselas mandan el origen del sitio (sin la ruta ni el folio) y el resto del sistema sigue sin enviar Referer. Para producción conviene un servidor de teselas propio o contratado (`MAPA_TESELAS_URL`): los servidores de OSM son de voluntarios y no admiten uso intensivo. | Que el mapa base se vea. | Hecho: en el navegador, las 15 teselas de CC-2026-AME-0001 cargan con el mapa; pruebas de navegador con mapas en verde |
| D-27 | Redacción de las historias enfocada en la acción (18-nov-2026, nota del profesor a la HU-1.1). Las 26 historias pasan de «Como [rol], quiero [lo que desea], por lo que [lo que hace], para [la meta]» a «Como [rol], quiero [acción], para [beneficio]» (`sistema/especificacion/modelo.json`, en `main` y en `sprint-1`); títulos, roles, puntos, sprints y los demás criterios no cambian. HU-1.1: «Como personal de la Delegación, quiero registrar la solicitud con los datos generales de la persona solicitante, los datos del predio y los datos específicos del programa, para iniciar su trámite», con un solo criterio: «Se genera un folio único para la solicitud» (antes: acuse con fecha y hora, y municipio de la Delegación, que siguen como reglas del registro con sus pruebas). Se agregó `test_hu_1_1_genera_folio_unico` (folios distintos con consecutivo creciente entre Delegaciones y rechazo de un folio repetido por la base de datos); el formulario de registro nombra sus secciones como la historia y se regeneraron sus capturas `hu_1_1_*`; manual y documentos del sprint 1 al día. La propuesta (carpeta de contexto, fuera de git) se actualizó con su script y conserva los originales. Verificado: `main` 566 + 40 y `sprint-1` 129 pruebas en verde; cada criterio de las 26 historias conserva sus pruebas. En una de cinco corridas, el recorrido de navegador de HU-1.1 falló una vez en `sprint-1` sin repetirse. | El profesor pidió que las historias se enfoquen en su acción y que la HU-1.1 tenga como único criterio el folio único. | Hecho |
| D-28 | Cotejo de las 26 historias con los 7 módulos, el código y las pantallas (19-nov-2026). La correspondencia función-historia es de uno a uno y las 9 historias construidas cumplen sus criterios; tres decían menos que su función y que el sistema y se ajustó su redacción, sin cambiar títulos, roles, puntos, sprints ni número de criterios: HU-1.2 (criterio 1: «entregado (con su archivo digitalizado), faltante o, si es condicional, no aplica»), HU-1.3 (el polígono lo levanta «la Delegación o el prestador de servicios forestales») y HU-2.2 (el titular se coteja con el Listado de Personas Beneficiarias Incumplidas y el predio con los predios con procedimiento o sanción; criterio 2 igual). Cambió `sistema/especificacion/modelo.json` y la planeación del sprint 1 (md y PDF); el código no, porque ya lo hacía. Documento nuevo `entregas/interfaces/Historias_e_interfaces.pdf` con el cotejo, las historias y el apartado de interfaz (capturas del sprint 1 y nuevas de todas las bandejas, pestañas, estados, acuses, catálogos y de cada programa con reglas mínimas de demostración); se rehace con `entregas/generar_historias_interfaces.py`, que también genera, en la raíz, `Historias_de_usuario_e_interfaces.pdf` (versión para exponer al profesor, sin las observaciones de problemas) y `Registro_de_cambios_historias_e_interfaces.pdf` (qué se agregó, modificó, notó y falta). Pendiente: llevar los ajustes a `propuesta/` en `main` con `actualizar_propuesta.py`. Hallazgos de pantalla: el acceso negado muestra la página 403 de Django sin diseño, y el dictamen técnico escribe «None a None ha» cuando las reglas no traen rango de superficie. Verificado: `sprint-1` 129 pruebas en verde. | Que cada historia diga lo que hacen su función y sus pantallas. | Hecho (sin commit) |
| D-29 | Observaciones del profesor al sprint 1 (23-nov-2026), atendidas en `sprint-1` sin commit. (1) HU-1.4: cada requisito faltante lleva la observación de la Dirección, obligatoria (modelo `ObservacionValidacion`, una por requisito y validación); el aviso de faltantes, la notificación y la pestaña Requisitos la muestran. (2) HU-2.1 y HU-2.2: al registrar cada dictamen se expide su documento en PDF (`dictamen/documentos.py`, plantillas `dictamen/pdf/`), con folio DT-/DJ-programa-año-consecutivo, firmas y huella SHA-256, y queda como `Documento` de tipo «dictamen» del expediente; sustituye al acuse que llevaba el título «Dictamen técnico/jurídico» (se quitó el campo `acuse` de los dictámenes). (3) HU-2.2: revisión de la propiedad o legal posesión del predio (`RevisionPropiedad`; tipos de documento de CC 8.1.1.2 fr. VII en `datos/dictamen.json`); sin documento a nombre del titular, que ampare la superficie del polígono, vigente y sin conflicto (8.1.1.1 fr. VII) no puede ser procedente; además cada documento legal se marca válido o no válido con su observación. (4) HU-2.4 pasa a «Reasignaciones e incidentes» con criterios nuevos: cada incidente con su acuerdo y causa; desistimiento, cancelación y baja llevan a la persona beneficiaria al estado nuevo «baja» y liberan su monto; la reasignación pasa a «aprobada» a las primeras de la lista de espera, en su orden y sin rebasar el recurso liberado; la sustitución hace las dos cosas; cada salida y entrada queda en `MovimientoListado`. La instrucción de pago (PSAHEM) y la validación de reportes (PEG) siguen como acuerdos que dejan constancia, ya no como criterio. (5) HU-2.3: vistas separadas de Candidatos y Beneficiarios (menú «Listados», CSV). (6) Trazabilidad: criterio nuevo al final de las 21 historias de M1 a M6; `nucleo/trazabilidad.py` registra al usuario en el historial aunque no haya petición web, los cambios por `update()` pasaron a `save()` para quedar en el historial, y la pestaña «Trazabilidad» del expediente muestra el historial de todos sus registros campo por campo. También: página 403 con el diseño del sistema y sin «None a None ha» (hallazgos de D-28). Migraciones `nucleo 0004`, `recepcion 0002`, `dictamen 0002`. Demostración: Las Trojes de 4.5 ha y presupuesto de $26,000 para mostrar un desistimiento y su reasignación. Puntos de las historias sin cambio (conviene re-estimar HU-2.2 y HU-2.4). Documento `Registro_de_cambios_observaciones_23_nov.pdf`. Verificado: `sprint-1` 155 pruebas en verde (146 sin navegador y 9 recorridos). | Observaciones del profesor del 23-nov. | Hecho (sin commit) |
