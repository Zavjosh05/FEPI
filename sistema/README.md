# Sistema de programas de PROBOSQUE

Prototipo del sprint 1 (módulos M1, Recepción y expediente, y M2, Dictamen y Comité) del sistema que lleva el trámite de los
seis programas de apoyo de PROBOSQUE: Capturando Carbono (CC), Manejo Forestal Sustentable (MFS),
Plantaciones Sustentables (PS), Restauración Hidrológico-Forestal (RHF), PSAHEM (PSA) y
Guardabosques (PEG). Tienen reglas cargadas CC, PS, RHF y PSAHEM; MFS y PEG existen en el catálogo sin archivo de reglas.

Historias implementadas: HU-1.1 Registro de la solicitud, HU-1.2 Revisión del expediente,
HU-1.3 Ubicación del predio, HU-1.4 Validación del expediente, HU-2.1 Dictamen técnico, HU-2.2 Dictamen
jurídico, HU-2.3 Sesión de aprobación y HU-2.4 Sesiones de seguimiento.

## Cómo levantar

Requisitos: Docker con Compose 2.24 o posterior. En Windows, Docker vive en WSL:

```
wsl -e bash -lc "cd /mnt/c/Users/<usuario>/Documents/GitHub/FEPI/sistema && docker compose up --build"
```

En otro equipo basta con `docker compose up --build` dentro de `sistema/`.

- El sitio queda en **http://localhost:8080** (Nginx → Gunicorn).
- Al arrancar, el contenedor `web` aplica las migraciones, recolecta los estáticos y corre
  `cargar_catalogos`, `cargar_reglas` y `cargar_demo` (los tres son idempotentes).
- Variables: copiar `.env.ejemplo` a `.env` y cambiar los valores. Sin `.env` se usan los valores de
  desarrollo de `docker-compose.yml`. `.env` no se versiona.
- Para borrar todo (base y archivos): `docker compose down -v`.

Servicios de `docker-compose.yml`:

| Servicio | Qué hace |
| --- | --- |
| `bd` | PostgreSQL 17 + PostGIS 3.5 (volumen `bd_datos`). |
| `web` | Django 5.2 LTS con Gunicorn (imagen de producción, sin herramientas de prueba). |
| `nginx` | Sirve los estáticos y entrega los archivos del expediente solo después de que Django revisa el permiso (`X-Accel-Redirect`). Puerto 8080. |
| `plazos` | Corre `manage.py revisar_plazos` cada 24 h (bucle simple, sin cron ni Celery). |
| `pruebas` | Perfil aparte: pytest + Playwright con Chromium (etapa `pruebas` del Dockerfile). |

## Cómo probar

Desde `sistema/` (en este equipo, dentro de WSL: `wsl -e bash -lc "cd /mnt/c/.../FEPI/sistema && <comando>"`).
Docker Compose acepta argumentos para el servicio `pruebas`; al terminar, `docker compose down`.

| Qué | Comando | Tiempo medido |
|---|---|---|
| Rápidas (sin navegador) | `docker compose --profile pruebas run --rm pruebas pytest -m "not navegador"` | 119 pruebas, ~62 s (71 s con arranque) |
| Una historia | `docker compose --profile pruebas run --rm pruebas pytest pruebas/test_hu_2_3.py` | ~15–25 s |
| Todo (rápidas + recorridos de Playwright) | `docker compose --profile pruebas run --rm pruebas` | 127 pruebas, ~114 s (120 s con arranque) |
| Todo y regenerar capturas | `docker compose --profile pruebas run --rm -e CAPTURAS=1 pruebas` | igual que «todo» |

Los recorridos de Playwright (todo lo que usa `page` o `live_server`, en `pruebas/e2e/`) llevan el marcador
`navegador` (registrado en `pytest.ini`) y corren al final. **Las capturas solo se guardan con `CAPTURAS=1`**; sin
esa variable la fixture `captura` no escribe nada y `git status` queda limpio. Van a `CAPTURAS_DIR`
(por omisión `/entregas/sprint_1/capturas`, la carpeta `entregas/` de la raíz del repositorio montada en el
contenedor); para otro sprint: `-e CAPTURAS_DIR=/entregas/sprint_2/capturas`. Para regenerar solo algunas:
`... run --rm -e CAPTURAS=1 pruebas pytest pruebas/e2e/test_recorrido_hu_2_3.py`.

Las pruebas unitarias y de criterios corren con pytest-django contra PostGIS. Las historias, sus criterios y las
necesidades se leen de
`especificacion/modelo.json` y `especificacion/necesidades_v12.json`; ahí está también el texto de las
Reglas de Operación 2026 al que remiten los numerales y las líneas de `reglas/*.json`.

