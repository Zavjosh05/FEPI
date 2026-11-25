# PROBOSQUE 2026 — Sistema modular de programas y Calculadora forestal

Este archivo es el contexto para la sesión de desarrollo que va a construir los prototipos. Léelo completo antes de empezar.
Fuente: la *Propuesta de solución modular — Programas PROBOSQUE 2026* (versión del 12-nov-2026, en `docs/`).

## 1. Contexto y forma de trabajo

- **Cliente:** PROBOSQUE (Protectora de Bosques del Estado de México). **Usuario:** Joshua, estudiante que levanta necesidades y propone la solución para un curso; el profesor revisa cada entrega.
- **Idioma:** todo en español: interfaz, mensajes, documentación y nombres del dominio en el código (`Expediente`, `Predio`, `Ministracion`). Lo técnico del framework puede ir en inglés.
- **Quién desarrolla:** la sesión de desarrollo, con revisión del equipo. Cada entrega debe poder probarse con código: pruebas automáticas y capturas.
- **Qué se construye:** dos subsistemas independientes:
  1. **Sistema de programas** (módulos M1 a M6): el trámite de seis programas de apoyo, desde la solicitud hasta el padrón.
  2. **Calculadora forestal** (M7): masa forestal del Estado de México por municipio y año. Ya existe un prototipo (`calculadora/mapa_edomex.html`).
- **Regla de oro de trazabilidad:** cada **función** (M1.1…M7.5) tiene **una sola historia de usuario** (HU-1.1…HU-7.5). Nombra pruebas, ramas y commits con el ID de la historia (por ejemplo `test_hu_3_3_contrato_firmado_en_plazo`, commit `HU-3.3: firma del contrato`). Las necesidades (CC-DRF-02, …) se cubren con funciones; la matriz está en `datos/modelo.json`.

### Documentos de referencia (carpeta `docs/`)

| Archivo | Para qué |
| --- | --- |
| `Propuesta_solucion_modular_PROBOSQUE_2026.pdf` | La propuesta aprobada: arquitectura, módulos, funciones, historias, matriz, plan. |
| `Tablas_de_necesidades_por_rol_PROBOSQUE_2026_v12.pdf` | **Necesidades vigentes** (133 de los programas + 5 de la Calculadora). Cada necesidad cita su numeral de las ROP. |
| `ROP_PROBOSQUE_2026_texto.txt` | Texto de las Reglas de Operación 2026 y manuales de formatos (Gaceta del Gobierno, 27-ene-2026). **Es la autoridad** cuando una regla, plazo o formato no queda claro. El PDF original se conserva aparte. |
| `historico/` | Versiones anteriores de las tablas de necesidades (v9 a v11), solo para consulta. |
| `Matriz_funciones_historias_PROBOSQUE.xlsx` | Matriz necesidad × función, catálogo, historias, complejidad y sprints. |

Datos para usar desde código (carpeta `datos/`): `modelo.json` (módulos, funciones, historias con criterios, puntos, sprint y el mapeo necesidad → funciones) y `necesidades_v12.json` (texto completo de cada necesidad). Úsalos para generar fixtures y pruebas en lugar de copiar texto a mano.

### Los seis programas (clave en los IDs de necesidad)

| Clave | Programa | Notas |
| --- | --- | --- |
| CC | Capturando Carbono | Verificación en campo en 15 días hábiles. |
| MFS | Manejo Forestal Sustentable | Prestador de servicios forestales (polígono, contrato de servicios técnicos con RFN); flujo G de prórroga por causa externa. |
| PS | Plantaciones Sustentables | Vale de Planta (vigencia 30 días); cita a firma en 5 días hábiles tras la publicación; cambio de polígono antes de plantar; verificación en 30 días hábiles. |
| RHF | Restauración Hidrológico-Forestal | PTRFI del prestador; Diagnóstico Técnico en la visita; Vale de Planta (15 días hábiles); verificación en 10 días hábiles. |
| PSA | PSAHEM (Pago por Servicios Ambientales Hidrológicos) | Comité Técnico del FIPASAHEM; pago con cheques de la Fiduciaria (70 % y 30 %), cobro en 3 meses; instrucción de pago tramitada en 5 días hábiles; Índice de Presión Económica a la Deforestación (INECC). |
| PEG | Guardabosques | CASPEG; reportes mensuales evaluados antes de cada ministración (hasta 4 al año); credencial; dictamen en 45 días hábiles; no usa polígono, planta ni lista de espera. |

Roles en los IDs: BEN persona beneficiaria (o Guardabosque), PSF prestador de servicios forestales, DRF Delegación Regional Forestal, VIV vivero, ARP área responsable del programa (Dirección que es Instancia Ejecutora; en PEG es DPF, Dirección de Protección Forestal), UJ Unidad Jurídica, COM Comité (Secretaría Técnica e integrantes), AF Administración y Finanzas, FID Fiduciaria, DEV equipo desarrollador (Calculadora).

Plazos y reglas que aparecen en varias historias: firma del contrato en **10 días hábiles** después de la notificación (PSAHEM: plazo de la convocatoria); aviso de caso fortuito en **15 días hábiles**; refrendo con documentación legal vigente de hasta **3 años**; toda notificación a la persona beneficiaria va **por conducto de la Delegación**; **todo envío o entrega registra fecha, hora y acuse**; la solicitud se registra **a nombre del predio** en la Delegación que le corresponde.

