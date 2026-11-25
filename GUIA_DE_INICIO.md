# Guía de inicio (versión del sprint 2)

Esta rama (`sprint-2`) guarda el proyecto tal como quedó al cerrar el **sprint 2** (16 de noviembre de 2026), con los
ajustes por las observaciones del profesor del 23 de noviembre. Abarca:

- **Lo del sprint 1:** la recepción de solicitudes, la validación, los dictámenes y las sesiones del Comité
  (reasignaciones e incidentes incluidas).
- **Publicación y contrato (módulo M3):** publicación de resultados con su página pública, modelos y elaboración del
  contrato, firma, y Vale de Planta con la salida del vivero.
- **Pagos (módulo M5):** solicitud de pago, pago de la ministración, remisión a la Fiduciaria y cheques de PSAHEM.
- **Cuatro programas con reglas cargadas:** Capturando Carbono, Plantaciones Sustentables, Restauración
  Hidrológico-Forestal y PSAHEM.
- **Calculadora forestal:** la masa forestal por año, el balance entre dos años con su histograma y la capa de
  incendios.

Falta lo del sprint 3 (ejecución, seguimiento y cierre), que está en la rama `main` con las 26 historias.

Lo que hace cada pantalla está en el [Manual de usuario](MANUAL_DE_USUARIO.md). Esta guía dice cómo ponerlo a
funcionar:

1. **Sistema de programas** (carpeta `sistema/`): aplicación web que se levanta con Docker y se abre en el navegador.
2. **Calculadora forestal** (carpeta `docs/`): página estática con el mapa de la masa forestal. No necesita Docker.

---

## 1. Sistema de programas

### 1.1 Lo que se necesita

| Qué | Para qué | Notas |
| --- | --- | --- |
| **Git** | Bajar el código | Cualquier versión reciente. |
| **Docker** con **Compose 2.24 o posterior** | Correr la base de datos, la aplicación y el servidor web | Ver abajo cómo instalarlo en Windows. |
| Unos **3 GB libres** en disco | Imágenes de Docker y base de datos | La imagen de pruebas, opcional, ocupa más. |
| **Internet** la primera vez | Descargar las imágenes de Docker y las bibliotecas de Python | Después solo hace falta para el mapa base de fondo. |

Para comprobar que Docker está listo:

```bash
docker compose version
```

Debe decir 2.24 o un número mayor.

#### Windows: Docker dentro de WSL

En el equipo donde se desarrolló, Docker corre dentro de WSL (Ubuntu 24.04), sin Docker Desktop. Una vez por equipo:

1. En PowerShell como administrador, instala WSL con Ubuntu y reinicia cuando lo pida:

   ```powershell
   wsl --install -d Ubuntu-24.04
   ```

2. Abre «Ubuntu» desde el menú Inicio, crea tu usuario y escribe:

   ```bash
   sudo apt update
   sudo apt install -y docker.io docker-compose-v2
   sudo usermod -aG docker $USER
   ```

3. Cierra Ubuntu, en PowerShell escribe `wsl --shutdown` y vuelve a abrir Ubuntu. Comprueba con
   `docker compose version`.

Con Docker Desktop también funciona: los comandos de abajo se escriben igual en su terminal. En Linux, instala
`docker.io` y `docker-compose-v2` (o Docker Engine desde docker.com). En macOS, usa Docker Desktop.

### 1.2 Bajar esta versión

```bash
git clone https://github.com/Zavjosh05/FEPI.git
cd FEPI
git checkout sprint-2
```

En Windows con WSL, el repositorio puede quedar en una carpeta de Windows, por ejemplo
`C:\Users\<usuario>\Documents\GitHub\FEPI`, y dentro de Ubuntu se llega a ella con
`/mnt/c/Users/<usuario>/Documents/GitHub/FEPI`.

### 1.3 Levantar el sistema

Desde la carpeta `sistema/`:

```bash
cd sistema
docker compose up --build
```

En Windows, desde PowerShell, sin abrir Ubuntu:

```powershell
wsl -e bash -lc "cd /mnt/c/Users/<usuario>/Documents/GitHub/FEPI/sistema && docker compose up --build"
```

**La primera vez tarda varios minutos**: construye la imagen y, al arrancar, crea la base de datos, carga los
catálogos (municipios y Delegaciones), las reglas de Capturando Carbono y los datos de demostración. Las siguientes
veces arranca en menos de un minuto.

El sistema está listo cuando el navegador abre **http://localhost:8080/entrar/**. Deja abierta la ventana donde corre
`docker compose`: ahí se ve lo que pasa y, en WSL, cerrarla puede apagar Ubuntu y con él el sistema.

### 1.4 Entrar

Todas las cuentas de demostración usan la contraseña **`Probosque2026`**. Es solo para demostración: nunca la uses
en un servidor real.