Cada criterio de aceptación tiene al menos una prueba con el ID de su historia en el nombre
(`pruebas/test_hu_1_1.py` … `test_hu_2_4.py`); las del núcleo están en `pruebas/test_nucleo_*.py`.
Los recorridos de Playwright están en `pruebas/e2e/` (uno por historia; los de M2 en archivos
`test_recorrido_hu_2_*.py`) y corren con Chromium en español de México (`--lang=es-MX`, zona horaria de
la Ciudad de México). PEG, que no tiene archivo de reglas, se prueba con fixtures
(`pruebas/fixtures_m2.py`) que crean su programa-ejercicio, su plazo y sus ministraciones.

## Usuarios de demostración

Contraseña de prueba para todos: **`Probosque2026`** (solo para demostración; nunca en un servidor real).

| Usuario | Unidad | Para qué |
| --- | --- | --- |
| `del_amecameca` | Delegación Regional Forestal Amecameca | Ventanilla: registra, revisa requisitos, levanta polígono, envía, notifica. |
| `del_toluca` | Delegación Regional Forestal Toluca | Igual, otra Delegación (solo ve lo suyo). |
| `del_valle` | Delegación Regional Forestal Valle de Bravo | Igual. |
| `dir_drff` | Dirección de Restauración y Fomento Forestal | Instancia Ejecutora de CC, MFS, PS, RHF y PSA: valida o avisa faltantes, dictamen técnico, listado preliminar, cumple acuerdos. |
| `dir_dpf` | Dirección de Protección Forestal | Instancia Ejecutora de PEG (dictamen técnico; validación de reportes). |
| `juridica` | Unidad Jurídica | Dictamen jurídico, Listado de Personas Beneficiarias Incumplidas y predios sancionados. |
| `comite` | Secretaría Técnica del Comité | Sesiones: convocatoria, documentos, listados, acta, acuerdos. |
| `finanzas` | Dirección de Administración, Finanzas y de Gestión Documental | (Sprint 2.) |
| `vivero` | Vivero (demostración) | (Sprint 2.) |
| `fiduciaria` | Fiduciaria | Ve en su bandeja las instrucciones de pago del Comité (PSAHEM). |
| `admin` | — (superusuario) | Admin de Django para catálogos: `/admin/`. |

Solicitudes de demostración (CC 2026): Los Ocotes (recibida, revisión a medias), Ejido San Rafael
(recibida, completa, con polígono), La Cañada (en la Dirección), Rancho El Capulín (aviso de faltantes
notificado), El Tecolote (desechada) y, para M2: Los Encinos del Monte (con dictamen técnico, falta el
jurídico; traslapa con La Joya Alta), El Ocotal (en dictamen, plazo vencido), Potrero Viejo
(dictaminada, en la bandeja de la Secretaría Técnica) y la sesión de aprobación SO-CC-2026-01 con acta:
Predio Agua Blanca (refrendo, con cambio de lugar del polígono) y La Joya Alta aprobadas, Las Trojes en
lista de espera y Cerro de la Cruz no factible (su titular, Rogelio Bautista Núñez, está en el Listado
de Incumplidas). La sesión de seguimiento SO-CC-2026-02 tiene tres acuerdos (uno cumplido; dos
pendientes en las bandejas de la Dirección y de la Unidad Jurídica).

## Estructura

```
sistema/
├── docker-compose.yml, Dockerfile, .env.ejemplo, requirements*.txt, pytest.ini, manage.py
├── docker/            entrypoint.sh y nginx.conf
├── probosque/         proyecto Django (settings, urls, wsgi)
├── nucleo/            app común: modelos, días hábiles, acuses PDF, carga de catálogos y reglas,
│                      bandeja, permisos, comandos (cargar_catalogos, cargar_reglas, cargar_demo,
│                      revisar_plazos) y datos de demostración
├── recepcion/         app M1: revisión de requisitos, polígonos, validación; servicios.py (reglas),
│                      geometria.py (GeoJSON/KML/SHP), vistas y plantillas por pestaña
├── dictamen/          app M2, un módulo por historia: tecnico.py (HU-2.1), juridico.py (HU-2.2),
│                      aprobacion.py (HU-2.3), seguimiento.py (HU-2.4); sesiones.py y comun.py
│                      compartidos; vistas/, formularios/ y templates/dictamen/ con la misma división;
│                      registro.py conecta la app con las bandejas, el menú y los plazos del núcleo
├── plantillas/        base.html
├── estaticos/         css, js del mapa y vendor/ (Bootstrap 5.3.9, htmx 2.0.11, Leaflet 1.9.4,
│                      Leaflet-Geoman 2.20.6; sin CDN)
├── reglas/            CC.json, catalogos.json, indice_rop.json (extraídos de las ROP; no se editan a mano)
├── datos/             municipios_edomex.geojson, flujo_tramite.json, sistema.json, dictamen.json,
│                      dias_inhabiles_2026.json
├── especificacion/    modelo.json, necesidades_v12.json y el texto de las ROP 2026
├── herramientas/      preparar_municipios.py (convierte la capa de IDEFOR a GeoJSON)
└── pruebas/           pytest (test_nucleo_*, test_hu_1_*, test_hu_2_*, fixtures_m2.py) y e2e/ (Playwright)
```

