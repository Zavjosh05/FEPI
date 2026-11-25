# Tareas por persona del sprint 2

Detalle de los paquetes de trabajo de la [Planeación del sprint 2](PLANEACION_SPRINT_2.md), agrupados por responsable.
Cada tarea dice qué se buscaba, **cómo se diseñó** (las decisiones y su porqué), **cómo se ejecutó** (qué se construyó y
dónde está), cómo se comprobó y el commit donde quedó en la rama `sprint-2`. Los criterios de aceptación son los vigentes
en `sistema/especificacion/modelo.json`, con el criterio de trazabilidad que el profesor pidió el 23 de noviembre.

| Persona | Rol | Paquetes | Puntos |
| --- | --- | --- | ---: |
| Joshua | Coordinación, núcleo y publicación | T25 Base de M3 y M5 · T26 HU-3.1 · T36 Cierre técnico · T41 Resumen · T42 Coordinación · T43b Trazabilidad de M3 y M5 | 20 |
| Omar | Firma, planta y solicitud de pago; datos y pruebas | T28 HU-3.3 · T29 HU-3.4 · T30 HU-5.1 · T37 Datos de prueba · T38 Pruebas en paralelo · T39 Tropiezos de interfaz | 18 |
| Cin | Reglas, contrato y pagos de Administración y Finanzas y Fiduciaria | T22 Reglas de PS · T23 Reglas de RHF · T24 Reglas de PSAHEM · T27 HU-3.2 · T31 HU-5.2 · T32 HU-5.3 | 20 |
| Angel | Calculadora, integración y bajas | T33 HU-7.2 · T34 HU-7.3 · T35 INFyS · T40 Recorridos · T43a Bajas y reasignaciones | 20 |

**Convenciones que comparten todos** (las mismas del sprint 1):

- Rutas relativas a `sistema/` salvo que se diga otra cosa.
- Pruebas con el identificador de la historia en el nombre.
- Un commit por historia verificada.
- Requisitos, plazos y montos como datos, nunca en el código.
- Cada estado se cambia solo con `Expediente.cambiar_estado`, que valida contra la tabla de transiciones y escribe la
  bitácora.
- **Nuevas en el sprint 2:**
  - Un módulo de servicios por historia (`contrato/firma.py`, `pagos/solicitudes.py`…) y los modelos en `models/<historia>.py`.
  - Todo aviso a una persona sale por `nucleo.notificaciones`, por conducto de la Delegación.
  - Todo plazo se pide a `nucleo.plazos.vencimiento(expediente, uso)`, que sabe qué evento lo arranca.
  - Cada modelo de `contrato` y `pagos` lleva historial (`django-simple-history`) y se guarda con `save()`, para que el
    usuario quede registrado.

[[SALTO]]

## Joshua — Coordinación, núcleo y publicación (20 puntos)

### T25 · Base de M3 y M5 (8 puntos)

**Objetivo.** Las piezas que todas las historias de contrato y pagos usan, para que ninguna las repita: avisos a las
personas, plazos con evento de arranque, estados y bandejas, monto aprobado y los cuatro programas corriendo de punta a
punta.

**Cómo se diseñó.** Se partió en siete partes pequeñas (S2-02a a S2-02g), cada una con su commit, para que un corte no
perdiera el trabajo:

- **Notificaciones en el núcleo (S2-02a).** La notificación por conducto de la Delegación vivía en M1 (aviso de faltantes).
  `nucleo.Notificacion` y `nucleo/notificaciones.py` la generalizan: cada aviso tiene dos momentos con fecha, hora y acuse,
  el envío a la Delegación y la notificación a la persona. Es la única forma de avisar; HU-3.1 y HU-5.2 la usan.
- **Plazos con evento de arranque (S2-02b, R-03).** Las Reglas de Operación no cuentan igual los plazos de firma en CC
  (desde la publicación) y en PS (desde la notificación). `nucleo.plazos.vencimiento(expediente, uso)` es el único punto que
  calcula un vencimiento: `datos/sistema.json` dice qué plazo usa el sistema para cada cosa (`usos_de_plazo`) y qué hito del
  expediente lo arranca (`Hito`: publicación de resultados, firma del contrato, entrega del vale…).
- **Estados y bandejas de M3 y M5 (S2-02c).** Los estados nuevos (`publicada`, `notificada`, `contrato_elaborado`,
  `contrato_en_delegacion`, `contratada`, `sin_firma_en_plazo`, `recurso_liberado`, `vale_entregado`, `planta_entregada`,
  `ministracion_solicitada`, `pagada`, `remitida_fiduciaria`, `cheque_emitido`, `cheque_enviado`, `cheque_entregado`) y sus
  transiciones son datos de `datos/flujo_tramite.json`, con la unidad que atiende cada uno; el núcleo no cambia.
- **Monto aprobado (S2-02d).** `nucleo.montos.monto_aprobado(expediente, superficie)` da el monto por hectárea de las
  reglas (CC $2,000; PS, RHF y PSAHEM según modalidad), el total y las ministraciones (70 % y 30 %; en CC pago único hasta
  5 ha). El Comité y el contrato usan la misma cuenta.
- **M1 y M2 con PS, RHF y PSAHEM (S2-02e).** El recorrido de recepción y dictamen se probó con los cuatro programas; lo
  propio de cada uno quedó en las reglas (tipos de persona, modalidades, superficie máxima, criterios técnicos).
- **Tropiezos de interfaz del sprint 1 (S2-02f, P-13 a P-18).** Botón «siguiente paso» en el expediente, aviso del polígono
  pendiente, enlace del aviso al requisito, acción para llevar a sesión, aprobada en bandeja y descarga de acuses.
- **Apps `contrato` y `pagos` y su demostración (S2-02g).** Cada app trae sus modelos, su `registro.py` (paneles de bandeja,
  menú, siguiente paso, revisión de plazos) y su `demo.py`.

**Cómo se ejecutó.**

