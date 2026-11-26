# Secuencia de prueba del sprint 2

Cómo simular a mano, en el navegador, todas las funciones del sprint 2 (publicación, contrato, pagos y Calculadora) con los
datos de prueba de esta carpeta. Cada escenario dice quién entra, qué hace, con qué archivo y **qué debe pasar**; si el
sistema hace otra cosa, es un hallazgo.

El recorrido va, por usuario, **desde la solicitud autorizada hasta el pago**: un programa estatal (Plantaciones
Sustentables, con Vale de Planta y pago por transferencia) y PSAHEM (con la Fiduciaria y el cheque), más la baja y la
reasignación con contrato, el vale vencido (RHF se repone, PS no) y la Calculadora. Para llegar a «autorizada» desde cero,
con una solicitud capturada por la ventanilla, está la [secuencia del sprint 1](../sprint_1/SECUENCIA_DE_PRUEBA.md)
(escenarios A y H).

## 1. Qué datos de prueba hay

| Fuente | Qué trae | Para qué sirve |
| --- | --- | --- |
| **Demostración** (`cargar_demo`, se carga sola al levantar el sistema) | Lo del sprint 1 más solicitudes de PS, RHF y PSAHEM con su sesión de aprobación detenidas en cada punto de la publicación, el contrato y los pagos, con un calendario simulado de la Convocatoria 2026 cuya fecha de corte es **el día en que se carga** | Ver cada pantalla con datos y revisar casos que no se arman rápido: contrato por firmar a un día hábil de vencer, vale vigente y vencido, contrato sin firma en plazo, cheque por vencer |
| **Esta carpeta** (`datos_prueba/sprint_2/`) | Cinco documentos PDF de prueba (contrato firmado, carta compromiso, comprobante de cuenta y dos documentos de sesión) y un script que agrega dos casos de PS **con la fecha de hoy** | Subir archivos y recorrer de punta a punta lo que la demostración no trae: una solicitud de PS por publicar y una baja con reasignación desde la Lista de espera de PS |
| **Datos del sprint 1** (`datos_prueba/sprint_1/`) | Polígonos, PDF de requisitos y fichas de solicitudes | Llevar una solicitud nueva hasta su autorización (secuencia del sprint 1) |
| **Pruebas automáticas** (`sistema/pruebas/`) | 473 pruebas que crean sus propios datos, entre ellas los recorridos completos del sprint 2 por servicios y por la interfaz | Comprobar el sistema sin intervención (Guía de inicio, sección 1.8) |

### Contenido de esta carpeta

| Archivo | Qué es |
| --- | --- |
| `documentos/contrato_firmado_de_prueba.pdf` | El contrato firmado digitalizado que se sube en «Registrar la firma» |
| `documentos/carta_compromiso_de_prueba.pdf` | La carta compromiso para entregar un Vale de Planta antes de firmar el contrato |
| `documentos/comprobante_cuenta_bancaria.pdf` | El comprobante de la cuenta bancaria de la pestaña «Pagos» (CC, PS y RHF) |
| `documentos/documento_de_sesion_casos_de_seguimiento.pdf` | Documento de la convocatoria de una sesión de seguimiento |
| `documentos/documento_de_sesion_instruccion_de_pago.pdf` | Documento de la sesión en la que el Comité instruye el pago de PSAHEM |
| `preparar_casos_ps.py` | Agrega a la demostración *Plantación Cumbres* (PS aprobada, por publicar) y el caso de la baja con contrato: *Vereda Alta* (con contrato en la Delegación), *Cañada Honda* (primera de la Lista de espera) y una sesión de seguimiento por cerrar |
| `generar_datos_prueba.py` | Vuelve a crear los PDF de `documentos/` (`python datos_prueba/sprint_2/generar_datos_prueba.py`, solo necesita matplotlib) |

Los requisitos de las solicitudes (si se capturan desde cero) usan los PDF de `datos_prueba/sprint_1/documentos/`. Todos los
nombres son inventados.