## Estados del trámite (sprints 1 y 2)

Los estados y las transiciones son datos (`datos/flujo_tramite.json`, editables en el admin). El único
punto del código que cambia un estado es `Expediente.cambiar_estado(destino, usuario, motivo)`: valida
contra la tabla (origen, destino, tipo de unidad, programa opcional), revisa que el expediente sea de la
unidad del usuario, pide motivo cuando la transición lo exige y escribe la bitácora. Al cargar el
archivo, las transiciones que ya no aparecen en él dejan de estar permitidas.

```mermaid
stateDiagram-v2
    [*] --> recibida: Delegación registra (HU-1.1)
    recibida --> enviada_direccion: Delegación envía (HU-1.2)
    recibida --> desechada: Delegación, no completó en plazo (A)
    enviada_direccion --> validada: Dirección valida (HU-1.4)
    enviada_direccion --> faltantes: Dirección avisa faltantes (A)
    faltantes --> enviada_direccion: Delegación reenvía
    faltantes --> desechada: Dirección, faltantes no atendidos (A)
    validada --> dictaminada: con los dos dictámenes, técnico (Dirección, HU-2.1) y jurídico (UJ, HU-2.2)
    dictaminada --> aprobada: acta del Comité, Lista de Personas Beneficiarias (HU-2.3)
    dictaminada --> lista_espera: acta del Comité, Lista de espera (C)
    dictaminada --> no_factible: acta del Comité, Lista de No factibles (B)
    lista_espera --> aprobada: reasignación por acuerdo del Comité
    desechada --> [*]
    no_factible --> [*]
```

Sprint 2 (tabla lista; las acciones las construyen las historias HU-3.x y HU-5.x). En M5 el expediente
recorre los estados de pago una vez por ministración.

```mermaid
stateDiagram-v2
    aprobada --> publicada: Dirección publica (HU-3.1)
    publicada --> notificada: Delegación notifica con acuse (HU-3.1)
    notificada --> contrato_elaborado: Dirección elabora (HU-3.2)
    contrato_elaborado --> contrato_en_delegacion: Dirección envía (HU-3.2)
    contrato_en_delegacion --> contratada: Delegación registra la firma (HU-3.3)
    publicada --> sin_firma_en_plazo: Dirección, plazo vencido (D)
    notificada --> sin_firma_en_plazo
    contrato_elaborado --> sin_firma_en_plazo
    contrato_en_delegacion --> sin_firma_en_plazo
    sin_firma_en_plazo --> recurso_liberado: Secretaría Técnica, acuerdo del Comité (D)
    contratada --> vale_entregado: Delegación, PS y RHF (HU-3.4)
    vale_entregado --> planta_entregada: vivero (HU-3.4)
    planta_entregada --> ministracion_solicitada: Dirección (HU-5.1)
    contratada --> ministracion_solicitada: Dirección (HU-5.1)
    ministracion_solicitada --> contratada: Administración y Finanzas devuelve (motivo)
    ministracion_solicitada --> pagada: Administración y Finanzas, salvo PSAHEM (HU-5.2)
    pagada --> ministracion_solicitada: siguiente ministración
    ministracion_solicitada --> remitida_fiduciaria: Administración y Finanzas, PSAHEM (HU-5.2)
    remitida_fiduciaria --> cheque_emitido: Fiduciaria (HU-5.3)
    cheque_emitido --> cheque_enviado: Fiduciaria envía a la Delegación (HU-5.3)
    cheque_enviado --> cheque_entregado: Delegación entrega (HU-5.3)
    cheque_entregado --> ministracion_solicitada: siguiente ministración
    recurso_liberado --> [*]
```