Flujos alternos (estados del trámite): A expediente incompleto, B dictamen no factible, C lista de espera, D caso fortuito, E incumplimiento y reintegro, F sustitución, G prórroga (solo MFS).

## 2. Arquitectura y tecnologías (decididas)

| Capa | Tecnología | Notas para construir |
| --- | --- | --- |
| Presentación | Plantillas de Django + **HTMX** + **Bootstrap 5**; **Leaflet** para mapas; **WeasyPrint** para PDF | Sin SPA ni API aparte. HTMX para tablas, filtros, bandejas y cambios de estado. |
| Aplicación | **Django** (Python) con **GeoDjango** | Un solo proyecto; una app por módulo (`recepcion`, `dictamen`, `contrato`, `ejecucion`, `pagos`, `seguimiento`) y una app `nucleo`. |
| Estados del trámite | Campo de estado en el modelo + tabla de transiciones permitidas, validadas en el código | No hace falta django-fsm ni otra librería de estados. |
| Plazos y avisos | Comando de Django (`manage.py revisar_plazos`) que corre cada día con cron (servicio en Docker Compose) | **No** usar Celery/Redis en el prototipo; agregarlo solo si los avisos crecen. |
| Datos | **PostgreSQL + PostGIS** | Una sola base para trámite y geometrías (polígonos, municipios). |
| Archivos | Disco del servidor con el almacenamiento de archivos de Django (`FileSystemStorage`, volumen de Docker) | **No usar MinIO**: desde octubre de 2025 no publica binarios ni imágenes de su edición comunitaria y en 2026 su repositorio quedó archivado. Si hace falta S3, usar `django-storages` con SeaweedFS, Garage o un servicio en la nube, cambiando solo la configuración. |
| Historial | `django-simple-history` | Quién, qué, fecha y hora de cada cambio. |
| Pruebas | **pytest + pytest-django** y **Playwright** | Una o más pruebas por criterio de aceptación; Playwright toma capturas de cada prototipo para revisión. |
| Infraestructura | **Docker Compose** (web con Gunicorn, Nginx, PostGIS, cron), repositorio en **GitHub** | Todo el entorno descrito en archivos del repositorio. Servidor: de PROBOSQUE o un VPS (sin definir). |
| Maquetas | HTML con Bootstrap | Son la primera versión de las pantallas reales; no se usa Figma. |
| Calculadora | Python (pystac-client, rasterio, geopandas, numpy), QGIS para revisión; página estática con **D3.js**; resultados en archivos JSON, TopoJSON y COG/PNG | **Opción A** aprobada: sin servidor ni base de datos. Pasar a una API (FastAPI + TiTiler + PostGIS) solo si se pide comparar cualquier par de años al momento. **No usar Google Earth Engine** (licencia comercial para uso gubernamental). |

### Núcleo común (app `nucleo`)
- **Expediente único por predio:** todo (dictámenes, acuerdos, contrato, pagos, verificaciones, reintegros) cuelga del expediente.
- **Estados y bandejas:** al terminar una etapa, el expediente pasa a la bandeja de la unidad siguiente.
- **Roles y permisos:** grupos de Django por unidad (Delegación, Dirección, Unidad Jurídica, Secretaría Técnica, Administración y Finanzas, vivero, Fiduciaria) y por programa. Personas beneficiarias y prestadores entran por un portal externo.
- **Reglas por programa y ejercicio:** requisitos por tipo de persona y modalidad, montos, porcentajes de ministración, plazos y modelos de documentos como datos (no en código).
- **Días hábiles:** calendario configurable de días inhábiles.
- **Bitácora y acuses:** cada envío/entrega guarda fecha, hora y acuse (PDF).

### Modelo de datos inicial
| Entidad | Qué guarda | Módulos |
| --- | --- | --- |
| Programa, Ejercicio | Requisitos, montos, porcentajes, plazos, modelos de documentos | Núcleo |
| Usuario, Unidad, Rol | Acceso y permisos | Núcleo |
| Predio | Municipio, Delegación, polígono (geometría), Diagnóstico Técnico | M1, M4 |
| Persona | Solicitante o beneficiaria, Guardabosque, núcleo agrario, prestador (RFN) | M1, M3, M6 |
| Expediente | Solicitud, programa, estado, acuse de recepción | M1 a M6 |
| Documento | Archivo, tipo, fecha y hora de entrega, acuse | Todos |
| Dictamen | Técnico o jurídico, resultado, motivo | M2 |
| Sesion, Acuerdo | Comité, fecha, orden del día, acuerdos y expedientes | M2 |
| Contrato | Modelo validado, firmas, fecha y hora de firma, ampliaciones | M3 |
| ValePlanta, SalidaPlanta | Especie, cantidad, vivero, vigencia, entrega | M3 |
| Envio | Avisos, informes, bitácoras, reportes con fecha y hora | M4 |
| Verificacion, Incidencia | Superficie verificada, ajuste, incidencias con documento | M4 |
| Ministracion, Pago | Solicitud, soportes, pago o cheque, fechas | M5 |
| CasoSeguimiento | Reasignación, sustitución, incumplimiento, devolución, reintegro | M6 |