**Por qué el script.** La demostración se carga con un calendario simulado cuya fecha de corte es el día de la carga
(D-32): recién levantada, *Plantación Los Pinos* está por firmar a un día hábil de vencer (sirve para registrar una firma ese
día), *Cañada Seca* ya venció sin firma, el vale de *Mirador de los Pinos* está vigente y el de *Ladera Verde* vencido, y el
cheque de *Loma Verde* está por vencer. Lo que la demostración no trae es un caso para recorrer de punta a punta: ya publicó
PS, RHF y CC (no queda nada de PS por publicar) y la Lista de espera de PS está vacía. El script crea esos dos casos con la hora
de hoy. Si se prueba días después de la carga, los plazos de la demostración siguen el reloj real: *Plantación Los Pinos*,
*Rancho La Huerta* y *Barranca Honda* quedarán «Sin firma en plazo» en pocos días hábiles (*Plantación Los Pinos*, al segundo
día hábil después de la carga); para tenerla fresca, vuelve a levantar el sistema desde cero (`down -v`).

**Comprobado el 25 de noviembre de 2026** en el navegador (Chromium con Playwright, sobre la demostración cargada y el script
corrido, con las mismas pantallas que usa una persona): los escenarios A, B, C, D, E y F de abajo, paso por paso, y la
Calculadora, con las cifras que se citan. Lo que no coincidía con la primera redacción quedó corregido en este documento.

## 2. Antes de empezar

1. Levanta el sistema como dice la [Guía de inicio](../../GUIA_DE_INICIO.md). Si conviven varias ramas, usa su nombre de
   proyecto: `docker compose up --build` desde `sistema/` (en PowerShell, `wsl docker compose up --build`). Para partir de
   la demostración limpia: `docker compose down -v` y de nuevo `up --build`.
2. Con el sistema ya levantado y la demostración cargada, **corre una sola vez** el script de esta carpeta, desde `sistema/`:

   ```bash
   docker compose exec -T web python manage.py shell < ../datos_prueba/sprint_2/preparar_casos_ps.py
   ```

   Debe terminar con «Listo. Caso 1: … Plantación Cumbres …; Caso 2: … Vereda Alta …, … Cañada Honda …». Si lo corres otra vez
   dice «Ya estaba preparado». En PowerShell no se puede usar `<` para leer un archivo; desde `sistema/` escribe:

   ```powershell
   wsl sh -c "docker compose exec -T web python manage.py shell < ../datos_prueba/sprint_2/preparar_casos_ps.py"
   ```
3. Abre http://localhost:8080/entrar/. Contraseña de todos los usuarios: `Probosque2026`. Para cambiar de unidad: **Salir** y
   entra con el usuario que indica cada paso.
4. Ten a la mano la carpeta `documentos/` de esta carpeta.

> **Sobre los folios.** Los folios (por ejemplo `PS-2026-AME-0008`) dependen de lo que ya haya en la base; los escenarios
> nombran a cada solicitud por su **predio** (se busca en la bandeja con la casilla «Buscar»).
>
> **Sobre las fechas.** Los plazos que corren desde hoy (10 días hábiles para firmar, 30 días para recoger la planta en PS, 3
> meses para cobrar un cheque) vencerán en la fecha que muestre cada pantalla. Si repites la secuencia otro día, vuelve a
> levantar el sistema desde cero (`down -v`, con lo que la demostración toma la nueva fecha de corte) y a correr el script.
> La fecha de corte no baja del 19-nov-2026 ni pasa del 31-dic-2026; `DEMO_FECHA_CORTE=AAAA-MM-DD` fija otra en ese rango.

## 3. Escenarios

Los escenarios A, B, C y E usan solicitudes distintas y se pueden recorrer en cualquier orden; D usa casos de la
demostración que no se tocan en los otros.

### Escenario A. PSAHEM: de la solicitud autorizada al cheque entregado

