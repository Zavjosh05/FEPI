# Tareas por persona del sprint 1

Detalle de los paquetes de trabajo de la [Planeación del sprint 1](PLANEACION_SPRINT_1.md), agrupados por
responsable. Cada tarea dice qué se buscaba, **cómo se diseñó** (las decisiones y su porqué), **cómo se ejecutó**
(qué se construyó y dónde está), cómo se comprobó y el commit donde quedó en la rama `sprint-1`.

| Persona | Rol | Paquetes | Puntos |
| --- | --- | --- | ---: |
| Joshua | Coordinación y núcleo técnico | T01 Infraestructura · T02 Núcleo · T11 Sesión de aprobación (HU-2.3) · T15 Coordinación | 13 |
| Omar | Recepción (M1) | T04 HU-1.1 · T05 HU-1.2 · T06 HU-1.3 · T07 HU-1.4 | 14 |
| Cin | Reglas y dictamen (M2) | T03 Reglas de CC · T08 Base M2 · T09 HU-2.1 · T10 HU-2.2 | 13 |
| Angel | Calculadora, seguimiento e integración | T12 HU-2.4 · T13 HU-7.1 · T14 Recorridos y modelo de datos | 14 |

**Convenciones que comparten todos:**

- Rutas relativas a `sistema/` salvo que se diga otra cosa.
- Pruebas con el identificador de la historia en el nombre.
- Un commit por historia verificada.
- Requisitos, plazos y montos como datos, nunca en el código.
- Cada estado se cambia solo con `Expediente.cambiar_estado`, que valida contra la tabla de transiciones y escribe la
  bitácora.

[[SALTO]]

## Joshua — Coordinación y núcleo técnico (13 puntos)

### T01 · Infraestructura del sistema (3 puntos)

**Objetivo.** Que cualquier integrante levante el sistema completo con un solo comando y en las mismas condiciones.

**Cómo se diseñó.**

- **Docker Compose con cinco servicios**, para que el entorno de desarrollo sea el mismo que el de un servidor:

  | Servicio | Qué es | Por qué |
  | --- | --- | --- |
  | `bd` | PostgreSQL 17 con PostGIS 3.5 | Las consultas espaciales (traslapes, superficies) las hace la base de datos |
  | `web` | Django 5.2 LTS con Gunicorn | Aplicación |
  | `nginx` | Servidor web | Sirve los archivos estáticos y entrega los documentos del expediente solo después de que Django revisa el permiso (`X-Accel-Redirect`): los archivos nunca tienen una dirección pública |
  | `plazos` | `revisar_plazos` cada 24 horas | Un bucle simple, sin cron ni colas de tareas |
  | `pruebas` | pytest y Playwright con Chromium | En un perfil aparte, para no cargar la imagen de producción |

- **Docker Engine dentro de WSL (Ubuntu 24.04)**, porque el equipo de desarrollo no tiene Docker en Windows (decisión
  del 13 de noviembre).
- **Bibliotecas de interfaz copiadas en `estaticos/vendor/`** (Bootstrap 5, HTMX, Leaflet y Leaflet-Geoman) en lugar
  de un CDN, para que el sistema funcione en una red sin salida a internet.
- **Variables en `.env`** (con `.env.ejemplo` versionado) y valores de desarrollo por omisión.

**Cómo se ejecutó.**

- `docker-compose.yml` y un `Dockerfile` de varias etapas: producción y pruebas.
- `docker/entrypoint.sh` prepara el sitio al arrancar: migraciones, estáticos, `cargar_catalogos`, `cargar_reglas` y
  `cargar_demo`, todos idempotentes.
- `docker/nginx.conf`.
- Proyecto Django en `probosque/`: configuración, rutas y zona horaria de la Ciudad de México.

**Cómo se comprobó.** `docker compose up --build` desde cero levanta el sitio en http://localhost:8080. La batería
corre con `docker compose --profile pruebas run --rm pruebas`.

**Commit:** `6f6a11f` (base del sistema, junto con T02 y T03).

### T02 · Núcleo común (5 puntos)

**Objetivo.** Las piezas que todas las historias usan, para que ninguna las repita.

**Cómo se diseñó.**

- **Expediente único por predio.** El predio tiene su folio (`PRED-000001`), que conserva entre programas (ROP CC
  8.1.1.2 fr. XVII). Cada solicitud a un programa y ejercicio es un `Expediente` con folio `CC-2026-AME-0001`, y de él
  cuelga todo. Los modelos del trámite llevan historial de cambios (`django-simple-history`).
