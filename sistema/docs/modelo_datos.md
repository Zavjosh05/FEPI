# Modelo de datos

Diagrama entidad-relación del Sistema de programas, generado a partir de los modelos de Django con
`herramientas/diagrama_er.py` (no se dibuja a mano: si cambia un modelo, se vuelve a generar). Son
36 tablas propias en tres apps (`nucleo`, `recepcion`, `dictamen`) sobre PostgreSQL + PostGIS. El diagrama
completo, con todos los campos, está en [`modelo_datos.mmd`](modelo_datos.mmd).

Para leerlo: `||--o{` es «uno a muchos» obligatorio, `|o--o{` «uno a muchos» opcional, `||--o|` «uno a uno»
y `}o--o{` «muchos a muchos». Aquí cada tabla muestra su llave, sus llaves foráneas y sus campos
principales. No se dibujan las relaciones hacia `Usuario` (casi todas las tablas guardan quién registró)
ni las tablas de historial que crea django-simple-history (una `Historical…` por tabla del trámite).

```bash
docker compose --profile pruebas run --rm --no-deps --entrypoint python pruebas     herramientas/diagrama_er.py > docs/modelo_datos.mmd
```

## 1. Reglas por programa y catálogos (núcleo)

Lo que cambia de un programa a otro vive aquí como datos: requisitos por tipo de persona y modalidad,
plazos, formatos, montos y ministraciones de cada ejercicio; los estados del trámite y sus transiciones
permitidas; las unidades con sus usuarios y los municipios que atiende cada Delegación.

```mermaid
erDiagram
  Ejercicio ||--o{ Formato : ejercicio
  Ejercicio ||--o{ Ministracion : ejercicio
  Ejercicio ||--o{ Modalidad : ejercicio
  Ejercicio ||--o{ MontoApoyo : ejercicio
  Ejercicio ||--o{ Plazo : ejercicio
  Ejercicio ||--o{ Requisito : ejercicio
  Ejercicio ||--o{ TipoPersona : ejercicio
  Estado ||--o{ Transicion : destino
  Estado ||--o{ Transicion : origen
  Modalidad |o--o{ MontoApoyo : modalidad
  Programa |o--o{ Transicion : programa
  Programa ||--o{ Ejercicio : programa
  Requisito }o--o{ Modalidad : modalidades
  Requisito }o--o{ TipoPersona : tipos_persona
  Unidad |o--o{ Municipio : delegacion
  Unidad |o--o{ Usuario : unidad
  Unidad }o--o{ Programa : programas
  DiaInhabil {
    int id PK
    fecha fecha UK
    texto descripcion
    texto fuente
  }
  Ejercicio {
    int id PK
    int programa_id FK
    int anio
    bool vigente
    texto fuente
    texto archivo_reglas
  }
  Estado {
    int id PK
    texto clave UK
    texto nombre
    texto descripcion
    texto tipo_unidad_bandeja
    texto visible_para
  }
  Formato {
    int id PK
    int ejercicio_id FK
    texto clave
    texto nombre
    texto uso
    int linea_rop
  }
  Ministracion {
    int id PK
    int ejercicio_id FK
    int numero
    decimal porcentaje
    texto regimen
    texto condicion
  }
  Modalidad {
    int id PK
    int ejercicio_id FK
    texto clave
    texto nombre
    texto descripcion
    texto fundamento
  }
  MontoApoyo {
    int id PK
    int ejercicio_id FK
    texto concepto
    decimal monto
    texto unidad
    int modalidad_id FK
    texto fundamento
  }
  Municipio {
    int id PK
    texto clave UK
    texto nombre UK
    geom_multipoligono geom
    int delegacion_id FK
  }
  Plazo {
    int id PK
    int ejercicio_id FK
    texto clave
    texto descripcion
    int cantidad
    texto unidad
  }
  Programa {
    int id PK
    texto clave UK
    texto nombre
    bool usa_poligono
    texto descripcion
  }
  Requisito {
    int id PK
    int ejercicio_id FK
    texto clave
    texto texto
    bool aplica_en_refrendo
    bool es_documento_legal
  }
  TipoPersona {
    int id PK
    int ejercicio_id FK
    texto clave
    texto nombre
    texto fundamento
    int orden
  }
  Transicion {
    int id PK
    int programa_id FK
    int origen_id FK
    int destino_id FK
    texto tipo_unidad
    texto accion
    bool requiere_motivo
  }
  Unidad {
    int id PK
    texto clave UK
    texto nombre
    texto tipo
    texto sede
    texto domicilio
  }
  Usuario {
    int id PK
    texto username UK
    int unidad_id FK
    texto cargo
  }
```

## 2. Expediente y recepción (M1)