| Estado | Bandeja (quién lo atiende) | También lo consultan |
| --- | --- | --- |
| `recibida`, `faltantes` | Delegación | Dirección del programa |
| `enviada_direccion` | Dirección del programa | — |
| `validada` (en dictamen) | Dirección (si le falta el técnico) y Unidad Jurídica (si le falta el jurídico) | Secretaría Técnica |
| `dictaminada` | Secretaría Técnica del Comité | Unidad Jurídica |
| `aprobada` | Dirección (publica, M3) | Unidad Jurídica, Secretaría Técnica |
| `lista_espera`, `no_factible` | — | Unidad Jurídica, Secretaría Técnica |
| `publicada`, `contrato_en_delegacion` | Delegación (notifica y cita; recaba la firma) | Unidad Jurídica |
| `notificada`, `contrato_elaborado` | Dirección (elabora y envía el contrato) | Unidad Jurídica |
| `sin_firma_en_plazo` | Dirección y Secretaría Técnica (recurso por liberar) | Unidad Jurídica |
| `contratada`, `planta_entregada`, `pagada`, `cheque_entregado` | Dirección (solicita la ministración) | Administración y Finanzas, Jurídica, vivero, Fiduciaria según el estado |
| `vale_entregado` | Vivero (PS y RHF) | — |
| `ministracion_solicitada` | Administración y Finanzas | Unidad Jurídica |
| `remitida_fiduciaria`, `cheque_emitido` | Fiduciaria (PSAHEM) | Administración y Finanzas |
| `cheque_enviado` | Delegación (entrega el cheque) | Fiduciaria, Administración y Finanzas |
| `recurso_liberado` | — (final) | Unidad Jurídica, Secretaría Técnica |

Una Delegación solo ve sus expedientes; una Dirección, los de los programas de los que es Instancia
Ejecutora; las demás unidades, los estados que atienden o consultan. Además, cada unidad ve en su bandeja
los **acuerdos del Comité** que le toca cumplir (HU-2.4).

## Decisiones tomadas

- **Reglas como datos.** `cargar_reglas` lee `reglas/<CLAVE>.json` (hoy solo `CC.json`): tipos de
  persona, modalidades, requisitos (con bandera de documento legal, `aplica_en_refrendo`, opcional y
  condición), plazos (cantidad + unidad; admite `cantidad: null` y unidades como `fecha_limite`),
  formatos, montos y ministraciones (estas dos quedan listas para el sprint 2). Las claves que el
  esquema no usa todavía se guardan en `Ejercicio.datos`. `datos/sistema.json` indica qué plazo usa el
  sistema para cada cosa y qué evento lo arranca (`usos_de_plazo`, ver «Base de M3 y M5») y para la vigencia
  en refrendo (`vigencia_documentacion_legal_refrendo`, 3 años).
- **Modalidades de CC.** El archivo de CC trae como «modalidades» los tres tipos de superficie, dos
  regímenes de pago y el refrendo. Al registrar solo se eligen los tipos de superficie
  (`ajustes_reglas` en `datos/sistema.json`); el refrendo es una casilla del expediente.
- **Expediente único por predio.** El predio tiene su folio (`PRED-000001`) que conserva entre
  programas (ROP CC 8.1.1.2 fr. XVII); cada solicitud a un programa-ejercicio es un `Expediente` con
  folio `CC-2026-AME-0001` y todo (requisitos, documentos, polígonos, validaciones, acuses, bitácora)
  cuelga de él. Los modelos del trámite llevan `django-simple-history`.
- **Municipios y Delegaciones.** Los 125 municipios vienen de la capa de IDEFOR, simplificada a ~40 m
  (`herramientas/preparar_municipios.py`). La capa no trae la clave INEGI: la clave es interna
  (`M001`…`M125`, orden alfabético). La asignación a Delegaciones es la de la Convocatoria 2026
  (`reglas/catalogos.json`); los nombres se empatan sin acentos y por prefijo («Acambay» → «Acambay de
  Ruíz Castañeda») y la carga falla con un mensaje que nombra al municipio si alguno no empata o queda
  sin Delegación. La interfaz la muestra como «según la Convocatoria 2026, por confirmar con el
  cliente»; se edita en el admin (Municipios).
- **HU-1.1.** Solo la Delegación registra. Si el municipio del predio lo atiende otra Delegación, se
  rechaza y el mensaje dice cuál (ROP CC 8.1.3); en el formulario se avisa por HTMX al elegir el
  municipio. El acuse de recepción (PDF con folio, fecha y hora) indica el plazo de 5 días hábiles para
  completar la documentación.
- **HU-1.2, regla de envío.** Se puede enviar a la Dirección cuando (1) todos los requisitos aplicables
  están revisados, (2) ninguno está faltante, porque las ROP piden la documentación completa para atender
  la solicitud (CC 8.1.1.2 fr. XIV), y (3) cada entregado tiene su archivo digitalizado o, en refrendo,
  es documentación vigente que obra en PROBOSQUE. «No aplica» solo se permite en requisitos opcionales o
  con condición. El polígono no es condición de envío: las ROP lo levantan después (CC 10.1 fr. III).