- `nucleo/notificaciones.py`, `nucleo/plazos.py`, `nucleo/montos.py`, modelos `Notificacion` y `Hito`.
- `datos/flujo_tramite.json` y `datos/sistema.json`.
- Apps `contrato/` y `pagos/` con el mismo patrón que `dictamen/` (`registro.py` + puntos de `nucleo/extensiones.py`).

**Cómo se comprobó.** `test_nucleo_notificaciones.py` (5), `test_nucleo_plazos.py` (8), `test_nucleo_montos.py` (6),
`test_nucleo_flujo_m3_m5.py` (7), `test_nucleo_superficie.py` (4), `test_nucleo_tropiezos_interfaz.py` (7) y
`test_nucleo_apps_contrato_pagos.py` (3), más el recorrido del sprint 1 con los cuatro programas.

**Commits:** `47cc5ee`, `d1a8c64`, `2bee813`, `30c4124`, `f22eb15`, `d49aacc`, `2fa15a7` (más `a3ce6ff` con las capturas).

### T26 · Publicación y notificaciones (HU-3.1, 3 puntos)

**Historia.** Como personal del área responsable del programa, quiero publicar los listados aprobados y avisar a cada persona su resultado por conducto de la Delegación, para que los plazos corran desde una notificación comprobable.

**Criterios de aceptación:**

1. Los listados autorizados por el Comité están publicados en la fecha de la convocatoria.
2. Cada aviso tiene su acuse y la fecha y la hora de envío y de notificación.
3. Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).

**Cómo se diseñó.**

- **Quién publica y cuándo.** Solo la Dirección Instancia Ejecutora del programa, solo una sesión de aprobación con acta
  que **autorizó la publicación**, y una sola vez por sesión. Es la salida natural de HU-2.3.
- **Qué se publica.** Una copia de lo que ve el público (`ResultadoPublicado`): folio, predio, municipio y resultado; el
  nombre solo en el listado de personas beneficiarias (el padrón que mandan publicar las ROP, CC 9.4.3 fr. III); nunca CURP,
  RFC ni documentos.
- **Fecha de la convocatoria (R-05).** Las ROP no fijan fecha ni días para publicar: la pantalla dice «Sin fecha en las
  reglas» y registra la fecha y la hora reales; si un programa trae un plazo, se compara y se guarda `dentro_de_fecha`.
- **Avisos.** Cada solicitud recibe su aviso por conducto de la Delegación; en PS, además, la cita a firma (5 días hábiles).
  Al notificar el resultado, el expediente pasa a `notificada` (`extensiones.AL_NOTIFICAR`).
- **Página pública** sin iniciar sesión (`/contrato/resultados/`), solo de lo ya publicado y con búsqueda por folio; es la
  forma en que el público se entera sin tener cuenta (S2-05).

**Cómo se ejecutó.**

- `contrato/models/publicacion.py` (`Publicacion`, `ResultadoPublicado`), `contrato/publicacion.py`
  (`publicar`, `registrar_entrega`, `por_entregar`, `sesiones_por_publicar`), `vistas/publicacion.py` y
  `templates/contrato/publicacion/`.
- Paneles de bandeja «Listados autorizados por publicar» y «Notificaciones por entregar», siguiente paso en el expediente y
  pestaña «Contrato».

**Cómo se comprobó.** 22 pruebas en `test_hu_3_1.py` y 2 del índice público (`test_hu_3_1_indice_publico.py`; P-32 corrigió
que un programa se repetía por cada publicación), el recorrido con navegador (`hu_3_1_*`, 13 capturas) y las 7 del
recorrido completo.

**Commit:** `4fbf940` (con el ajuste P-32 en `8dd8805`).

### T36 · Cierre técnico (3 puntos)

**Objetivo.** Dejar el sprint ordenado y mantenible: una batería de pruebas que se pueda correr completa, un menú que
quepa en pantalla y la documentación técnica al día.

**Cómo se diseñó.**

- **PDF ligero (P-22).** La batería llegó a 13 min 40 s (366 pruebas) porque casi todas arman expedientes completos y cada
  acuse, contrato o vale se renderiza con WeasyPrint (4 a 8 s). Por omisión una fixture sustituye el render por un PDF mínimo
  válido con el texto visible; siguen con el render verdadero las pruebas marcadas `pdf_real`, las de navegador y toda la
  batería con `PDF_REAL=1` (antes de cada entrega). Además, las contraseñas de prueba se cifran con MD5.
- **Menú por módulo (P-21).** Con los cuatro módulos el menú de la Dirección ya no cabía a 1366 px y tapaba el nombre y
  «Salir». Cada módulo registra sus enlaces con un `grupo` en `extensiones.MENU` y el núcleo arma el menú de cada persona con
  lo que su unidad tiene; un grupo con un solo enlace se muestra como enlace simple.
- **Modelo de datos y README.** Diagramas entidad-relación por área (núcleo, recepción, dictamen, contrato, pagos) generados
  del código y las decisiones de cada historia en `sistema/README.md`.

**Cómo se ejecutó.** `nucleo/acuses.py` (`_render_pdf`), `pruebas/conftest.py` (`pdf_ligero`, `hash_rapido`),
`nucleo/contexto.py`, `nucleo/extensiones.py` (`GRUPOS_MENU`), `plantillas/base.html`, `herramientas/diagrama_er.py` y
`docs/modelo_datos.md`.

**Cómo se comprobó.** 4 pruebas de navegador del menú (`test_menu_por_modulo.py`, escritorio y móvil) y la batería completa
sin cambios de resultado.

**Commits:** `88d9f93`, `f24d627`, `c94a5c9`.

### T41 · Resumen del sprint (2 puntos) y T42 · Coordinación (2 puntos)

**Objetivo.** Que el sprint quede documentado y que lo entregado funcione junto.

**Cómo se diseñó y ejecutó.**