| Usuario | Unidad | Qué hace en esta versión |
| --- | --- | --- |
| `del_amecameca`, `del_toluca`, `del_valle` | Delegaciones Regionales Forestales Amecameca, Toluca y Valle de Bravo | Registran solicitudes, revisan requisitos, levantan el polígono, notifican resultados y avisos de pago, recaban la firma del contrato, entregan el Vale de Planta, emiten el oficio de solicitud de pago y entregan los cheques; cada Delegación ve solo lo suyo |
| `dir_drff` | Dirección de Restauración y Fomento Forestal | Valida o avisa faltantes, dictamen técnico, publica los listados, elabora y envía los contratos, solicita las ministraciones y cumple acuerdos (CC, MFS, PS, RHF y PSAHEM) |
| `dir_dpf` | Dirección de Protección Forestal | Lo mismo para Guardabosques (sin reglas cargadas todavía) |
| `juridica` | Unidad Jurídica | Dictamen jurídico, Listado de Personas Beneficiarias Incumplidas y validación de los modelos de contrato |
| `comite` | Secretaría Técnica del Comité | Sesiones de aprobación y de seguimiento; en PSAHEM, solicita a la Fiduciaria el pago de las solicitudes aceptadas |
| `finanzas` | Dirección de Administración, Finanzas y de Gestión Documental | Revisa las solicitudes de pago (acepta o devuelve) y registra los pagos |
| `vivero` | Vivero (demostración) | Valida el Vale de Planta y registra la salida de planta |
| `fiduciaria` | Fiduciaria | PSAHEM: emite el cheque de cada ministración y lo envía a la Delegación |
| `admin` | Superusuario | Administración de catálogos en http://localhost:8080/admin/ |

Para cambiar de unidad, sal con «Salir» y entra con otro usuario. Cualquier persona, sin iniciar sesión, puede
consultar los resultados publicados en http://localhost:8080/contrato/resultados/ (hay un enlace en la pantalla de
entrada).

**Fechas de la demostración.** Los datos de ejemplo se cargan con un calendario simulado de la Convocatoria 2026:
cada paso ocurre en la fecha que le toca (recepción en febrero, dictámenes en abril y mayo, sesiones del Comité,
publicaciones y contratos hasta el **19 de noviembre de 2026**, la «fecha de corte»). Los plazos que corren desde
entonces (firma del contrato, vigencia del Vale de Planta, cobro del cheque) se miden con el reloj real: según el día
en que pruebes, algunos aparecerán vencidos, como en cualquier expediente real.
Por eso los contratos que la demostración dejó por firmar el 19 de noviembre ya aparecen «Sin firma en plazo»: para probar una
firma, una publicación de Plantaciones Sustentables o una reasignación con datos de hoy, la
[secuencia de prueba del sprint 2](datos_prueba/sprint_2/SECUENCIA_DE_PRUEBA.md) trae un script que los agrega (sección 2 de la
secuencia).

### 1.5 Detener, volver a empezar y borrar

| Para | Comando, desde `sistema/` |
| --- | --- |
| Detener | `Ctrl+C` en la ventana donde corre y luego `docker compose down` |
| Volver a levantar | `docker compose up` (los datos se conservan) |
| Borrar todo y empezar de cero | `docker compose down -v` y luego `docker compose up --build` |
| Correr en segundo plano | `docker compose up -d --build`; ver lo que pasa con `docker compose logs -f web` |

`down -v` borra la base de datos y los archivos subidos; al volver a levantar, la demostración se carga de nuevo.

**Después de los ajustes del 23-nov** (observaciones del profesor) hay tablas nuevas y la demostración cambió: si ya
tenías el sistema levantado con datos, usa `docker compose down -v` y `docker compose up --build` para que los dictámenes
de ejemplo tengan su documento en PDF, la revisión de la propiedad y la reasignación.

**Si en el mismo equipo conviven varias ramas** (por ejemplo, `sprint-2` desplegada en su propia carpeta junto a
`main` o `sprint-1`): el archivo `docker-compose.yml` fija el nombre de proyecto `probosque`, así que todas usarían los
mismos contenedores y los mismos volúmenes, y chocarían. Para separarlas, da a cada rama su propio nombre de proyecto
con `-p` en **todos** los comandos de Compose:

```bash
cd sistema
docker compose -p probosque_s2 up --build          # levantar
docker compose -p probosque_s2 logs -f web         # ver lo que pasa
docker compose -p probosque_s2 down                # detener (con -v borra también la base y los archivos)
```

Con `-p` los volúmenes y la red se llaman `probosque_s2_…` y no se mezclan con los de otra rama. Lo que `-p` **no**
separa es el puerto: todas publican el 8080, así que solo una puede estar levantada a la vez (o cambia el puerto como
dice la sección 1.7). Las imágenes tampoco se separan (`probosque-sistema:0.1` y `probosque-sistema-pruebas:0.1`): al
cambiar de rama, levanta con `--build`.

### 1.6 Configuración (opcional)