- **Estados y transiciones como datos** (`datos/flujo_tramite.json`, editables en el administrador).
  - Cada transición dice el estado de origen y de destino, qué tipo de unidad puede hacerla, si es propia de un
    programa y si exige motivo.
  - Un solo punto del código cambia estados: `Expediente.cambiar_estado(destino, usuario, motivo)`. Valida la tabla,
    que el expediente sea de la unidad del usuario y el motivo, y escribe la bitácora.
  - Así los módulos siguientes agregan estados sin tocar el código del núcleo.
- **Días hábiles.**
  - Sin sábados, domingos ni el catálogo `DiaInhabil` (calendario 2026 de demostración, porque las Reglas no traen
    uno).
  - Un plazo en días hábiles empieza a contar el día hábil siguiente al hecho.
  - En días naturales, meses o años, si el último día es inhábil vence el siguiente hábil.
- **Acuses.** Cada envío o entrega genera un `Acuse` con folio `AC-AAAA-NNNNNN`, fecha y hora, PDF (WeasyPrint) con
  su huella SHA-256, y un evento en la bitácora.
- **Unidades y permisos.**
  - Tipos de unidad: Delegación, Dirección, Unidad Jurídica, Secretaría Técnica, Administración y Finanzas, vivero y
    Fiduciaria.
  - Una Delegación ve solo lo suyo; una Dirección, los programas de los que es Instancia Ejecutora.
  - La **bandeja** muestra lo que el estado del expediente le toca atender a cada unidad.
- **Municipios y Delegaciones.**
  - Los 125 municipios vienen de la capa de IDEFOR, simplificada a unos 40 m (`herramientas/preparar_municipios.py`).
  - La asignación a Delegaciones es la de la Convocatoria 2026 (`reglas/catalogos.json`). Los nombres se empatan sin
    acentos y por prefijo, y la carga falla con un mensaje claro si alguno no empata.
- **Puntos de extensión** (`nucleo/extensiones.py`): filtros y paneles de bandeja, pestañas del expediente, menú,
  revisión de plazos y datos de demostración. Así los módulos se conectan al núcleo sin que el núcleo dependa de
  ellos, y varias personas trabajan sin tocar los mismos archivos.

**Cómo se ejecutó.**

- `nucleo/models.py`: Unidad, Usuario, Municipio, DiaInhabil, Programa, Ejercicio, TipoPersona, Modalidad,
  Requisito, Plazo, Formato, MontoApoyo, Ministracion, Estado, Transicion, Persona, Predio, Expediente, Documento,
  Acuse y Evento.
- `dias_habiles.py`, `acuses.py` con su plantilla PDF, `catalogos.py`.
- Las vistas de entrada y bandeja.
- Los comandos `cargar_catalogos`, `cargar_reglas`, `cargar_demo` y `revisar_plazos`.

**Cómo se comprobó.** 34 pruebas del núcleo:

| Archivo | Pruebas | Qué comprueba |
| --- | ---: | --- |
| `test_nucleo_dias_habiles.py` | 10 | Inicio y vencimiento de plazos con fines de semana y días inhábiles |
| `test_nucleo_transiciones_permisos.py` | 13 | Que solo la unidad correcta haga cada paso |
| `test_nucleo_reglas.py` | 9 | Carga de reglas |
| `test_nucleo_moneda.py` | 2 | Formato de moneda |

**Commit:** `6f6a11f`.

### T11 · Sesión de aprobación del Comité (HU-2.3, 3 puntos)

**Objetivo.** Criterios de aceptación:

1. Existe la convocatoria con orden del día y documentos, y su fecha y hora.
2. Existe un acta con los listados aprobados y la autorización de publicación.

**Cómo se diseñó.**

- **Quién decide.** Según las Reglas de CC (10.1 fr. VI y VII; 9.4.3 fr. I y III), los dictámenes solo producen el
  listado preliminar; el Comité aprueba la Lista de Personas Beneficiarias, la Lista de espera y la Lista de
  solicitudes No factibles. Por eso las tres salidas del estado «Dictaminada» las registra la Secretaría Técnica con
  el acta, y se quitó la transición directa de «Validada» a «No factible».
- **Convocatoria.**
  - Exige orden del día y al menos un documento.
  - Se rechaza si no se envía con la anticipación de las reglas: 3 días hábiles para las ordinarias y 24 horas para
    las extraordinarias (CC 9.4.2).
  - Su acuse lleva la fecha y la hora, el orden del día y los integrantes del Comité tomados de las reglas.
- **Propuesta de listados.**
  - Ordena las factibles por los criterios que se pueden leer del expediente: reforestaciones primero (8.1.2 fr. I) y
    refrendos después (fr. II). Desempata por fecha y hora de registro (8.1.2, último párrafo).
  - Asigna hasta donde alcanza el recurso disponible que escribe la Secretaría Técnica ($2,000 por hectárea factible,
    numeral 7.2). El resto va a la lista de espera con su lugar.