- Revisión de cada historia antes de aceptarla: se repiten sus pruebas y las rápidas, y se revisan sus capturas.
- Tablero (`entregas/AVANCE.md`, tabla del sprint 2) y bitácora de decisiones (`entregas/BITACORA.md`): R-13 a R-16 (hallazgos
  de las reglas), S2-02 a S2-06, D-11, D-12 y D-15 (decisiones de diseño), P-19 a P-34 (problemas) y W-15 a W-18 (forma de
  trabajo).
- **Resumen en PDF con diagramas y capturas** (`entregas/generar_resumen.py`, `entregas/sprint_2/Resumen_sprint_2.pdf`): la
  problemática, la arquitectura, los módulos, cómo se cubrieron las necesidades, las pruebas, las decisiones y los límites,
  con el diagrama de estados dibujado desde la tabla de transiciones y el anexo de capturas (W-16).

**Commits:** `0598b95`, `9d5827f`, `5849d57`, `6283c13`.

### T43b · Trazabilidad de M3 y M5 y documentación (2 puntos; parte de T43)

Ver «Integración de las observaciones del profesor a M3 y M5» al final de este documento.

[[SALTO]]

## Omar — Firma, planta y solicitud de pago; datos y pruebas (18 puntos)

### T28 · Firma del contrato (HU-3.3, 5 puntos)

**Historia.** Como personal de la Delegación, quiero recabar la firma del contrato dentro del plazo y verificar las firmas y el sello, para formalizar el apoyo.

**Criterios de aceptación:**

1. Existe el contrato firmado, con la fecha y la hora de la firma, dentro del plazo.
2. En MFS existe el contrato de servicios técnicos con el RFN y la carta compromiso; en PEG, la credencial entregada.
3. Un contrato sin firma al vencer el plazo queda señalado para liberar el recurso.
4. Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).

**Cómo se diseñó.**

- **Quién firma y cómo se recibe.** Solo la Delegación del expediente, con el contrato ya enviado. Pide quién firma (la
  persona o su representante), el contrato firmado digitalizado y la **verificación de firmas y sello**: una lista por tipo
  de persona (persona física, jurídico colectiva, núcleo agrario con Presidencia, Secretaría, Tesorería y sello) en
  `datos/contrato.json`. Todos los puntos deben marcarse; si no, el contrato no se recibe.
- **Dos fechas (R-03).** Siempre se muestran la **fecha programada de firma** y el **vencimiento para liberar el recurso**,
  con los días hábiles que faltan. Una firma fuera de la programada pero dentro del vencimiento es válida y queda marcada;
  una posterior al vencimiento no se recibe.
- **Formalización propia (criterio 2).** MFS y Guardabosques no tienen archivo de reglas: su formalización (contrato de
  servicios técnicos con el RFN y carta compromiso; credencial entregada) está como datos en `datos/contrato.json` y se
  prueba con programas de fixtures.
- **Sin firma al vencer (criterio 3).** `revisar_plazos` señala el contrato (estado `sin_firma_en_plazo`, renglón de
  bitácora del sistema, aviso a la Dirección). **Liberar el recurso no es automático:** la Dirección lo confirma con un motivo
  y el monto queda como recurso liberado para que el Comité lo reasigne (HU-2.4).

**Cómo se ejecutó.**

- `contrato/models/firma.py` (`FirmaContrato`, `ElementoFormalizacion`, `SinFirma`), `contrato/firma.py`
  (`registrar_firma`, `puntos_de_verificacion`, `formalizacion_propia`, `revisar_firmas`, `liberar_recurso`),
  `formularios/firma.py`, `vistas/firma.py` y `templates/contrato/firma/`.
- `Expediente.cambiar_estado(por_sistema=True)` para el cambio que hace el sistema sin usuario, y el gancho
  `extensiones.AL_FIRMAR` para que HU-3.4 reaccione a la firma.
- Pantallas «Firmas», «Registrar la firma», paneles de bandeja y señalamiento en la pestaña «Contrato».

**Cómo se comprobó.** 32 pruebas en `test_hu_3_3.py` y el recorrido con navegador (`hu_3_3_*`, 9 capturas).

**Commit:** `d877a63` (con `27640f0`, P-19: nombres legibles de plazos y modalidad en la pestaña).

### T29 · Entrega de planta (HU-3.4, 5 puntos)

**Historia.** Como personal del vivero, quiero validar el Vale de Planta y registrar la salida de planta por especie y cantidad, para entregar solo la planta autorizada.

**Criterios de aceptación:**

1. Existe un Vale de Planta vigente por la especie y la cantidad entregadas.
2. La salida de planta tiene especie, cantidad y fecha.
3. Un vale vencido no es válido y puede reponerse.
4. Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).

**Cómo se diseñó.**

- **Solo PS y RHF.** RFI modalidad uno no recibe planta; CC, MFS, PEG y PSAHEM no usan vale (dato por programa en
  `datos/contrato.json` → `vale_de_planta`).
- **El vale.** La Delegación lo entrega con especie y cantidad (se propone la planta por hectárea de las reglas por la
  superficie aprobada; un ajuste exige motivo), el vivero que entrega y el acuse. Antes de firmar el contrato se exige la
  carta compromiso (PS 8.1.6 inciso f; RHF inciso g).
- **Vigencia desde las reglas.** PS: 30 días naturales desde la entrega (el texto no dice hábiles o naturales, R-13); RHF: 15
  días hábiles. Un vale vencido no es válido: el vivero no registra salida con él.
- **Reposición.** RHF sí la prevé (el vale nuevo referencia al anterior, cubre solo lo no entregado y pide confirmar la
  disponibilidad); PS no, y la pantalla lo dice citando la regla.
- **Salida del vivero.** Especie, cantidad, fecha y hora; salidas parciales; nunca más de lo autorizado por especie. Al
  completarse, `vale_entregado → planta_entregada`.

**Cómo se ejecutó.**

