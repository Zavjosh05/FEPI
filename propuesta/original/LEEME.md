# Originales de la propuesta

Copias sin cambios de la propuesta tal como se entregó (12-13 de noviembre de 2026), para referencia:

| Archivo | Qué es |
| --- | --- |
| `CONTEXTO.md` | Contexto de la propuesta |
| `datos/modelo.json` | Módulos, funciones e historias |
| `docs/Propuesta_solucion_modular_PROBOSQUE_2026.pdf` | La propuesta |
| `docs/Matriz_funciones_historias_PROBOSQUE.xlsx` | Matriz de necesidades, funciones e historias |

No se editan. La versión vigente está en la carpeta de arriba. Los cambios están en `../CAMBIOS_HU.md`.
`herramientas/actualizar_propuesta.py` rehace el PDF y la matriz siempre a partir de estas copias.

Al incorporar la propuesta al repositorio (18-nov-2026) se hicieron estos ajustes de redacción, sin cambiar el
contenido técnico:

- El archivo de contexto se renombró a `CONTEXTO.md`. En él, dos frases sobre quién desarrolla dicen ahora «la sesión
  de desarrollo», y la ubicación del PDF de las Reglas dice «se conserva aparte».
- En el PDF de la propuesta se rehicieron las páginas 4 y 6 con el mismo contenido y diseño
  (`herramientas/paginas_4_y_6.py`). Cambian dos frases sobre cómo se desarrolla:
  - el criterio de factibilidad «que se pueda construir y probar por completo con código»;
  - el primer riesgo, que ahora es «Revisión de lo que se desarrolla».

El resto es el original.
