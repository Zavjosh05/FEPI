# Secuencia de prueba del sprint 1

Cómo simular a mano, en el navegador, todas las funciones del sprint 1 con los datos de prueba de esta carpeta. Cada
escenario dice quién entra, qué hace, con qué archivo y **qué debe pasar**; si el sistema hace otra cosa, es un
hallazgo.

## 1. Qué datos de prueba hay

| Fuente | Qué trae | Para qué sirve |
| --- | --- | --- |
| **Demostración** (`cargar_demo`, se carga sola al levantar el sistema) | Usuarios de cada unidad; doce solicitudes de Capturando Carbono 2026 detenidas en cada paso del trámite; una sesión de aprobación con acta; una sesión de seguimiento con tres acuerdos; una persona en el Listado de Incumplidas | Ver cada pantalla con datos y continuar trámites a medias sin capturar desde cero |
| **Pruebas automáticas** (`sistema/pruebas/`) | 128 pruebas que crean sus propios datos, entre ellas un recorrido completo por servicios y nueve recorridos con el navegador | Comprobar el sistema sin intervención (Guía de inicio, sección 1.8) |
| **Esta carpeta** (`datos_prueba/sprint_1/`) | Polígonos para subir, documentos PDF de ejemplo y fichas de solicitudes | Probar a mano lo que la demostración no permite: subir archivos y capturar solicitudes nuevas con resultados conocidos |

Antes de esta carpeta, el proyecto no tenía archivos para que una persona probara la carga de polígonos y documentos:
las pruebas automáticas los generan en memoria. Por eso se crearon estos.

### Contenido de esta carpeta

| Archivo | Qué es |
| --- | --- |
| `poligonos/01_amecameca_12ha.geojson`, `.kml` y `_shapefile.zip` | El mismo predio válido de 12 ha en Amecameca, en los tres formatos que acepta el sistema |
| `poligonos/02_amecameca_correccion.geojson` | El mismo predio movido 40 m: un cambio que el sistema marca como «Corrección» |
| `poligonos/03_amecameca_cambio_de_lugar.geojson` | El predio movido 2.5 km: el sistema lo marca como «Cambio de lugar» |
| `poligonos/04_fuera_del_municipio.geojson` | Un cuadro sobre el límite de Amecameca: la mitad queda fuera |
| `poligonos/05_invalido_se_cruza.geojson` | Un polígono cuyos lados se cruzan: geometría inválida |
| `poligonos/06_juchitepec_traslapa_demo.geojson` | 6 ha en Juchitepec que se encima con dos solicitudes de la demostración |
| `poligonos/07_amecameca_250ha_fuera_de_rango.geojson` | 250 ha: fuera del rango de 1 a 200 ha de Capturando Carbono |
| `poligonos/LEEME.csv` | La lista anterior con la superficie y lo que debe pasar con cada uno |
| `documentos/*.pdf` | Ocho documentos de ejemplo marcados «DOCUMENTO DE PRUEBA» (solicitud única, identificación, CURP, acreditación de la propiedad…). `documento_generico.pdf` sirve para cualquier requisito |
| `fichas_solicitudes.csv` | Seis solicitudes ficticias listas para capturar, con el resultado esperado de cada una |
| `generar_datos_prueba.py` | Vuelve a crear todo lo anterior (`python datos_prueba/sprint_1/generar_datos_prueba.py` con el entorno de la Calculadora) |

Todos los nombres, CURP, RFC, teléfonos y correos son inventados.

**Comprobado el 18 de noviembre de 2026** contra el sistema del sprint 1, por los mismos servicios que usan las
pantallas:

- Los tres formatos del predio 01 dan 12 ha «dentro del municipio».
- El 02 queda como «Corrección» y el 03 como «Cambio de lugar».
- El 04 da el aviso «El 50.0 % del polígono queda fuera del municipio de Amecameca».
- El 05 se rechaza por geometría inválida.
- El 06 muestra traslapes de 3.1 ha con cada una de las dos solicitudes de la demostración.
- El 07 queda fuera de rango.
- La solicitud en Zinacantepec se rechaza.
- La persona de la ficha G aparece en el cotejo.
- Un PDF de esta carpeta se acepta como requisito entregado.

## 2. Antes de empezar

1. Levanta el sistema como dice la [Guía de inicio](../../GUIA_DE_INICIO.md). Para partir de la demostración limpia:
   `docker compose down -v` y `docker compose up --build` desde `sistema/`.