- `contrato/models/planta.py` (`Especie`, `Vivero`, `ValePlanta`, `RenglonVale`, `SalidaPlanta`), `contrato/planta.py`
  (`emitir_vale`, `propuesta`, `validar_vale`, `registrar_salida`, `al_firmar`), `formularios/planta.py`,
  `vistas/planta.py` y `templates/contrato/planta/`.
- Catálogos de especies y viveros de demostración (`catalogos_planta`), editables en el administrador.
- Pantallas «Vales» (Delegación y Dirección) y «Planta» (vivero).

**Cómo se comprobó.** 26 pruebas en `test_hu_3_4.py` y el recorrido con navegador (`hu_3_4_*`, 10 capturas); la demostración
trae un vale vigente con salidas parciales, uno vencido sin reposición (PS) y uno vencido con reposición (RHF).

**Commit:** `d5698c8` (con `0871a66`, P-28: un solo nombre para el vale y aviso de «planta entregada»).

### T30 · Solicitud de pago (HU-5.1, 3 puntos)

**Historia.** Como personal del área responsable del programa, quiero solicitar el pago de cada ministración con todos sus soportes, para que se pague sin pedir nada más.

**Criterios de aceptación:**

1. La solicitud tiene todos sus soportes.
2. Existe la fecha y la hora del envío a Administración y Finanzas.
3. Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).

**Cómo se diseñó.**

- **Oficio de la Delegación.** Solo con el contrato firmado; PDF de plantilla propia marcada «BORRADOR» (las ROP no traen el
  formato, R-07).
- **Soportes como datos.** `datos/pagos.json` dice, para la primera ministración y para «siguientes», qué soportes pide cada
  programa con su fundamento: CC, PS y RHF, contrato firmado, oficio y comprobante de cuenta; PSAHEM, contrato o convenio,
  oficio, dictámenes y la **instrucción de pago del Comité Técnico** (un acuerdo de HU-2.4). La verificación en campo de las
  siguientes ministraciones queda como soporte pendiente del sprint 3.
- **Enviar.** Solo el área responsable; el servicio impide el envío si falta un soporte y dice cuál. El envío deja fecha,
  hora, copia de los soportes, acuse y el estado `ministracion_solicitada`.

**Cómo se ejecutó.** `pagos/models/solicitudes.py` (`OficioPago`, `ComprobanteCuenta`, `SolicitudPago`),
`pagos/solicitudes.py` (`emitir_oficio`, `adjuntar_comprobante`, `preparar_solicitud`, `enviar_solicitud`, `FUENTES`),
`formularios/solicitudes.py`, `vistas/solicitudes.py`, `templates/pagos/solicitudes/` y `datos/pagos.json`.

**Cómo se comprobó.** 22 pruebas en `test_hu_5_1.py` y el recorrido con navegador (`hu_5_1_*`, 8 capturas).

**Commit:** `82d2ed8`.

### T37 · Datos de prueba (3 puntos)

**Objetivo.** Que la demostración sea verosímil y que los plazos se puedan probar en sus bordes.

**Cómo se diseñó.**

- **Reloj simulado (G-03).** `nucleo/reloj.py` hace que todo el sistema vea un momento simulado como «ahora»; la carga de
  demostración corre en el calendario de la Convocatoria 2026 (recepción en febrero, dictámenes en abril a junio, sesiones
  en julio y noviembre) con **fecha de corte** el 19-nov-2026 (`nucleo/demo_calendario.py`). Así la demostración sale igual
  cualquier día en que se cargue.
- **Bordes de cada plazo.** Pruebas en el último día, el día siguiente, fines de semana y días inhábiles de cada plazo.
- **Generador con volumen (G-02).** `generar_datos --programa --n --semilla` crea cientos de solicitudes hasta la publicación
  y una prueba de volumen que detectó consultas repetidas (P-34).

**Cómo se ejecutó.** `nucleo/reloj.py`, `nucleo/demo_calendario.py`, `nucleo/generador.py` y su comando, y las demostraciones
`dictamen/demo.py`, `contrato/demo.py` y `pagos/demo.py` con un `paso(fecha, hora)` por cada acción.

**Cómo se comprobó.** `test_nucleo_reloj_demo.py` (4), `test_nucleo_plazos_bordes.py` (16 casos), `test_nucleo_generador.py` (2)
y `test_nucleo_volumen.py` (2).

**Commits:** `f1addff`, `8e95e4c`, `d9bbf7d`.

### T38 · Pruebas en paralelo (2 puntos)

**Cómo se diseñó.** Pytest-xdist si acorta la corrida sin volverla frágil. Cada proceso trabaja con su propia base de prueba
(`test_probosque_gw0`…) y su carpeta temporal de archivos, y las pruebas con navegador van aparte porque `live_server` vacía
la base.

**Cómo se ejecutó.** `docker/pruebas.sh` (rápidas con `-n 4`, recorridos con `-n 3`), `requirements-pruebas.txt`,
`docker-compose.yml` y la sección «Cómo probar» del README.

**Cómo se comprobó.** Tres corridas completas sin intermitencias: de ~8 min 40 s en serie a 4 min 46 s a 5 min 3 s.

**Commit:** `6753f8c`.

### T39 · Tropiezos de interfaz del recorrido (2 puntos)

**Objetivo.** Corregir lo que el recorrido por la interfaz (T40) encontró y que las pruebas de servicio no ven.

**Cómo se ejecutó.** Nueve ajustes (P-23 a P-31): bitácora desempatada por orden de registro, enlace a «Iniciar sesión» en
las páginas públicas, folio de la notificación que abre el aviso por registrar, la solicitud de PSAHEM por remitir en «Por
atender» de la Secretaría Técnica, plazo «cumplido en plazo», un solo nombre para el vale, fecha de la sesión en lugar de su
clave interna, y más. Se corrigió después de cada recorrido hasta que ya no hubo tropiezos.

**Cómo se comprobó.** `test_nucleo_tropiezos_interfaz_s2.py` (10) y el recorrido corregido.

**Commit:** `0871a66`.

[[SALTO]]