- **Ajustes.** El Comité puede mover una solicitud de lista o de lugar con un motivo obligatorio, que queda en el acta
  y en la bitácora. Una no factible no puede pasar a las listas de apoyo.

**Cómo se ejecutó.**

- `dictamen/sesiones.py` (integrantes, crear sesión, agregar documento, anticipación requerida, enviar convocatoria).
- `dictamen/aprobacion.py` (criterios de priorización, orden, monto por hectárea, candidatas, proponer listados,
  ajustar, registrar acta).
- Modelos `SesionComite`, `DocumentoSesion` y `ResolucionSesion`.
- Vistas y plantillas de la sesión, y el acta en PDF.

**Cómo se comprobó.** 11 pruebas en `test_hu_2_3.py`: anticipación ordinaria y extraordinaria, documentos
obligatorios, orden de la propuesta, recurso, ajuste con motivo y acta que mueve los estados. Además, un recorrido con
navegador (`e2e/test_recorrido_hu_2_3.py`) con capturas `hu_2_3_*`.

**Commit:** `40ac657`.

### T15 · Coordinación (2 puntos)

**Objetivo.** Que el sprint avance en orden, que lo entregado funcione junto y que las decisiones queden escritas.

**Cómo se diseñó.**

- Revisión de cada historia antes de aceptarla: se repiten sus pruebas y las rápidas, y se revisan sus capturas.
- Un tablero de avance por tarea y una bitácora de decisiones con identificadores fijos (T-, C-, R-, D-, P-, W-) y
  estados (Hecho, Aceptado, Propuesto, Por decidir, Descartado).
- Revisión del sprint con el cliente antes de empezar el siguiente.

**Cómo se ejecutó.**

- `entregas/AVANCE.md` y `entregas/BITACORA.md` (commit `9b4a013`).
- Ajustes tras la revisión (`045feb7`) y su registro (`ecb61db`).
- Registro de decisiones sobre el plazo de firma, los faltantes y el acceso externo para el sprint 2 (`faef4b1`).
- Resumen del sprint en PDF con diagramas y anexo de capturas (`entregas/generar_resumen.py`,
  `entregas/sprint_1/Resumen_sprint_1.pdf`).

[[SALTO]]

## Omar — Recepción, módulo M1 (14 puntos)

### T04 · Registro de la solicitud (HU-1.1, 3 puntos)

**Historia.** Como personal de la Delegación, quiero registrar la solicitud con los datos generales de la persona
solicitante, los datos del predio y los datos específicos del programa, para iniciar su trámite.

**Criterio de aceptación:** se genera un folio único para la solicitud.

**Cómo se diseñó.**

- **Tres grupos de datos,** que son las secciones del formulario:
  - Datos específicos del programa: programa y ejercicio, tipo de persona, modalidad, refrendo, representante legal y
    observaciones. Va primero porque los tipos de persona y las modalidades dependen del programa.
  - Datos del predio: folio de predio ya registrado, municipio, nombre, superficie y localidad.
  - Datos generales de la persona solicitante: nombre o razón social, CURP, RFC, teléfono, correo y representante.
- **Folio único.** Tiene la forma `CC-2026-AME-0001`: programa, ejercicio, Delegación y un consecutivo del programa y
  ejercicio. El consecutivo se toma con bloqueo de fila (`Consecutivo.siguiente`), así que dos registros simultáneos
  no reciben el mismo número. Además, la base de datos no admite folios repetidos (restricción `unique`).
- Solo la Delegación registra.
- **Validación del municipio.** Si el municipio del predio lo atiende otra Delegación, se rechaza y el mensaje dice
  cuál (ROP CC 8.1.3). El formulario lo avisa con HTMX al elegir el municipio, antes de enviar.
- **Formulario según las reglas.** Los tipos de persona y las modalidades salen de las reglas del programa. En CC solo
  se eligen los tipos de superficie; el refrendo es una casilla.
- **Predio que ya existe.** Se puede capturar el folio de un predio ya registrado para que conserve su folio.
- **Acuse de recepción.** PDF con folio, fecha y hora, y el plazo de 5 días hábiles para completar la documentación.

**Cómo se ejecutó.**

- `recepcion/forms.py` (formulario de registro) y `recepcion/servicios.py` (`DatosSolicitud`,
  `delegacion_que_corresponde`, `registrar_solicitud`).
- Plantillas `registrar.html` y `_delegacion_municipio.html` (aviso con HTMX).
- La pestaña Solicitud del expediente.

