# Corridas estatales anteriores (zona `^(B|VSA/)`)

Corridas del 14 de octubre al 3 de noviembre de 2026, con la zona forestal anterior
(`^(B|VSA/)`, 484,695 ha), sin clasificador del destino y, en noviembre-diciembre, con
comparaciones directas (cada par de años por separado). Se guardan para repetir o comparar
resultados; cada carpeta conserva su LEEME con el comando y la ruta de salida originales.

| Carpeta | Qué es | La reemplaza |
|---|---|---|
| `edomex_2023_2024/` | Primer balance estatal | `edomex_serie_2023_2025/` (comparación 2023_2024) |
| `edomex_2024_2025/` | Balance 2024 → 2025 directo | `edomex_serie_2023_2025/` (2024_2025) |
| `edomex_2023_2025/` | Balance 2023 → 2025 directo | `edomex_serie_2023_2025/` (2023_2025) |
| `edomex_2025_2026_sepoct/` | Preliminar septiembre-octubre | `edomex_2025_2026_sepoct/` |
| `validacion_hansen/` | Validación contra Hansen y muestra de 105 puntos sin etiquetar | `validacion_hansen/` (la muestra sigue solo aquí) |

**Qué cambió:**

- Dentro de la zona anterior, la comparación 2023 → 2024 de la serie es idéntica a
  `edomex_2023_2024/`.
- 2024 → 2025 y 2023 → 2025 cambian porque la serie encadena el bosque año con año. Ver
  `resultados/edomex_serie_2023_2025/LEEME.md`.

Para repetir estas corridas con el código actual: `--clases-forestales "^(B|VSA/)"
--no-clasificar-destino` y `correr` por cada par.
