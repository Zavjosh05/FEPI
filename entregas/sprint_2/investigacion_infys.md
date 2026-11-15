# Datos de especie del INFyS para el Estado de México

Fecha de la consulta: 14-nov-2026. Se distingue lo **comprobado** (abrí la fuente) de lo **leído** (solo descrito) y de lo **no confirmado**.

## Respuesta corta

- **Actualización 15-nov-2026:** el SNMF sigue caído, pero los mismos archivos (estado por estado, 2015–2020 incluido) están en IDEFOR y se bajan directo; ver «Vías alternativas (15-nov-2026)» al final. Cobertura medida: 55 de los 125 municipios.
- **¿Se puede?** Sí, pero no como descarga abierta y directa. Los datos de arbolado con especie del INFyS 2015–2020 están en el catálogo de microdatos de la FAO, que remite al sitio del Sistema Nacional de Monitoreo Forestal (SNMF) y exige aceptar un descargo de responsabilidad y una declaración de confidencialidad (leído). No pude abrir la descarga ni ver las tablas, así que **no está confirmado** que traigan clave de municipio ni coordenadas.
- **Fuente recomendada:** microdatos del INFyS 2015–2020 (FAO, estudio 2620 / SNMF) para las especies, y la capa pública de conglomerados de IDEFOR (`infys_teoricas_cusv_svii_mgm_2023_wgs84`) para ubicar cada conglomerado en un municipio (`CVE_ENT`, `CVE_MUN`, `IdConglome`; coordenadas **teóricas**, no las reales de campo).
- **Qué falta:** (1) que una persona autorizada de PROBOSQUE acepte los términos y baje las tablas (no lo hice yo); (2) confirmar nombres de campos y si hay coordenadas reales; (3) que PROBOSQUE confirme si tiene el Inventario Estatal con especies.
- **Cobertura:** parcial por diseño. Solo ~42 % de los conglomerados se muestreó en 2015–2020. Muchos municipios quedarán «sin registros»; señalarlos, como pide la historia, es necesario.

## Fuentes

| Fuente | Enlace | Acceso | Formato / contenido | Ubicación | Licencia / términos | Verificación |
|---|---|---|---|---|---|---|
| Microdatos INFyS 2015–2020 (FAO) | https://microdata.fao.org/index.php/catalog/2620 (descarga: `/get-microdata`) | Datos en repositorio externo; pide aceptar descargo y declaración de confidencialidad | Exportación de SQL Server a .csv/Excel por pestañas; arbolado ≥ 7.5 cm con especie, altura, daños; anexos PDF de 3 a 55 MB | No dice si hay coordenadas reales o enmascaradas | Descargo (CONAFOR no responde por la interpretación); cita obligatoria; datos personales de contactos reservados (política PGCIEG) | Página y metadatos DDI leídos; archivos de datos **no vistos** |
| Sitio SNMF, «Datos del inventario» | https://snmf.cnf.gob.mx/datos-del-inventario/ | Es el destino que enlaza la FAO | Documentación y datos | Desconocida | Desconocida | **No abrió** (conexión rechazada) |
| IDEFOR, conglomerados (malla teórica) | https://idefor.cnf.gob.mx/layers/geonode%3Ainfys_teoricas_cusv_svii_mgm_2023_wgs84 | Libre (acceso «Anyone», sin registro) | 26,220 puntos; campos `X_WGS84, Y_WGS84, NOM_MUN, CVE_MUN, NOMGEO, CVE_ENT, StratoForm, DESCRIPCIO, CLAVE, IdConglome` | Coordenadas teóricas + municipio (Marco Geoestadístico 2023) | Titular CONAFOR; el portal muestra CC BY-NC-SA 2.5 México sin ligarla expresamente a la capa | Ficha de metadatos leída; WFS no probado (ver riesgos) |
| IDEFOR, capas modeladas (densidad, área basal) | p. ej. `geonode:densidad_4326` | Libre | Ráster por formación forestal | Sin especie | Igual | Solo descritas en buscador |
| Microdatos INFyS 2004–2009 (FAO) | https://microdata.fao.org/index.php/catalog/2655 | Mismo esquema (descargo + confidencialidad) | Ciclo 1 | Sin dato | Igual | Página leída |
| GBIF | https://api.gbif.org | Libre, API sin registro | Registros de herbario y observación | Coordenadas del colector; municipio a veces vacío | CC0 / CC BY / CC BY-NC según conjunto | **Comprobado**: 95,032 registros de plantas con coordenada en el estado (`stateProvince=México`); no son solo árboles |
| Inventario Forestal del Estado de México 2010 (PROBOSQUE) | Citado en una tesis UNAM | Desconocido | Centrado en cartografía | Desconocida | Desconocida | Solo referencia; no encontré el documento |

