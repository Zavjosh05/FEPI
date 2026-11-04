# Validación contra Hansen Global Forest Change (CF-DEV-09)

Corrida del 4 de noviembre de 2026 con `src/validar_hansen.py` (versión 0.7.0). Compara la pérdida
de bosque del prototipo con la de Hansen GFC **v1.13** en el Estado de México, para 2023 → 2024 y
2024 → 2025. Usa la serie encadenada `resultados/edomex_serie_2023_2025/` y la zona forestal
ampliada `^(B|S|M|VSA/)`. La validación anterior (zona `^(B|VSA/)`, corridas directas, 3-nov-2026)
y la muestra de puntos están en `resultados/anteriores_0.5/validacion_hansen/`.

> **Hansen no es la verdad de campo.** Es otro mapa hecho con satélite (Landsat, 30 m) y usa otra
> definición de pérdida. Aquí sirve para ver dónde coinciden las dos fuentes y dónde no. En cada
> desacuerdo, quién tiene razón solo lo dicen la fotointerpretación y las visitas de campo, que
> son la otra parte de CF-DEV-09 y todavía no existen. Precisión y exhaustividad se calculan
> "tomando Hansen como referencia", no como exactitud del prototipo.

## Contenido

| Archivo | Qué es |
|---|---|
| `validacion_estatal.csv` | Una fila por periodo con los totales del estado |
| `validacion_municipios.csv` | Una fila por periodo y municipio (125 × 2) |
| `coincidencia_2023_2024.tif`, `coincidencia_2024_2025.tif` | uint8 en la malla del prototipo (10 m, EPSG:32614): 0 fuera de la zona forestal, 1 zona sin pérdida, 2 pérdida en ambos, 3 solo prototipo, 4 solo Hansen |
| `mapa_coincidencia.png` | Arriba, el estado con coincidencia por celda de 250 m. Abajo, un acercamiento de 8 km a 10 m |
| `corrida.json` | Parámetros de la corrida |

La muestra para fotointerpretar (`muestra_puntos_2023_2024.csv`, `estratos_2023_2024.csv`) no se
rehízo: sigue en `resultados/anteriores_0.5/validacion_hansen/` (ver abajo).

Los recortes de Hansen quedaron en `datos/edomex/hansen/`, que git ignora: `lossyear` pesa 0.6 MB
y `treecover2000` 21 MB.

## Comando

Desde la raíz del repositorio, con las capas de `datos/edomex/`:

```bash
python src/validar_hansen.py
```

Los valores por defecto son los de esta corrida. Para comparar otro periodo:
`--comparacion resultados/edomex_serie_2023_2025/cambio_2023_2025.tif 2024,2025`. Para rehacer solo el
PNG: `--solo-mapa`.

**Tiempo:** la primera vez tarda unos 2 min. Lee ~100 MB de internet en 44 s y la comparación
toma 30–50 s. Después reutiliza los recortes: esta corrida tardó 43 s.

## Fuente: Hansen GFC v1.13

- **Versión:** `GFC-2025-v1.13`, la más reciente (marzo de 2026). Trae pérdida de 2001 a 2025, así
  que alcanza para los dos periodos. No hay v1.14.
- **Capas usadas:** `lossyear` (0 = sin pérdida; 1–25 = año 2001–2025) y `treecover2000` (% de copa
  en 2000).
- **Archivos:** `https://storage.googleapis.com/earthenginepartners-hansen/GFC-2025-v1.13/`. Se usan
  4 teselas de 10°: 20N_100W, 20N_110W, 30N_100W y 30N_110W.
- **Lectura:** el estado cae en el borde de las 4 teselas. Los archivos no están teselados por
  dentro (una franja por fila), así que se leen por ventanas de filas con `/vsicurl`. Así se
  bajan ~100 MB (estimado por la fracción de filas) en lugar de los 1,118 MB de las 8 teselas
  completas.
- **Definición de pérdida:** "stand-replacement disturbance", es decir, el paso de bosque a no
  bosque, con árboles de más de 5 m.
- **Aviso de los autores:** el mapa es un indicador relativo. No debe usarse el conteo de píxeles
  para estimar superficies definitivas; para eso hay que usarlo como estrato de un muestreo
  probabilístico. Además, el año de pérdida puede tener inconsistencias entre años.