## Cin — Reglas, contrato y pagos de Administración y Finanzas y Fiduciaria (20 puntos)

### T22, T23 y T24 · Reglas de PS, RHF y PSAHEM (3 puntos cada una)

**Objetivo.** Que los tres programas que faltaban tengan sus reglas como datos, con numeral y línea de las Reglas de
Operación, para probar el sistema con más de un programa.

**Cómo se diseñó.** Cada programa lo extrajo una unidad de proceso distinta y en paralelo, con el mismo esquema que CC
(`reglas/CC.json`): tipos de persona, modalidades, requisitos con bandera de documento legal, plazos con cantidad y unidad,
formatos, montos, ministraciones y criterios. Lo que el esquema no usa todavía se guarda en `Ejercicio.datos`. Cada
hallazgo contrario a lo esperado se anotó en la bitácora (R-13 a R-15).

| Programa | Requisitos | Plazos | Modalidades | Hallazgos |
| --- | ---: | ---: | ---: | --- |
| PS (T22, `c979a30`) | 23 | 27 | 3 conceptos de apoyo | Los plazos de firma están al revés que en CC (R-13); la vigencia del vale es de 30 días y no se prevé su reposición; el mantenimiento funciona como refrendo |
| RHF (T23, `ef3e66d`) | 32 | 31 | 4 (montos de $30,000, $14,000, $3,500 y $3,000 por hectárea) | El PTRFI lo entrega la persona solicitante; vale de planta de 15 días hábiles con reposición; lista de espera propia (R-15) |
| PSAHEM (T24, `a8dad5c`) | 19 | 25 | 4 (dos seleccionables) | Los 5 días hábiles son para que la Secretaría Técnica solicite el pago a la Fiduciaria; paga con cheque; no hay plazo para publicar (R-14) |

**Cómo se ejecutó.** `reglas/PS.json`, `RHF.json` y `PSA.json`, con `reglas/indice_rop.json` para los rangos de líneas del
texto de cada programa. Se cargan con `cargar_reglas`, que reconoce cada archivo.

**Cómo se comprobó.** `test_nucleo_reglas.py` (9) y el recorrido de recepción y dictamen con los cuatro programas
(`f22eb15`).

**Commits:** `c979a30`, `ef3e66d`, `a8dad5c`.

### T27 · Elaboración del contrato (HU-3.2, 3 puntos)

**Historia.** Como personal del área responsable del programa, quiero elaborar el contrato de cada solicitud aprobada sobre el modelo validado y enviarlo a la Delegación, para que se firme.

**Criterios de aceptación:**

1. Existe un contrato por solicitud aprobada, elaborado sobre un modelo validado.
2. Existe la fecha y la hora del envío a la Delegación.
3. Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).

**Cómo se diseñó.**

- **Modelos de contrato (S2-04, R-07).** Las ROP no traen el texto del Contrato de Adhesión, del Convenio de Concertación ni
  del Adendum. `ModeloContrato` (por programa, ejercicio y tipo) tiene `VersionModelo`: el área responsable registra el texto
  con campos entre llaves (se validan contra `contratos.CAMPOS`) y **la Unidad Jurídica lo valida o lo devuelve**, con fecha,
  hora, quién y observaciones. Cambiar el texto crea una versión nueva por validar; la anterior se conserva y los contratos
  ya elaborados guardan la suya.
- **Plantilla base propia,** marcada «BORRADOR – modelo por validar» en el nombre, el texto y las pantallas: hay que quitarle
  la marca y validarla antes de usarla.
- **Elaborar.** Solo la Dirección Instancia Ejecutora, solo de una solicitud aprobada, publicada y notificada, y solo sobre la
  versión vigente validada de un modelo del mismo programa y del tipo que toca (Convenio en PSAHEM con fondos concurrentes;
  Contrato de Adhesión en los demás). Lo impide el servicio, no solo la pantalla.
- **El documento.** PDF con persona, predio, modalidad, superficie aprobada, monto y ministraciones (`nucleo.montos`) y el
  plazo de firma, con su huella SHA-256 y la leyenda del modelo y su validación. Uno por solicitud, con folio
  `CTO-<programa>-<año>-NNNN`; se rehace mientras no se envíe.
- **Enviar a la Delegación.** Fecha, hora y acuse; el estado pasa a `contrato_en_delegacion` y la Delegación ve el PDF solo
  desde el envío.
- **Adendum.** Solo el modelo de datos (MFS aún no tiene reglas).

**Cómo se ejecutó.** `contrato/models/contratos.py` (`ModeloContrato`, `VersionModelo`, `Contrato`, `Adendum`),
`contrato/contratos.py` (`registrar_modelo`, `crear_plantilla_base`, `modificar_modelo`, `validar_version`, `elaborar_contrato`,
`enviar_a_delegacion`), `formularios/contratos.py`, `vistas/contratos.py` y `templates/contrato/contratos/` (incluido el PDF).

**Cómo se comprobó.** 22 pruebas en `test_hu_3_2.py` (dos con el PDF real) y el recorrido con navegador (`hu_3_2_*`, 12
capturas).

**Commit:** `e9a1f2c`.

### T31 · Pago de la ministración (HU-5.2, 5 puntos)

**Historia.** Como personal de Administración y Finanzas, quiero revisar la solicitud de pago y pagar la ministración o remitirla a la Fiduciaria, para que la persona beneficiaria reciba su apoyo.

**Criterios de aceptación:**

1. Cada pago está asociado a su solicitud, con la fecha del pago.
2. En PSAHEM existe la fecha de remisión a la Fiduciaria.
3. Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).

**Cómo se diseñó.**

- **Revisión.** Solo Administración y Finanzas; **acepta** (vuelve a comprobar soportes e importe) o **devuelve** con
  observaciones obligatorias (acuse; el expediente vuelve a `contratada` y el área responsable la corrige y la reenvía; se
  conserva cada revisión).