Catálogos iniciales: municipios del Estado de México (capa `geonode:municipios` de IDEFOR, WFS `https://idefor.cnf.gob.mx/geoserver/ows`), Delegaciones y municipios que atiende cada una (pendiente de confirmar con el cliente).

## 3. Módulos, funciones e historias de usuario

Formato de historia: «Como [rol], quiero [acción], para [beneficio]», centrada en la acción del usuario. Los criterios de aceptación son **condiciones**, no acciones ("Existe…", "Queda…"). Puntos en escala Fibonacci. Cada criterio debe tener al menos una prueba automática.

### M1. Recepción y expediente

Recibe la solicitud en la Delegación, integra el expediente digital del predio con su ubicación y lo deja validado para dictaminarse.

**M1.1 · HU-1.1 · Registro de la solicitud** — 3 puntos · sprint 1
- Función: Registro de la solicitud a nombre del predio en la Delegación que le corresponde, con su acuse y la fecha y la hora de recepción.
- Historia: Como personal de la Delegación, quiero registrar la solicitud con los datos generales de la persona solicitante, los datos del predio y los datos específicos del programa, para iniciar su trámite.
- Criterios: (1) Se genera un folio único para la solicitud. (2) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-DRF-01, MFS-DRF-01, PS-DRF-01, RHF-DRF-01, PSA-DRF-01, PEG-DRF-01

**M1.2 · HU-1.2 · Revisión del expediente** — 3 puntos · sprint 1
- Función: Revisión de los requisitos según el programa, el tipo de persona y la modalidad; digitalización del expediente (incluido el PTRFI en RHF) y su envío a la Dirección, con la fecha y la hora del envío.
- Historia: Como personal de la Delegación, quiero revisar los requisitos del expediente y enviarlo digitalizado a la Dirección, para que la solicitud no se detenga por falta de documentos.
- Criterios: (1) Cada requisito del programa, del tipo de persona y de la modalidad está revisado como entregado (con su archivo digitalizado), faltante o, si es condicional, no aplica. (2) El expediente digital está en la Dirección, con la fecha y la hora del envío. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-DRF-01, MFS-DRF-01, PS-DRF-01, RHF-PSF-01, RHF-DRF-01, PSA-DRF-01, PEG-DRF-01

**M1.3 · HU-1.3 · Ubicación del predio** — 5 puntos · sprint 1
- Función: Ubicación del predio: polígono levantado en campo por la Delegación o por el prestador de servicios forestales, Diagnóstico Técnico (RHF) y cambio de lugar del polígono antes de plantar (PS).
- Historia: Como personal de la Delegación, quiero registrar el polígono del predio levantado en campo por la Delegación o por el prestador de servicios forestales, para conocer su ubicación y su superficie real al dictaminar y verificar.
- Criterios: (1) Existe un polígono asociado al expediente del predio. (2) Si el polígono cambia de lugar, existen el anterior y el nuevo. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-DRF-01, MFS-PSF-01, MFS-DRF-01, PS-BEN-01, PS-DRF-01, PS-DRF-05, RHF-DRF-01, PSA-DRF-01

**M1.4 · HU-1.4 · Validación del expediente** — 3 puntos · sprint 1
- Función: Validación del expediente por la Dirección que es Instancia Ejecutora, incluidos los refrendos, y aviso de los faltantes dentro del plazo de evaluación.
- Historia: Como personal del área responsable del programa, quiero validar el expediente contra las reglas del programa y avisar cada faltante con su observación, para que la solicitud pase a dictamen o se corrija a tiempo.
- Criterios: (1) El expediente está validado o tiene un aviso de faltantes con fecha límite. (2) Cada requisito señalado como faltante tiene la observación de la Dirección (qué falta o por qué no es válido) y el aviso de faltantes la incluye. (3) En un refrendo, la documentación legal vigente de hasta 3 años es válida. (4) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-ARP-01, MFS-ARP-01, PS-ARP-01, RHF-ARP-01, PSA-ARP-01, PEG-DPF-01

### M2. Dictamen y Comité

Determina si cada solicitud procede y lleva al Comité lo que debe aprobar o acordar durante el ejercicio.

**M2.1 · HU-2.1 · Dictamen técnico** — 5 puntos · sprint 1
- Función: Dictamen técnico con los criterios del programa y su análisis cartográfico (diagnóstico técnico forestal en CC, revisión de polígonos en MFS, Índice de Presión Económica a la Deforestación en PSAHEM), y listado preliminar de solicitudes factibles y no factibles.
- Historia: Como personal del área responsable del programa, quiero elaborar el dictamen técnico de cada solicitud, expedido como documento, y el listado preliminar, para proponer al Comité qué solicitudes apoyar.
- Criterios: (1) Cada solicitud tiene un dictamen técnico factible o no factible, con su motivo, expedido como documento PDF con folio y adjunto al expediente. (2) Existe un listado preliminar con el resultado técnico y jurídico de cada solicitud. (3) En PEG, el dictamen existe dentro de los 45 días hábiles. (4) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-ARP-02, MFS-ARP-02, PS-ARP-02, RHF-ARP-02, PSA-ARP-02, PEG-DPF-02