- **HU-1.3.** Se acepta GeoJSON, KML y Shapefile en .zip (con o sin .prj; sin .prj y con coordenadas
  grandes se asume UTM 14N), o el dibujo en el mapa con Leaflet-Geoman. La superficie se calcula en
  EPSG:32614. Una geometría inválida se rechaza; si cae fuera (o parcialmente fuera, >0.5 %) del
  municipio se guarda con aviso. Cada cambio conserva el polígono anterior; si el traslape
  (intersección/unión) es menor de 50 % se marca «cambio de lugar», si no «corrección». Se registra quién
  lo levantó (Delegación o prestador con RFN). Si el programa no usa polígono (PEG), la pestaña no
  aparece y el servicio lo rechaza.
- **HU-1.4.** La Dirección ve cada requisito con una revisión automática contra las reglas y marca los
  faltantes. Sin faltantes, el expediente queda validado (constancia en PDF). Con faltantes, se emite el
  aviso con fecha límite = fecha del aviso + 5 días hábiles (plazo de las reglas, calendario de días
  inhábiles), dirigido a la persona solicitante por conducto de la Delegación; el expediente pasa a la
  bandeja de la Delegación, que registra la notificación (acuse) y reenvía cuando recibe lo faltante.
  En refrendo, la documentación que obra en PROBOSQUE vale si su fecha no es anterior a la recepción
  menos la vigencia de las reglas (3 años); si es más vieja, la Delegación no la acepta y la Dirección
  la marca como faltante.
- **Días hábiles.** Sábados, domingos y el catálogo `DiaInhabil`. Un plazo en días hábiles empieza a
  contar el día hábil siguiente al evento; en días naturales, meses o años, si el último día es
  inhábil vence el siguiente hábil. Las ROP no traen calendario: se cargó uno de demostración 2026
  (`datos/dias_inhabiles_2026.json`), editable en el admin.
- **Acuses.** Cada envío o entrega (recepción, envío a la Dirección, validación, aviso de faltantes,
  notificación) genera un `Acuse` con folio `AC-AAAA-NNNNNN`, fecha y hora, PDF (WeasyPrint) y su huella
  SHA-256, y un evento en la bitácora.
- **Archivos.** `FileSystemStorage` en el volumen `archivos`; no hay URL pública de los archivos: se
  descargan por vistas que revisan la unidad del usuario.
- **Revisión de plazos.** En este sprint `revisar_plazos` solo señala en la bitácora (una vez) los
  avisos de faltantes vencidos y las solicitudes con faltantes cuyo plazo desde la recepción venció;
  no cambia estados.
- **Mapa base.** OpenStreetMap si hay conexión (`MAPA_TESELAS_URL`); vacío = sin teselas (las pruebas
  corren así).
- **Requisitos que no son documentos (ajuste a M1).** `datos/sistema.json`
  (`ajustes_reglas.CC.requisitos_sin_documento`) marca CC-REQ-01 y CC-REQ-03 como condiciones: se
  revisan como «cumple» o «no cumple» sin archivo (campo `Requisito.requiere_documento`). La pestaña
  Requisitos muestra solo el estado de cada fila y un botón «Revisar» que despliega su formulario. Los
  campos de archivo usan un botón «Elegir archivo» propio (`estaticos/js/archivos.js`), porque el texto
  del control nativo depende del idioma del navegador.

### Módulo M2 (Dictamen y Comité)

- **Organización.** Un módulo de servicios por historia (`dictamen/tecnico.py`, `juridico.py`,
  `aprobacion.py`, `seguimiento.py`), con sus vistas (`dictamen/vistas/`), formularios
  (`dictamen/formularios/`), plantillas (`templates/dictamen/<historia>/`) y pruebas por separado. Lo
  común: `models.py`, migraciones, `urls.py`, `admin.py`, `comun.py`, `sesiones.py` (convocatoria) y
  `registro.py`. El núcleo no depende de `dictamen`: la app se registra en `nucleo/extensiones.py`
  (filtros y paneles de bandeja, pestaña del expediente, menú, revisión de plazos y datos de
  demostración), que es donde se conectarán los módulos M3 a M6.
- **Estados.** Los dictámenes técnico y jurídico corren en paralelo sobre el expediente validado; el que
  completa el par pasa el expediente a `dictaminada` (bandeja de la Secretaría Técnica). Se quitó la
  transición `validada → no_factible` del sprint anterior: según las ROP de CC (10.1 fr. VI y VII; 9.4.3
  fr. I y III) los dictámenes producen el listado preliminar y es el Comité quien aprueba la Lista de
  Personas Beneficiarias, la Lista de espera y la Lista de No factibles. Por eso las tres salidas de
  `dictaminada` las registra la Secretaría Técnica con el acta. `Estado.tipo_unidad_bandeja` admite
  varios tipos de unidad (separados por coma) y `Estado.visible_para`, las unidades que solo consultan.
