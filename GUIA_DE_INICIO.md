# Guía de inicio (versión del sprint 1)

Esta rama (`sprint-1`) guarda el proyecto tal como quedó al cerrar el **sprint 1** (14 de noviembre de 2026): la
recepción de solicitudes, la validación, los dictámenes y las sesiones del Comité, con el programa Capturando
Carbono, más la consulta de la masa forestal por año en la Calculadora. La versión completa, con las 26 historias,
está en la rama `main`.

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
git checkout sprint-1
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
| `del_amecameca` | Delegación Regional Forestal Amecameca | Registra solicitudes, revisa requisitos, levanta el polígono, envía a la Dirección y notifica |
| `del_toluca`, `del_valle` | Delegaciones Toluca y Valle de Bravo | Lo mismo; cada Delegación ve solo lo suyo |
| `dir_drff` | Dirección de Restauración y Fomento Forestal | Valida o avisa faltantes, dictamen técnico, listado preliminar y cumple acuerdos |
| `dir_dpf` | Dirección de Protección Forestal | Lo mismo para Guardabosques (sin reglas cargadas todavía) |
| `juridica` | Unidad Jurídica | Dictamen jurídico y Listado de Personas Beneficiarias Incumplidas |
| `comite` | Secretaría Técnica del Comité | Sesiones de aprobación y de seguimiento |
| `fiduciaria` | Fiduciaria | Vería las instrucciones de pago que acuerda el Comité de PSAHEM; en esta versión PSAHEM no tiene reglas, así que la demostración no trae ninguna |
| `admin` | Superusuario | Administración de catálogos en http://localhost:8080/admin/ |

`finanzas` y `vivero` existen pero no tienen tareas en esta versión (llegan en el sprint 2). Para cambiar de unidad,
sal con «Salir» y entra con otro usuario.

**Fechas de la demostración.** En esta versión los datos de ejemplo se fechan el día en que se cargan, salvo
algunos plazos que se arman hacia atrás para que haya casos vencidos.

### 1.5 Detener, volver a empezar y borrar

| Para | Comando, desde `sistema/` |
| --- | --- |
| Detener | `Ctrl+C` en la ventana donde corre y luego `docker compose down` |
| Volver a levantar | `docker compose up` (los datos se conservan) |
| Borrar todo y empezar de cero | `docker compose down -v` y luego `docker compose up --build` |
| Correr en segundo plano | `docker compose up -d --build`; ver lo que pasa con `docker compose logs -f web` |

`down -v` borra la base de datos y los archivos subidos; al volver a levantar, la demostración se carga de nuevo.

**Si en el mismo equipo usas también la versión de `main`:** las dos usan los mismos nombres de contenedores, de
imágenes y de volúmenes. Al cambiar de una a otra, detén la que corre con `docker compose down -v` y levanta la otra
con `--build`.

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

Desde `sistema/`, la corrida completa de esta versión (128 pruebas, unos 2 minutos, con Chromium para los
recorridos):

```bash
docker compose --profile pruebas run --rm pruebas
```

Al terminar, `docker compose down`. Las variantes están en [`sistema/README.md`](sistema/README.md), sección «Cómo
probar».

---

## 2. Calculadora forestal

La página ya está generada en el repositorio; no hace falta correr la calculadora para verla.

**Opción A, archivo único.** Abre [`docs/mapa_edomex.html`](docs/mapa_edomex.html) con doble clic. Trae todos los
datos adentro y funciona sin servidor.

**Opción B, sitio por partes** (`docs/calculadora/`, la versión de esta historia, que carga los datos conforme se
consultan). Necesita servirse por HTTP. Con Python 3, desde la raíz del repositorio:

```bash
python -m http.server 8766 --bind 127.0.0.1 --directory docs/calculadora
```

y abre **http://127.0.0.1:8766/**. Se detiene con `Ctrl+C`. Las dos opciones necesitan internet para cargar las
bibliotecas del mapa.

**Volver a calcular** (opcional y pesado): requiere Python 3.13 y `pip install -r requirements.txt`; las
instrucciones están en el [`README.md`](README.md), secciones «Instalación» y «Uso». Las pruebas de la página corren
con `pytest pruebas/calculadora` (15 pruebas).

---

## 3. Dónde está cada cosa

| Qué | Dónde |
| --- | --- |
| Manual de usuario de esta versión | [`MANUAL_DE_USUARIO.md`](MANUAL_DE_USUARIO.md) |
| Datos de prueba y secuencia para simular cada función | [`datos_prueba/sprint_1/SECUENCIA_DE_PRUEBA.md`](datos_prueba/sprint_1/SECUENCIA_DE_PRUEBA.md) |
| Planeación del sprint 1 y tareas por persona | `entregas/sprint_1/planeacion/` |
| Resumen del sprint 1 (PDF con diagramas y capturas) | `entregas/sprint_1/Resumen_sprint_1.pdf` |
| Capturas de cada pantalla | `entregas/sprint_1/capturas/` |
| Detalle técnico, decisiones y pendientes con el cliente | [`sistema/README.md`](sistema/README.md) |
| Reglas de Capturando Carbono, con numeral y línea de las Reglas de Operación | `sistema/reglas/CC.json` |
| Modelo de datos | `sistema/docs/modelo_datos.md` |
| Avance y decisiones | `entregas/AVANCE.md`, `entregas/BITACORA.md` |