**Licencia:** [Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/).
Se puede copiar, redistribuir y transformar para cualquier fin, incluso comercial, dando crédito,
enlazando la licencia e indicando los cambios. **Cambios hechos aquí:** recorte al estado,
remuestreo a la malla UTM de 10 m del prototipo y reclasificación en categorías de coincidencia.

- **Crédito al mostrar los datos:** Source: Hansen/UMD/Google/USGS/NASA
- **Cita:**

  > Hansen, M. C., P. V. Potapov, R. Moore, M. Hancher, S. A. Turubanova, A. Tyukavina, D. Thau,
  > S. V. Stehman, S. J. Goetz, T. R. Loveland, A. Kommareddy, A. Egorov, L. Chini, C. O. Justice,
  > and J. R. G. Townshend. 2013. High-Resolution Global Maps of 21st-Century Forest Cover Change.
  > Science 342 (15 November): 850–53. Data available on-line from:
  > https://glad.earthengine.app/view/global-forest-change.

## Método

1. **Malla común: Hansen se lleva a la malla de 10 m del prototipo, no al revés.** Se usa vecino
   más cercano: cada píxel de 10 m toma el valor del píxel de Hansen (~26 × 28 m) que contiene su
   centro. Hay tres razones:
   - Las hectáreas del prototipo quedan idénticas a las de su balance: 10,147.35 ha en
     2023 → 2024 (711 por incendio y 9,436 otras) y 6,080.30 ha en 2024 → 2025, igual que los
     `balance_*.csv` de la serie.
   - La zona forestal y los municipios se rasterizan una sola vez, en la misma malla que usó el
     prototipo. Ningún píxel del prototipo con bosque cae fuera de la zona (`proto_fuera_zona_ha` = 0).
   - Llevar el prototipo a 30 m obligaría a elegir una regla de agregación (¿pérdida si ≥ 1, 5 o
     9 subpíxeles?). Esa regla cambiaría sus hectáreas, y cada opción favorecería a una de las dos
     fuentes.

   El vecino más cercano conserva la superficie de Hansen en promedio. Dentro del estado, sin filtro
   de zona, Hansen da 2,833.98 ha de pérdida 2024 en la malla de 10 m contra 2,837.17 ha contadas en
   su malla original con el área de cada píxel según su latitud (−0.1 %). Para 2025, 1,942.84 contra
   1,946.29.
2. **Dominio:** la zona forestal INEGI Serie VII con las claves `^(B|S|M|VSA/)`, las mismas de la
   serie (512,576 ha). Para repetir la validación anterior: `--clases-forestales "^(B|VSA/)"` con
   los rásters de `anteriores_0.5`.
3. **Qué se compara:**
   - Prototipo: las clases 2 y 3 del ráster de cambio.
   - Hansen: `lossyear` = 24 para 2023 → 2024 y = 25 para 2024 → 2025.
   - El periodo del prototipo va de nov-dic a nov-dic. El de Hansen es el año calendario, medido
     con compuestos de la temporada de crecimiento. Por eso no coinciden del todo, y se reporta
     aparte cuánta pérdida del prototipo pone Hansen un año antes o un año después.
4. **Coincidencia exacta:** ambos = P ∩ H; solo prototipo = P − H; solo Hansen = H − P.
   - Precisión = ambos / P: qué parte de la pérdida del prototipo también marca Hansen.
   - Exhaustividad = ambos / H: qué parte de la pérdida de Hansen encuentra el prototipo.
5. **Coincidencia con tolerancia de 30 m.** Un píxel de pérdida de una fuente cuenta como
   coincidente si la otra tiene pérdida a ≤ 3 píxeles (30 m) en filas y columnas. Esto absorbe el
   desfase de posición entre Landsat y Sentinel-2 y las diferencias de borde por el tamaño de píxel.

## Resultados

| | 2023 → 2024 (Hansen 2024) | 2024 → 2025 (Hansen 2025) |
|---|---|---|
| Pérdida del prototipo | 10,147 ha (711 incendio + 9,436 otra) | 6,080 ha (sin polígonos de incendio de 2025) |
| Pérdida de Hansen en la zona forestal | 1,890 ha | 1,342 ha |
| … de ella, en bosque base del prototipo | 1,787 ha (95 %) | 1,192 ha (89 %) |
| … con copa 2000 ≥ 30 % | 1,551 ha | 1,046 ha |
| Ambos | 583 ha | 156 ha |
| Solo prototipo | 9,564 ha | 5,924 ha |
| Solo Hansen | 1,307 ha | 1,186 ha |
| **Precisión** (exacta / con 30 m) | **6 % / 8 %** | **3 % / 4 %** |
| **Exhaustividad** (exacta / con 30 m) | **31 % / 69 %** | **12 % / 36 %** |
| Precisión de la pérdida por incendio | 40 % | — |
| Precisión de las otras pérdidas | 3 % | 3 % |
| Pérdida del prototipo que Hansen pone el año anterior o el siguiente | 56 + 133 ha | 25 ha (Hansen aún no trae 2026) |