**Cómo se comprobó.** 10 pruebas en `test_hu_1_1.py`. El criterio lo comprueba
`test_hu_1_1_genera_folio_unico`: cuatro solicitudes de dos Delegaciones reciben folios distintos con consecutivo
creciente, y la base de datos rechaza un folio repetido. Las demás pruebas cubren las reglas del registro: acuse,
municipio de la Delegación, solo la Delegación registra y predio ya registrado. Además, el recorrido con navegador
(capturas `hu_1_1_*`, incluida la bandeja en un teléfono).

**Commit:** `6ee4927`.

### T05 · Revisión del expediente (HU-1.2, 3 puntos)

**Objetivo.** Criterios de aceptación:

1. Cada requisito del programa, del tipo de persona y de la modalidad está revisado.
2. El expediente digital está en la Dirección con la fecha y la hora del envío.

**Cómo se diseñó.**

- **Requisitos aplicables.** Se calculan con el tipo de persona y la modalidad (`requisitos_aplicables`). Cada uno
  queda entregado (con su archivo), faltante o, si es opcional o condicional, «no aplica».
- **Requisitos que son condiciones.** Los que no son documentos (CC-REQ-01 y CC-REQ-03) se revisan como «cumple» o
  «no cumple», sin archivo.
- **Regla de envío.** Todos revisados, ninguno faltante (CC 8.1.1.2 fr. XIV pide la documentación completa) y cada
  entregado con su archivo o, en un refrendo, documentación vigente que obra en PROBOSQUE. El polígono no es
  condición: las Reglas lo levantan después (CC 10.1 fr. III).
- **Pantalla.** Una fila por requisito con su estado y un botón «Revisar» que despliega su formulario y se guarda
  con HTMX, sin recargar.
- **Botón de archivo propio**, porque el texto del control nativo depende del idioma del navegador.

**Cómo se ejecutó.**

- Modelo `RevisionRequisito`.
- Servicios `revisar_requisito`, `problemas_para_enviar` y `enviar_a_direccion`.
- Plantillas `_fila_requisito.html` y `_panel_envio.html`, y `estaticos/js/archivos.js`.

**Cómo se comprobó.** 9 pruebas en `test_hu_1_2.py` y el recorrido con navegador (capturas `hu_1_2_*`).

**Commit:** `2c92b2c`.

### T06 · Ubicación del predio (HU-1.3, 5 puntos)

**Objetivo.** Criterios de aceptación:

1. Existe un polígono asociado al expediente.
2. Si el polígono cambia de lugar, existen el anterior y el nuevo.

**Cómo se diseñó.**

- **Formatos.** GeoJSON, KML y Shapefile en `.zip`, con o sin `.prj`. Sin `.prj` y con coordenadas grandes se asume
  UTM 14N. Como respaldo, el dibujo en el mapa con Leaflet-Geoman.
- **Superficie.** Se calcula en UTM 14N (EPSG:32614) para que las hectáreas sean reales.
- **Validez y ubicación.**
  - Una geometría inválida (por ejemplo, lados que se cruzan) se rechaza.
  - Si el polígono cae fuera del municipio, o parcialmente fuera en más de 0.5 %, se guarda con aviso. La tolerancia
    absorbe la simplificación del límite municipal.
- **Historial.** Cada cambio conserva el polígono anterior. Si el traslape (intersección entre unión) es menor de 50 %
  se marca «cambio de lugar»; si no, «corrección».
- **Quién lo levantó.** Delegación o prestador de servicios forestales con su RFN, y la fecha. Si el programa no usa
  polígono (Guardabosques), la pestaña no aparece.

**Cómo se ejecutó.**

- `recepcion/geometria.py` (lectura de archivos con GDAL, validez, superficie, ubicación en el municipio y traslape).
- Modelo `Poligono`, servicio `registrar_poligono` y la pestaña Ubicación con el mapa y el historial.

**Cómo se comprobó.** 11 pruebas en `test_hu_1_3.py`: formatos, proyección, inválido, fuera del municipio,
corrección y cambio de lugar. Además, el recorrido con navegador (capturas `hu_1_3_*`).

**Commit:** `15e7511`.

### T07 · Validación del expediente (HU-1.4, 3 puntos)

**Objetivo.** Criterios de aceptación:

1. El expediente está validado o tiene un aviso de faltantes con fecha límite.
2. En un refrendo, la documentación legal vigente de hasta 3 años es válida.

**Cómo se diseñó.**

- **Pantalla de validación.** La Dirección ve cada requisito con la revisión de la Delegación y una revisión
  automática contra las reglas, y marca los faltantes.