- **HU-2.1.** La lista de verificación se arma con `superficie`, `criterios_elegibilidad_tecnica`,
  `inelegibles` y `criterios_seleccion` del archivo de reglas; un criterio «no cumple» impide el dictamen
  factible. El análisis cartográfico usa PostGIS: polígono vigente, superficie en EPSG:32614, rango del
  programa, ubicación en el municipio y traslapes (`geom__intersects`) con polígonos vigentes de otros
  expedientes del mismo ejercicio, con su superficie en hectáreas; se guarda una copia en el dictamen.
  El plazo de dictaminación sale de las reglas (`datos/dictamen.json` nombra las claves): en PEG,
  45 días hábiles desde la recepción (Convocatoria PEG, base quinta, fr. II, línea 9516); en CC, la fecha
  límite de la Convocatoria (30-jun-2026). El dictamen queda «en plazo» o «fuera de plazo»; sin
  dictamen, «en plazo», «por vencer» (5 días hábiles o menos) o «vencido», y `revisar_plazos` lo señala
  una vez en la bitácora. El listado preliminar reúne el resultado técnico y jurídico de cada solicitud
  validada y se exporta a CSV en UTF-8 con BOM (Excel lo abre con acentos).
- **HU-2.2.** El Listado de Personas Beneficiarias Incumplidas y los predios con procedimiento o
  sanción son catálogos con historial (`django-simple-history`); una baja desactiva, no borra. El cotejo
  es automático (persona, CURP, RFC, nombre sin acentos y predio) y se muestra en la pantalla y en el
  acuse. Con coincidencias, el **servicio** rechaza el dictamen procedente. Un predio sancionado con el
  reintegro hecho deja de impedir el apoyo (CC 8.1.1.1, inelegibles fr. III). En refrendo se pide el
  dictamen igual (CC 10.1 fr. IV).
- **HU-2.3.** La convocatoria exige orden del día y al menos un documento y se rechaza si no se envía con
  la anticipación de las reglas (`convocatoria_sesion_comite`: 3 días hábiles; 24 horas si es
  extraordinaria); su acuse lleva la fecha y la hora del envío, el orden del día y los integrantes del
  Comité tomados de `CC.json` (`instancias.comite`) o de `catalogos.json`. La propuesta de listados
  ordena las factibles por los criterios de priorización que se pueden leer del expediente
  (`datos/dictamen.json`: reforestaciones primero, 8.1.2 fr. I; refrendos, fr. II) y desempata por fecha y
  hora de registro (8.1.2, último párrafo); asigna hasta donde alcance el recurso disponible
  ($2,000 por ha de superficie factible, numeral 7.2) y el resto va a la lista de espera con su lugar.
  El Comité puede mover una solicitud de listado o de lugar con un motivo obligatorio, que queda en el
  acta, en el historial y en la bitácora; una no factible no puede pasar a los listados de apoyo. El acta
  (PDF) trae los tres listados y la autorización de publicación, y mueve cada expediente a `aprobada`,
  `lista_espera` o `no_factible`.
- **HU-2.4.** Los tipos de acuerdo y el área que los cumple por omisión están en `datos/dictamen.json`
  (reasignación, sustitución, caso fortuito, suspensión, cancelación, baja, reintegro, instrucción de
  pago a la Fiduciaria solo en PSAHEM y por ministración, validación de reportes solo en PEG y por
  periodo, y otro). Cada acuerdo lleva sus expedientes y su unidad responsable, que lo ve en su bandeja y
  lo marca como cumplido. `ministraciones_sin_instruccion` y `periodos_sin_validacion` dicen qué falta.
  Los acuerdos todavía no ejecutan nada en otros módulos: `dictamen.seguimiento.RECEPTORES` es el punto
  de conexión (tipo de acuerdo → funciones) para pagos (M5) y seguimiento (M6).

### Base de M3 (Publicación y contrato) y M5 (Pagos)