**M2.2 · HU-2.2 · Dictamen jurídico** — 3 puntos · sprint 1
- Función: Dictamen jurídico de la documentación legal, con el cotejo del Listado de Personas Beneficiarias Incumplidas y de los predios con procedimiento o sanción (en PEG, acta de asamblea y representación del núcleo agrario).
- Historia: Como personal de la Unidad Jurídica, quiero dictaminar la documentación legal de cada solicitud, revisar que se acredite la propiedad o legal posesión del predio y cotejar a su titular con el Listado de Personas Beneficiarias Incumplidas y su predio con los predios con procedimiento o sanción, para que solo se aprueben solicitudes procedentes.
- Criterios: (1) Cada solicitud tiene un dictamen jurídico procedente o no procedente, con su motivo, expedido como documento PDF con folio y adjunto al expediente. (2) Una solicitud cuya propiedad o legal posesión del predio no se acredita (documento a nombre del titular, que ampare la superficie, vigente y sin conflicto) es no procedente. (3) Una solicitud cuyo titular está en el Listado de Personas Beneficiarias Incumplidas, o cuyo predio tiene un procedimiento o una sanción, es no procedente. (4) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-UJ-01, MFS-UJ-01, PS-UJ-01, RHF-UJ-01, PSA-UJ-01, PEG-UJ-01

**M2.3 · HU-2.3 · Sesión de aprobación** — 3 puntos · sprint 1
- Función: Sesión de aprobación: convocatoria y documentos de la sesión, y acta con la lista de personas beneficiarias o el padrón, la lista de espera, las no factibles y la autorización de publicación.
- Historia: Como integrante del Comité, quiero aprobar en sesión los listados de la convocatoria, para que se puedan publicar.
- Criterios: (1) Existe la convocatoria con orden del día y documentos, y la fecha y la hora de su envío. (2) Existe un acta con los listados aprobados y la autorización de publicación. (3) Las solicitudes candidatas (en dictamen, por aprobar y en lista de espera, en su orden) y las personas beneficiarias (con su monto y cómo entraron) se consultan en dos vistas separadas. (4) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-COM-01, MFS-COM-01, PS-COM-01, RHF-COM-01, PSA-COM-01, PEG-COM-01

**M2.4 · HU-2.4 · Sesiones de seguimiento** — 3 puntos · sprint 1
- Función: Sesiones de seguimiento: acuerdos de reasignación, sustitución, caso fortuito, suspensión, cancelación, baja y reintegro; en PSAHEM, instrucción de pago a la Fiduciaria; en PEG, validación de la evaluación de reportes.
- Historia: Como integrante del Comité, quiero acordar en las sesiones de seguimiento la atención de cada incidente del ejercicio y la reasignación del recurso liberado a la lista de espera, para que el recurso llegue a otra solicitud factible y cada caso tenga un área que lo atienda.
- Criterios: (1) Cada incidente (desistimiento, cancelación, baja, sustitución, caso fortuito, suspensión o reintegro) tiene un acuerdo con su causa, los expedientes a los que aplica y el área que debe atenderlo. (2) En una reasignación o sustitución, la persona beneficiaria que sale queda dada de baja y entra la siguiente solicitud de la lista de espera, en su orden, sin rebasar el recurso liberado. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-COM-02, MFS-COM-02, PS-COM-02, RHF-COM-02, PSA-COM-02, PSA-COM-03, PEG-COM-02

### M3. Publicación y contrato

Publica los resultados, notifica a las personas y formaliza el apoyo con el contrato firmado y, cuando aplica, la entrega de planta.

**M3.1 · HU-3.1 · Publicación y notificaciones** — 3 puntos · sprint 2
- Función: Publicación de los resultados o del padrón en la página de PROBOSQUE y en las Delegaciones, y avisos y notificaciones por conducto de la Delegación (faltantes, cita a firma, omisiones, devoluciones), con la fecha y la hora y su acuse.
- Historia: Como personal del área responsable del programa, quiero publicar los listados aprobados y avisar a cada persona su resultado por conducto de la Delegación, para que los plazos corran desde una notificación comprobable.
- Criterios: (1) Los listados autorizados por el Comité están publicados en la fecha de la convocatoria. (2) Cada aviso tiene su acuse y la fecha y la hora de envío y de notificación. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-ARP-01, CC-ARP-03, CC-ARP-07, CC-UJ-03, MFS-ARP-01, MFS-ARP-03, MFS-ARP-07, MFS-UJ-03, PS-DRF-02, PS-ARP-01, PS-ARP-03, PS-ARP-07, PS-UJ-03, RHF-ARP-01, RHF-ARP-03, RHF-ARP-07, RHF-UJ-03, PSA-ARP-01, PSA-ARP-03, PSA-ARP-07, PSA-UJ-03, PEG-DPF-01, PEG-DPF-03

**M3.2 · HU-3.2 · Elaboración del contrato** — 3 puntos · sprint 2
- Función: Validación jurídica del modelo de Contrato de Adhesión o Convenio de Concertación (y su adendum) y elaboración de cada contrato con los datos de la solicitud aprobada; ampliación de plazo por causa externa en MFS.
- Historia: Como personal del área responsable del programa, quiero elaborar el contrato de cada solicitud aprobada sobre el modelo validado y enviarlo a la Delegación, para que se firme.
- Criterios: (1) Existe un contrato por solicitud aprobada, elaborado sobre un modelo validado. (2) Existe la fecha y la hora del envío a la Delegación. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-ARP-04, CC-UJ-02, MFS-ARP-04, MFS-ARP-06, MFS-UJ-02, PS-ARP-04, PS-UJ-02, RHF-ARP-04, RHF-UJ-02, PSA-ARP-04, PSA-UJ-02, PEG-DPF-04, PEG-UJ-02

