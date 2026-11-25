# Cambios a las historias de usuario

Registro de los cambios que se han hecho a las historias de usuario (HU) de la propuesta después de su versión
original (12-13 de noviembre de 2026).

- **Originales:** quedan sin tocar en [`original/`](original/), para referencia.
- **Fuente de las historias:** `sistema/especificacion/modelo.json` del repositorio, que es la que usan el sistema y
  sus pruebas.
- **Cómo se actualiza esta carpeta:** cada vez que cambie una historia, se corre
  `herramientas/actualizar_propuesta.py` (el comando está en su encabezado). Actualiza:
  - `datos/modelo.json`;
  - `CONTEXTO.md`;
  - la hoja «Historias de usuario» de `docs/Matriz_funciones_historias_PROBOSQUE.xlsx`;
  - las páginas de historias del PDF de la propuesta (11 a 15 y 21 a 22), con el mismo estilo y la misma
    numeración. Las demás páginas se conservan tal cual.

## 25 de noviembre de 2026 · Observaciones del profesor al sprint 1 y trazabilidad en todas las historias

**Motivo.** Observaciones del profesor del 23 de noviembre al sprint 1, atendidas en las ramas `sprint-1` y
`sprint-2` (con la redacción de Omar) e integradas en la rama principal junto con el sprint 3.

| Historia | Antes | Ahora |
| --- | --- | --- |
| HU-1.4, historia | Como personal del área responsable del programa, quiero validar el expediente contra las reglas del programa y avisar los faltantes, para que la solicitud pase a dictamen o se corrija a tiempo. | Como personal del área responsable del programa, quiero validar el expediente contra las reglas del programa y avisar cada faltante con su observación, para que la solicitud pase a dictamen o se corrija a tiempo. |
| HU-1.4, criterio nuevo | — | Cada requisito señalado como faltante tiene la observación de la Dirección (qué falta o por qué no es válido) y el aviso de faltantes la incluye. |
| HU-2.1, historia | Como personal del área responsable del programa, quiero elaborar el dictamen técnico de cada solicitud y el listado preliminar, para proponer al Comité qué solicitudes apoyar. | Como personal del área responsable del programa, quiero elaborar el dictamen técnico de cada solicitud, expedido como documento, y el listado preliminar, para proponer al Comité qué solicitudes apoyar. |
| HU-2.1, criterio 1 | Cada solicitud tiene un dictamen técnico factible o no factible, con su motivo. | Cada solicitud tiene un dictamen técnico factible o no factible, con su motivo, expedido como documento PDF con folio y adjunto al expediente. |
| HU-2.2, historia | Como personal de la Unidad Jurídica, quiero dictaminar la documentación legal de cada solicitud y cotejar a su titular con el Listado de Personas Beneficiarias Incumplidas y su predio con los predios con procedimiento o sanción, para que solo se aprueben solicitudes procedentes. | Como personal de la Unidad Jurídica, quiero dictaminar la documentación legal de cada solicitud, revisar que se acredite la propiedad o legal posesión del predio y cotejar a su titular con el Listado de Personas Beneficiarias Incumplidas y su predio con los predios con procedimiento o sanción, para que solo se aprueben solicitudes procedentes. |
| HU-2.2, criterio 1 | Cada solicitud tiene un dictamen jurídico procedente o no procedente, con su motivo. | Cada solicitud tiene un dictamen jurídico procedente o no procedente, con su motivo, expedido como documento PDF con folio y adjunto al expediente. |
| HU-2.2, criterio nuevo | — | Una solicitud cuya propiedad o legal posesión del predio no se acredita (documento a nombre del titular, que ampare la superficie, vigente y sin conflicto) es no procedente. |
| HU-2.3, criterio nuevo | — | Las solicitudes candidatas (en dictamen, por aprobar y en lista de espera, en su orden) y las personas beneficiarias (con su monto y cómo entraron) se consultan en dos vistas separadas. |
| HU-2.4, título | Sesiones de seguimiento | Reasignaciones e incidentes |
| HU-2.4, historia | Como integrante del Comité, quiero tomar acuerdos en las sesiones de seguimiento y asignar cada uno al área que debe cumplirlo, para atender los casos que surgen durante el ejercicio. | Como integrante del Comité, quiero acordar en las sesiones de seguimiento la atención de cada incidente del ejercicio y la reasignación del recurso liberado a la lista de espera, para que el recurso llegue a otra solicitud factible y cada caso tenga un área que lo atienda. |
| HU-2.4, criterios | (1) Cada acuerdo indica a qué expedientes aplica y qué área debe cumplirlo. (2) En PSAHEM existe la instrucción de pago de cada ministración; en PEG, la validación de cada periodo de reportes. | (1) Cada incidente (desistimiento, cancelación, baja, sustitución, caso fortuito, suspensión o reintegro) tiene un acuerdo con su causa, los expedientes a los que aplica y el área que debe atenderlo. (2) En una reasignación o sustitución, la persona beneficiaria que sale queda dada de baja y entra la siguiente solicitud de la lista de espera, en su orden, sin rebasar el recurso liberado. |
| Las 21 historias de M1 a M6, criterio nuevo al final | — | Queda en la base de datos el registro de quién hizo cada acción, con la fecha y la hora y los valores anteriores y nuevos (trazabilidad). |