## Respuesta a la pregunta clave (ubicación)

- **Comprobado:** la capa pública de IDEFOR da, por conglomerado, clave de municipio y coordenadas **teóricas** (nodos de la malla, no el sitio medido). Para la historia basta con asignar cada conglomerado a un municipio.
- **Leído:** el centro puede reubicarse hasta 450 m (144 de 26,220 conglomerados, 0.55 %); el error al asignar municipio es mínimo salvo en límites.
- **No confirmado:** si la tabla de arbolado trae coordenadas reales, alteradas, solo `IdConglome` o clave de municipio. Inferencia (no comprobada): trae `Conglomerado` como llave, y entonces el cruce `IdConglome → CVE_MUN` con la capa de IDEFOR resuelve el municipio. Verificar con la tabla en mano.

## Cobertura esperada en el Estado de México (estimación mía, no dato publicado)

- Malla de 5 × 5 km en bosques templados: 1 conglomerado por 25 km². Con ~22,350 km² del estado y ~10,900 km² forestales, el orden de magnitud es de **cientos de conglomerados teóricos** (≈ 400–900 según cuántos caigan en zona forestal) y, con 42 % muestreado, **≈ 150–350 con datos de campo**; con decenas de árboles cada uno, miles de registros.
- Habrá cobertura en municipios forestales grandes y **ausencia en bastantes de los 125**, sobre todo pequeños, urbanos o agrícolas. El conteo exacto sale de cruzar la capa de IDEFOR con los 125 municipios (minutos, sin microdatos).

## Recomendación de implementación

1. Persona autorizada de PROBOSQUE baja los microdatos 2015–2020 aceptando los términos; guardar solo el extracto del estado 15 (pequeño). Registrar fecha de descarga y la cita exigida.
2. Bajar la capa de conglomerados de IDEFOR filtrada con `CVE_ENT='15'` y guardar `IdConglome → CVE_MUN`.
3. Unir el arbolado por `IdConglome`. Si trae coordenadas, usarlas solo para contrastar con el municipio.
4. Normalizar especie (nombre científico válido, sinonimias; la FAO reconoce errores de identificación) y conservar nombre común si existe.
5. Salidas: `especies_por_municipio.csv` (`cve_mun, municipio, especie, nombre_comun, genero, familia, n_registros, n_conglomerados, ciclo`) y `cobertura_municipios.csv` (`cve_mun, municipio, n_conglomerados_teoricos, n_con_datos, estado` = `con_registros` / `sin_registros`).
6. Interfaz: encabezado «INFyS 2015–2020; malla de 5 × 5 km; ~42 % de los conglomerados medidos». Municipio vacío: «Sin registros en el inventario» (no «sin especies»), distinguiendo sin conglomerado teórico frente a conglomerado no muestreado.
7. Si PROBOSQUE tiene el Inventario Estatal, usarlo como complemento con su año aparte. GBIF solo como capa opcional rotulada «colecciones», sin mezclarla con el INFyS.

## Riesgos y lo no confirmado

- **No abrí** `snmf.cnf.gob.mx` (conexión rechazada) ni la descarga de la FAO; no hice descarga de prueba porque exige aceptar términos, que no me corresponde. Tablas y campos: por confirmar.
- El `GetCapabilities` del WFS de IDEFOR respondió **503** (probado en esta sesión); no pude listar sus capas. La capa de conglomerados se verificó por su ficha de metadatos.
- Licencia de la capa y de los microdatos: confirmar que el uso en una herramienta institucional publicada es compatible (CC BY-NC-SA del portal, sin ligarse claramente a la capa).
- Sesgo: el 58 % sin muestrear y la inaccesibilidad por seguridad o permisos dejan huecos no aleatorios; sin registro no implica sin bosque.
- Errores de identificación taxonómica reconocidos por CONAFOR: presentar la lista como «registrada», no como inventario completo.