### Contra la validación anterior

| | Zona `^(B\|VSA/)`, corridas directas | Zona `^(B\|S\|M\|VSA/)`, serie |
|---|---|---|
| Pérdida del prototipo 2023 → 2024 | 8,496 ha | 10,147 |
| Pérdida del prototipo 2024 → 2025 | 3,336 ha | 6,080 |
| Precisión / exhaustividad 2023 → 2024 | 7 % / 31 % | 6 % / 31 % |
| Precisión / exhaustividad 2024 → 2025 | 5 % / 12 % | 3 % / 12 % |

- **Hansen casi no cambia:** con la zona ampliada solo agrega 7 ha en 2024 y 2 en 2025, y la
  exhaustividad queda igual.
- **El prototipo sí sube**, sobre todo en 2024 → 2025 (+2,744 ha). Casi todo viene de la selva baja
  caducifolia (1,586 y 1,866 ha de la clave SBC) y del matorral (951 ha de MC en 2024 → 2025), que
  Hansen no marca. Por eso baja la precisión.
- En 2024 → 2025 también influye el encadenamiento: el año base ahora es el bosque encadenado de
  2024 y no el de solo el umbral (ver el LEEME de la serie).

### Lectura

- **El prototipo marca 5.4 veces más pérdida que Hansen en 2023 → 2024 y 4.5 veces en
  2024 → 2025.** Más del 90 % de su pérdida no aparece en Hansen, también con 30 m de tolerancia.
  Mover un año solo agrega 189 ha. Casi todo es "otra pérdida": su precisión es de 3 %, contra
  40 % en la pérdida por incendio. Esto refuerza que las "otras pérdidas" **están por verificar**.
  Hansen solo registra remoción de copa (tala, incendio de copa, desmonte). El prototipo, en
  cambio, también marca cualquier caída de NDVI que cruce el umbral: copa raleada, sequía o caída
  de hojas en nov-dic, plaga, escarcha o nieve.
- **La selva baja caducifolia es el mayor desacuerdo.** Luvianos tiene 1,863 ha del prototipo
  contra 169 de Hansen en 2023 → 2024 (precisión 1 %) y 1,710 contra 120 en 2024 → 2025 (0.1 %).
  Otzoloapan (315 y 610 ha del prototipo, precisión < 1 %) y Santo Tomás (460 y 221 ha, 0.1 % y
  0 %) son iguales. Apunta a la caída de hojas en nov-dic, no a pérdida real.
- **Las laderas de los volcanes siguen igual.** Atlautla tiene 493 ha del prototipo contra 0.6 de
  Hansen, Amecameca 286 contra 8 y Tlalmanalco 167 contra 37. Ya se sospechaban en el piloto por
  nieve o escarcha. Con la selva, son los primeros lugares que conviene fotointerpretar.
- **Donde hay un evento grande, las dos fuentes lo ven.** En San Simón de Guerrero y Temascaltepec
  (el acercamiento del mapa) coinciden las mismas manchas de 2024: San Simón tiene precisión de 54 %
  y exhaustividad de 55 %. Sin embargo, el prototipo lo clasifica como "otra pérdida" porque no hay
  un polígono CONAFOR que lo cubra. Es el mejor candidato para verificar en campo qué pasó ahí.
- **La exhaustividad sube de 31 % a 69 % con 30 m de tolerancia.** El prototipo sí encuentra la
  mayoría de los lugares donde Hansen marca pérdida, pero no los mismos píxeles: los bordes
  difieren y el prototipo deja huecos dentro de las manchas de Hansen, porque su regla pide que el
  NDVI baje 0.10 y cruce el umbral en el mismo píxel. El 5 % de la pérdida de Hansen que cae fuera
  del bosque base del prototipo indica que la diferencia no viene de la definición de bosque.