**Funciones.** M1.4 (aviso de cada faltante con su observación), M2.1 y M2.2 (dictámenes expedidos como documento; M2.2
con la acreditación de la propiedad o legal posesión), M2.3 (vistas separadas de candidatos y de personas
beneficiarias) y M2.4 (reasignaciones e incidentes) dicen lo mismo que sus historias.

**Lo que siguió haciendo el sistema.** La instrucción de pago de PSAHEM y la validación de reportes de PEG dejan de ser
criterio de HU-2.4, pero siguen como acuerdos de seguimiento que dejan constancia, con sus pruebas.

**Cómo se concilió HU-2.4 con HU-6.1 y HU-6.2.** La baja y la reasignación tienen un solo registro en el sistema: lo
que acuerda el Comité directamente (HU-2.4) y lo que propone el área responsable (HU-6.1 y HU-6.2) usan el mismo recurso
liberado, en el orden de la lista de espera, y lo que una propuesta en trámite reasigna no se reasigna dos veces. La
«sustitución» de HU-2.4 (sale la persona beneficiaria y entra la siguiente de la lista de espera) es distinta de la
sustitución de HU-6.1 (la segunda persona beneficiaria continúa en lugar de la titular).

Puntos, roles y sprints, iguales (conviene volver a estimar HU-2.2 y HU-2.4). Se actualizaron `datos/modelo.json`,
`CONTEXTO.md`, la matriz y las páginas de historias del PDF de la propuesta. Con el criterio de trazabilidad, ocho
historias tienen cuatro criterios: en la matriz, que trae tres columnas de criterios, del tercero en adelante van juntos
en «Criterio 3»; en el PDF, las tablas de historias usan una letra un poco menor y se repartieron de otro modo en las
mismas páginas 12 a 15 (el PDF sigue con 26 páginas).

## 19 de noviembre de 2026 · HU-1.2, HU-1.3 y HU-2.2 dicen lo que ya hace su función

**Motivo.** Revisión de las historias contra su función y las pantallas (documento «Historias de usuario e
interfaces»). Tres historias decían menos que su función o mezclaban los dos catálogos del dictamen jurídico. El
sistema ya hacía lo que dicen ahora, así que el código no cambió.

| Historia | Antes | Ahora |
| --- | --- | --- |
| HU-1.2, criterio 1 | Cada requisito del programa, del tipo de persona y de la modalidad está revisado como entregado o faltante. | Cada requisito del programa, del tipo de persona y de la modalidad está revisado como entregado (con su archivo digitalizado), faltante o, si es condicional, no aplica. |
| HU-1.3, historia | Como personal de la Delegación, quiero registrar el polígono del predio levantado en campo, para conocer su ubicación y su superficie real al dictaminar y verificar. | Como personal de la Delegación, quiero registrar el polígono del predio levantado en campo por la Delegación o por el prestador de servicios forestales, para conocer su ubicación y su superficie real al dictaminar y verificar. |
| HU-2.2, historia | Como personal de la Unidad Jurídica, quiero dictaminar la documentación legal de cada solicitud y cotejar a su titular y su predio con el Listado de Personas Beneficiarias Incumplidas, para que solo se aprueben solicitudes procedentes. | Como personal de la Unidad Jurídica, quiero dictaminar la documentación legal de cada solicitud y cotejar a su titular con el Listado de Personas Beneficiarias Incumplidas y su predio con los predios con procedimiento o sanción, para que solo se aprueben solicitudes procedentes. |
| HU-2.2, criterio 2 | Una solicitud cuyo predio o titular está en el Listado de Personas Beneficiarias Incumplidas es no procedente. | Una solicitud cuyo titular está en el Listado de Personas Beneficiarias Incumplidas, o cuyo predio tiene un procedimiento o una sanción, es no procedente. |