**M3.3 · HU-3.3 · Firma del contrato** — 5 puntos · sprint 2
- Función: Firma del contrato por la persona beneficiaria dentro de los 10 días hábiles (en PSAHEM, el plazo de la convocatoria), con verificación de firmas y sello; contrato de servicios técnicos en MFS y credencial del Guardabosque en PEG.
- Historia: Como personal de la Delegación, quiero recabar la firma del contrato dentro del plazo y verificar las firmas y el sello, para formalizar el apoyo.
- Criterios: (1) Existe el contrato firmado, con la fecha y la hora de la firma, dentro del plazo. (2) En MFS existe el contrato de servicios técnicos con el RFN y la carta compromiso; en PEG, la credencial entregada. (3) Un contrato sin firma al vencer el plazo queda señalado para liberar el recurso. (4) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-DRF-02, MFS-PSF-02, MFS-DRF-02, PS-DRF-02, RHF-DRF-02, PSA-DRF-02, PEG-DRF-02, PEG-DPF-04

**M3.4 · HU-3.4 · Entrega de planta** — 5 puntos · sprint 2
- Función: Entrega de planta: Vale de Planta (con carta compromiso si se pide antes del contrato), salida de planta del vivero por especie y cantidad, y vigencia del vale (30 días en PS, 15 días hábiles en RHF) con su reposición.
- Historia: Como personal del vivero, quiero validar el Vale de Planta y registrar la salida de planta por especie y cantidad, para entregar solo la planta autorizada.
- Criterios: (1) Existe un Vale de Planta vigente por la especie y la cantidad entregadas. (2) La salida de planta tiene especie, cantidad y fecha. (3) Un vale vencido no es válido y puede reponerse. (4) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: PS-DRF-03, PS-VIV-01, RHF-BEN-01, RHF-DRF-03, RHF-VIV-01

### M4. Ejecución y verificación

Recibe lo que comprueba la ejecución de las actividades, desde el portal o en la Delegación, y registra la verificación en campo.

**M4.1 · HU-4.1 · Envío de comprobaciones** — 5 puntos · sprint 3
- Función: Envío de avisos (término, caso fortuito, cambio de polígono), informes, bitácoras, reportes mensuales y acuses de depósito por la persona beneficiaria o el Guardabosque, en el portal o en la Delegación, con la fecha y la hora y su acuse.
- Historia: Como persona beneficiaria, quiero enviar mis avisos, informes y reportes a la Delegación, para comprobar mis actividades dentro del plazo.
- Criterios: (1) Cada envío tiene su acuse con la fecha y la hora. (2) Una entrega en persona en la Delegación tiene el mismo registro. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-BEN-01, CC-BEN-02, MFS-BEN-01, PS-BEN-01, PS-BEN-02, RHF-BEN-01, RHF-BEN-02, PSA-BEN-01, PSA-BEN-02, PEG-BEN-01, PEG-BEN-02

**M4.2 · HU-4.2 · Verificación en campo** — 5 puntos · sprint 3
- Función: Verificación en campo y su resultado (formato, Informe Final o minuta, ajuste de superficie) y documentación de incidencias: caso fortuito, incumplimiento o causa externa.
- Historia: Como personal de la Delegación, quiero registrar el resultado de la verificación en campo y sus incidencias, para determinar el pago o el trámite que corresponde.
- Criterios: (1) Existe el resultado de la verificación con la superficie verificada y su ajuste, dentro del plazo del programa. (2) Cada incidencia tiene su tipo y el documento que la avala. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-DRF-03, CC-DRF-04, MFS-DRF-03, PS-DRF-04, PS-DRF-05, RHF-DRF-04, PSA-DRF-04

**M4.3 · HU-4.3 · Evaluación de reportes** — 3 puntos · sprint 3
- Función: Revisión de los reportes mensuales y acuses de depósito de los Guardabosques en la Delegación y su evaluación por la Dirección, para validarse en el CASPEG.
- Historia: Como personal del área responsable del programa, quiero evaluar por periodo los reportes mensuales de cada Guardabosque, para que el CASPEG valide la evaluación antes de cada pago.
- Criterios: (1) Existe la evaluación por Guardabosque y por periodo. (2) Queda identificado quién no entregó su reporte. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: PEG-BEN-01, PEG-BEN-02, PEG-DRF-03, PEG-DPF-05

### M5. Pagos

Solicita y realiza cada ministración con sus soportes, incluidos los cheques de PSAHEM.

**M5.1 · HU-5.1 · Solicitud de pago** — 3 puntos · sprint 2
- Función: Oficio de solicitud de pago de la Delegación en cuanto el contrato está firmado y solicitud de cada ministración con sus soportes a Administración y Finanzas, con la fecha y la hora del envío.
- Historia: Como personal del área responsable del programa, quiero solicitar el pago de cada ministración con todos sus soportes, para que se pague sin pedir nada más.
- Criterios: (1) La solicitud tiene todos sus soportes. (2) Existe la fecha y la hora del envío a Administración y Finanzas. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-DRF-02, CC-ARP-05, MFS-DRF-02, MFS-ARP-05, PS-DRF-02, PS-ARP-05, RHF-DRF-02, RHF-ARP-05, PSA-ARP-05, PEG-DPF-06