Solicitud de la demostración *Bosque El Zarco* (PSAHEM, Delegación Toluca, 30 ha; aprobada por el acta del Comité, sin
publicar). Usuarios: `dir_drff`, `del_toluca`, `comite`, `finanzas` y `fiduciaria`.

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| A1 | `dir_drff` | En la bandeja, el panel **Listados autorizados por publicar**; abre *Bosque El Zarco* (estado «Aprobada») y el botón **Publicar los resultados**. Pulsa **Publicar los listados** | La pantalla dice «Sin fecha en las reglas» (las ROP no fijan fecha para publicar). Queda **Publicada**, con fecha y hora, su acuse `AC-…` y, abajo, un aviso por solicitud («Avisos enviados a las Delegaciones»). El expediente sale de la bandeja de la Dirección |
| A2 | sin iniciar sesión | **Salir**; en la entrada, el enlace **Consulte los resultados publicados**. Elige PSAHEM con **Ver listados**; busca el folio de *Bosque El Zarco* con **Buscar** | Están los cuatro programas con su última publicación. El listado de personas beneficiarias muestra el nombre; los otros solo folio, predio y municipio; nunca CURP, RFC ni documentos. La búsqueda deja una sola fila |
| A3 | `del_toluca` | **Iniciar sesión**; el expediente está en «Resultados publicados». Botón **Notificar a la persona beneficiaria**: en el aviso del resultado, **Registrar entrega**, medio «En persona», **Registrar notificación** | Queda la fecha y la hora de la notificación y su acuse. El expediente pasa a «Persona beneficiaria notificada» y a la bandeja de la Dirección |
| A4 | `dir_drff` | Abre el expediente y **Elaborar el contrato**. Revisa los datos que llevará el contrato y pulsa **Elaborar el contrato** | Muestra persona, predio, superficie aprobada (30 ha), monto ($105,000.00: $3,500.00 por hectárea) y ministraciones (1.ª 70 % $73,500.00; 2.ª 30 % $31,500.00). PSAHEM ya trae un modelo validado, así que lo ofrece. Queda «Elaborado» con su PDF `CTO-PSA-2026-NNNN` |
| A5 | `dir_drff` | **Enviar a la Delegación** | Queda la fecha y la hora del envío con su acuse; el expediente pasa a «Contrato en la Delegación» y sale de la bandeja de la Dirección |
| A6 | `del_toluca` | Abre el expediente y **Registrar la firma del contrato**. Escribe quién firma y sube `contrato_firmado_de_prueba.pdf`, **sin** marcar la verificación; **Registrar la firma** | Aparece la **verificación de firmas y sello** y no se recibe el contrato |
| A7 | `del_toluca` | Marca todos los puntos de la verificación, vuelve a elegir el archivo y **Registrar la firma** | «Contrato firmado», con fecha, hora y acuse; arriba se vieron las dos fechas del plazo («Fecha programada de firma» y «Vencimiento para liberar el recurso») |
| A8 | `del_toluca` | En la bandeja, el panel de contratos firmados por emitir el oficio de pago; **Emitir el oficio** | Oficio `OFP-PSA-2026-NNNN` con su acuse. PSAHEM no pide comprobante de cuenta: paga con cheque |
| A9 | `dir_drff` | Abre el expediente («Contrato firmado») y **Solicitar la ministración 1**; en la lista de soportes ve el de la instrucción del Comité; pulsa **Enviar la solicitud a Administración y Finanzas** | No deja: el soporte «Instrucción de pago del Comité Técnico a la Fiduciaria» dice «Falta» («El Comité Técnico aún no instruye el pago de la ministración 1…»). Los otros tres soportes (contrato o convenio, oficio y dictámenes) están «Completo» |
| A10 | `comite` | Menú **Dictamen y Comité › Sesiones del Comité** → **Nueva sesión de seguimiento**: programa PSAHEM 2026, fecha **dentro de 5 días hábiles o más**, lugar y orden del día. **Crear sesión**; agrega `documento_de_sesion_instruccion_de_pago.pdf` y **Enviar convocatoria**. En **Registrar acuerdo**: tipo «Instrucción de pago», el texto del acuerdo, *Bosque El Zarco* y la ministración **1** | La convocatoria queda «Enviada»; el acuerdo aparece con «Ministración 1» y el área que lo cumple |
| A11 | `dir_drff` | Vuelve a **Solicitar la ministración 1** y **Enviar la solicitud a Administración y Finanzas** | Los cuatro soportes están completos. Queda «Enviada a Administración y Finanzas el…» con fecha, hora y acuse; el expediente pasa a «Ministración solicitada» |
| A12 | `finanzas` | Abre el expediente («Ministración solicitada») → **Revisar la solicitud de pago de la ministración 1** → **Aceptar la solicitud** | Queda «Aceptada». **No** hay formulario de pago (PSAHEM paga con cheque) y el expediente sale de la bandeja de Finanzas |
| A13 | `comite` | En la bandeja, el panel **Pagos por solicitar a la Fiduciaria**; abre el expediente → **Solicitar el pago a la Fiduciaria**; en **Oficio o referencia de la remisión** escribe `ST-FIPASAHEM/001/2026`; **Solicitar el pago** | Dice el plazo de **5 días hábiles** desde que el área envió la solicitud. Queda la fecha y la hora de la remisión y «en plazo» («cumplido en plazo»); el expediente pasa a «Remitida a la Fiduciaria» |
| A14 | `fiduciaria` | Abre el expediente («Remitida a la Fiduciaria») → **Emitir el cheque**: número `CHQ-PRUEBA-0001`, fecha de emisión de hoy; **Emitir el cheque**. Luego **Enviar el cheque a la Delegación** | El cheque queda a nombre de la persona y de su ministración 1 (importe igual al solicitado). Con el envío: fecha, hora y acuse; «Enviado a Delegación Regional Forestal Toluca» |
| A15 | `del_toluca` | En la bandeja, el panel **Cheques por entregar a las personas beneficiarias**; abre el expediente → **Registrar la entrega del cheque**: quién recibe; **Registrar la entrega** | Queda «Entregado el…» con fecha, hora y acuse y el mensaje «Debe cobrarlo a más tardar el…» (3 meses desde la entrega). El expediente queda «Cheque entregado». En el menú **Cheques**, la tabla «Entregados sin cobro» lo muestra con su vencimiento |
| A16 | cualquiera de la Dirección | Pestañas **Bitácora** y **Trazabilidad** del expediente (filtra por «Contrato», «Cheque», «Remisión a la Fiduciaria»…) | La bitácora trae cada paso de A1 a A15, en orden, con la unidad que lo hizo. La trazabilidad, cada alta y cada cambio de la publicación, el contrato, la firma, el oficio, la solicitud, la remisión y el cheque, con quién, cuándo y los valores |

