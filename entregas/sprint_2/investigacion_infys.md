# Datos de especie del INFyS para el Estado de México

Fecha de la consulta: 14-nov-2026. Se distingue lo **comprobado** (abrí la fuente) de lo **leído** (solo descrito) y de lo **no confirmado**.

## Respuesta corta

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