**M5.2 · HU-5.2 · Pago de la ministración** — 5 puntos · sprint 2
- Función: Revisión de la solicitud y pago por transferencia (con cheque solo en casos excepcionales); en PSAHEM, remisión a la Fiduciaria; en PEG, depósito al Guardabosque.
- Historia: Como personal de Administración y Finanzas, quiero revisar la solicitud de pago y pagar la ministración o remitirla a la Fiduciaria, para que la persona beneficiaria reciba su apoyo.
- Criterios: (1) Cada pago está asociado a su solicitud, con la fecha del pago. (2) En PSAHEM existe la fecha de remisión a la Fiduciaria. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-AF-01, MFS-AF-01, PS-AF-01, RHF-AF-01, PSA-AF-01, PEG-AF-01

**M5.3 · HU-5.3 · Entrega de cheques** — 3 puntos · sprint 2
- Función: Emisión de los cheques del 70% y del 30% por la Fiduciaria, su envío a las Delegaciones y su entrega a cada persona beneficiaria, que debe cobrarlos en un máximo de 3 meses.
- Historia: Como personal de la Fiduciaria, quiero emitir los cheques de PSAHEM y enviarlos a las Delegaciones, para que se entreguen a cada persona beneficiaria.
- Criterios: (1) Cada cheque está asociado a su persona beneficiaria y a su ministración, con la fecha y la hora del envío. (2) Existe la fecha de entrega de cada cheque. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: PSA-DRF-03, PSA-FID-01

### M6. Seguimiento y cierre

Atiende lo que se sale del camino normal (lista de espera, sustituciones, incumplimientos y reintegros) y cierra el ejercicio con el padrón.

**M6.1 · HU-6.1 · Lista de espera y sustituciones** — 5 puntos · sprint 3
- Función: Reasignación del recurso liberado a la lista de espera, sustitución por la segunda persona beneficiaria, desistimiento y atención de casos fortuitos, de sobrevivencia menor y de causa externa; solicitudes de la persona beneficiaria con acuse.
- Historia: Como personal del área responsable del programa, quiero proponer al Comité la reasignación del recurso liberado, las sustituciones y la atención de los casos especiales, para aprovechar todo el presupuesto.
- Criterios: (1) Cada propuesta indica el recurso liberado y sigue el orden de la lista de espera. (2) Cada solicitud de sustitución o de desistimiento tiene su acuse con la fecha y la hora. (3) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-BEN-03, CC-ARP-06, MFS-BEN-02, MFS-ARP-06, PS-BEN-03, PS-ARP-06, RHF-BEN-03, RHF-ARP-06, PSA-BEN-03, PSA-ARP-06

**M6.2 · HU-6.2 · Incumplimientos y reintegros** — 5 puntos · sprint 3
- Función: Suspensión, omisiones por subsanar, cancelación e inscripción en el Listado de Personas Beneficiarias Incumplidas; requerimiento de devolución (incluido el valor de la planta no establecida), cuenta para reintegros y comprobación del depósito.
- Historia: Como personal del área responsable del programa, quiero dar seguimiento a las omisiones, la suspensión, la cancelación y la devolución del recurso, para que los incumplimientos se corrijan o se sancionen.
- Criterios: (1) Cada omisión tiene su plazo para corregirse. (2) Un apoyo cancelado tiene su requerimiento de devolución con el monto y la cuenta para el depósito. (3) La persona con apoyo cancelado está en el Listado de Personas Beneficiarias Incumplidas. (4) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-ARP-07, CC-UJ-03, CC-AF-02, MFS-ARP-07, MFS-UJ-03, MFS-AF-02, PS-DRF-05, PS-ARP-07, PS-UJ-03, PS-AF-02, RHF-ARP-07, RHF-UJ-03, RHF-AF-02, PSA-ARP-07, PSA-UJ-03, PSA-AF-02

**M6.3 · HU-6.3 · Cierre del ejercicio** — 3 puntos · sprint 3
- Función: Listados de resultados finales, informe anual al Comité y padrón de personas beneficiarias publicado (en PEG, con altas, bajas y sustituciones).
- Historia: Como personal del área responsable del programa, quiero integrar los resultados finales, el padrón y el informe anual del ejercicio, para cerrar el ejercicio y cumplir con la Ley de Transparencia.
- Criterios: (1) Los resultados finales coinciden con las verificaciones y los pagos. (2) El padrón está publicado y actualizado. (3) Existe la fecha y la hora del envío del informe al Comité. (4) Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).
- Necesidades: CC-ARP-08, MFS-ARP-08, PS-ARP-08, RHF-ARP-08, PSA-ARP-08, PEG-DPF-07

### M7. Calculadora forestal

Permite conocer cuánta masa forestal hay en el Estado de México y en cada municipio, cómo cambia entre años, qué se perdió por incendios, a qué uso pasó el terreno y qué especies hay.

