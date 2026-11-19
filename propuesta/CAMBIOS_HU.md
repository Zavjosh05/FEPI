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