- **Notificaciones en el núcleo.** `nucleo.Notificacion` y `nucleo/notificaciones.py` son la única forma de
  notificar a la persona por conducto de la Delegación (faltantes, resultados, cita a firma, omisiones,
  devoluciones; `TipoNotificacion`). Dos momentos, cada uno con fecha, hora, acuse y renglón de bitácora:
  `emitir_notificacion(expediente, tipo, asunto, usuario, acuse_envio=None, …)` (la unidad que decide la
  manda a la Delegación; si no trae acuse propio se emite uno) y `registrar_notificacion(usuario_delegacion,
  notificacion, medio, fecha_hora=None)` (solo la Delegación de la notificación; fecha no futura ni anterior
  al envío). `pendientes_de_notificar(delegacion)` y `ultima_notificada(expediente, tipo)` sirven a bandejas
  y plazos; `extensiones.AL_NOTIFICAR` avisa a los módulos. Cada módulo guarda una referencia a la suya: M1
  lo hace en `Validacion.notificacion` (la migración `recepcion/0002` pasó los avisos existentes al núcleo;
  `Validacion.notificado_en`, `notificado_por` y `acuse_notificacion` quedan como propiedades).
- **Plazos con evento de arranque (R-03, R-12).** `nucleo.plazos.vencimiento(expediente, uso)` es el único
  cálculo de vencimientos por evento. `datos/sistema.json` → `usos_de_plazo` resuelve cada uso **por programa**
  (`por_omision` + lo propio del programa; `false` = no lo tiene) a una clave de plazo de las reglas, un evento
  de arranque y, si aplica, un tope. Devuelve un `Vencimiento` (`vencimiento`, `fecha_evento`, `tope`,
  `topado`, `texto`, `estado()`): si el evento no ha ocurrido, «sin fecha todavía». Los eventos que producen
  otros módulos se registran con `plazos.registrar_hito(expediente, clave, usuario, fecha_hora)` (modelo
  `Hito`) o con una función en `extensiones.EVENTOS_PLAZO`; el servicio no cambia.

  | Uso | Plazo de las reglas | Evento | Tope / nota |
  | --- | --- | --- | --- |
  | `faltantes_ventanilla` | `complemento_documentacion_faltante` (5 d. háb.) | `recepcion_solicitud` | fecha límite de recepción (`recepcion_solicitudes`, 27-mar-2026), ROP 8.1.1.2 |
  | `faltantes_direccion` | el mismo | `aviso_direccion` | decisión propia (las ROP no dan días, 10.1) |
  | `firma_programada` | `firma_contrato` (10 d. háb.) | CC y PSA: `publicacion_resultados`; PS y RHF: `notificacion_persona` | reasignadas: desde su notificación, hasta `fecha_limite_reasignados` |
  | `firma_liberacion` | `firma_contrato` | CC y RHF: `notificacion_persona`; PS y PSA: `publicacion_resultados` | vencido = «sin firma en plazo», recurso por liberar |
  | `cita_firma` (PS) | `cita_firma_contrato` (5 d. háb.) | `publicacion_resultados` | la Delegación notifica y cita |
  | `recoger_planta` (PS, RHF) | `recoger_planta_vivero` / `recoger_planta_vale` | `entrega_vale` | PS: «30 días» como naturales (R-13) |
  | `ptrfi_actualizado` (RHF) | `entrega_ptrfi_actualizado` | `notificacion_persona` | |
  | `instruccion_pago_fiduciaria`, `cobro_cheque` (PSA) | los de las reglas | `solicitud_pago_fiduciaria`, `entrega_cheque` | cheque: desde la entrega (R-14) |

  Si el evento ocurrió después del tope (por ejemplo, una solicitud de demostración recibida después del
  27-mar-2026), no se topa: se marca `evento_despues_del_tope` y el acuse lo avisa. M1 ya usa el servicio
  (acuse de recepción, aviso de faltantes, revisión de plazos).
- **Monto aprobado.** `nucleo.montos.monto_aprobado(expediente, superficie=None, condiciones=())` devuelve
  `MontoAprobado` (`superficie_ha`, `monto_ha`, `total`, `regimen`, `ministraciones` con número, porcentaje,
  importe y condición). Superficie: la que se pase o la factible del dictamen técnico
  (`extensiones.SUPERFICIE_APROBADA`, la registra M2) o la solicitada. Monto por hectárea: el de la modalidad
  del expediente o, si no tiene propio, el general del ejercicio; un concepto sin dinero da 0 sin
  ministraciones (PS, navideñas). `MontoApoyo.modalidad` se llena al cargar las reglas: con la clave del
  archivo o, en PS, por el inicio del concepto (`ajustes_reglas.PS.modalidad_de_montos`). Los montos con
  `requiere` (FSC en PSAHEM) cuentan solo con esa condición. El régimen de pago sale de
  `ajustes_reglas.<CLAVE>.regimen_pago`: CC por superficie (100 % hasta 5 ha; 70 y 30 arriba), PS y RHF por
  modalidad, PSAHEM fijo (70 y 30). La última ministración absorbe el redondeo. La propuesta de listados
  del Comité (HU-2.3) ya usa este servicio.