**M7.1 · HU-7.1 · Masa forestal por año** — 8 puntos · sprint 1
- Función: Masa forestal de cada año por municipio y para el Estado, y su evolución año con año.
- Historia: Como integrante del equipo desarrollador, quiero calcular la superficie con masa forestal de cada año disponible, para que PROBOSQUE conozca la cifra del Estado y de cada municipio y cómo evoluciona.
- Criterios: (1) Existe la superficie en hectáreas de cada año disponible, por municipio y para el Estado. (2) Existe la evolución año con año.
- Necesidades: CF-DEV-01

**M7.2 · HU-7.2 · Balance entre dos años** — 5 puntos · sprint 2
- Función: Balance entre un año inicial y uno final: masa forestal perdida, ganada y cambio neto, con su histograma.
- Historia: Como integrante del equipo desarrollador, quiero calcular el balance de masa forestal entre el año inicial y el año final que se elijan, para presentar en un histograma cuánto se perdió y cuánto se ganó.
- Criterios: (1) Existe la pérdida, la ganancia y el cambio neto en hectáreas, para el Estado y cada municipio. (2) Existe el histograma del periodo elegido.
- Necesidades: CF-DEV-02

**M7.3 · HU-7.3 · Pérdida por incendios** — 5 puntos · sprint 2
- Función: Ubicación y fecha de los incendios forestales y masa forestal perdida por ellos.
- Historia: Como integrante del equipo desarrollador, quiero integrar los incendios que publica CONAFOR y la masa forestal que se perdió por ellos, para ubicar las zonas más dañadas.
- Criterios: (1) Cada incendio tiene su ubicación y su fecha. (2) Existe la pérdida por incendio en hectáreas, por año y por municipio. (3) Un año que CONAFOR no ha publicado queda señalado.
- Necesidades: CF-DEV-03

**M7.4 · HU-7.4 · Cambio de uso del suelo** — 8 puntos · sprint 3
- Función: Uso del suelo al que pasó el terreno donde se perdió masa forestal, en los años con datos.
- Historia: Como integrante del equipo desarrollador, quiero clasificar el uso del suelo al que pasó el terreno donde se perdió masa forestal, para conocer las causas del cambio.
- Criterios: (1) La pérdida está clasificada como agrícola, urbana u otra, con el año y la fuente de los datos. (2) Un año sin datos de uso del suelo queda señalado.
- Necesidades: CF-DEV-04

**M7.5 · HU-7.5 · Especies por municipio** — 5 puntos · sprint 3
- Función: Especies forestales registradas en el bosque de cada municipio.
- Historia: Como integrante del equipo desarrollador, quiero integrar las especies que registra el inventario forestal de CONAFOR en cada municipio, para conocer la composición del bosque.
- Criterios: (1) Cada municipio tiene su lista de especies registradas, con el periodo del inventario. (2) Un municipio sin registros queda señalado.
- Necesidades: CF-DEV-05

## 4. Plan de trabajo: tres prototipos de una semana

Cada sprint termina en un prototipo que se puede mostrar. **Hecho** = las pruebas de los criterios de sus historias pasan, hay capturas de Playwright de cada pantalla y el prototipo levanta con `docker compose up`.

| Sprint | Prototipo | Historias | Puntos |
| --- | --- | --- | --- |
| 1 | Recepción y dictamen (M1, M2; M7.1) | HU-1.1, HU-1.2, HU-1.3, HU-1.4, HU-2.1, HU-2.2, HU-2.3, HU-2.4, HU-7.1 | 36 |
| 2 | Contrato y pagos (M3, M5; M7.2 y M7.3) | HU-3.1, HU-3.2, HU-3.3, HU-3.4, HU-5.1, HU-5.2, HU-5.3, HU-7.2, HU-7.3 | 37 |
| 3 | Ejecución, seguimiento y cierre (M4, M6; M7.4 y M7.5) | HU-4.1, HU-4.2, HU-4.3, HU-6.1, HU-6.2, HU-6.3, HU-7.4, HU-7.5 | 39 |

**Tareas de preparación (aún no realizadas):**
- **Sprint 1:** repositorio en GitHub; Docker Compose (Django, PostGIS, cron, Nginx); modelo de datos del expediente y roles; maquetas en HTML de ventanilla, expediente, validación y dictámenes; datos de prueba de un programa (Capturando Carbono) y pruebas de los criterios. Calculadora: separar los datos del HTML en archivos por año y mostrar la evolución anual.
- **Sprint 2:** maquetas de publicación, firma, Vale de Planta y pagos; plantillas PDF (contrato, oficio de solicitud de pago, Vale de Planta, acuses); parámetros por programa; registro de fecha y hora de cada envío. Calculadora: histograma del balance y pérdida por incendios.
- **Sprint 3:** maquetas del portal externo, verificación y seguimiento; plazos y avisos; conectar la verificación (M4.2) con el segundo pago (M5, que en el sprint 2 cubre solo la primera ministración); recorrido completo de un programa y luego los demás. Calculadora: uso del suelo (INEGI Serie VII) y especies (INFyS).

Orden sugerido dentro de cada sprint: modelo y migraciones → reglas y pruebas unitarias → pantallas con HTMX → pruebas de Playwright con capturas.

## 5. Calculadora forestal (M7)