- **Pago.** Referencia, fecha e importe **igual al solicitado**; transferencia (CC, PS, RHF), depósito (Guardabosques,
  como dato) o cheque solo como caso excepcional con motivo. El pago cuelga de la solicitud aceptada, así que no se paga dos
  veces; deja acuse, hito, estado `pagada` y el **aviso de pago** a la persona por conducto de la Delegación.
- **PSAHEM y quién remite a la Fiduciaria (R-16).** La historia lo pone en Administración y Finanzas; las ROP, a través de la
  Secretaría Técnica en 5 días hábiles (10.1 fr. X) y a Administración y Finanzas como responsable de los recursos (fr. XIV).
  Se resolvió: **remite la Secretaría Técnica después de que Administración y Finanzas acepta**; se cambió la unidad de la
  transición en `datos/flujo_tramite.json` y queda como duda para el cliente.
- **Fecha de remisión y plazo.** La remisión guarda fecha, hora, oficio, acuse y si fue «en plazo» o «fuera de plazo»; la
  revisión de plazos anota las vencidas sin remisión.

**Cómo se ejecutó.** `pagos/models/pagos.py` (`RevisionSolicitud`, `Pago`, `RemisionFiduciaria`), `pagos/pagos.py`
(`revisar_solicitud`, `registrar_pago`, `remitir_a_fiduciaria`, `revisar_remisiones`), `formularios/pagos.py`,
`vistas/pagos.py`, `templates/pagos/pagos/` y el tipo de aviso «Aviso de pago» en el núcleo.

**Cómo se comprobó.** 26 pruebas en `test_hu_5_2.py` y el recorrido con navegador (`hu_5_2_*`, 9 capturas).

**Commit:** `abc03e0`.

### T32 · Entrega de cheques (HU-5.3, 3 puntos)

**Historia.** Como personal de la Fiduciaria, quiero emitir los cheques de PSAHEM y enviarlos a las Delegaciones, para que se entreguen a cada persona beneficiaria.

**Criterios de aceptación:**

1. Cada cheque está asociado a su persona beneficiaria y a su ministración, con la fecha y la hora del envío.
2. Existe la fecha de entrega de cada cheque.
3. Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad).

**Cómo se diseñó.**

- **Emisión.** Solo la Fiduciaria y solo de un pago ya remitido: número de cheque único, importe igual al solicitado y fecha;
  queda ligado a la persona, la solicitud y la ministración (uno por persona y ministración).
- **Envío y entrega.** El envío deja fecha, hora y acuse y el aviso a la persona por la Delegación; la entrega, quién recibe,
  fecha y hora y acuse, y deja la ministración pagada para que el área solicite la siguiente.
- **Cobro en 3 meses.** El plazo de las reglas (ROP 8.1.7 fr. XVI) corre desde la entrega; el vencimiento se muestra en el
  expediente y en «Cheques», y la revisión de plazos avisa los por vencer y los vencidos. Solo es aviso: la baja por cheque
  vencido es del sprint 3.

**Cómo se ejecutó.** `pagos/models/cheques.py` (`Cheque`), `pagos/cheques.py` (`emitir_cheque`, `enviar_a_delegacion`,
`registrar_entrega`, `registrar_cobro`, `por_cobrar`, `revisar_cobros`), `formularios/cheques.py`, `vistas/cheques.py` y
`templates/pagos/cheques/`.

**Cómo se comprobó.** 17 pruebas en `test_hu_5_3.py` y el recorrido con navegador (`hu_5_3_*`, 6 capturas). La demostración
trae cheques emitido, enviado, entregado y por vencer.

**Commit:** `1af1d0a`.

[[SALTO]]

## Angel — Calculadora, integración y bajas (20 puntos)

### T33 · Balance entre dos años (HU-7.2, 5 puntos)

**Historia.** Como integrante del equipo desarrollador, quiero calcular el balance de masa forestal entre el año inicial y el año final que se elijan, para presentar en un histograma cuánto se perdió y cuánto se ganó.

**Criterios de aceptación:**

1. Existe la pérdida, la ganancia y el cambio neto en hectáreas, para el Estado y cada municipio.
2. Existe el histograma del periodo elegido.

**Cómo se diseñó.**

- **Cualquier par de años.** El balance sale de los CSV de la serie (`balance_<par>.csv`: pérdida por incendio, otras
  pérdidas y ganancia por municipio); la página lo muestra para el par elegido, para el Estado y para cada municipio.
- **Histograma.** El número de municipios por intervalo de cambio neto como porcentaje de su bosque inicial (de −10 a +10 %),
  solo con los municipios de 500 ha o más de bosque inicial, porque con menos el porcentaje es ruido; la nota dice cuántos
  quedan fuera. Cada gráfica tiene su tabla («Ver como tabla»).
- **Colores y tema.** Un color por concepto (incendio, otras pérdidas, ganancia y neto) y la misma gráfica en tema claro y oscuro, en escritorio y en móvil.

**Cómo se ejecutó.** `src/plantilla_mapa.html` (sección «Balance del periodo» y su histograma) y `docs/calculadora/`
regenerado con `src/mapa_interactivo.py --sitio`.

**Cómo se comprobó.** 13 pruebas con pytest y Playwright en `pruebas/calculadora/test_hu_7_2_balance_entre_dos_anios.py`
(cifras contra los CSV, histograma contra los municipios, tema oscuro y móvil) y 8 capturas `hu_7_2_*`.

**Commit:** `9254478`.

### T34 · Pérdida por incendios (HU-7.3, 5 puntos)

**Historia.** Como integrante del equipo desarrollador, quiero integrar los incendios que publica CONAFOR y la masa forestal que se perdió por ellos, para ubicar las zonas más dañadas.

**Criterios de aceptación:**

1. Cada incendio tiene su ubicación y su fecha.
2. Existe la pérdida por incendio en hectáreas, por año y por municipio.
3. Un año que CONAFOR no ha publicado queda señalado.

**Cómo se diseñó.**