Títulos, roles, puntos, sprints, funciones y número de criterios, iguales. Se actualizaron `datos/modelo.json`,
`CONTEXTO.md`, la matriz y las páginas de historias del PDF de la propuesta.

## 18 de noviembre de 2026 · La propuesta entra al repositorio

La carpeta de la propuesta se versiona como `propuesta/`. Cambios al incorporarla:

- El archivo de contexto se llama ahora `CONTEXTO.md`, con redacción neutra en tres frases.
- Las páginas 4 y 6 del PDF de la propuesta (y de su copia en `original/`) se rehicieron con una redacción neutral
  sobre cómo se desarrolla.
- El mapa de la Calculadora perdió una etiqueta `<meta>` sin efecto.

El contenido de las historias no cambió con esto. El detalle está en `original/LEEME.md`.

## 18 de noviembre de 2026 · Historias enfocadas en la acción

**Motivo.** Nota del profesor a la redacción de la HU-1.1: la historia debe enfocarse en su acción.

**Qué cambió en las 26 historias.**

- **Formato.** Pasó de «Como [rol], quiero [lo que desea], por lo que [lo que hace], para [la meta]» a «Como [rol],
  quiero [acción], para [beneficio]». La acción que antes quedaba escondida en «por lo que…» es ahora lo que el rol
  quiere hacer.
- **Ejemplo, HU-2.1.**
  - Antes: «quiero saber qué solicitudes son técnicamente factibles, por lo que elaboro el dictamen técnico y el
    listado preliminar, para proponer al Comité…».
  - Ahora: «quiero elaborar el dictamen técnico de cada solicitud y el listado preliminar, para proponer al
    Comité…».
- **Lo demás no cambió:** títulos, roles, puntos, sprints y funciones siguen igual. Los criterios de aceptación
  siguen igual salvo en la HU-1.1.

**HU-1.1 · Registro de la solicitud**, por indicación del profesor:

| | Antes | Ahora |
| --- | --- | --- |
| Historia | Como personal de la Delegación, quiero que cada solicitud quede asociada a su predio, por lo que registro la solicitud que entrega la persona solicitante, para iniciar el trámite. | Como personal de la Delegación, quiero registrar la solicitud con los datos generales de la persona solicitante, los datos del predio y los datos específicos del programa, para iniciar su trámite. |
| Criterios | (1) Existe una solicitud asociada al predio y se genera su acuse con la fecha y la hora de recepción. (2) El predio está en un municipio que atiende la Delegación. | Se genera un folio único para la solicitud. (único criterio) |

**Lo que siguió haciendo el sistema.** El acuse de recepción y la validación de que el municipio lo atiende la
Delegación dejan de ser criterios, pero el sistema los conserva como reglas del registro, con sus pruebas.

**Cambios en el sistema.**

- El formulario de registro nombra sus secciones como la historia:
  - Datos específicos del programa;
  - Datos del predio;
  - Datos generales de la persona solicitante.
- Una prueba nueva comprueba el folio único: `test_hu_1_1_genera_folio_unico`.

**Archivos de esta carpeta que se actualizaron:**

- `datos/modelo.json`;
- `CONTEXTO.md`, en el formato de historia, en las 26 líneas «Historia» y «Criterios» y en los lineamientos del
  profesor (sección 7);
- `docs/Matriz_funciones_historias_PROBOSQUE.xlsx`, en la hoja «Historias de usuario» (29 celdas);
- `docs/Propuesta_solucion_modular_PROBOSQUE_2026.pdf`, en las páginas 11 a 15 y 21 a 22.