**Prototipo actual:** `calculadora/mapa_edomex.html`, un solo HTML de ~2.7 MB generado por Python (script del equipo `prototipo_masa_forestal.py`, subcomandos `demo`, `calibrar`, `correr`; no está en este paquete). Usa **D3.js 7.9** (cdnjs) y lleva los datos en `<script type="application/json" id="datos">`:
- `unidades` (125 municipios con su trazo SVG `d` y `bbox`, ya proyectados a píxeles), `contorno` del Estado, `ancho`/`alto`, `celda` = 90 m.
- `periodos` (comparaciones entre años: `2023_2024`, etc., con `preliminar`, `filas` por municipio con campos `base, inc, otras, gan, actual, neto…`) y una cuadrícula de clases por periodo que se pinta en un canvas.
- `serie` (años 2023-2025, `umbral` 0.51, `filas[municipio][tipo][t] = [zona, bosque, inc, otras, gan, neto]`, `tend` por municipio, `tot`, `destino` para uso del suelo, aún vacío).
- `tipos` de bosque (Coníferas, Encino, Mesófilo de montaña, Selva baja caducifolia, Vegetación de zonas semiáridas, Otro) y `validacion` (2023-2024: precisión 0.058, exhaustividad 0.309; revisar).
- Vistas: comparar años o un año, cobertura por clases (estable, pérdida por incendio, otra pérdida, ganancia), coropleta del cambio neto, año de pérdida, tabla ordenable, detalle con serie y tendencia, alcances.

**Trabajo de la opción A:** que Python escriba archivos por año en lugar de un solo HTML: `datos/anios/AAAA.json` (cifras por municipio y tipo), `datos/municipios.topojson`, cuadrícula de 90 m como COG o PNG por año y por comparación; la página D3 los carga con `fetch` solo al consultarlos. Publicación en hospedaje estático (GitHub Pages).

**Decisiones técnicas vigentes:**
- Masa forestal = superficie con cobertura arbórea (ha) según NDVI de Sentinel-2; no es biomasa ni carbono.
- Compuesto anual de **noviembre-diciembre**; píxel = bosque si NDVI ≥ umbral (provisional **0.51**, falta calibrar con ~100 puntos); cambia de clase solo si ΔNDVI ≥ **0.10**; quemado si **dNBR ≥ 0.27** (B8A y B12).
- `bosque_final = bosque_inicial − pérdida_por_incendio − otras_pérdidas + ganancia`, por municipio y Estado.
- CRS de trabajo EPSG:32614; ~5 min por municipio.
- Fuentes: Sentinel-2 L2A Colección 1 (STAC `https://earth-search.aws.element84.com/v1`, colección `sentinel-2-c1-l2a`, escala 0.0001, offset −0.1); incendios CONAFOR por WFS de IDEFOR (`geonode:_2024_incendios_forestales`, …; **no hay capa 2025**); INEGI Uso del Suelo y Vegetación **Serie VII** (2021; la Serie VIII no se ha publicado); INFyS 2015-2020 (microdatos de la FAO, con declaración de confidencialidad); municipios de IDEFOR.
- No usar MODIS (se apaga en 2027); para fuego, VIIRS. No usar Google Earth Engine.

**Necesidades y estado en el prototipo:**

- CF-DEV-01 (M7.1): Cuantificación de la masa forestal — Cumplida en parte (calcula la superficie de cada año; falta mostrar su evolución)
- CF-DEV-02 (M7.2): Balance entre dos años — Pendiente (ya da las cifras entre dos años; falta el histograma)
- CF-DEV-03 (M7.3): Ubicación de incendios — Cumplida (falta 2025, que CONAFOR aún no publica)
- CF-DEV-04 (M7.4): Cambio de uso del suelo — Pendiente
- CF-DEV-05 (M7.5): Identificación de especies — Pendiente

## 6. Pendientes y preguntas abiertas
- Servidor para las demostraciones (PROBOSQUE o VPS).
- Delegaciones y municipios que atiende cada una; nombre de la fiduciaria del FIPASAHEM; departamento responsable de cada programa.
- Verificar los numerales de las ROP del PEG y sus flujos alternos.
- Calculadora: capa de incendios 2025, uso del suelo posterior a 2021, datos de especie del INFyS (¿traen coordenadas?), calibración del umbral NDVI, decidir si se quita el recorte con la Serie VII.
- El registro de la solicitud a nombre del predio y el portal externo son propuestas de diseño: las ROP solo piden presentar la solicitud y las entregas en la Delegación.

## 7. Lineamientos del profesor (si se editan historias o la propuesta)
- Una función ↔ una historia; la Calculadora, 5 necesidades ↔ 5 funciones ↔ 5 historias.
- Historias en una sola frase «Como [rol], quiero [acción], para [beneficio]», enfocadas en la acción del usuario (nota del profesor del 18-nov-2026 a la HU-1.1); describen la necesidad, no la solución.
- Criterios de aceptación como condiciones, nunca acciones. HU-1.1 tiene un solo criterio por indicación del profesor: «Se genera un folio único para la solicitud».
- Toda entrega o envío registra fecha y hora.
- La necesidad DRF-02 es **firmar** el contrato (no registrarlo firmado).
- No mencionar Scrum en el plan; los sprints se tratan como prototipos.