- **Sin faltantes,** el expediente queda validado, con constancia en PDF.
- **Con faltantes,** se emite el aviso con fecha límite: la fecha del aviso más 5 días hábiles. Es el plazo de
  complemento de las Reglas (8.1.1.2 fr. XIV), porque el de la Dirección no trae número (10.1 fr. V). El aviso va
  dirigido a la persona por conducto de la Delegación, que registra la notificación y reenvía.
- **Refrendo.** La documentación que obra en PROBOSQUE vale si no es anterior a la recepción menos 3 años
  (`vigencia_documentacion_legal_refrendo` en `datos/sistema.json`).
- **Revisión de plazos.** Señala una vez en la bitácora los avisos vencidos, sin cambiar estados: desechar lo confirma
  una persona.

**Cómo se ejecutó.**

- Modelo `Validacion`.
- Servicios `evaluar_para_validacion`, `validar_expediente`, `registrar_notificacion` y `plazo_recepcion`.
- Plantilla `validar.html` y la pestaña Validación.

**Cómo se comprobó.** 12 pruebas en `test_hu_1_4.py` y el recorrido con navegador (capturas `hu_1_4_*`, incluida la
bitácora).

**Commit:** `26bb9b7`.

[[SALTO]]

## Cin — Reglas y dictamen, módulo M2 (13 puntos)

### T03 · Reglas de Capturando Carbono (3 puntos)

**Objetivo.** Que el sistema sepa qué pide, en qué plazo y con qué monto el programa, sin escribirlo en el código.

**Cómo se diseñó.**

- **Un archivo por programa** (`reglas/CC.json`).
- **Qué contiene:**
  - tipos de persona;
  - modalidades;
  - requisitos, con bandera de documento legal, si aplica en refrendo, si es opcional y su condición;
  - plazos, con cantidad y unidad (admite «sin cantidad» y «fecha límite»);
  - formatos, montos y ministraciones;
  - criterios de elegibilidad y de selección;
  - integrantes del Comité.
- **Trazabilidad.** Cada dato lleva su numeral y la línea del texto de las Reglas de Operación 2026
  (`especificacion/ROP_PROBOSQUE_2026_texto.txt`), para poder comprobarlo.
- **Lo que el esquema aún no usa** se guarda en `Ejercicio.datos`, para el sprint 2.
- **Ajustes propios del programa,** como los requisitos que no son documentos o qué «modalidades» son en realidad
  tipos de superficie, van aparte en `datos/sistema.json`. Así no se altera lo que dicen las Reglas.

**Cómo se ejecutó.**

- Lectura del texto de las Reglas por rangos de líneas.
- Captura en `reglas/CC.json` y `reglas/catalogos.json` (Delegaciones y municipios de la Convocatoria 2026).
- El comando `cargar_reglas`, que valida el archivo y lo carga.

**Cómo se comprobó.** Las 9 pruebas de `test_nucleo_reglas.py` (carga, claves y referencias) y su uso en todas las
historias de M1 y M2.

**Commit:** `6f6a11f`.

### T08 · Base del módulo de dictamen (2 puntos)

**Objetivo.** La estructura común de M2, para que las cuatro historias se construyan por separado.

**Cómo se diseñó.**

- **Un módulo por historia:** `tecnico.py`, `juridico.py`, `aprobacion.py` y `seguimiento.py`, cada uno con sus
  vistas, formularios, plantillas y pruebas.
- **Lo común:** modelos, rutas, administración y `registro.py`, que conecta la app con el núcleo por medio de
  `extensiones.py`.
- **Estados en paralelo.** Los dictámenes técnico y jurídico corren al mismo tiempo sobre el expediente validado; el
  que completa el par lo pasa a «Dictaminada».
- **Estados con varias unidades.** `Estado.tipo_unidad_bandeja` admite varias (separadas por coma) y
  `Estado.visible_para` dice las que solo consultan.

**Cómo se ejecutó.** App `dictamen` (`models.py`, `comun.py`, `registro.py`, `urls.py`, `admin.py`), con los ajustes
a recepción que pidió la integración.

**Commit:** `50269bf`.

### T09 · Dictamen técnico (HU-2.1, 5 puntos)

**Objetivo.** Criterios de aceptación:

1. Cada solicitud tiene un dictamen técnico factible o no factible, con su sustento.
2. Existe un listado preliminar con el resultado técnico y jurídico de cada solicitud.
3. En PEG, el dictamen existe dentro de los 45 días hábiles.

**Cómo se diseñó.**

- **Lista de verificación desde las reglas:** superficie, criterios de elegibilidad técnica, inelegibles y criterios
  de selección. Un criterio «no cumple» impide el dictamen factible.