## Fuentes consultadas

- https://microdata.fao.org/index.php/catalog/2620 (y `/related-materials`, `/get-microdata`)
- https://microdata.fao.org/index.php/metadata/export/2620/ddi (descargado y leído, borrado)
- https://microdata.fao.org/index.php/catalog/2655
- https://idefor.cnf.gob.mx/layers/geonode%3Ainfys_teoricas_cusv_svii_mgm_2023_wgs84/layer_info_metadata
- https://api.gbif.org/v1/occurrence/search (conteo)

## Vías alternativas (15-nov-2026)

**Resultado:** sí hay una descarga directa y abierta, y no pasa por el SNMF. La página «Datos del inventario» del SNMF enlaza archivos que están alojados en **IDEFOR**, y IDEFOR sigue respondiendo. Se bajó y se midió el archivo del Estado de México 2015–2020.

### Vías probadas (15-nov-2026)

| Vía | Qué se intentó | Resultado exacto | ¿Sirve? |
|---|---|---|---|
| SNMF oficial | `http`/`https` de `snmf.cnf.gob.mx`, ruta `/datos-del-inventario/`, y `snigf.cnf.gob.mx` | Sin conexión (`Failed to connect` a los puertos 80 y 443, ~21 s); `www.snmf…` no resuelve el nombre | No (sitio caído hoy) |
| FAO, «Get Microdata» | `https://microdata.fao.org/index.php/catalog/2620/get-microdata` | Responde 200, pero solo remite a `snmf.cnf.gob.mx/datos-del-inventario/`; sin archivos propios | No, pero da la pista |
| Wayback, sitio SNMF | CDX de `snmf.cnf.gob.mx*` | Capturas de 2022 y de oct-2026 de las páginas; la de «datos-del-inventario» es del 19-jun-2022. No hay archivos de datos alojados en ese sitio | **Sí, como mapa**: la captura trae los enlaces reales |
| Enlaces de esa captura | `https://idefor.cnf.gob.mx/documents/<id>/download` | 200 con el archivo. Por estado y ciclo: 2004–2007 (ids 854–888), 2009–2014 (889–920), 2015–2020 (1062–1093; **Estado de México = 1078**), diccionarios (1006, 833, 852, 837) y ecuaciones de volumen | **Sí. Es la vía** |
| Wayback, archivo de datos | `archive.org/wayback/available` | `documents/1078/download` tiene copia del 27-mar-2023; `documents/1462/download` no tiene | Respaldo |
| GBIF | `dataset/search` con «Inventario Nacional Forestal», «INFyS», «CONAFOR», «Inventario Forestal y de Suelos», filtro país MX; búsqueda de organización «CONAFOR» | Ningún conjunto del INFyS mexicano. Salen inventarios de otros países (Perú-SERFOR, España, Colombia) y estudios de CONABIO/UNAM ajenos. La organización no existe en GBIF (0 resultados) | No |
| CONABIO / SNIB | `www.snib.mx` abre; `snibgeoportal.conabio.gob.mx` no conectó | No encontré el INFyS como proyecto del SNIB; no es descarte firme (no pude consultar su buscador por API) | No confirmado |
| IDEFOR, WFS | `GetCapabilities` 2.0.0 y 1.1.0 | **503** otra vez | No |
| IDEFOR, API GeoNode | `/api/layers/` y `/api/documents/` (`/api/v2/...` da 404) | Responden: 792 capas y 1,387 documentos. Capas con arbolado: solo ráster/polígonos por formación (densidad, área basal, «composición total» 2009–2014) y mallas de muestreo; **ninguna con especie por conglomerado**. Documentos: además de las bases por estado, `INFyS_Especies_2015_2020` (id 1462, `Especies_por_conglomerado_anio_Ciclo_3_15072022.xlsx`, 33 MB, nacional; no se bajó) | Los documentos sí |
| Zenodo / otros | API de Zenodo, «INFyS» y el nombre completo | 3 resultados, ninguno es el INFyS (biomasa en selvas, riqueza de árboles, Yucatán) | No |
| Inventario Estatal 2010/2014 | Búsqueda general | No apareció en línea; sigue siendo pregunta para PROBOSQUE | Pendiente |

