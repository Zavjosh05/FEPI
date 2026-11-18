# Avance de los prototipos

Tablero de trabajo. Dice qué está hecho, qué sigue y cómo retomar si el trabajo se interrumpe a la mitad.
El porqué de cada decisión está en [BITACORA.md](BITACORA.md).

## Siguiente paso

> **Sprint 3 en curso** (autorizado por Joshua el 16-nov). Seguir la tabla del sprint 3 en orden: la primera tarea
> que no esté en «Hecho» es la que sigue.

## Cómo retomar un trabajo interrumpido

1. `git status` y `git log --oneline -5` en la rama `prototipos`: lo commiteado está verificado; lo que
   aparezca sin commitear es la tarea que quedó a medias.
2. Leer «Siguiente paso» y la tabla del sprint en curso: la tarea «En curso» es la que hay que terminar.
3. Correr las pruebas rápidas (abajo). Si pasan, lo que hay en el árbol sirve: se completa, se verifica y
   se hace el commit. Si fallan y no se entiende por qué, se descarta solo esa tarea
   (`git stash` o `git restore`) y se vuelve a empezar: cada tarea es de una historia o menos.
4. Al cerrar un sprint se escribe su resumen en PDF (`python entregas/generar_resumen.py N`, dentro de la imagen de
   Docker; el texto va en `sprint_N/resumen_contenido.html` y sus datos en `resumen_datos.json`).
5. Al terminar una tarea, en el mismo commit: marcarla aquí como «Hecho» con su commit, mover «Siguiente
   paso» y actualizar la bitácora si hubo una decisión.

Estados de una tarea: **Pendiente**, **En curso**, **Por verificar** (construida, falta revisarla y
commitearla), **Hecho**.

## Cómo correr las pruebas

Desde Windows, con Docker dentro de WSL:

```bash
wsl -e bash -lc "cd /mnt/c/Users/josh/Documents/GitHub/FEPI/sistema && docker compose --profile pruebas run --rm pruebas"
```

Ese comando corre todo en paralelo (unos 5 minutos con 432 pruebas: primero las rápidas con 4 procesos y luego los
recorridos de navegador con 3). Durante el trabajo se usan las formas cortas, agregando al final:

| Para | Se agrega | Tarda |
| --- | --- | --- |
| Pruebas rápidas, sin navegador | `pytest -m "not navegador" -n 4` | ~3 min |
| Con los PDF reales en todas (antes de cada entrega) | `-e PDF_REAL=1` antes de `pruebas` | ~8 min |
| En serie, para depurar | `-e PRUEBAS_N=0 -e PRUEBAS_N_NAVEGADOR=0` antes de `pruebas`, o `-n 0` | ~9 min |
| Una sola historia | `pytest pruebas/test_hu_2_3.py` | ~20 s |
| Guardar capturas | `-e CAPTURAS=1` antes de `pruebas` | — |

Si cambió el código, el sitio se levanta con `docker compose up --build`: sin `--build` corre la imagen
anterior. La Calculadora se prueba aparte, con el entorno de Python del repositorio:
`pytest pruebas/calculadora`.

## Sprint 1 · Recepción y dictamen (M1, M2; M7.1) — terminado, en revisión

| Tarea | Qué | Estado | Commit |
| --- | --- | --- | --- |
| HU-7.1 | Masa forestal por año: sitio por archivos y evolución anual | Hecho | `d8b71ff` |
| Base | Docker Compose, núcleo común, reglas de Capturando Carbono | Hecho | `6f6a11f` |
| HU-1.1 | Registro de la solicitud con acuse | Hecho | `6ee4927` |
| HU-1.2 | Revisión de requisitos y envío a la Dirección | Hecho | `2c92b2c` |
| HU-1.3 | Polígono del predio levantado en campo | Hecho | `15e7511` |
| HU-1.4 | Validación y aviso de faltantes | Hecho | `26bb9b7` |
| Base M2 | Estados nuevos, bandejas, sesiones del Comité | Hecho | `50269bf` |
| HU-2.1 | Dictamen técnico y listado preliminar | Hecho | `3417f37` |
| HU-2.2 | Dictamen jurídico y Listado de Incumplidas | Hecho | `160ae8b` |
| HU-2.3 | Sesión de aprobación con acta | Hecho | `40ac657` |
| HU-2.4 | Sesiones de seguimiento con acuerdos | Hecho | `a27e107` |
| Revisión | Diagrama del modelo de datos y prueba del recorrido completo | Hecho | `68dc445` |
| Revisión | Bitácora de decisiones y este tablero | Hecho | `9b4a013` |