### Escenario B. Plantaciones Sustentables: de la solicitud autorizada al pago

Caso 1 del script: *Plantación Cumbres* (Ozumba, Delegación Amecameca, 4 ha de plantación comercial; aprobada, sin publicar).
Usuarios: `dir_drff`, `del_amecameca`, `vivero` y `finanzas`.

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| B1 | `dir_drff` | Abre *Plantación Cumbres* → **Publicar los resultados** → **Publicar los listados** | Queda publicada con acuse. Entre los avisos de abajo, para Cumbres, el del resultado y la **Cita a firma del contrato** (solo en PS) |
| B2 | `del_amecameca` | Abre el expediente («Resultados publicados») → **Notificar a la persona beneficiaria**. Registra la entrega de **los dos avisos** (resultado y cita a firma), medio «Teléfono» | Cada uno queda con fecha, hora y acuse. Con el resultado notificado, el expediente pasa a «Persona beneficiaria notificada» |
| B3 | `dir_drff` | Abre el expediente → **Elaborar el contrato** → **Elaborar el contrato**; luego **Enviar a la Delegación** | PS ya trae un modelo de contrato validado por la Unidad Jurídica (se ofrece «Contrato de Adhesión PS 2026 (modelo de demostración)»). Queda el PDF `CTO-PS-2026-NNNN`, la fecha y la hora del envío y su acuse |
| B4 | `del_amecameca` | Abre el expediente → **Registrar la firma del contrato**. Mira las dos fechas. Escribe quién firma y pulsa **Registrar la firma** sin archivo | Las dos fechas coinciden: en PS ambas corren desde la publicación (10 días hábiles: «faltan 10 días háb.»). Sin archivo dice «Falta el archivo: el contrato firmado digitalizado» |
| B5 | `del_amecameca` | Sube `contrato_firmado_de_prueba.pdf` sin la verificación y luego con todos los puntos marcados | Primero pide la verificación y no se recibe; después queda «Contrato firmado», con fecha, hora y acuse |
| B6 | `del_amecameca` | En la bandeja, el panel **Contratos firmados por entregar su Vale de Planta**; abre *Plantación Cumbres*. Mira la **Planta propuesta**; elige un vivero, **Pino patula** 3000 y **Oyamel** 1400; **Entregar el vale** | La propuesta es **4400 piezas (1100 por hectárea × 4 ha aprobadas)**. El vale queda con su folio `VP-PS-2026-NNNN`, la fecha y la hora, el acuse y la vigencia («hasta el…», 30 días naturales); el expediente pasa a «Vale de Planta entregado» |
| B7 | `vivero` | En la bandeja, el panel **Vales de Planta vigentes por surtir** → **Abrir la salida de planta**. Escribe el folio del vale y **Validar el vale**; registra **Pino patula** 3000, luego **Oyamel** 9999 y después **Oyamel** 1400 | El vale se valida. La primera salida queda. La de 9999 se rechaza: «no se entrega más de lo autorizado» por especie. La de 1400 completa el vale y dice que el expediente pasó a «Planta entregada» |
| B8 | `del_amecameca` | Menú **Pagos**: el panel de contratos firmados por emitir el oficio; abre *Plantación Cumbres* → **Emitir el oficio** | Oficio `OFP-PS-2026-NNNN` con su acuse. Falta aún el comprobante de la cuenta |
| B9 | `dir_drff` | Abre el expediente («Planta entregada») → **Solicitar la ministración 1** → **Enviar la solicitud a Administración y Finanzas** | No deja: «No se puede enviar la solicitud: falta Comprobante de la cuenta bancaria…». La lista de soportes dice «Falta» en ese y quién lo resuelve (la Delegación) |
| B10 | `del_amecameca` | En la pestaña **Pagos** del expediente, sube `comprobante_cuenta_bancaria.pdf` y **Guardar** | Queda «Recibido el…» |
| B11 | `dir_drff` | Vuelve a **Solicitar la ministración 1** → **Enviar la solicitud a Administración y Finanzas** | Soportes completos. Queda «Enviada a Administración y Finanzas el…» con fecha, hora y acuse; estado «Ministración solicitada». El importe es el 70 % del monto |
| B12 | `finanzas` | Abre el expediente → **Revisar la solicitud de pago de la ministración 1**. Escribe una observación y **Devolver con observaciones** | La solicitud queda «Devuelta» con la observación y su acuse; vuelve a la bandeja del área responsable |
| B13 | `dir_drff` | Abre el expediente → **Corregir y reenviar la ministración 1** → **Enviar la solicitud a Administración y Finanzas** | Dice «envío 2» |
| B14 | `finanzas` | Revisa y **Aceptar la solicitud**. En **Registrar el pago de la ministración 1**: forma «Transferencia electrónica», una referencia, la fecha de hoy y el importe (ya viene el solicitado); **Registrar el pago** | Queda «Pagada», con la fecha del pago, su solicitud, la referencia y el acuse. Un importe distinto del solicitado no se acepta. El expediente pasa a «Ministración pagada» |
| B15 | `del_amecameca` | En la bandeja, el panel de notificaciones: el **Aviso de pago** de *Plantación Cumbres* (también habrá uno de otra solicitud de la demostración); regístralo con medio «Teléfono» | Queda la fecha y la hora de la notificación del pago a la persona |
| B16 | `dir_drff` | Pestañas **Bitácora** y **Trazabilidad** del expediente | Cada paso de B1 a B15 con su fecha y hora, en orden; en la trazabilidad, el vale, cada salida de planta, el oficio, el comprobante, la solicitud, la revisión y el pago |