El expediente único por predio: la solicitud, la revisión de cada requisito con su documento, los
polígonos (el vigente y los anteriores), la validación con su aviso de faltantes y la observación de la Dirección
sobre cada requisito (`ObservacionValidacion`), los acuses y la bitácora. Las tablas de historial
(`Historical…`) guardan cada alta, cambio o baja con el usuario, la fecha y la hora: es la trazabilidad que muestra
la pestaña «Trazabilidad» del expediente.

```mermaid
erDiagram
  Acuse |o--o{ Evento : acuse
  Acuse |o--o{ Validacion : acuse
  Acuse |o--o{ Validacion : acuse_notificacion
  Documento |o--o{ RevisionRequisito : documento
  Ejercicio ||--o{ Expediente : ejercicio
  Ejercicio ||--o{ Requisito : ejercicio
  Estado |o--o{ Evento : estado_destino
  Estado |o--o{ Evento : estado_origen
  Estado ||--o{ Expediente : estado
  Expediente |o--o{ Acuse : expediente
  Expediente ||--o{ Documento : expediente
  Expediente ||--o{ Evento : expediente
  Expediente ||--o{ Poligono : expediente
  Expediente ||--o{ RevisionRequisito : expediente
  Expediente ||--o{ Validacion : expediente
  Municipio ||--o{ Predio : municipio
  Persona |o--o{ Poligono : prestador
  Persona ||--o{ Expediente : solicitante
  Persona ||--o{ Predio : titular
  Poligono |o--o{ Poligono : anterior
  Predio ||--o{ Expediente : predio
  Requisito |o--o{ Documento : requisito
  Requisito ||--o{ RevisionRequisito : requisito
  RevisionRequisito ||--o{ ObservacionValidacion : revision
  Unidad |o--o{ Acuse : unidad
  Unidad |o--o{ Documento : unidad
  Unidad |o--o{ Evento : unidad
  Unidad |o--o{ Municipio : delegacion
  Unidad ||--o{ Expediente : delegacion
  Validacion ||--o{ ObservacionValidacion : validacion
  Validacion }o--o{ RevisionRequisito : faltantes
  Acuse {
    int id PK
    texto folio UK
    int expediente_id FK
    texto referencia
    texto tipo
    texto titulo
    fecha_hora fecha_hora
    int unidad_id FK
  }
  Documento {
    int id PK
    int expediente_id FK
    texto tipo
    int requisito_id FK
    texto nombre
    archivo archivo
    fecha_hora fecha_entrega
    int unidad_id FK
  }
  Ejercicio {
    int id PK
    int anio
    bool vigente
    texto fuente
    texto archivo_reglas
  }
  Estado {
    int id PK
    texto clave UK
    texto nombre
    texto descripcion
    texto tipo_unidad_bandeja
    texto visible_para
  }
  Evento {
    int id PK
    int expediente_id FK
    fecha_hora fecha_hora
    int unidad_id FK
    texto tipo
    texto descripcion
    int estado_origen_id FK
    int estado_destino_id FK
    texto motivo
    int acuse_id FK
  }
  Expediente {
    int id PK
    texto folio UK
    int ejercicio_id FK
    int predio_id FK
    int solicitante_id FK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    int delegacion_id FK
    int estado_id FK
    fecha_hora fecha_recepcion
  }
  Municipio {
    int id PK
    texto clave UK
    texto nombre UK
    geom_multipoligono geom
    int delegacion_id FK
  }
  Persona {
    int id PK
    texto tipo
    texto nombre
    texto curp
    texto rfc
  }
  Predio {
    int id PK
    texto folio UK
    texto nombre
    int municipio_id FK
    texto localidad
    int titular_id FK
    decimal superficie_declarada_ha
    fecha_hora creado
  }
  Requisito {
    int id PK
    int ejercicio_id FK
    texto clave
    texto texto
    bool aplica_en_refrendo
    bool es_documento_legal
  }
  Unidad {
    int id PK
    texto clave UK
    texto nombre
    texto tipo
    texto sede
    texto domicilio
  }
  ObservacionValidacion {
    int id PK
    int validacion_id FK
    int revision_id FK
    bool faltante
    texto origen
    texto observacion
  }
  Poligono {
    int id PK
    int expediente_id FK
    geom_multipoligono geom
    decimal superficie_ha
    texto levantado_por
    int prestador_id FK
    texto responsable
    int anterior_id FK
  }
  RevisionRequisito {
    int id PK
    int expediente_id FK
    int requisito_id FK
    texto estado
    int documento_id FK
    bool en_archivo_probosque
    fecha fecha_documento
    texto observaciones
  }
  Validacion {
    int id PK
    int expediente_id FK
    texto resultado
    fecha_hora fecha_hora
    texto observaciones
    json detalle
    int acuse_id FK
    int acuse_notificacion_id FK
  }
```