2. Abre http://localhost:8080/entrar/. Contraseña de todos los usuarios: `Probosque2026`.
3. Ten a la mano `fichas_solicitudes.csv` (se abre en Excel) y las carpetas `poligonos/` y `documentos/`.
4. Para cambiar de unidad: **Salir** y entra con el usuario que indica cada paso.

> **Sobre las fechas.** La convocatoria 2026 de Capturando Carbono fija el 30 de junio de 2026 como límite para
> dictaminar. Si pruebas después de esa fecha, el dictamen técnico dirá «fuera de plazo» o «vencido»: es lo esperado.

## 3. Escenarios

Recorre los escenarios en orden: A deja una solicitud lista para el Comité, que usan los escenarios D, H e I.

### Escenario A. Camino completo de una solicitud nueva

Ficha **A** de `fichas_solicitudes.csv` (Teresa Aguilar Montes, Predio Las Palomas, Amecameca, 12 ha).

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| A1 | `del_amecameca` | **Registrar solicitud** y captura la ficha A. **Registrar y generar acuse** | Folio `CC-2026-AME-00NN`, estado «Solicitud recibida», acuse de recepción en PDF con fecha, hora y el plazo de 5 días hábiles |
| A2 | `del_amecameca` | Pestaña **Requisitos**: en cada renglón **Revisar**. En los documentos, **Entregado** y sube el PDF que corresponda de `documentos/` (o `documento_generico.pdf`). En las condiciones, **Cumple**. En los opcionales o condicionales que no apliquen, **No aplica** | Cada renglón cambia de estado sin recargar; el contador baja hasta «0 sin revisar» |
| A3 | `del_amecameca` | Antes de terminar A2, intenta **Enviar expediente digital a la Dirección** | No deja: dice qué requisitos faltan por revisar |
| A4 | `del_amecameca` | Pestaña **Ubicación**: sube `01_amecameca_12ha.geojson`, «Personal de la Delegación», tu nombre y la fecha. **Registrar polígono** | Polígono vigente de 12 ha, «Dentro del municipio», primer renglón del historial |
| A5 | `del_amecameca` | Con todo revisado, **Enviar expediente digital a la Dirección** | Acuse de envío; el expediente sale de «Por atender» y queda «En revisión de la Dirección» |
| A6 | `dir_drff` | Abre el expediente, pestaña **Validación**, **Abrir pantalla de validación**. No marques faltantes. **Validar expediente** | Estado «Validado · en dictamen» con constancia en PDF |
| A7 | `dir_drff` | Pestaña **Dictámenes**, **Elaborar dictamen técnico**. Revisa el análisis cartográfico, marca **Cumple** en los criterios, **Factible**, superficie factible 12. **Registrar dictamen técnico** | El análisis dice 12 ha, dentro del rango de 1 a 200 ha y del municipio, sin traslapes. Queda el dictamen con su acuse |
| A8 | `juridica` | Mismo expediente, **Elaborar dictamen jurídico**: el cotejo no encuentra coincidencias. **Procedente**, un motivo. **Registrar dictamen jurídico** | Con los dos dictámenes, el estado pasa a «Dictaminada» y el expediente aparece en la bandeja de `comite` |
| A9 | `dir_drff` | Menú **Listado preliminar**; **Exportar CSV (Excel)** | La solicitud aparece como factible y procedente; el CSV abre en Excel con acentos |

La solicitud sigue en el escenario H (Comité).

### Escenario B. Faltantes, notificación y reenvío

Para no capturar todos los requisitos de nuevo, usa **La Cañada** (`CC-2026-AME-0003`), que la demostración deja en
revisión de la Dirección. Si prefieres una nueva, captura la ficha **B** y llévala hasta el paso A5.

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| B1 | `dir_drff` | Pantalla de validación de La Cañada: marca un requisito como **Faltante** y escribe una observación. **Emitir aviso de faltantes** | Estado «Aviso de faltantes», con fecha límite a 5 días hábiles del aviso, sin contar fines de semana ni días inhábiles; el expediente regresa a la Delegación |
| B2 | `del_amecameca` | Pestaña **Validación**: **Registrar notificación a la persona solicitante** | Fecha y hora de la notificación con su acuse |
| B3 | `del_amecameca` | Pestaña **Requisitos**: el requisito faltante, **Entregado** con un PDF de `documentos/`. Luego **Reenviar a la Dirección con los faltantes** | Regresa a «En revisión de la Dirección» |
| B4 | `dir_drff` | Valida el expediente | «Validado · en dictamen» |

**Para ver un aviso vencido:** Rancho El Capulín ya tiene su aviso notificado en la demostración. El sistema señala en
la bitácora los avisos vencidos, una vez al día, con la revisión de plazos.