- **Análisis cartográfico con PostGIS:** polígono vigente, superficie en EPSG:32614, rango del programa (1 a 200 ha en
  CC), ubicación en el municipio y traslapes con los polígonos vigentes de otros expedientes del mismo ejercicio, con
  su superficie en hectáreas. Se guarda una copia en el dictamen.
- **Plazo de dictaminación.** Sale de las reglas: en CC, la fecha límite de la Convocatoria (30 de junio de 2026); en
  PEG, 45 días hábiles desde la recepción (Convocatoria PEG, base quinta, fr. II). Se muestra «en plazo», «por
  vencer» (5 días hábiles o menos) o «vencido».
- **Listado preliminar** con el resultado técnico y jurídico, exportable a CSV en UTF-8 con BOM, para que Excel abra
  los acentos.

**Cómo se ejecutó.**

- `dictamen/tecnico.py` (`lista_verificacion`, `analisis_cartografico`, `plazo_dictamen`, `situacion_plazo`,
  `dictaminar`, `listado_preliminar`, `listado_csv`, `revisar_plazos_dictamen`).
- Modelo `DictamenTecnico` y la pantalla con el mapa de traslapes.

**Cómo se comprobó.** 13 pruebas en `test_hu_2_1.py`, incluido el plazo de 45 días de PEG con datos de prueba, y el
recorrido con navegador (capturas `hu_2_1_*`).

**Commit:** `3417f37`.

### T10 · Dictamen jurídico (HU-2.2, 3 puntos)

**Objetivo.** Criterios de aceptación:

1. Cada solicitud tiene un dictamen jurídico procedente o no procedente.
2. Una solicitud cuyo titular o predio está en el Listado de Personas Beneficiarias Incumplidas no es procedente.

**Cómo se diseñó.**

- **Catálogos con historial.** El Listado de Incumplidas y los predios con procedimiento o sanción conservan su
  historial; una baja desactiva, no borra.
- **Cotejo automático** por persona, CURP, RFC, nombre sin acentos y predio. Se muestra en la pantalla y en el acuse.
- **El servicio impide el procedente** con coincidencias, no solo la pantalla.
- **Predio sancionado.** Con el reintegro hecho deja de impedir el apoyo (CC 8.1.1.1, inelegibles fr. III).
- **Refrendo.** También pide dictamen jurídico (CC 10.1 fr. IV).

**Cómo se ejecutó.**

- `dictamen/juridico.py` (`cotejar`, `dictaminar`, `registrar_incumplida`, `registrar_predio_sancionado`,
  `dar_de_baja`).
- Modelos `DictamenJuridico`, `PersonaIncumplida` y `PredioSancionado`.
- La pantalla Incumplidas.

**Cómo se comprobó.** 10 pruebas en `test_hu_2_2.py` y el recorrido con navegador (capturas `hu_2_2_*`).

**Commit:** `160ae8b`.

[[SALTO]]

## Angel — Calculadora, seguimiento e integración (14 puntos)

### T13 · Masa forestal por año (HU-7.1, 8 puntos)

**Objetivo.** Criterios de aceptación:

1. Existe la superficie en hectáreas de cada año disponible, por municipio.
2. Existe la evolución año con año.

**Cómo se diseñó.**

- **Página por partes.** La página de la Calculadora pesaba 2.7 MB en un solo archivo. Se diseñó un **sitio estático
  por partes** que al abrir pide solo el índice, los municipios, la comparación inicial y su cuadrícula (unos
  0.45 MB). Lo demás se pide al consultarlo, con «Cargando…» y un «Reintentar» si un archivo falla.
- **Archivo único conservado.** El modo de un solo HTML se conserva con la misma plantilla y los mismos datos, para
  usarlo sin servidor.
- **Mapa.** Municipios y contorno estatal en TopoJSON en EPSG:32614, con arcos compartidos simplificados a 45 m (ya
  no quedan huecos entre municipios), dibujados con `d3.geoIdentity` sobre la malla de la cuadrícula para que
  coincidan.
- **Evolución del Estado** siempre a la vista: gráfica con la cifra de cada año y la recta de tendencia, y tabla con
  bosque, porcentaje de la zona forestal y cambio contra el año anterior.
- **Datos de origen.** La serie 2023–2025 de Sentinel-2 de noviembre-diciembre ya calculada
  (`resultados/edomex_serie_2023_2025/`). La historia no recalcula: publica.

**Cómo se ejecutó.**

- `src/mapa_interactivo.py --sitio` escribe `docs/calculadora/index.html` y `datos/`: `indice.json`,
  `municipios.topojson`, `anios/`, `tendencias.json`, `comparaciones/` y `cuadriculas/` en PNG.