Pruebas al cierre: 128 del sistema (121 antes de los ajustes; la última es el recorrido completo por la interfaz) y 15 de la Calculadora, todas en verde. Capturas en
`sprint_1/capturas/` (49).

### Ajustes tras la revisión del 14-nov

| Tarea | Qué (problema en la bitácora) | Estado | Commit |
| --- | --- | --- | --- |
| A-1 | Lista de verificación del dictamen técnico sin marcar por omisión (P-01) | Hecho | `045feb7` |
| A-2 | El acta no se registra antes de la fecha de la sesión (P-02) | Hecho | `045feb7` |
| A-3 | «Ajustado» solo en la fila que el Comité movió (P-04) | Hecho | `045feb7` |
| A-4 | Montos con separador de miles (P-05) | Hecho | `045feb7` |
| A-5 | Capturas solo cuando se piden (P-06) | Hecho | `045feb7` |
| A-6 | Pruebas rápidas separadas de las de navegador (P-07) | Hecho | `045feb7` |
| A-7 | Recorrido completo por la interfaz, con una sola solicitud y cambio de usuario en cada relevo (P-09) | Hecho | `450a5ac` |
| Resumen | Resumen en PDF del sprint 1 (`sprint_1/Resumen_sprint_1.pdf`) | Hecho | `0598b95` |

## Sprint 2 · Contrato y pagos (M3, M5; M7.2 y M7.3) — terminado el 16-nov

Orden de trabajo. Cada renglón es una tarea que se puede hacer, verificar y commitear por separado; las
que dicen «en paralelo» no tocan los mismos archivos.

| Tarea | Qué | Depende de | Estado | Commit |
| --- | --- | --- | --- | --- |
| S2-00 | Subir la rama `prototipos` con el sprint 1 al repositorio remoto | Indicación de Joshua | Hecho | 14-nov, 17 commits |
| S2-01a | Reglas de Plantaciones Sustentables desde las ROP (`reglas/PS.json`) | — (en paralelo) | Hecho | `c979a30` |
| S2-01b | Reglas de Restauración Hidrológico-Forestal (`reglas/RHF.json`) | — (en paralelo) | Hecho | `ef3e66d` |
| S2-01c | Reglas de PSAHEM (`reglas/PSA.json`) | — (en paralelo) | Hecho | `a8dad5c` |
| S2-02 | Base de M3 y M5: notificaciones en el núcleo, montos y ministraciones, evento que arranca cada plazo, estados nuevos | S2-01 | Hecho | `47cc5ee` a `2fa15a7` (7 commits) |
| S2-03 | HU-3.1 Publicación y notificaciones | S2-02 | Hecho | `4fbf940` |
| S2-04 | HU-3.2 Elaboración del contrato (modelo validado por Jurídico) | S2-02 | Hecho | `e9a1f2c` |
| S2-05 | HU-3.3 Firma del contrato | S2-04 | Hecho | `d877a63` |
| S2-06 | HU-3.4 Entrega de planta (PS y RHF) | S2-05 | Hecho | `d5698c8` |
| S2-07 | HU-5.1 Solicitud de pago | S2-05 | Hecho | `82d2ed8` |
| S2-08 | HU-5.2 Pago de la ministración | S2-07 | Hecho | `abc03e0` |
| S2-09 | HU-5.3 Entrega de cheques (PSAHEM) | S2-08 | Hecho | `1af1d0a` |
| S2-10 | HU-7.2 Histograma del balance entre dos años | — (en paralelo) | Hecho | `9254478` |
| S2-11 | HU-7.3 Pérdida por incendios: lo que falte contra sus criterios | S2-10 | Hecho | `5bfa706` |
| S2-12 | Investigación de los datos del INFyS para HU-7.5 | — (en paralelo) | Hecho | `5f899fb` |
| S2-13a | Cierre técnico: acortar la batería (P-20), menú por módulo (P-21), modelo de datos y README al día | S2-09 | Hecho | `88d9f93`, `f24d627`, `c94a5c9` |
| S2-13b | Tropiezos de interfaz del recorrido del sprint 2 (P-23 a P-31) | S2-14 | Hecho | `0871a66` |
| S2-13c | Pruebas en paralelo (W-17) | S2-13b | Hecho | `6753f8c` |
| S2-13 | Datos de prueba: generador con semilla y calendario simulado | S2-09 | Hecho | `f1addff`, `8e95e4c`, `d9bbf7d` |
| S2-14 | Recorrido completo del sprint 2 (servicios y navegador), batería completa y entrega | Todo lo anterior | Hecho | `62b5ae4` (servicios), `38e7e6a` (interfaz) |
| S2-15 | Resumen en PDF del sprint 2 (`sprint_2/Resumen_sprint_2.pdf`) | S2-14 | Hecho | `5849d57` |