### Escenario C. Solicitud de un municipio de otra Delegación

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| C1 | `del_amecameca` | **Registrar solicitud** con la ficha **C** (municipio Zinacantepec) | Al elegir el municipio, el formulario avisa que lo atiende la Delegación Regional Forestal Toluca; al registrar, no deja y dice a qué Delegación corresponde |

### Escenario D. Polígonos: formatos, cambios y errores

Sobre la solicitud del escenario A (pestaña **Ubicación**, como `del_amecameca`):

| # | Archivo | Motivo del cambio | Qué debe pasar |
| --- | --- | --- | --- |
| D1 | `01_amecameca_12ha.kml` y luego `01_amecameca_12ha_shapefile.zip` | «Prueba de formato» | Los dos se aceptan con 12 ha; el historial conserva cada polígono anterior |
| D2 | `02_amecameca_correccion.geojson` | «Ajuste del levantamiento» | 12.5 ha; el historial lo marca «Corrección» |
| D3 | `03_amecameca_cambio_de_lugar.geojson` | «El predio estaba mal ubicado» | El historial lo marca «Cambio de lugar» |
| D4 | `04_fuera_del_municipio.geojson` | «Prueba de límite» | Se guarda con el aviso «El 50.0 % del polígono queda fuera del municipio de Amecameca» |
| D5 | `05_invalido_se_cruza.geojson` | — | Se rechaza: «La geometría no es válida (Self-intersection…)»; el polígono vigente no cambia |
| D6 | Dibujo en el mapa | «Prueba de dibujo» | Se guarda como «Dibujado en el mapa» con su superficie calculada |

Al terminar, vuelve a cargar `01_amecameca_12ha.geojson` para dejar el predio en su lugar. El dictamen técnico usa el
polígono vigente.

### Escenario E. Traslape con otras solicitudes (núcleo agrario)

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| E1 | `del_amecameca` | Registra la ficha **E** (Ejido Juchitepec, núcleo agrario, con representante) | Pide los requisitos de núcleo agrario; entre ellos, el del Órgano del Comisariado |
| E2 | `del_amecameca` | **Ubicación**: `06_juchitepec_traslapa_demo.geojson`. Revisa los requisitos y envía a la Dirección | 6 ha, dentro de Juchitepec |
| E3 | `dir_drff` | Valida y abre **Elaborar dictamen técnico** | El análisis cartográfico lista dos traslapes, con Los Encinos del Monte y La Joya Alta, de unas 3.1 ha cada uno, y el mapa los dibuja |

### Escenario F. Superficie fuera del rango del programa

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| F1 | `del_amecameca` | Registra la ficha **F** (250 ha), carga `07_amecameca_250ha_fuera_de_rango.geojson`, revisa requisitos y envía | — |
| F2 | `dir_drff` | Valida y abre el dictamen técnico | El análisis dice que 250 ha está fuera del rango de 1 a 200 ha |
| F3 | `dir_drff` | Marca **No cumple** en el criterio de superficie e intenta **Factible** | No deja registrar el dictamen factible con un criterio que no se cumple; registra **No factible** con su motivo |

### Escenario G. Persona en el Listado de Incumplidas

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| G1 | `juridica` | Menú **Incumplidas** | Rogelio Bautista Núñez (CURP `BANR600101HMCTXG09`) está en el Listado |
| G2 | `del_valle` | Registra la ficha **G** (Villa de Allende), revisa los requisitos y envía | — |
| G3 | `dir_drff` | Valida y registra el dictamen técnico **Factible** | — |
| G4 | `juridica` | **Elaborar dictamen jurídico** | El cotejo automático encuentra a la persona en el Listado; **Procedente** no se puede registrar. Registra **No procedente** con su motivo |
| G5 | `juridica` | **Incumplidas**: inscribe a otra persona inventada con **Inscribir**; luego dala de **Baja** con un motivo | La baja no la borra: queda inactiva y con historial |

La solicitud queda «Dictaminada» con el jurídico no procedente: el Comité la pondrá en la Lista de No factibles.

### Escenario H. Sesión de aprobación del Comité