### Escenario C. Modelos de contrato: registrar y validar

La demostración trae un modelo validado de CC, PS, RHF y PSAHEM, y una **plantilla base** «BORRADOR – modelo por validar» de
CC, PS y PSAHEM. Aquí se valida la de CC.

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| C1 | `dir_drff` | Menú **Publicación y contrato › Modelos** | La lista trae ocho modelos con su estado; las tres plantillas base dicen «Por validar» |
| C2 | `dir_drff` | Abre la **Plantilla base · Contrato de Adhesión** de CC 2026. En **Cambiar el texto**, borra la primera línea («BORRADOR – modelo por validar») y **Guardar versión nueva** | Quedan dos versiones: la 2 «Por validar». Mientras no se valide, no se elaboran contratos sobre ese modelo |
| C3 | `juridica` | En la bandeja, el panel **Modelos por validar** (tres); abre el de CC 2026 · versión 2. Elige **Validada**, escribe una observación y **Registrar la revisión** | La versión queda «Validada», con fecha, hora, quién la validó y la observación |

### Escenario D. Contrato sin firma en plazo y vale vencido

Todos son casos de la demostración (no se tocan en los otros escenarios).

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| D1 | `del_valle` | Abre *Cañada Seca* (PS) → **Registrar la firma del contrato** | El plazo dice «Vencimiento para liberar el recurso: 08/10/2026 vencido». La firma ya no se puede registrar: el contrato está señalado «sin firma en plazo» y el área responsable debe confirmar la liberación del recurso |
| D2 | `dir_drff` | Menú **Publicación y contrato › Firmas**; en «Sin firma en plazo · recurso por liberar», en la fila de *Cañada Seca*, escribe el **Motivo** y pulsa **Liberar el recurso** | Avisa «Recurso liberado (…)». La tabla «Sin firma en plazo» queda en 0 y aparece la sección «Recurso liberado» con el folio, la fecha, la hora y el motivo; el expediente pasa a «Recurso liberado», con acuse. El monto queda como recurso liberado para que el Comité lo reasigne (escenario E) |
| D3 | `vivero` | Menú **Planta**: escribe el folio del vale de *Ladera Verde* (PS) y **Validar el vale** | «El vale … venció el 05/11/2026 y un vale vencido no es válido: no se entrega planta». Explica que las Reglas de PS no prevén reponerlo (8.1.7 inciso e) |
| D4 | `del_toluca` | Abre el vale de *Ladera Verde* (menú **Vales**) | «Vencido · no válido» y la misma explicación; **no** hay botón para reponerlo |
| D5 | `del_valle` | Menú **Vales**: abre el vale original de *Cerro Gordo* (RHF) | El vale original, «Repuesto» (venció el 03/11/2026: se entregaron 600 de 1800), tiene una salida; el nuevo vale de reposición cubre **solo lo no entregado** (1200), vigente. RHF sí repone |