Sin configuración, el sistema usa valores de desarrollo. Para cambiarlos, copia `sistema/.env.ejemplo` a
`sistema/.env` y edítalo: clave secreta de Django, servidores permitidos, contraseña de la base de datos, mapa base
y `CARGAR_DEMO` (0 para arrancar sin datos de ejemplo sobre una base vacía). La contraseña de la base se fija cuando
la base se crea: si la cambias después, borra la base con `docker compose down -v`.

### 1.7 Si algo falla

| Síntoma | Causa probable y qué hacer |
| --- | --- |
| `docker: command not found` o `permission denied` | Docker no está instalado, o tu usuario no está en el grupo `docker`: repite el paso 2 de 1.1 y `wsl --shutdown`. |
| `port is already allocated` o la página no abre | Otro programa usa el puerto 8080. Ciérralo, o cambia `"8080:80"` en `sistema/docker-compose.yml` por, por ejemplo, `"8090:80"`, y entra por ese puerto. |
| La página da error 502 o no deja entrar | La primera carga sigue en curso. Espera a que la ventana de `docker compose` deje de escribir y recarga. |
| Ves otra versión del sistema | Faltó `--build`, o quedó corriendo la de otra rama (sección 1.5). |
| El sistema se apagó solo en Windows | WSL apaga Ubuntu cuando no hay ventanas suyas abiertas. Deja abierta la ventana de `docker compose up`. |
| Quieres ver qué falló | `docker compose logs web`. |

### 1.8 Pruebas automáticas (opcional)

Desde `sistema/`, la corrida completa de esta versión (473 pruebas, con Chromium para los recorridos; unos
6 minutos: 442 rápidas y 31 recorridos de navegador):

```bash
docker compose -p probosque_s2 --profile pruebas run --rm pruebas
```

Si una corrida anterior se interrumpió, puede quedar una base de pruebas a medias y la siguiente falla con «database
… already exists»: corre `docker compose -p probosque_s2 down`, o agrega `--create-db` a `pytest`. Corre un solo comando
de Docker a la vez: dos corridas simultáneas chocan en los nombres de las bases de prueba.

Al terminar, `docker compose -p probosque_s2 down`. Las variantes están en [`sistema/README.md`](sistema/README.md), sección «Cómo
probar».

---

## 2. Calculadora forestal

La página ya está generada en el repositorio; no hace falta correr la calculadora para verla.

**Opción A, archivo único.** Abre [`docs/mapa_edomex.html`](docs/mapa_edomex.html) con doble clic. Trae todos los
datos adentro y funciona sin servidor.

**Opción B, sitio por partes** (`docs/calculadora/`, que carga los datos conforme se consultan; es la que trae el
balance entre dos años con su histograma y la capa de incendios). Necesita servirse por HTTP. Con Python 3, desde la raíz del repositorio:

```bash
python -m http.server 8766 --bind 127.0.0.1 --directory docs/calculadora
```

y abre **http://127.0.0.1:8766/**. Se detiene con `Ctrl+C`. Las dos opciones necesitan internet para cargar las
bibliotecas del mapa.

**Volver a calcular** (opcional y pesado): requiere Python 3.13 y `pip install -r requirements.txt`; las
instrucciones están en el [`README.md`](README.md), secciones «Instalación» y «Uso». Las pruebas de la página corren
con `pytest pruebas/calculadora` (43 pruebas: 15 de la masa por año, 13 del balance y 15 de los incendios).

---

## 3. Dónde está cada cosa

| Qué | Dónde |
| --- | --- |
| Manual de usuario de esta versión | [`MANUAL_DE_USUARIO.md`](MANUAL_DE_USUARIO.md) |
| Datos de prueba y secuencia para simular cada función del sprint 2 | [`datos_prueba/sprint_2/SECUENCIA_DE_PRUEBA.md`](datos_prueba/sprint_2/SECUENCIA_DE_PRUEBA.md) |
| Los del sprint 1 (polígonos, documentos y fichas), que la secuencia del sprint 2 también usa | `datos_prueba/sprint_1/` |
| Planeación del sprint 2 y tareas por persona | `entregas/sprint_2/planeacion/` |
| Resumen del sprint 2 (PDF con diagramas y capturas) | `entregas/sprint_2/Resumen_sprint_2.pdf` |
| Capturas de cada pantalla | `entregas/sprint_2/capturas/` (sprint 2) y `entregas/sprint_1/capturas/` (sprint 1) |
| Detalle técnico, decisiones y pendientes con el cliente | [`sistema/README.md`](sistema/README.md) |
| Reglas de cada programa, con numeral y línea de las Reglas de Operación | `sistema/reglas/CC.json`, `PS.json`, `RHF.json` y `PSA.json` |
| Modelo de datos | `sistema/docs/modelo_datos.md` |
| Avance y decisiones | `entregas/AVANCE.md`, `entregas/BITACORA.md` |