Usa las solicitudes que dejaste «Dictaminadas» (A, y si los hiciste, E y G), más Potrero Viejo de la demostración.

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| H1 | `comite` | **Sesiones del Comité** → **Nueva sesión de aprobación**: Capturando Carbono 2026, ordinaria, fecha **dentro de 2 días hábiles**, lugar y orden del día. **Crear sesión** | La sesión queda creada |
| H2 | `comite` | **Agregar documento** (un PDF de `documentos/`) y **Enviar convocatoria a los integrantes** | No deja enviar: las reglas piden 3 días hábiles de anticipación para una ordinaria |
| H3 | `comite` | Crea otra sesión con fecha **dentro de 5 días hábiles** o más, agrega el documento y envía la convocatoria | Acuse con fecha, hora, orden del día e integrantes del Comité |
| H4 | `comite` | **Generar propuesta** con un **Recurso disponible** menor que la suma de las solicitudes factibles, por ejemplo $30,000 | Las factibles, ordenadas por priorización (reforestaciones, luego refrendos, luego fecha de registro), van a la Lista de Personas Beneficiarias hasta donde alcanza ($2,000 por hectárea); las demás, a la Lista de espera con su lugar; las no factibles o no procedentes, a la Lista de No factibles |
| H5 | `comite` | **Ajustar** una solicitud de lugar o de lista con un motivo | Se mueve y el motivo queda; una no factible no puede pasar a las listas de apoyo |
| H6 | `comite` | **Registrar acta con los listados aprobados** | Acta en PDF con las tres listas y la autorización de publicación; cada expediente queda «Aprobada», «Lista de espera» o «No factible» |

### Escenario I. Sesión de seguimiento y acuerdos

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| I1 | `comite` | **Nueva sesión de seguimiento** (con convocatoria, como en H3) y **Registrar acuerdo**: tipo «Otro», un texto, la solicitud del escenario A y el área «Dirección de Restauración y Fomento Forestal» | El acuerdo queda en la sesión |
| I2 | `dir_drff` | Bandeja: el acuerdo aparece arriba. **Marcar cumplido** | Sale de su bandeja y queda «cumplido» en la sesión |
| I3 | `dir_drff` y `juridica` | Bandeja | La demostración trae en la sesión SO-CC-2026-02 un acuerdo pendiente para cada una (caso fortuito y otro) y uno ya cumplido (reasignación) |

La instrucción de pago a la Fiduciaria es de PSAHEM, que en esta versión no tiene reglas cargadas: no se puede
simular en la demostración. La cubren las pruebas automáticas (`pruebas/test_hu_2_4.py` y su recorrido con
navegador).

### Escenario J. Solicitud desechada

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| J1 | `del_amecameca` | Registra cualquier ficha sin revisar requisitos y pulsa **Tener por desechada la solicitud** con un motivo | Estado «Solicitud desechada»; ya no aparece en «Por atender» pero sí en «Todos los míos». El Tecolote (demostración) es otro ejemplo |

### Escenario K. Bitácora, acuses y permisos

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| K1 | cualquiera | Pestañas **Documentos y acuses** y **Bitácora** de la solicitud A | Cada paso de A1 a H6 aparece con fecha, hora y usuario; cada acuse abre su PDF |
| K2 | `del_toluca` | Busca el folio de la solicitud A en la bandeja | No aparece: cada Delegación ve solo lo suyo |
| K3 | `del_amecameca` | Abre una solicitud en «En revisión de la Dirección» | No ve los botones de validación: no le toca ese paso |

### Escenario L. Calculadora forestal

Abre la página como dice la Guía de inicio, sección 2.

| # | Qué hace | Qué debe pasar |
| --- | --- | --- |
| L1 | Modo **Un año**, año 2025 | Bosque del Estado: 466,058 ha (90.9 % de la zona forestal); cambio desde 2024: −1,897 ha; tendencia −3,545 ha/año |
| L2 | Evolución del bosque | 473,148 ha en 2023, 467,955 en 2024 y 466,058 en 2025, iguales en la gráfica y en la tabla |
| L3 | Busca «Luvianos» y ábrelo | Su serie baja de 24,194 a 20,871 ha, con una tendencia de −1,662 ha/año. Es el caso de la selva baja caducifolia que la página advierte |
| L4 | Modo **Comparar años**, 2023 → 2024 | Pérdida por incendio, otras pérdidas y ganancia del periodo; el cambio neto coincide con la diferencia de L2 |
| L5 | Vista **Año de pérdida** en el mapa y la sección **Alcances** | Los colores van del año más antiguo al más reciente; Alcances explica qué no se puede afirmar todavía |

## 4. Si algo no sale como dice la tabla

Anota el escenario y el paso, el usuario, el folio y lo que viste. Revisa la pestaña **Bitácora** del expediente y,
si hubo un error de la página, `docker compose logs web`. Para volver a empezar: `docker compose down -v` y
`docker compose up --build`.