### Escenario E. Baja y reasignación con contrato

Caso 2 del script: *Vereda Alta* (PS, Delegación Toluca) es persona beneficiaria publicada, notificada y con su **contrato
enviado a la Delegación**; *Cañada Honda* (PS, Delegación Amecameca) es la primera de la Lista de espera; hay una **sesión de
seguimiento** de PS convocada y sin cerrar. Usuarios: `comite`, `del_toluca`, `dir_drff`, `del_amecameca`.

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| E1 | `comite` | Menú **Sesiones del Comité** → la sesión de seguimiento de PS 2026 por cerrar | Muestra la **Lista de espera** con *Cañada Honda* ($30,000.00) y el recurso liberado sin reasignar: $0.00 |
| E2 | `comite` | **Registrar acuerdo**: tipo «Desistimiento», causa y texto, expediente *Plantación El Cedro* (PS, con una ministración ya solicitada) | No deja: «Ya tiene una ministración solicitada o pagada: en lugar de la baja procede el reintegro…» |
| E3 | `comite` | El mismo acuerdo con *Vereda Alta* (causa: «Escrito de desistimiento…») | La persona sale de la lista («Baja · recurso liberado»); el recurso liberado sube a **$30,000.00**; aparece en los movimientos |
| E4 | `del_toluca` | Abre *Vereda Alta* y **Registrar la firma del contrato** (entrando por la dirección de la pantalla, porque el botón del expediente ya no aparece) | La pantalla ya no ofrece el formulario de firma: «El expediente está «Baja · recurso liberado»: solo se registra la firma de un contrato que ya llegó a la Delegación» |
| E5 | `comite` | Nuevo acuerdo «Reasignación» con *Cañada Honda* | Pasa de «Lista de espera» a «Aprobada (persona beneficiaria)»; el recurso liberado queda en $0.00; en los movimientos, quién sale y quién entra |
| E6 | `comite` | **Cerrar la sesión (acta registrada)** | «Sesión de seguimiento cerrada». Con una reasignación, el acta queda autorizada para publicar |
| E7 | `dir_drff` | En la bandeja, el panel **Listados autorizados por publicar** trae la sesión de seguimiento; ábrela y **Publicar los listados** | El listado de personas beneficiarias trae a *Cañada Honda* como «Reasignación». Al publicar pasa a «Resultados publicados», con su aviso y sus plazos de firma |
| E8 | `del_amecameca` | Notifica el resultado de *Cañada Honda* (menú **Notificaciones**) | «Persona beneficiaria notificada»: la Dirección ya puede elaborar su contrato (como en B3) |
| E9 | `dir_drff` | Menú **Listados › Beneficiarios**, programa **PS 2026** | *Cañada Honda* aparece resaltada con «Reasignación · acuerdo SO-PS-2026-…/002 (lugar 1 de la lista de espera)» y su situación («Resultados publicados · por notificar»); abajo, la tabla de las que salieron trae *Vereda Alta* con su acuerdo y causa, el recurso que liberó ($30,000.00) y la fecha |