### Fuente recomendada ahora

**`INFyS_2015_2020_Mexico.xlsx` desde IDEFOR** (`https://idefor.cnf.gob.mx/documents/1078/download`, 14.2 MB, publicado 14-jun-2022, catalogado por CONAFOR/GSNMF), con el diccionario `documents/1006/download`. Es el mismo ciclo que se quería, de la propia CONAFOR, y se bajó sin cuenta ni aceptar términos (no vi declaración alguna en la página archivada ni en la ficha). Trae diez hojas; las útiles son **Conglomerado** (282 filas, con `Cve_Municipio_C3` y `Municipio_C3`) y **Arbolado** (10,391 árboles con nombre científico APG, nombre común, familia, género, condición, diámetro, altura y coordenadas del sitio).

### Qué cambia en la implementación

- **Ya no hace falta el cruce con la capa de conglomerados de IDEFOR para el municipio:** la hoja Conglomerado trae la clave y el nombre del municipio, y se une a Arbolado por `IDConglomerado`. La capa teórica solo serviría para saber cuántos conglomerados «debería» haber por municipio.
- Las coordenadas de Arbolado son del sitio. Cruzadas con `municipios_edomex.gpkg`, **los 10,391 registros caen en un polígono y el nombre coincide con el de la hoja Conglomerado en 100 %**.
- Leer el xlsx pide `openpyxl` (no está en `.venv`). La hoja Arbolado declara más de 227 mil filas, pero solo 10,392 tienen valores; con pandas se lee en ~8 s.
- Conviene guardar el CSV extraído como dato de la herramienta, con el ciclo y la fecha de consulta, y anotar el enlace de Wayback como respaldo.

### Cobertura real medida

- 282 conglomerados en la base del estado: 149 muestreados, 133 no; **135 tienen arbolado** (árboles por año de campo: 2015, 2,776; 2016, 2,823; 2018, 2,338; 2019, 2,454).
- **10,391 árboles**: 9,444 vivos, 579 muertos en pie, 368 tocones. 222 nombres distintos: **139 especies** (binomio); el resto solo género (3,737 registros, p. ej. «Quercus», «Pinus») o «ZZ Género desconocido» (822). Solo 56 % de los registros llega a especie.
- **55 de los 125 municipios (44 %) tienen registros**; 51 con al menos una especie al nivel binomial. 20 municipios tienen conglomerado pero sin arbolado medido, y 50 no aparecen en la base. Mediana de 118 registros y 7 especies por municipio con datos; 30 de los 55 dependen de un solo conglomerado. Más registros: Luvianos (727), Temascaltepec (708), Sultepec (606), Chapa de Mota (553), Amatepec (456).
- La estimación anterior de este documento (150–350 conglomerados con datos) resultó alta: son 135.

### Límites honestos

- No es el INFyS completo: es el extracto del estado de la hoja Arbolado; no se revisaron las otras hojas ni los ciclos 2004–2014 (hay archivos equivalentes: 2009–2014 id 899 y 2004–2007 id 871; no se midieron).
- Cobertura parcial por diseño (malla de ~5 × 5 km y solo 149 de 282 conglomerados medidos). «Sin registros» no significa «sin bosque».
- «Sin conglomerado» en el CSV significa que el municipio no aparece en la base de 282; no se comparó con la malla teórica completa.
- Árboles de 7.5 cm de diámetro o más: no hay sotobosque, arbustos ni hierbas. Un 44 % de los registros no llega a especie.
- **Licencia no confirmada:** la ficha de IDEFOR deja la licencia vacía y el portal muestra CC BY-NC-SA 2.5 México en general. Antes de publicar, confirmar el uso con CONAFOR y citar la fuente. No se vio la declaración de confidencialidad de la FAO.
- La captura del SNMF es de 2022; IDEFOR puede renumerar documentos. Su WFS sigue caído (503).

### Lo guardado

`datos/edomex/infys/` (git lo ignora): `arbolado_edomex_2015_2020.csv`, `especies_por_municipio_2015_2020.csv`, `cobertura_municipios_2015_2020.csv` y `LEEME.md` (fuente, dirección, fecha, licencia, cita).
