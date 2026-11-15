# Avance de los prototipos

Tablero de trabajo. Dice qué está hecho, qué sigue y cómo retomar si el trabajo se interrumpe a la mitad.
El porqué de cada decisión está en [BITACORA.md](BITACORA.md).

## Siguiente paso

> **Sprint 2 en curso** (autorizado por Joshua el 14-nov). Seguir la tabla del sprint 2 en orden: la
> primera tarea que no esté en «Hecho» es la que sigue.

## Cómo retomar un trabajo interrumpido

1. `git status` y `git log --oneline -5` en la rama `prototipos`: lo commiteado está verificado; lo que
   aparezca sin commitear es la tarea que quedó a medias.
2. Leer «Siguiente paso» y la tabla del sprint en curso: la tarea «En curso» es la que hay que terminar.
3. Correr las pruebas rápidas (abajo). Si pasan, lo que hay en el árbol sirve: se completa, se verifica y
   se hace el commit. Si fallan y no se entiende por qué, se descarta solo esa tarea
   (`git stash` o `git restore`) y se vuelve a empezar: cada tarea es de una historia o menos.
4. Al terminar una tarea, en el mismo commit: marcarla aquí como «Hecho» con su commit, mover «Siguiente
   paso» y actualizar la bitácora si hubo una decisión.

Estados de una tarea: **Pendiente**, **En curso**, **Por verificar** (construida, falta revisarla y
commitearla), **Hecho**.

## Cómo correr las pruebas

Desde Windows, con Docker dentro de WSL:

```bash
wsl -e bash -lc "cd /mnt/c/Users/josh/Documents/GitHub/FEPI/sistema && docker compose --profile pruebas run --rm pruebas"
```

Ese comando corre todo (unos 2 minutos). Durante el trabajo se usan las formas cortas, agregando al final:

| Para | Se agrega | Tarda |
| --- | --- | --- |
| Pruebas rápidas, sin navegador | `pytest -m "not navegador"` | ~1 min |
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

## Sprint 2 · Contrato y pagos (M3, M5; M7.2 y M7.3) — en curso desde el 14-nov

Orden de trabajo. Cada renglón es una tarea que se puede hacer, verificar y commitear por separado; las
que dicen «en paralelo» no tocan los mismos archivos.

| Tarea | Qué | Depende de | Estado | Commit |
| --- | --- | --- | --- | --- |
| S2-00 | Subir la rama `prototipos` con el sprint 1 al repositorio remoto | Indicación de Joshua | Hecho | 14-nov, 17 commits |
| S2-01a | Reglas de Plantaciones Sustentables desde las ROP (`reglas/PS.json`) | — (en paralelo) | Hecho | `c979a30` |
| S2-01b | Reglas de Restauración Hidrológico-Forestal (`reglas/RHF.json`) | — (en paralelo) | Hecho | `ef3e66d` |
| S2-01c | Reglas de PSAHEM (`reglas/PSA.json`) | — (en paralelo) | Hecho | `a8dad5c` |
| S2-02 | Base de M3 y M5: notificaciones en el núcleo, montos y ministraciones, evento que arranca cada plazo, estados nuevos | S2-01 | En curso | |
| S2-03 | HU-3.1 Publicación y notificaciones | S2-02 | Pendiente | |
| S2-04 | HU-3.2 Elaboración del contrato (modelo validado por Jurídico) | S2-02 | Pendiente | |
| S2-05 | HU-3.3 Firma del contrato | S2-04 | Pendiente | |
| S2-06 | HU-3.4 Entrega de planta (PS y RHF) | S2-05 | Pendiente | |
| S2-07 | HU-5.1 Solicitud de pago | S2-05 | Pendiente | |
| S2-08 | HU-5.2 Pago de la ministración | S2-07 | Pendiente | |
| S2-09 | HU-5.3 Entrega de cheques (PSAHEM) | S2-08 | Pendiente | |
| S2-10 | HU-7.2 Histograma del balance entre dos años | — (en paralelo) | Hecho | `9254478` |
| S2-11 | HU-7.3 Pérdida por incendios: lo que falte contra sus criterios | S2-10 | Hecho | `5bfa706` |
| S2-12 | Investigación de los datos del INFyS para HU-7.5 | — (en paralelo) | Hecho | `5f899fb` |
| S2-13 | Datos de prueba: generador con semilla y calendario simulado | S2-09 | Pendiente | |
| S2-14 | Recorrido completo del sprint 2 (servicios y navegador), batería completa y entrega | Todo lo anterior | Pendiente | |

## Sprint 3 · Ejecución, seguimiento y cierre (M4, M6; M7.4 y M7.5) — sin empezar

Se detalla al cerrar el sprint 2. Ya se sabe que empieza por subir el sprint 2 al repositorio (S3-00) y
por las reglas de MFS y Guardabosques (S3-01), y que incluye HU-4.1 a 4.3, HU-6.1 a 6.3, HU-7.4, HU-7.5,
el portal externo, los plazos y avisos, y el recorrido de un programa completo, de la solicitud al padrón.