### Escenario F. Calculadora forestal: balance entre dos años e incendios

Abre la página como dice la Guía de inicio, sección 2, en modo **Comparar años**.

| # | Qué hace | Qué debe pasar |
| --- | --- | --- |
| F1 | **Desde** 2024, **Hasta** 2025 | Bosque 467,955 → 466,058 ha; cambio neto −1,897 ha (−0.4 %); pérdida por incendio 0† (CONAFOR aún no publica los incendios de 2025), otras pérdidas 6,080 y ganancia 4,183 |
| F2 | **Balance del periodo** | Cuatro barras: Incendio 0†, Otras pérdidas −6,080, Ganancia +4,183, Cambio neto −1,897. «† Parcial: CONAFOR aún no publica los incendios de 2025…» |
| F3 | **Municipios según su cambio neto** (histograma) | «26 pierden bosque y 46 ganan, de 72 municipios con 500 ha o más de bosque inicial; los otros 53 no entran porque tienen menos.» **Ver como tabla** da los mismos conteos |
| F4 | **Desde** 2023, **Hasta** 2024 | Neto −5,194 ha (−1.1 %): incendio −711, otras pérdidas −9,436, ganancia +4,954. Histograma: 61 pierden y 9 ganan, de 70 municipios |
| F5 | Elige un municipio (por ejemplo, **Luvianos**) en la tabla o con **Buscar** | «Luvianos: bosque inicial 22,431 ha (2024) → bosque final 20,871 ha (2025); cambio neto −1,560 ha (−7.0 %). Quita la selección para ver el Estado.» Las barras: Incendio 0†, Otras pérdidas −1,710, Ganancia +150, Cambio neto −1,560 |
| F6 | Quita la selección del municipio. **Desde** 2023, **Hasta** 2025; en **Incendios del periodo**, **Ver los incendios y su tabla** | «1,092 incendios del periodo: CONAFOR reporta 52,655 ha de polígonos; 16,377 ha tienen dNBR ≥ 0.27, 8,408 ha dentro del bosque, y 361 ha de bosque quedaron sin copa al cierre». **Pérdida por incendio por año**: 2023 (nov-dic) 2 incendios, 2024 1,090 y 2025 «CONAFOR aún no publica los incendios de 2025», nunca cero |
| F7 | Vista **Incendios** del mapa | Un círculo por incendio, proporcional a lo quemado en el bosque; al tocar uno, su clave, fecha, municipio y hectáreas |
| F8 | En la tabla de incendios, pulsa el encabezado **Fecha** o **Reportadas (ha)** para ordenar (con un municipio elegido, la tabla trae solo los suyos) | Cada fila lleva fecha, municipio, hectáreas reportadas, quemadas en bosque, sin copa al cierre y clave (por ejemplo, 2024-03-27 Amatepec 6,961.1 ha, clave `24-12-0141`) |

### Escenario G. Permisos y trazabilidad

| # | Entra como | Qué hace | Qué debe pasar |
| --- | --- | --- | --- |
| G1 | `del_toluca` | Busca en la bandeja un folio de una Delegación distinta (por ejemplo, el de *Plantación Cumbres*) | No aparece: cada Delegación ve solo lo suyo |
| G2 | `del_toluca` | Escribe en el navegador `/contrato/modelos/` | Página «Acceso no permitido», con el botón para volver a la bandeja |
| G3 | `finanzas` | Escribe `/contrato/firmas/` | Igual: «Acceso no permitido» |
| G4 | cualquiera que vea el expediente | Pestaña **Trazabilidad** de cualquier expediente de los escenarios A o B | Cada alta y cambio con usuario y unidad, fecha y hora, y los campos que cambiaron (antes → después); también los registros de M3 y M5 |

## 4. Si algo no sale como dice la tabla

Anota el escenario y el paso, el usuario, el folio y lo que viste. Revisa la pestaña **Bitácora** del expediente y, si hubo un
error de la página, `docker compose logs web`. Para volver a empezar: `docker compose down -v`,
`docker compose up --build` y de nuevo el script de la sección 2.