- **M1 y M2 con PS, RHF y PSAHEM.** El recorrido completo corre en los cuatro programas con reglas. Lo que
  se corrigió por estar pensado para CC: el rango de superficie se lee por modalidad (`nucleo/reglas.py`,
  `rango_superficie`: por concepto en PS, por cuenca en PSAHEM con máximo mayor si hay FSC, sin máximo en RHF),
  en la lista de verificación y en el análisis cartográfico del dictamen técnico; el Comité de PSAHEM se lee
  de `instancias.comite_tecnico` (Comité Técnico del FIPASAHEM); el registro rechaza en el servicio, no solo
  en el formulario, las modalidades no seleccionables. Lo que ya funcionaba sin cambios: los requisitos que
  no son documentos (PS, RHF y PSAHEM los marcan en sus reglas con `requiere_documento: false`), los plazos de
  faltantes y de dictaminación (cada programa tiene el suyo) y las modalidades no seleccionables de PSAHEM
  (fondos concurrentes y refrendo, marcadas en sus reglas). PSAHEM no trae `convocatoria_sesion_comite`: la
  convocatoria de su Comité Técnico no valida anticipación mientras no se tenga su Reglamento Interno (R-14).
  La priorización del Comité (`datos/dictamen.json`) solo tiene criterios de CC; en los demás programas se
  ordena por fecha y hora de registro.

## Diferencias con la especificación (mandan las ROP)

- La especificación pide asignar municipios a Delegaciones de forma provisional; las ROP y la
  Convocatoria sí traen la tabla completa (125 municipios), así que se usa esa tabla, marcada por
  confirmar.
- El polígono se levanta después de entregar el expediente (CC 10.1 fr. III), por eso no es requisito
  para enviarlo a la Dirección.
- La no factibilidad no la decide la Dirección ni la Unidad Jurídica por sí solas: el dictamen produce
  el listado preliminar y el Comité aprueba la Lista de solicitudes No factibles (CC 10.1 fr. VI y VII;
  9.4.3 fr. I y III). Se quitó la transición directa `validada → no_factible`.
- En CC el plazo de dictaminación no es un número de días sino la fecha límite de la Convocatoria
  (30-jun-2026); el de 45 días hábiles es solo de PEG.

## Pendientes con el cliente

- Confirmar la asignación de municipios a Delegaciones y el calendario oficial de días inhábiles 2026.
- Plazo del aviso de faltantes de la Dirección: las ROP dicen «dentro del plazo de evaluación»
  (10.1 fr. V) sin cantidad; se usó el de complemento (5 días hábiles, 8.1.1.2 fr. XIV) contado desde el
  aviso. Falta decidir si corre desde el aviso o desde la notificación de la Delegación, y si debe
  topar con la fecha límite de recepción de la Convocatoria (27-mar-2026).
- Requisitos que no son documentos: se marcaron CC-REQ-01 y CC-REQ-03 (`datos/sistema.json`); confirmar
  la lista.
- Priorización en CC: las ROP no traen puntaje; se propone el orden reforestaciones → refrendos → fecha
  de registro. Confirmar con el Comité los demás criterios (8.1.2 fr. III a X necesitan datos que hoy no
  se capturan: índice de presión, ANP, grupos prioritarios…).
- Recurso disponible por sesión y monto por hectárea cuando la superficie factible difiere de la
  solicitada.
- Plazo de convocatoria de los Comités de PSAHEM y PEG (5 días hábiles en el CASPEG, línea 8939) y
  sus integrantes: cuando existan sus archivos de reglas.
- Si el acta debe esperar a la fecha de la sesión: hoy se puede registrar en cuanto se envía la
  convocatoria.
- Clave INEGI de los municipios (la capa de IDEFOR no la trae).
- Nombre de la fiduciaria del FIPASAHEM y departamento responsable de cada programa.
- Reglas de MFS y PEG (archivos `reglas/<CLAVE>.json`).

## Modelo de datos y recorrido completo

- [`docs/modelo_datos.md`](docs/modelo_datos.md): diagrama entidad-relación por áreas (núcleo, recepción,
  dictamen), generado desde los modelos con `herramientas/diagrama_er.py`; el completo, con todos los
  campos, está en `docs/modelo_datos.mmd`.
- `pruebas/test_sprint_1_recorrido_completo.py` (parametrizada por programa: CC, PS, RHF y PSAHEM): una sola solicitud recorre el registro, los requisitos, el
  polígono, el envío, el aviso de faltantes y su reenvío, la validación, los dos dictámenes, la sesión de
  aprobación y un acuerdo de seguimiento. En cada relevo comprueba el estado, en la bandeja de qué unidad
  queda, el acuse y el renglón de la bitácora.