- **Ubicación y fecha.** Cada incendio de CONAFOR lleva su clave, fecha, municipio, centroide (en la malla de la capa y en
  longitud y latitud) y las hectáreas reportadas, quemadas en bosque y sin copa al cierre.
- **Pérdida por incendio por año y municipio.** Se resume por año de inicio del incendio, para el Estado y cada municipio.
- **Un año sin publicar.** CONAFOR no publica 2025: el índice lo marca, y la página lo señala en las cifras, la tabla y la
  capa, con una marca de parcial (†) o «sin dato». Nunca se presenta como cero.
- **Mapa.** Una vista «Incendios» con un círculo por incendio, proporcional a lo quemado en el bosque.

**Cómo se ejecutó.** `src/mapa_interactivo.py` (datos de incendios por periodo) y `src/plantilla_mapa.html` (vista, tabla
ordenable y avisos); `docs/calculadora/datos/` regenerado.

**Cómo se comprobó.** 15 pruebas en `pruebas/calculadora/test_hu_7_3_perdida_por_incendios.py` y 12 capturas `hu_7_3_*`.

**Commit:** `5bfa706`.

### T35 · Investigación del INFyS para HU-7.5 (2 puntos)

**Objetivo.** Decidir de dónde saldrán los datos de especie para el cálculo por especie del sprint 3.

**Cómo se ejecutó.** `entregas/sprint_2/investigacion_infys.md`: el Inventario Nacional Forestal y de Suelos publica los
datos por estado en IDEFOR; el portal pide cuenta, y se registró la decisión sobre el acceso y la descarga de los
microdatos (C-08, C-12 y C-16 de la bitácora).

**Commits:** `5f899fb`, `18ee61b`, `9ec6d86`, `49e09ac`.

### T40 · Recorridos completos y capturas (3 puntos)

**Objetivo.** Comprobar que las historias del sprint funcionan juntas, no solo cada una con sus pruebas.

**Cómo se diseñó.**

- **Por servicios.** Una solicitud por programa (CC, PS, RHF y PSAHEM) recorre publicación, contrato, firma, planta (donde
  aplica), solicitud de pago, pago o cheque; en cada relevo se comprueba el estado, la bandeja, el acuse y el renglón de la
  bitácora.
- **Por la interfaz.** Dos tramos en Chromium cambiando de usuario en cada relevo: PS de «aprobada» al pago, y PSAHEM de
  «contratada» al cheque entregado, con la instrucción de pago del Comité por la pantalla.

**Cómo se ejecutó.** `pruebas/test_sprint_2_recorrido_completo.py` y `pruebas/e2e/test_recorrido_sprint_2_completo.py`
(24 capturas `recorrido_sprint_2_*`), y `test_recorrido_tropiezos_s2.py`.

**Cómo se comprobó.** Los recorridos en verde dentro de la batería completa; el de la interfaz encontró los tropiezos de T39.

**Commits:** `62b5ae4` (servicios) y `38e7e6a` (interfaz).

### T43a · Bajas y reasignaciones con publicación, contrato y pagos (3 puntos; parte de T43)

Ver «Integración de las observaciones del profesor a M3 y M5» a continuación.

[[SALTO]]

## Integración de las observaciones del profesor a M3 y M5 (T43, 5 puntos)

**Contexto.** En la revisión del 23 de noviembre el profesor hizo seis observaciones al sprint 1 (D-29): observación de cada
faltante, documento de los dictámenes, título y criterio de HU-2.4, propiedad del predio, candidatos y beneficiarios en vistas
distintas y trazabilidad en la base de datos. Se atendieron en `sprint-1`; el 24 de noviembre se integraron en `sprint-2`
(merge `6c5815f`, D-30). Para M3 y M5 hubo que **extenderlas**, porque la baja, la lista de espera y la trazabilidad ya no
terminan en el acta del Comité.

### T43a · Bajas y reasignaciones (HU-2.4) con publicación, contrato y pagos — Angel, 3 puntos

**Criterio vigente de HU-2.4:**

1. Cada incidente (desistimiento, cancelación, baja, sustitución, caso fortuito, suspensión o reintegro) tiene un acuerdo con
   su causa, los expedientes a los que aplica y el área que debe atenderlo.
2. En una reasignación o sustitución, la persona beneficiaria que sale queda dada de baja y entra la siguiente solicitud de la
   lista de espera, en su orden, sin rebasar el recurso liberado.
3. Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos
   (trazabilidad).

**Cómo se diseñó.**

- **Cuándo procede la baja.** En cualquier etapa **anterior a la primera ministración solicitada**
  (`seguimiento.ESTADOS_CON_BAJA`: aprobada, publicada, notificada, contrato elaborado o en la Delegación, sin firma en plazo,
  contratada, con vale o con planta entregada). Con una ministración en curso o pagada el sistema la rechaza y pide el acuerdo
  de **reintegro**.
- **La persona dada de baja ya no avanza.** `seguimiento.exigir_vigente` se llama desde `contrato` y `pagos`: no firma, no se
  le elabora contrato, no recibe ni surte vale, no se emite su oficio ni se solicita su ministración.
- **El recurso que se libera por no firmar en plazo** (HU-3.3) entra como recurso liberado con un `MovimientoListado` sin
  acuerdo (gancho `AL_LIBERAR_RECURSO`) y el Comité lo reasigna igual que el de una baja. Si el Comité da de baja a una
  persona `sin_firma_en_plazo`, deja de estar «por liberar».
- **Una sola transición para liberar.** La de `sin_firma_en_plazo → recurso_liberado` de la Secretaría Técnica se quitó: el
  Comité da de baja por acuerdo y la Dirección confirma la liberación.
- **La reasignación se publica.** `publicacion.filas_por_publicar` arma lo que se publica: quien salió antes de publicar ya no
  aparece y quien entró desde la lista de espera aparece como «Reasignación». Si la reasignación llega después de publicar el
  acta de aprobación, al cerrar la sesión de seguimiento con reasignaciones su acta queda autorizada y la Dirección la
  publica: la persona pasa a `publicada`, recibe su aviso y corren sus plazos.