- `src/plantilla_mapa.html`, compartida con el archivo único.
- Se corrigió un doble redondeo: 2023 aparecía como 473,149 ha cuando la suma es 473,148.48.
- Entrada `[0.8.0]` en `CHANGELOG.md`.

**Cómo se comprobó.** 15 pruebas con pytest y Playwright en
`pruebas/calculadora/test_hu_7_1_masa_forestal_por_anio.py`:

- Cada año trae sus 125 municipios y el Estado.
- Las hectáreas coinciden con la serie calculada, y el Estado con la suma de sus municipios.
- La evolución está en el índice y en cada municipio.
- La página carga sin errores y pide los datos solo al consultarlos.
- Municipios y cuadrícula quedan alineados.
- Funciona el tema oscuro.
- Un archivo que falta muestra un mensaje.
- El archivo único trae los mismos datos y funciona sin servidor.

Capturas `hu_7_1_*`.

**Commit:** `d8b71ff`.

### T12 · Sesiones de seguimiento (HU-2.4, 3 puntos)

**Objetivo.** Criterios de aceptación:

1. Cada acuerdo indica a qué expedientes aplica y qué área debe cumplirlo.
2. En PSAHEM existe la instrucción de pago de cada ministración; en PEG, la validación de cada periodo de reportes.

**Cómo se diseñó.**

- **Tipos de acuerdo como datos** (`datos/dictamen.json`), con el área que los cumple por omisión: reasignación,
  sustitución, caso fortuito, suspensión, cancelación, baja, reintegro, instrucción de pago a la Fiduciaria (solo
  PSAHEM y por ministración), validación de reportes (solo PEG y por periodo) y otro.
- **Seguimiento por área.** Cada acuerdo lleva sus expedientes y su unidad responsable, que lo ve en su bandeja y lo
  marca como cumplido.
- **Qué falta.** `ministraciones_sin_instruccion` y `periodos_sin_validacion` dicen qué ministración o periodo no tiene
  todavía su acuerdo.
- **Sin efectos todavía.** Los acuerdos no ejecutan nada en otros módulos; `RECEPTORES` queda como punto de conexión
  (tipo de acuerdo → funciones) para pagos y seguimiento en los sprints 2 y 3.

**Cómo se ejecutó.**

- `dictamen/seguimiento.py` (`tipos_acuerdo`, `unidad_sugerida`, `registrar_acuerdo`, `acuerdos_pendientes`,
  `cumplir`, `cerrar_sesion`, `ministraciones_sin_instruccion`, `periodos_sin_validacion`).
- Modelo `Acuerdo` y el panel de acuerdos en la bandeja.
- PSAHEM y PEG, que aún no tenían reglas, se probaron con datos de prueba propios (`pruebas/fixtures_m2.py`).

**Cómo se comprobó.** 9 pruebas en `test_hu_2_4.py` y el recorrido con navegador (capturas `hu_2_4_*`, incluida la
bandeja de la Fiduciaria).

**Commit:** `a27e107`.

### T14 · Recorridos completos y modelo de datos (3 puntos)

**Objetivo.** Comprobar que las nueve historias funcionan juntas, no solo cada una con sus pruebas, y documentar la
base de datos.

**Cómo se diseñó.**

- **Recorrido por servicios.** Una sola solicitud pasa por todo: registro, requisitos, polígono, envío, aviso de
  faltantes y reenvío, validación, los dos dictámenes, sesión de aprobación y un acuerdo de seguimiento. En cada
  relevo se comprueba el estado, en qué bandeja queda, el acuse y el renglón de la bitácora.
- **Recorrido por la interfaz.** La misma secuencia con clics en Chromium, cambiando de usuario en cada relevo. Es lo
  que haría el personal real; encuentra tropiezos de navegación que las pruebas de servicio no ven.
- **Modelo de datos generado desde el código,** no dibujado a mano, para que no se desactualice. Va por áreas
  (núcleo, recepción, dictamen), porque con todas las tablas juntas el diagrama no se lee.

**Cómo se ejecutó.**

- `pruebas/test_sprint_1_recorrido_completo.py` y `pruebas/e2e/test_recorrido_sprint_1_completo.py`, con 11 capturas
  `recorrido_sprint_1_*`.
- `herramientas/diagrama_er.py`, que genera `docs/modelo_datos.md` (diagramas por área) y `docs/modelo_datos.mmd`
  (completo).

**Cómo se comprobó.** Los dos recorridos en verde dentro de la batería completa (128 pruebas al cierre; 129 con la prueba del folio único). El de la interfaz se
agregó tras la revisión con el cliente, cuando se pidió confirmar el funcionamiento por pantallas además de por
servicios.

**Commits:** `68dc445` (modelo de datos y recorrido por servicios) y `450a5ac` (recorrido por la interfaz).