Pruebas al cierre: 432 del sistema (corridas con todos los documentos PDF reales) y 43 de la Calculadora, todas en
verde. Sitio levantado con una base nueva y revisado en el navegador. Resumen: `sprint_2/Resumen_sprint_2.pdf`.

## Sprint 3 · Ejecución, seguimiento y cierre (M4, M6; M7.4 y M7.5) — iniciado el 16-nov

Joshua autorizó iniciarlo el 16-nov al cerrar el sprint 2. Cada renglón es una tarea que se hace, se verifica y se
registra por separado; las que dicen «en paralelo» no tocan los mismos archivos ni usan Docker.

| Tarea | Qué | Depende de | Estado | Commit |
| --- | --- | --- | --- | --- |
| S3-00 | Subir la rama `prototipos` con el sprint 2 al repositorio remoto | — | Hecho | 16-nov |
| S3-01a | Reglas de Manejo Forestal Sustentable desde las ROP (`reglas/MFS.json`) | — (en paralelo) | Hecho | `1a192d4` |
| S3-01b | Reglas de Guardabosques desde las ROP y su convocatoria (`reglas/PEG.json`) | — (en paralelo) | Hecho | `eb0c4dd` (con las pruebas ajustadas) |
| S3-02 | Base de M4 y M6: apps `ejecucion` y `seguimiento`, estados nuevos, cuentas del portal externo, plazos, y recepción a pagos funcionando con MFS y Guardabosques | S3-01 | Hecho | `5a67840` a `99fe534` (5 commits) |
| S3-03 | HU-4.1 Envío de comprobaciones, en el portal o en la Delegación | S3-02 | Hecho | `9b3149c` |
| S3-04 | HU-4.2 Verificación en campo y conexión con la segunda ministración | S3-03 | Hecho | `030688c` |
| S3-05 | HU-4.3 Evaluación de reportes de Guardabosques | S3-04 | Hecho | `133dc4a` (y `d856dc3`, límite de tiempo por prueba) |
| S3-06 | HU-6.1 Lista de espera y sustituciones | S3-05 | Hecho | `80c4b9d` |
| S3-07 | HU-6.2 Incumplimientos y reintegros | S3-06 | Hecho | `1e0c644` |
| S3-08 | HU-6.3 Cierre del ejercicio y padrón | S3-07 | Hecho | `f7e8687` |
| S3-09 | HU-7.4 Uso del suelo al que pasó el terreno perdido (Calculadora) | — (en paralelo) | Hecho | `545b692` |
| S3-10 | HU-7.5 Especies por municipio (Calculadora) | S3-09 | Hecho | `807186c` |
| S3-11 | Cierre técnico: recorrido de un programa completo, de la solicitud al padrón, por servicios (seis programas) y por la interfaz; tropiezos; textos de la interfaz sin la palabra «sprint»; modelo de datos y README | S3-08 | Hecho | `e68c3c2` a `b147b95` (5 commits) |
| S3-12 | Verificación final: batería con PDF reales, Calculadora, sitio con base nueva | S3-10, S3-11 | Hecho | batería con PDF reales 564 + 40 (1 omitida a propósito); Calculadora 77; base nueva y navegador |
| S3-13 | Resumen en PDF del sprint 3 (`sprint_3/Resumen_sprint_3.pdf`) | S3-12 | En curso |  |
| S3-14 | Entrega a Joshua para revisión (sin subir hasta que lo indique) | S3-13 | Pendiente | |