## 3. Dictamen y Comité (M2)

Un dictamen técnico y uno jurídico por expediente, cada uno con su documento en PDF (`Documento` de tipo
«dictamen»); la revisión de la propiedad o legal posesión del predio (`RevisionPropiedad`, una por dictamen
jurídico); el Listado de Personas Beneficiarias Incumplidas y los predios sancionados; las sesiones del Comité
con sus documentos; la resolución de cada expediente en la sesión de aprobación; los acuerdos de seguimiento
(incidentes y reasignaciones, con su causa, su área responsable y el recurso que liberan o reasignan) y los
movimientos de listado que producen (`MovimientoListado`: quién sale de la Lista de Personas Beneficiarias y
quién entra desde la lista de espera).

```mermaid
erDiagram
  Acuerdo ||--o{ MovimientoListado : acuerdo
  Acuerdo }o--o{ Expediente : expedientes
  DictamenJuridico ||--o| RevisionPropiedad : dictamen
  Documento |o--o{ DictamenJuridico : documento
  Documento |o--o{ DictamenTecnico : documento
  Ejercicio ||--o{ Expediente : ejercicio
  Ejercicio ||--o{ SesionComite : ejercicio
  Expediente ||--o{ Documento : expediente
  Expediente ||--o{ MovimientoListado : expediente
  Expediente ||--o{ ResolucionSesion : expediente
  Expediente ||--o| DictamenJuridico : expediente
  Expediente ||--o| DictamenTecnico : expediente
  Persona |o--o{ PersonaIncumplida : persona
  Persona ||--o{ Expediente : solicitante
  Persona ||--o{ Predio : titular
  Predio |o--o{ PredioSancionado : predio
  Predio ||--o{ Expediente : predio
  SesionComite ||--o{ Acuerdo : sesion
  SesionComite ||--o{ DocumentoSesion : sesion
  SesionComite ||--o{ ResolucionSesion : sesion
  Unidad |o--o{ Documento : unidad
  Unidad ||--o{ Acuerdo : unidad_responsable
  Unidad ||--o{ Expediente : delegacion
  Acuerdo {
    int id PK
    int sesion_id FK
    texto numero
    texto tipo
    texto descripcion
    int unidad_responsable_id FK
    int ministracion
  }
  DictamenJuridico {
    int id PK
    int expediente_id FK
    texto resultado
    texto motivo
    json cotejo
    json documentacion
    texto folio UK
    int documento_id FK
  }
  DictamenTecnico {
    int id PK
    int expediente_id FK
    texto resultado
    texto motivo
    decimal superficie_factible_ha
    json verificacion
    texto folio UK
    int documento_id FK
  }
  DocumentoSesion {
    int id PK
    int sesion_id FK
    texto nombre
    archivo archivo
    fecha_hora fecha_hora
  }
  MovimientoListado {
    int id PK
    int acuerdo_id FK
    int expediente_id FK
    texto movimiento
    texto estado_anterior
    texto estado_nuevo
    int lugar_lista_espera
  }
  PersonaIncumplida {
    int id PK
    texto nombre
    texto curp
    texto rfc
    int persona_id FK
    texto programa
  }
  PredioSancionado {
    int id PK
    int predio_id FK
    texto descripcion_predio
    texto tipo
    texto descripcion
    texto autoridad
  }
  ResolucionSesion {
    int id PK
    int sesion_id FK
    int expediente_id FK
    texto resultado
    texto resultado_propuesto
    int orden
    int orden_propuesto
  }
  RevisionPropiedad {
    int id PK
    int dictamen_id FK
    texto tipo_documento
    texto nombre_documento
    texto numero_documento
    fecha fecha_documento
  }
  SesionComite {
    int id PK
    int ejercicio_id FK
    texto tipo
    texto caracter
    texto numero
    fecha_hora fecha_hora
  }
  Documento {
    int id PK
    int expediente_id FK
    texto tipo
    texto nombre
    archivo archivo
    fecha_hora fecha_entrega
    int unidad_id FK
  }
  Ejercicio {
    int id PK
    int anio
    bool vigente
    texto fuente
    texto archivo_reglas
  }
  Expediente {
    int id PK
    texto folio UK
    int ejercicio_id FK
    int predio_id FK
    int solicitante_id FK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    int delegacion_id FK
    fecha_hora fecha_recepcion
  }
  Persona {
    int id PK
    texto tipo
    texto nombre
    texto curp
    texto rfc
  }
  Predio {
    int id PK
    texto folio UK
    texto nombre
    texto localidad
    int titular_id FK
    decimal superficie_declarada_ha
    fecha_hora creado
  }
  Unidad {
    int id PK
    texto clave UK
    texto nombre
    texto tipo
    texto sede
    texto domicilio
  }
```