[[SALTO]]

## Resumen de entregables por persona

| Persona | Commits | Pruebas propias | Capturas |
| --- | --- | ---: | --- |
| Joshua | `6f6a11f` (con Cin), `40ac657`, `9b4a013`, `045feb7`, `ecb61db`, `faef4b1` | 34 del núcleo + 11 de HU-2.3 + su recorrido | `hu_2_3_*` |
| Omar | `6ee4927`, `2c92b2c`, `15e7511`, `26bb9b7` | 42 (HU-1.1 a 1.4) + sus recorridos | `hu_1_1_*` a `hu_1_4_*` |
| Cin | `6f6a11f` (reglas), `50269bf`, `3417f37`, `160ae8b` | 9 de reglas + 23 (HU-2.1 y 2.2) + sus recorridos | `hu_2_1_*`, `hu_2_2_*` |
| Angel | `d8b71ff`, `a27e107`, `68dc445`, `450a5ac` | 15 de la Calculadora + 9 de HU-2.4 + los dos recorridos completos | `hu_7_1_*`, `hu_2_4_*`, `recorrido_sprint_1_*` |

## Cómo se integró el trabajo de las cuatro personas

1. **El primer día:** Joshua deja la infraestructura y el núcleo, y Cin las reglas. Con eso Omar empieza la
   recepción, y Angel trabaja en paralelo la Calculadora, que no depende del sistema.
2. **Recepción sin tocar el núcleo:** Omar construye sobre los modelos y servicios comunes. Lo que es propio de la
   recepción vive en `recepcion/`.
3. **Dictamen enganchado al núcleo:** Cin conecta la app `dictamen` por medio de `nucleo/extensiones.py` (pestaña,
   menú, paneles de bandeja), así que ni Omar ni Joshua tienen que editar sus archivos.
4. **Integración en la sesión de aprobación:** Joshua toma los dictámenes de Cin para la sesión, y Angel cuelga los
   acuerdos de la sesión.
5. **Prueba de todo junto:** Angel hace los recorridos completos sobre el trabajo de todos. Los tropiezos que
   encuentra regresan a su responsable.
6. **Revisión antes de aceptar:** Joshua revisa cada historia antes de aceptarla y registra en la bitácora las
   decisiones y las dudas para el cliente.

## Ajustes por las observaciones del profesor (23-nov-2026)

Las observaciones del 23-nov se atendieron en la rama `sprint-1` (detalle en la sección 11 de la planeación, en el
renglón D-29 de `entregas/BITACORA.md` y en `Registro_de_cambios_observaciones_23_nov.pdf`). Cada ajuste cae en la
parte de quien construyó la historia; los puntos de las historias no cambiaron.

| Persona | Paquete | Qué entregar | Dónde |
| --- | --- | --- | --- |
| Omar | T16 · HU-1.4 | Observación de la Dirección en cada requisito faltante (obligatoria), en el aviso, la notificación y la pestaña Requisitos | `recepcion/models.py` (`ObservacionValidacion`), `recepcion/servicios.py`, `validar.html`, `pruebas/test_hu_1_4.py` |
| Cin | T17 · HU-2.1 y HU-2.2 | Documento PDF de cada dictamen (folio DT-/DJ-, firmas, huella), adjunto al expediente | `dictamen/documentos.py`, `templates/dictamen/pdf/`, `pruebas/test_hu_2_1.py` y `test_hu_2_2.py` |
| Cin | T18 · HU-2.2 | Revisión de la documentación legal y de la propiedad o legal posesión del predio; sin propiedad acreditada no hay procedente | `dictamen/juridico.py`, `RevisionPropiedad`, `datos/dictamen.json` (`propiedad`), `juridico/dictaminar.html` |
| Angel | T19 · HU-2.4 | «Reasignaciones e incidentes»: causa, baja que libera recurso, reasignación en el orden de la lista de espera, sustitución, `MovimientoListado` | `dictamen/seguimiento.py`, `datos/dictamen.json` (`efecto`), `datos/flujo_tramite.json` (estado `baja`), `pruebas/test_hu_2_4.py` |
| Joshua | T20 · HU-2.3 | Vistas de Candidatos y Beneficiarios (menú «Listados», CSV) | `dictamen/listados.py`, `vistas/listados.py`, `templates/dictamen/listados/` |
| Joshua | T21 · todas | Trazabilidad: usuario en el historial, `save()` en lugar de `update()`, pestaña «Trazabilidad»; criterio en las 21 historias del sistema | `nucleo/trazabilidad.py`, `extensiones.TRAZABILIDAD`, `pestanas/trazabilidad.html`, `especificacion/modelo.json` |