- **2024 → 2025 coincide menos.** Parte de la pérdida de Hansen 2025 rodea las manchas de 2024.
  Puede ser mortalidad tardía después de un incendio o tala que siguió; el prototipo ya no la
  cuenta porque esos píxeles dejaron de ser bosque en 2024 o porque la caída de NDVI no llegó a
  0.10. Para 2025 no hay polígonos de incendio, así que no se puede separar lo que fue fuego.
- **Esto no dice qué fuente acierta.** Una precisión baja puede venir de falsas pérdidas del
  prototipo o de pérdidas reales que Hansen no registra porque no remueven la copa completa. Una
  exhaustividad baja puede venir de pérdidas que el prototipo no ve o de errores de Hansen.
  Resolverlo requiere la muestra fotointerpretada.

### Municipios

`validacion_municipios.csv` trae todas las columnas por municipio. Los que tienen más pérdida de
Hansen en 2023 → 2024 son San Simón de Guerrero (230 ha), Jilotzingo (176), Temascaltepec (176),
Luvianos (169) y Tejupilco (133). Los que tienen más pérdida del prototipo son Luvianos (1,863),
Tlatlaya (799), Temascaltepec (553), Atlautla (493), Ocuilan (469) y Santo Tomás (460).

## Columnas de los CSV

Todas las superficies están en hectáreas, contadas en la malla de 10 m.

**Superficies:**

| Columna | Qué es |
|---|---|
| `zona_forestal_ha` | Superficie de la zona forestal |
| `bosque_base_proto_ha` | Bosque del año base según el prototipo (clases 1–3) |
| `proto_perdida_ha`, `proto_perdida_incendio_ha`, `proto_otra_perdida_ha` | Pérdida del prototipo: total, clase 2 y clase 3 |
| `hansen_perdida_ha` | `lossyear` en los años pedidos, dentro de la zona forestal |
| `hansen_en_bosque_proto_ha` | Lo mismo, pero solo dentro del bosque base del prototipo |
| `hansen_perdida_tc_ha` | Lo mismo con `treecover2000` ≥ 30 % |
| `hansen_sin_zona_ha` | Pérdida de Hansen en todo el municipio o estado, sin filtro de zona |
| `hansen_sin_zona_malla_original_ha` | Solo en el estatal: lo mismo contado en la malla de Hansen, como revisión del remuestreo |

**Coincidencia:**

| Columna | Qué es |
|---|---|
| `ambos_ha`, `ambos_incendio_ha`, `ambos_otra_ha` | Píxeles que marcan las dos fuentes (total y por clase del prototipo) |
| `solo_proto_ha`, `solo_hansen_ha` | Píxeles que marca una sola fuente |
| `proto_cerca_hansen_ha`, `hansen_cerca_proto_ha` | Pérdida de una fuente con pérdida de la otra a ≤ 30 m |
| `proto_hansen_anio_ant_ha`, `proto_hansen_anio_sig_ha` | Pérdida del prototipo que Hansen pone el año anterior o el siguiente |
| `proto_fuera_zona_ha` | Revisión: debe ser 0 |

**Proporciones:**

| Columna | Qué es |
|---|---|
| `precision`, `exhaustividad`, `f1` | Coincidencia exacta, con Hansen como referencia |
| `precision_tol`, `exhaustividad_tol` | Lo mismo con la tolerancia de 30 m |
| `exhaustividad_en_bosque_proto` | Ambos ÷ Hansen dentro del bosque base del prototipo |
| `precision_incendio`, `precision_otra` | Precisión por clase del prototipo |

Las proporciones quedan vacías cuando el divisor es 0.

## Muestra para fotointerpretar (pendiente de etiquetar)

La muestra de 105 puntos de `src/muestra_puntos.py` (semilla 2026, 15 por estrato) se sorteó con
la validación anterior y sigue en `resultados/anteriores_0.5/validacion_hansen/`, con su LEEME.
Sus estratos salen del cambio 2023 → 2024 dentro de la zona `^(B|VSA/)`, que la serie reproduce
idéntico, así que sigue valiendo para esa zona. No cubre la selva baja caducifolia ni el matorral
(SBC, MC, MDR): para validarlos hay que sortear puntos nuevos con `src/muestra_puntos.py`.

- **Nadie ha etiquetado los puntos.** `clase` se llena con 1 (bosque) o 0 (no bosque) en nov-dic
  2024; hay que borrar los que no se puedan interpretar.
- `calibrar` arma el compuesto NDVI de toda la `--aoi` de una sola vez y con el estado entero no
  cabe en memoria: hay que calibrar por zonas más chicas.