- **Beneficiarios sigue a la persona** en todo el trámite y muestra las bajas.

**Cómo se ejecutó.** `dictamen/seguimiento.py` (`ESTADOS_CON_BAJA`, `ESTADOS_CON_PAGO`, `exigir_vigente`,
`al_liberar_recurso`, `cerrar_sesion`), `contrato/publicacion.py`, `contrato/contratos.py`, `contrato/firma.py`,
`contrato/planta.py`, `pagos/solicitudes.py`, `dictamen/listados.py`, `datos/flujo_tramite.json` y las plantillas de
Beneficiarios, Dictámenes y Publicación.

**Cómo se comprobó.** `test_hu_2_4_con_contrato_y_pagos.py` (6): la persona dada de baja ya no firma ni cobra, con una
ministración solicitada no hay baja sino reintegro, el recurso liberado por no firmar se reasigna y se publica, y la baja
antes de publicar se refleja en la publicación; más 14 pruebas de `test_hu_2_4.py`.

**Commit:** `53e78c0`.

### T43b · Trazabilidad de M3 y M5 y documentación — Joshua, 2 puntos

**Criterio de trazabilidad (en cada una de las siete historias de M3 y M5):** queda en la base de datos el registro de quién hizo cada
acción, con la fecha y la hora y los valores anteriores y nuevos.

**Cómo se diseñó.**

- **Historial en cada modelo.** Todos los modelos de `contrato` y `pagos` llevan `django-simple-history`; el historial
  registra siempre al usuario (las altas y los cambios se guardan con `save()`, no con `update()`, y se usa el motivo del
  cambio cuando el paso lo pide).
- **Pestaña «Trazabilidad».** `contrato/registro.py` y `pagos/registro.py` entregan sus fuentes a `nucleo/trazabilidad.py`:
  publicación, resultado publicado, modelo y versión, contrato, adendum, firma, formalización, sin firma, vale, renglón de
  vale, salida de planta, oficio, comprobante, solicitud de pago, revisión, pago, remisión y cheque.
- **Documentación.** README, modelo de datos y bitácora (D-30).

**Cómo se ejecutó.** `nucleo/trazabilidad.py`, `registro.py` de `contrato` y `pagos`, y los servicios que guardan con
`save()` en `contrato/` y `pagos/`.

**Cómo se comprobó.** Una prueba de trazabilidad por historia en `test_hu_3_1.py` a `test_hu_5_3.py` (usuario, fecha y valores
anterior y nuevo) y la prueba de la pestaña; la de vigencia del vale sigue la regla de días hábiles (`d74da3c`).

**Commits:** `286cd22`, `77b2180`, `d74da3c`.

[[SALTO]]

## Resumen de entregables por persona

| Persona | Commits | Pruebas propias | Capturas |
| --- | --- | --- | --- |
| Joshua | `47cc5ee`, `d1a8c64`, `2bee813`, `30c4124`, `f22eb15`, `d49aacc`, `2fa15a7`, `4fbf940`, `88d9f93`, `f24d627`, `c94a5c9`, `5849d57`, `286cd22`, `77b2180` | 40 del núcleo y la base + 24 de HU-3.1 + 4 del menú | `hu_3_1_*`, `s2_14_*` |
| Omar | `d877a63`, `d5698c8`, `82d2ed8`, `f1addff`, `8e95e4c`, `d9bbf7d`, `6753f8c`, `0871a66` | 32 de HU-3.3 + 26 de HU-3.4 + 22 de HU-5.1 + 24 de calendario, bordes y generador + 10 de tropiezos | `hu_3_3_*`, `hu_3_4_*`, `hu_5_1_*` |
| Cin | `c979a30`, `ef3e66d`, `a8dad5c`, `e9a1f2c`, `abc03e0`, `1af1d0a` | 9 de reglas + 22 de HU-3.2 + 26 de HU-5.2 + 17 de HU-5.3 | `hu_3_2_*`, `hu_5_2_*`, `hu_5_3_*` |
| Angel | `9254478`, `5bfa706`, `5f899fb`, `62b5ae4`, `38e7e6a`, `53e78c0` | 28 de la Calculadora (HU-7.2 y 7.3) + 6 de bajas con contrato y pagos + los recorridos completos | `hu_7_2_*`, `hu_7_3_*`, `recorrido_sprint_2_*` |

## Cómo se integró el trabajo de las cuatro personas

1. **El primer día:** Cin deja las reglas de PS, RHF y PSAHEM (tres unidades de proceso en paralelo) y Angel arranca la
   Calculadora, que no depende del sistema.
2. **Base antes que historias:** Joshua termina la base de M3 y M5 (avisos, plazos con evento, estados, monto) y la
   publicación. Con eso, el resto puede avanzar sin tocar el núcleo.
3. **Cada app, un solo punto de enganche:** `contrato` y `pagos` se conectan con su `registro.py` y los puntos de
   `nucleo/extensiones.py` (pestaña, menú, paneles de bandeja, revisión de plazos, avisos), así que ni Omar ni Cin editan el
   núcleo.
4. **De la publicación al cheque, en cadena:** Cin elabora el contrato sobre lo que publica Joshua, Omar lo formaliza y
   entrega la planta, y Omar solicita el pago que Cin paga y emite. Cada paso deja el estado en el que empieza el siguiente.
5. **Prueba de todo junto:** Angel hace los recorridos por servicios y por la interfaz sobre el trabajo de todos; los
   tropiezos regresan a Omar para corregirlos (T39).
6. **Revisión antes de aceptar:** Joshua revisa cada historia antes de aceptarla, corre la batería completa y registra en la
   bitácora las decisiones y las dudas para el cliente.
7. **Observaciones del profesor:** Angel extiende la baja y la reasignación a M3 y M5 y Joshua extiende la trazabilidad
   (T43), con una sola integración y una sola corrida de la batería completa.
