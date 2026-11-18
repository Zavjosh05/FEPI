# Modelo de datos

Diagrama entidad-relación del Sistema de programas, generado a partir de los modelos de Django con
`herramientas/diagrama_er.py` (no se dibuja a mano: si cambia un modelo, se vuelve a generar). Son
76 tablas propias en ocho apps (`nucleo`, `recepcion`, `dictamen`, `contrato`, `pagos`, `portal`, `ejecucion` y
`seguimiento`) sobre PostgreSQL + PostGIS, en ocho áreas (secciones 1 a 8). El diagrama
completo, con todos los campos, está en [`modelo_datos.mmd`](modelo_datos.mmd).

Para leerlo: `||--o{` es «uno a muchos» obligatorio, `|o--o{` «uno a muchos» opcional, `||--o|` «uno a uno»
y `}o--o{` «muchos a muchos». Aquí cada tabla muestra su llave, sus llaves foráneas y sus campos
principales. No se dibujan las relaciones hacia `Usuario` (casi todas las tablas guardan quién registró)
ni las tablas de historial que crea django-simple-history (una `Historical…` por tabla del trámite).

```bash
docker compose --profile pruebas run --rm --no-deps --entrypoint python pruebas herramientas/regenerar_modelo_datos.py
```

(`regenerar_modelo_datos.py` vuelve a dibujar cada diagrama de este archivo con sus mismas entidades y el `.mmd` completo.)

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
    fecha_hora reglas_cargadas
    json datos
  }
  Estado {
    int id PK
    texto clave UK
    texto nombre
    texto descripcion
    texto tipo_unidad_bandeja
    texto visible_para
    texto flujo_alterno
    bool final
  }
  Formato {
    int id PK
    int ejercicio_id FK
    texto clave
    texto nombre
    texto uso
    int linea_rop
    int orden
  }
  Ministracion {
    int id PK
    int ejercicio_id FK
    int numero
    decimal porcentaje
    texto regimen
    texto condicion
    texto fundamento
    bool supuesto
  }
  Modalidad {
    int id PK
    int ejercicio_id FK
    texto clave
    texto nombre
    texto descripcion
    texto fundamento
    bool seleccionable
    int orden
  }
  MontoApoyo {
    int id PK
    int ejercicio_id FK
    texto concepto
    decimal monto
    texto unidad
    int modalidad_id FK
    texto fundamento
    json datos
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
    fecha fecha_fin
    texto corre_desde
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
    bool requiere_documento
    bool opcional
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
    texto telefono
    bool asignacion_confirmada
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
polígonos (el vigente y los anteriores), la validación con su aviso de faltantes, los acuses y la bitácora.
La notificación por conducto de la Delegación (`Notificacion`, con el envío y la notificación a la persona) y
los hitos que arrancan plazos (`Hito`: publicación, firma, entrega del Vale o del cheque) son del núcleo y
los usan todos los módulos.

```mermaid
erDiagram
  Acuse |o--o{ Evento : acuse
  Acuse |o--o{ Notificacion : acuse_envio
  Acuse |o--o{ Notificacion : acuse_notificacion
  Acuse |o--o{ Validacion : acuse
  Documento |o--o{ RevisionRequisito : documento
  Ejercicio ||--o{ Expediente : ejercicio
  Ejercicio ||--o{ Requisito : ejercicio
  Estado |o--o{ Evento : estado_destino
  Estado |o--o{ Evento : estado_origen
  Estado ||--o{ Expediente : estado
  Expediente |o--o{ Acuse : expediente
  Expediente ||--o{ Documento : expediente
  Expediente ||--o{ Evento : expediente
  Expediente ||--o{ Hito : expediente
  Expediente ||--o{ Notificacion : expediente
  Expediente ||--o{ Poligono : expediente
  Expediente ||--o{ RevisionRequisito : expediente
  Expediente ||--o{ Validacion : expediente
  Municipio ||--o{ Predio : municipio
  Notificacion ||--o| Validacion : notificacion
  Persona |o--o{ Expediente : persona_beneficiaria
  Persona |o--o{ Notificacion : destinatario
  Persona |o--o{ Poligono : prestador
  Persona ||--o{ Expediente : solicitante
  Persona ||--o{ Predio : titular
  Poligono |o--o{ Poligono : anterior
  Predio ||--o{ Expediente : predio
  Requisito |o--o{ Documento : requisito
  Requisito ||--o{ RevisionRequisito : requisito
  Unidad |o--o{ Acuse : unidad
  Unidad |o--o{ Documento : unidad
  Unidad |o--o{ Evento : unidad
  Unidad |o--o{ Municipio : delegacion
  Unidad |o--o{ Notificacion : unidad_origen
  Unidad ||--o{ Expediente : delegacion
  Unidad ||--o{ Notificacion : delegacion
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
    texto destinatario
    json contenido
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
    fecha_hora reglas_cargadas
    json datos
  }
  Estado {
    int id PK
    texto clave UK
    texto nombre
    texto descripcion
    texto tipo_unidad_bandeja
    texto visible_para
    texto flujo_alterno
    bool final
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
    json datos
  }
  Expediente {
    int id PK
    texto folio UK
    int ejercicio_id FK
    int predio_id FK
    int solicitante_id FK
    int persona_beneficiaria_id FK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    int delegacion_id FK
    int estado_id FK
    fecha_hora fecha_recepcion
    fecha_hora enviado_direccion
    texto observaciones
  }
  Hito {
    int id PK
    int expediente_id FK
    texto clave
    fecha_hora fecha_hora
    texto referencia
    json datos
    fecha_hora registrado_en
  }
  Municipio {
    int id PK
    texto clave UK
    texto nombre UK
    geom_multipoligono geom
    int delegacion_id FK
  }
  Notificacion {
    int id PK
    int expediente_id FK
    texto tipo
    texto asunto
    int destinatario_id FK
    int unidad_origen_id FK
    int delegacion_id FK
    fecha_hora enviada_en
    int acuse_envio_id FK
    fecha_hora notificada_en
    texto medio
    int acuse_notificacion_id FK
    texto observaciones
  }
  Persona {
    int id PK
    texto tipo
    texto nombre
    texto curp
    texto rfc
    texto rfn
    texto representante
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
    bool requiere_documento
    bool opcional
  }
  Unidad {
    int id PK
    texto clave UK
    texto nombre
    texto tipo
    texto sede
    texto domicilio
    texto telefono
    bool asignacion_confirmada
  }
  Poligono {
    int id PK
    int expediente_id FK
    geom_multipoligono geom
    decimal superficie_ha
    texto levantado_por
    int prestador_id FK
    texto responsable
    fecha fecha_levantamiento
    texto origen
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
    fecha_hora revisado_en
  }
  Validacion {
    int id PK
    int expediente_id FK
    texto resultado
    fecha_hora fecha_hora
    texto observaciones
    json detalle
    fecha fecha_limite
    texto plazo_aplicado
    int acuse_id FK
    int notificacion_id FK
  }
```

## 3. Dictamen y Comité (M2)

Un dictamen técnico y uno jurídico por expediente, el Listado de Personas Beneficiarias Incumplidas y los
predios sancionados, las sesiones del Comité con sus documentos, la resolución de cada expediente en la
sesión de aprobación y los acuerdos de seguimiento con su área responsable.

```mermaid
erDiagram
  Acuerdo }o--o{ Expediente : expedientes
  Ejercicio ||--o{ Expediente : ejercicio
  Ejercicio ||--o{ SesionComite : ejercicio
  Expediente ||--o{ ResolucionSesion : expediente
  Expediente ||--o| DictamenJuridico : expediente
  Expediente ||--o| DictamenTecnico : expediente
  Persona |o--o{ Expediente : persona_beneficiaria
  Persona |o--o{ PersonaIncumplida : persona
  Persona ||--o{ Expediente : solicitante
  Persona ||--o{ Predio : titular
  Predio |o--o{ PredioSancionado : predio
  Predio ||--o{ Expediente : predio
  SesionComite ||--o{ Acuerdo : sesion
  SesionComite ||--o{ DocumentoSesion : sesion
  SesionComite ||--o{ ResolucionSesion : sesion
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
    texto periodo
    texto estado
  }
  DictamenJuridico {
    int id PK
    int expediente_id FK
    texto resultado
    texto motivo
    json cotejo
    fecha_hora fecha_hora
  }
  DictamenTecnico {
    int id PK
    int expediente_id FK
    texto resultado
    texto motivo
    decimal superficie_factible_ha
    json verificacion
    json analisis
    fecha fecha_limite
  }
  DocumentoSesion {
    int id PK
    int sesion_id FK
    texto nombre
    archivo archivo
    fecha_hora fecha_hora
  }
  PersonaIncumplida {
    int id PK
    texto nombre
    texto curp
    texto rfc
    int persona_id FK
    texto programa
    texto motivo
    texto acuerdo
  }
  PredioSancionado {
    int id PK
    int predio_id FK
    texto descripcion_predio
    texto tipo
    texto descripcion
    texto autoridad
    fecha fecha
    bool reintegro_realizado
  }
  ResolucionSesion {
    int id PK
    int sesion_id FK
    int expediente_id FK
    texto resultado
    texto resultado_propuesto
    int orden
    int orden_propuesto
    decimal monto
    json criterios
  }
  SesionComite {
    int id PK
    int ejercicio_id FK
    texto tipo
    texto caracter
    texto numero
    fecha_hora fecha_hora
    texto lugar
    texto orden_del_dia
  }
  Ejercicio {
    int id PK
    int anio
    bool vigente
    texto fuente
    texto archivo_reglas
    fecha_hora reglas_cargadas
    json datos
  }
  Expediente {
    int id PK
    texto folio UK
    int ejercicio_id FK
    int predio_id FK
    int solicitante_id FK
    int persona_beneficiaria_id FK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    int delegacion_id FK
    fecha_hora fecha_recepcion
    fecha_hora enviado_direccion
    texto observaciones
  }
  Persona {
    int id PK
    texto tipo
    texto nombre
    texto curp
    texto rfc
    texto rfn
    texto representante
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
    texto telefono
    bool asignacion_confirmada
  }
```

## 4. Publicación y contrato (M3)

La publicación de resultados de una sesión de aprobación con acta (`Publicacion`, con un `ResultadoPublicado` por solicitud: lo que
ve el público), el modelo de contrato por programa con sus versiones validadas por la Unidad Jurídica (`ModeloContrato`,
`VersionModelo`), el contrato elaborado por solicitud (`Contrato`, con su huella y su `Adendum` para ampliar plazos), la firma
con sus elementos de formalización y el señalamiento de las que vencen sin firma (`FirmaContrato`, `ElementoFormalizacion`,
`SinFirma`) y el Vale de Planta con sus renglones y las salidas del vivero (`ValePlanta`, `RenglonVale`, `SalidaPlanta`, con los
catálogos `Especie` y `Vivero`). Los avisos a la persona no tienen tabla propia: son `Notificacion` del núcleo, igual que los hitos
que arrancan los plazos.

```mermaid
erDiagram
  Contrato ||--o{ Adendum : contrato
  Contrato ||--o| FirmaContrato : contrato
  Especie ||--o{ RenglonVale : especie
  Expediente ||--o{ Notificacion : expediente
  Expediente ||--o{ ResultadoPublicado : expediente
  Expediente ||--o{ ValePlanta : expediente
  Expediente ||--o| Contrato : expediente
  Expediente ||--o| FirmaContrato : expediente
  Expediente ||--o| SinFirma : expediente
  FirmaContrato ||--o{ ElementoFormalizacion : firma
  ModeloContrato ||--o{ VersionModelo : modelo
  Publicacion ||--o{ ResultadoPublicado : publicacion
  RenglonVale ||--o{ SalidaPlanta : renglon
  ValePlanta |o--o{ ValePlanta : repone
  ValePlanta ||--o{ RenglonVale : vale
  ValePlanta ||--o{ SalidaPlanta : vale
  VersionModelo |o--o{ Adendum : version_modelo
  VersionModelo ||--o{ Contrato : version_modelo
  Vivero ||--o{ ValePlanta : vivero
  Adendum {
    int id PK
    int contrato_id FK
    int version_modelo_id FK
    texto motivo
    fecha plazo_original
    fecha plazo_nuevo
    archivo archivo
    fecha_hora creado_en
  }
  Contrato {
    int id PK
    int expediente_id FK
    texto folio UK
    int version_modelo_id FK
    texto tipo
    texto texto
    json datos
    archivo archivo
    texto huella
    fecha_hora elaborado_en
  }
  ElementoFormalizacion {
    int id PK
    int firma_id FK
    texto clave
    texto nombre
    texto dato_etiqueta
    texto dato
    archivo archivo
  }
  Especie {
    int id PK
    texto nombre UK
    texto nombre_cientifico
    bool activa
  }
  FirmaContrato {
    int id PK
    int contrato_id FK
    int expediente_id FK
    fecha_hora firmado_en
    texto firmante
    texto firmante_nombre
    archivo archivo
    texto huella
    json verificacion
  }
  ModeloContrato {
    int id PK
    texto tipo
    texto nombre
    bool es_base
    fecha_hora creado_en
  }
  Publicacion {
    int id PK
    fecha_hora publicada_en
    texto lugares
    fecha fecha_limite
    bool dentro_de_fecha
    texto fundamento_fecha
  }
  RenglonVale {
    int id PK
    int vale_id FK
    int especie_id FK
    int cantidad
  }
  ResultadoPublicado {
    int id PK
    int publicacion_id FK
    int expediente_id FK
    texto resultado
    int orden
    texto folio
    texto predio
    texto municipio
    texto persona
  }
  SalidaPlanta {
    int id PK
    int renglon_id FK
    int vale_id FK
    int cantidad
    fecha_hora salido_en
    fecha_hora registrada_en
    texto observaciones
  }
  SinFirma {
    int id PK
    int expediente_id FK
    fecha vencio_el
    fecha_hora senalado_en
    texto motivo
    fecha_hora liberado_en
    texto motivo_liberacion
  }
  ValePlanta {
    int id PK
    texto folio UK
    int expediente_id FK
    int vivero_id FK
    fecha_hora entregado_en
    fecha vence_el
    texto vigencia_texto
    bool anticipado
    archivo carta_compromiso
    int propuesta_total
    int repone_id FK
  }
  VersionModelo {
    int id PK
    int modelo_id FK
    int numero
    texto texto
    texto estado
    fecha_hora creada_en
    fecha_hora revisada_en
    texto observaciones
  }
  Vivero {
    int id PK
    texto clave UK
    texto nombre
    texto municipio
    bool activo
  }
  Expediente {
    int id PK
    texto folio UK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    fecha_hora fecha_recepcion
    fecha_hora enviado_direccion
    texto observaciones
  }
  Notificacion {
    int id PK
    int expediente_id FK
    texto tipo
    texto asunto
    fecha_hora enviada_en
    fecha_hora notificada_en
    texto medio
    texto observaciones
  }
```

## 5. Pagos (M5)

El oficio de la Delegación y el comprobante de la cuenta bancaria (`OficioPago`, `ComprobanteCuenta`), la solicitud de cada
ministración con su lista de soportes (`SolicitudPago`), la revisión de Administración y Finanzas, que acepta o devuelve
(`RevisionSolicitud`), el pago registrado (`Pago`, uno por solicitud aceptada), la remisión a la Fiduciaria en PSAHEM
(`RemisionFiduciaria`) y el cheque de cada ministración (`Cheque`). El aviso de pago a la persona es una `Notificacion`
del núcleo.

```mermaid
erDiagram
  Expediente ||--o{ Cheque : expediente
  Expediente ||--o{ ComprobanteCuenta : expediente
  Expediente ||--o{ Notificacion : expediente
  Expediente ||--o{ Pago : expediente
  Expediente ||--o{ RemisionFiduciaria : expediente
  Expediente ||--o{ SolicitudPago : expediente
  Expediente ||--o| OficioPago : expediente
  Notificacion |o--o{ Cheque : aviso
  Notificacion |o--o{ Pago : aviso
  RemisionFiduciaria ||--o| Cheque : remision
  SolicitudPago ||--o{ RevisionSolicitud : solicitud
  SolicitudPago ||--o| Cheque : solicitud
  SolicitudPago ||--o| Pago : solicitud
  SolicitudPago ||--o| RemisionFiduciaria : solicitud
  Expediente {
    int id PK
    texto folio UK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    fecha_hora fecha_recepcion
    fecha_hora enviado_direccion
    texto observaciones
  }
  Notificacion {
    int id PK
    int expediente_id FK
    texto tipo
    texto asunto
    fecha_hora enviada_en
    fecha_hora notificada_en
    texto medio
    texto observaciones
  }
  Cheque {
    int id PK
    int solicitud_id FK
    int remision_id FK
    int expediente_id FK
    int ministracion
    texto numero UK
    decimal importe
    fecha emitido_en
    fecha_hora registrado_en
    fecha_hora enviado_en
    int aviso_id FK
    fecha_hora entregado_en
  }
  ComprobanteCuenta {
    int id PK
    int expediente_id FK
    archivo archivo
    texto descripcion
    texto huella
    fecha_hora subido_en
  }
  OficioPago {
    int id PK
    int expediente_id FK
    texto folio UK
    fecha_hora emitido_en
    archivo archivo
    texto huella
  }
  Pago {
    int id PK
    int solicitud_id FK
    int expediente_id FK
    int ministracion
    decimal importe
    texto tipo
    texto referencia
    fecha fecha_pago
    texto motivo_cheque
    int aviso_id FK
  }
  RemisionFiduciaria {
    int id PK
    int solicitud_id FK
    int expediente_id FK
    int ministracion
    fecha_hora remitida_en
    fecha_hora recibida_en
    fecha vence_el
    bool en_plazo
    texto oficio
  }
  RevisionSolicitud {
    int id PK
    int solicitud_id FK
    texto resultado
    int envio
    texto observaciones
    fecha_hora revisada_en
  }
  SolicitudPago {
    int id PK
    int expediente_id FK
    int ministracion
    decimal porcentaje
    decimal importe
    texto tipo_pago
    texto estado
    fecha_hora preparada_en
  }
```

## 6. Portal de personas beneficiarias

La cuenta externa (`CuentaExterna`: un `Usuario` sin unidad interna, con la CURP como usuario, ligado a la `Persona`), los
expedientes que ve (`AccesoExpediente`, con el papel de persona beneficiaria o de prestador) y el código de consulta del
expediente (`CodigoConsulta`, respaldo sin cuenta). Los códigos se guardan cifrados y se imprimen en un `Acuse`. Además,
el `Expediente` guarda además a la persona beneficiaria cuando no es quien solicita (`persona_beneficiaria`: el
Guardabosque en PEG).

```mermaid
erDiagram
  Acuse |o--o{ AccesoExpediente : acuse
  Acuse |o--o{ CodigoConsulta : acuse
  CuentaExterna ||--o{ AccesoExpediente : cuenta
  Expediente |o--o{ Acuse : expediente
  Expediente ||--o{ AccesoExpediente : expediente
  Expediente ||--o| CodigoConsulta : expediente
  Persona |o--o{ Expediente : persona_beneficiaria
  Persona ||--o{ CuentaExterna : persona
  Persona ||--o{ Expediente : solicitante
  Acuse {
    int id PK
    texto folio UK
    int expediente_id FK
    texto referencia
    texto tipo
    texto titulo
    fecha_hora fecha_hora
    texto destinatario
    json contenido
  }
  Expediente {
    int id PK
    texto folio UK
    int solicitante_id FK
    int persona_beneficiaria_id FK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    fecha_hora fecha_recepcion
    fecha_hora enviado_direccion
    texto observaciones
  }
  Persona {
    int id PK
    texto tipo
    texto nombre
    texto curp
    texto rfc
    texto rfn
    texto representante
  }
  AccesoExpediente {
    int id PK
    int cuenta_id FK
    int expediente_id FK
    texto rol
    fecha_hora otorgado_en
    int acuse_id FK
  }
  CodigoConsulta {
    int id PK
    int expediente_id FK
    texto codigo_hash
    fecha_hora creado_en
    int acuse_id FK
  }
  CuentaExterna {
    int id PK
    int persona_id FK
    fecha_hora creada_en
    texto codigo_hash
    fecha_hora codigo_emitido_en
    fecha_hora activada_en
  }
```

## 7. Ejecución y verificación (M4)

Lo que la persona beneficiaria (o el Guardabosque, o el prestador con RFN) envía desde el portal o entrega en la Delegación, con
su acuse y el medio (`Comprobacion`); el resultado de la verificación en campo con la superficie verificada, su ajuste y lo
ministrado de más (`Verificacion`) y las incidencias con su tipo y documento (`Incidencia`). En Guardabosques, la revisión de la
Delegación de cada reporte mensual (`RevisionReporte`), la evaluación interna por Guardabosque y por periodo
(`EvaluacionPeriodo`) y su envío al CASPEG (`EnvioEvaluacion`), que lo valida con un `Acuerdo` de su sesión de seguimiento.

```mermaid
erDiagram
  Acuerdo }o--o{ Expediente : expedientes
  Comprobacion |o--o{ EvaluacionPeriodo : comprobacion
  Comprobacion |o--o{ Verificacion : comprobacion
  Comprobacion ||--o{ RevisionReporte : comprobacion
  EnvioEvaluacion |o--o{ EvaluacionPeriodo : envio
  Expediente ||--o{ Comprobacion : expediente
  Expediente ||--o{ EvaluacionPeriodo : expediente
  Expediente ||--o{ Incidencia : expediente
  Expediente ||--o{ RevisionReporte : expediente
  Expediente ||--o{ Verificacion : expediente
  Verificacion ||--o{ Incidencia : verificacion
  Acuerdo {
    int id PK
    texto numero
    texto tipo
    texto descripcion
    int ministracion
    texto periodo
    texto estado
  }
  Comprobacion {
    int id PK
    int expediente_id FK
    texto tipo
    texto nombre
    texto fundamento
    texto medio
    fecha_hora enviada_en
    texto persona_entrega
  }
  EnvioEvaluacion {
    int id PK
    texto periodo
    texto nombre_periodo
    fecha_hora enviado_en
    int cumplen
    int no_cumplen
    int no_entregaron
  }
  EvaluacionPeriodo {
    int id PK
    int expediente_id FK
    texto periodo
    texto nombre_periodo
    texto resultado
    texto motivo
    int comprobacion_id FK
    bool automatica
    fecha_hora evaluada_en
    int envio_id FK
  }
  Incidencia {
    int id PK
    int verificacion_id FK
    int expediente_id FK
    texto tipo
    texto descripcion
    archivo archivo
    texto huella
    fecha_hora registrada_en
    fecha_hora atendida_en
  }
  RevisionReporte {
    int id PK
    int comprobacion_id FK
    int expediente_id FK
    texto periodo
    texto resultado
    texto observaciones
    fecha_hora revisada_en
  }
  Verificacion {
    int id PK
    int expediente_id FK
    int comprobacion_id FK
    texto tipo_documento
    texto nombre_documento
    fecha fecha_visita
    decimal superficie_aprobada_ha
    decimal superficie_verificada_ha
    decimal ajuste_pct
  }
  Expediente {
    int id PK
    texto folio UK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    fecha_hora fecha_recepcion
    fecha_hora enviado_direccion
    texto observaciones
  }
```

## 8. Seguimiento y cierre (M6)

**Lista de espera, sustituciones e incumplimientos.** Las solicitudes de la persona (sustitución, desistimiento, fallecimiento)
con su acuse (`SolicitudPersona`); las propuestas del área responsable al Comité (`Propuesta`: reasignación, baja, sustitución,
caso fortuito, cancelación, suspensión), que se ejecutan al cumplirse su `Acuerdo`; el recurso liberado y a quién se reasigna
(`RecursoLiberado`); el aviso de omisiones con la fecha que fija el área (`AvisoOmision`); lo que el sistema señala para que una
persona lo confirme (`Senalamiento`) y el requerimiento de devolución con su monto, la cuenta (`CuentaReintegro`) y el depósito
(`Requerimiento`). La prórroga de MFS (`Prorroga`) y el adendum (`Adendum`, sección 4) no se dibujan.

```mermaid
erDiagram
  Acuerdo |o--o{ Requerimiento : acuerdo
  Acuerdo ||--o| Propuesta : acuerdo
  Acuerdo }o--o{ Expediente : expedientes
  CuentaReintegro |o--o{ Requerimiento : cuenta
  Expediente |o--o{ RecursoLiberado : expediente
  Expediente ||--o{ AvisoOmision : expediente
  Expediente ||--o{ Requerimiento : expediente
  Expediente ||--o{ Senalamiento : expediente
  Expediente ||--o{ SolicitudPersona : expediente
  Propuesta |o--o{ RecursoLiberado : propuesta
  Propuesta |o--o{ Requerimiento : propuesta
  Propuesta |o--o{ Senalamiento : propuesta
  Propuesta |o--o{ SolicitudPersona : propuesta
  Propuesta }o--o{ Expediente : expedientes
  Acuerdo {
    int id PK
    texto numero
    texto tipo
    texto descripcion
    int ministracion
    texto periodo
    texto estado
  }
  Expediente {
    int id PK
    texto folio UK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    fecha_hora fecha_recepcion
    fecha_hora enviado_direccion
    texto observaciones
  }
  AvisoOmision {
    int id PK
    int expediente_id FK
    texto omisiones
    texto causa
    fecha vence
    texto plazo_texto
    texto estado_al_avisar
    fecha_hora creado_en
  }
  CuentaReintegro {
    int id PK
    texto titular
    texto banco
    texto cuenta
    texto referencia
    texto nota
    bool vigente
  }
  Propuesta {
    int id PK
    texto tipo
    texto descripcion
    texto fundamento
    decimal monto_liberado
    decimal monto_asignado
    decimal saldo
    int acuerdo_id FK
  }
  RecursoLiberado {
    int id PK
    int expediente_id FK
    texto origen
    decimal monto
    texto descripcion
    texto referencia
    fecha_hora liberado_en
    int propuesta_id FK
    fecha_hora reasignado_en
  }
  Requerimiento {
    int id PK
    int expediente_id FK
    int propuesta_id FK
    int acuerdo_id FK
    texto motivo
    texto base
    decimal monto_ministrado
    decimal monto_base
    int plantas_no_establecidas
    decimal precio_planta
    int cuenta_id FK
  }
  Senalamiento {
    int id PK
    int expediente_id FK
    texto tipo
    texto clave
    texto descripcion
    texto fundamento
    json datos
    fecha_hora creado_en
    int propuesta_id FK
  }
  SolicitudPersona {
    int id PK
    int expediente_id FK
    texto tipo
    texto nombre
    texto medio
    fecha_hora presentada_en
    texto persona_presenta
    texto motivo
    int propuesta_id FK
  }
```

**Cierre del ejercicio.** La copia de los resultados finales de cada expediente al cerrarlo (`CierreExpediente`), la publicación del
padrón por programa y ejercicio (`PadronPublicacion`; el padrón se calcula en cada consulta) y el informe anual al Comité con la
fecha y la hora de su envío y de su recepción, y la sesión en que se presenta (`InformeAnual`).

```mermaid
erDiagram
  Acuse |o--o{ CierreExpediente : acuse
  Acuse |o--o{ InformeAnual : acuse
  Acuse |o--o{ InformeAnual : acuse_recepcion
  Acuse |o--o{ PadronPublicacion : acuse
  Acuse |o--o{ SesionComite : acuse_acta
  Acuse |o--o{ SesionComite : acuse_convocatoria
  Ejercicio ||--o{ Expediente : ejercicio
  Ejercicio ||--o{ SesionComite : ejercicio
  Ejercicio ||--o| InformeAnual : ejercicio
  Ejercicio ||--o| PadronPublicacion : ejercicio
  Expediente |o--o{ Acuse : expediente
  Expediente ||--o| CierreExpediente : expediente
  SesionComite |o--o{ InformeAnual : sesion
  SesionComite {
    int id PK
    int ejercicio_id FK
    texto tipo
    texto caracter
    texto numero
    fecha_hora fecha_hora
    texto lugar
    texto orden_del_dia
    int acuse_convocatoria_id FK
    int acuse_acta_id FK
  }
  Acuse {
    int id PK
    texto folio UK
    int expediente_id FK
    texto referencia
    texto tipo
    texto titulo
    fecha_hora fecha_hora
    texto destinatario
    json contenido
  }
  Ejercicio {
    int id PK
    int anio
    bool vigente
    texto fuente
    texto archivo_reglas
    fecha_hora reglas_cargadas
    json datos
  }
  Expediente {
    int id PK
    texto folio UK
    int ejercicio_id FK
    bool es_refrendo
    bool con_representante_legal
    decimal superficie_solicitada_ha
    fecha_hora fecha_recepcion
    fecha_hora enviado_direccion
    texto observaciones
  }
  CierreExpediente {
    int id PK
    int expediente_id FK
    texto tipo
    json resumen
    texto motivo
    fecha_hora cerrado_en
    int acuse_id FK
  }
  InformeAnual {
    int id PK
    int ejercicio_id FK
    json resumen
    archivo archivo
    texto huella
    fecha_hora enviado_en
    int acuse_id FK
    int sesion_id FK
    fecha_hora recibido_en
    int acuse_recepcion_id FK
    texto observaciones
  }
  PadronPublicacion {
    int id PK
    int ejercicio_id FK
    fecha_hora publicada_en
    int acuse_id FK
    texto fundamento
  }
```
