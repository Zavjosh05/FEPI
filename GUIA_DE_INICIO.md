# Guía de inicio

Cómo poner a funcionar en un equipo propio las dos partes de este repositorio:

1. **Sistema de programas** (carpeta `sistema/`): la aplicación web que lleva el trámite de los seis programas de
   PROBOSQUE, de la solicitud al padrón. Se levanta con Docker y se abre en el navegador.
2. **Calculadora forestal** (carpeta `docs/`): la página con el mapa de la masa forestal del Estado de México. Es una
   página estática: no necesita Docker.

Esta guía es para verlas funcionando. Para el detalle técnico (cómo se construyó, pruebas, decisiones) están
[`sistema/README.md`](sistema/README.md) y el [`README.md`](README.md) de la Calculadora.

---

## 1. Sistema de programas

### 1.1 Lo que se necesita

| Qué | Para qué | Notas |
| --- | --- | --- |
| **Git** | Bajar el código | Cualquier versión reciente. |
| **Docker** con **Compose 2.24 o posterior** | Correr la base de datos, la aplicación y el servidor web | Ver abajo cómo instalarlo en Windows. |
| Unos **3 GB libres** en disco | Imágenes de Docker y base de datos | La imagen de pruebas, opcional, ocupa 1.8 GB más. |
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

Con Docker Desktop también funciona: los comandos de abajo se escriben igual en su terminal.

En Linux, instala `docker.io` y `docker-compose-v2` (o Docker Engine desde docker.com). En macOS, usa Docker Desktop.

### 1.2 Bajar el código

```bash
git clone https://github.com/Zavjosh05/FEPI.git
cd FEPI
git checkout prototipos
```

Mientras los prototipos no se unan a `main`, todo está en la rama `prototipos`. En Windows con WSL, el repositorio
puede quedar en una carpeta de Windows, por ejemplo `C:\Users\<usuario>\Documents\GitHub\FEPI`, y dentro de Ubuntu se
llega a ella con `/mnt/c/Users/<usuario>/Documents/GitHub/FEPI`.

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

**La primera vez tarda varios minutos**: construye la imagen y, al arrancar, crea la base de datos, carga las reglas
de los seis programas y los datos de demostración. Las siguientes veces arranca en menos de un minuto.

El sistema está listo cuando el navegador abre **http://localhost:8080/entrar/**. Deja abierta la ventana donde corre
`docker compose`: ahí se ve lo que pasa y, en WSL, cerrarla puede apagar Ubuntu y con él el sistema.

### 1.4 Entrar

Todas las cuentas de demostración usan la contraseña **`Probosque2026`**. Es solo para demostración: nunca la uses
en un servidor real.

| Usuario | Unidad | Qué hace |
| --- | --- | --- |
| `del_amecameca` | Delegación Regional Forestal Amecameca | Ventanilla, notificaciones, firma, comprobaciones y verificación en campo |
| `del_toluca`, `del_valle` | Delegaciones Toluca y Valle de Bravo | Lo mismo; cada Delegación ve solo lo suyo |
| `dir_drff` | Dirección de Restauración y Fomento Forestal | Área responsable de CC, MFS, PS, RHF y PSAHEM: validación, dictamen, contrato, pagos y cierre |
| `dir_dpf` | Dirección de Protección Forestal | Área responsable de Guardabosques: evaluación de reportes |
| `juridica` | Unidad Jurídica | Dictamen jurídico, modelos de contrato y Listado de Incumplidas |
| `comite` | Secretaría Técnica del Comité | Sesiones, actas, acuerdos e informe anual |
| `finanzas` | Administración y Finanzas | Solicitudes de pago, pagos y depósitos de reintegro |
| `vivero` | Vivero | Vales de planta y salidas de planta |
| `fiduciaria` | Fiduciaria | Cheques de PSAHEM |

Para cambiar de unidad, sal con el botón «Salir» y entra con otro usuario. Cada usuario empieza en su **Bandeja**: lo
que le toca atender, con el panel «Por vencer».

Páginas que no piden cuenta:

| Página | Dirección |
| --- | --- |
| Resultados publicados | http://localhost:8080/contrato/resultados/ |
| Padrón de personas beneficiarias | http://localhost:8080/padron/ |
| Portal de personas beneficiarias (entrada) | http://localhost:8080/portal/entrar/ |

En el portal hay una cuenta de demostración activa: la de un Guardabosque, con usuario `SARM800101HMCNZR09` y la misma
contraseña.

**Por dónde empezar.** La sección «Recorrer el sistema completo» de [`sistema/README.md`](sistema/README.md) da el
orden de un trámite de Capturando Carbono, de la firma al padrón público, con el usuario de cada paso. En
`entregas/sprint_N/Resumen_sprint_N.pdf` están las pantallas de cada parte. Para saber qué hace cada unidad y cada botón, el
[Manual de usuario](MANUAL_DE_USUARIO.md).

**Sobre las fechas de la demostración.** Los datos de ejemplo están fechados en el calendario 2026 de cada
convocatoria, hasta el 19 de noviembre de 2026. El sistema usa la fecha real, así que en días posteriores verás más
plazos vencidos: es lo esperado. Para levantar el sistema sin datos de ejemplo, arráncalo con `CARGAR_DEMO=0` en el
archivo `.env` (sección 1.6) sobre una base vacía.

### 1.5 Detener, volver a empezar y borrar

| Para | Comando, desde `sistema/` |
| --- | --- |
| Detener | `Ctrl+C` en la ventana donde corre y luego `docker compose down` |
| Volver a levantar | `docker compose up` (los datos se conservan) |
| Levantar después de cambiar el código | `docker compose up --build` (sin `--build` corre la versión anterior) |
| Borrar todo y empezar de cero | `docker compose down -v` y luego `docker compose up --build` |
| Correr en segundo plano | `docker compose up -d --build`; ver lo que pasa con `docker compose logs -f web` |

`down -v` borra la base de datos y los archivos subidos. Al volver a levantar, la demostración se carga de nuevo.

### 1.6 Configuración (opcional)

Sin configuración, el sistema usa valores de desarrollo. Para cambiarlos, copia `sistema/.env.ejemplo` a
`sistema/.env` y edítalo. Ahí están la clave secreta de Django, los nombres de servidor permitidos, la contraseña de
la base de datos, el mapa base y `CARGAR_DEMO`. El archivo `.env` no se sube a git. La contraseña de la base se fija
cuando la base se crea: si la cambias después, borra la base con `docker compose down -v` antes de volver a levantar.

**Antes de ponerlo en un servidor real**: cambia la clave secreta y la contraseña de la base de datos, quita los
usuarios de demostración (`CARGAR_DEMO=0` sobre una base vacía) y configura HTTPS. El prototipo no se ha probado en
un servidor real.

### 1.7 Si algo falla

| Síntoma | Causa probable y qué hacer |
| --- | --- |
| `docker: command not found` o `permission denied` al usar Docker | Docker no está instalado, o tu usuario no está en el grupo `docker`: repite el paso 2 de 1.1 y cierra la sesión de Ubuntu (`wsl --shutdown`). |
| `port is already allocated` o la página no abre | Otro programa usa el puerto 8080. Ciérralo, o cambia `"8080:80"` en `sistema/docker-compose.yml` por otro puerto, por ejemplo `"8090:80"`, y entra por ese puerto. |
| La página da error 502 o no deja entrar | La primera carga sigue en curso. Espera a que la ventana de `docker compose` deje de escribir y recarga. |
| Ves una versión vieja después de actualizar el código | Faltó `--build`. |
| El sistema se apagó solo en Windows | WSL apaga Ubuntu cuando no hay ventanas suyas abiertas. Deja abierta la ventana donde corre `docker compose up`. |
| Quieres ver qué falló | `docker compose logs web` muestra lo que escribió la aplicación. |

### 1.8 Pruebas automáticas (opcional)

Desde `sistema/`, una corrida completa: unas 600 pruebas, de 7 a 8 minutos, con Chromium para las de navegador.

```bash
docker compose --profile pruebas run --rm pruebas
```

Al terminar, `docker compose down`. Las variantes (solo las rápidas, con capturas, con los PDF reales) están en
[`sistema/README.md`](sistema/README.md), sección «Cómo probar».

---

## 2. Calculadora forestal

La página ya está generada en el repositorio. No hace falta correr la calculadora para verla.

**Opción A, archivo único.** Abre [`docs/mapa_edomex.html`](docs/mapa_edomex.html) con doble clic. Trae todos los
datos adentro (unos 3.6 MB) y funciona sin servidor.

**Opción B, sitio por partes** (`docs/calculadora/`, la versión que carga los datos conforme se consultan). Necesita
servirse por HTTP. Con Python 3 instalado, desde la raíz del repositorio:

```bash
python -m http.server 8766 --bind 127.0.0.1 --directory docs/calculadora
```

y abre **http://127.0.0.1:8766/**. Se detiene con `Ctrl+C`. Si se publica la carpeta `docs/` con GitHub Pages, esta
es la versión que se ve en línea.

Las dos opciones necesitan internet para cargar las bibliotecas del mapa.

**Volver a calcular** (opcional y pesado): correr la calculadora sobre imágenes de satélite requiere Python 3.13,
`pip install -r requirements.txt` y, para el Estado completo, unas dos horas y 5 GB de memoria. Las instrucciones
están en el [`README.md`](README.md), secciones «Instalación» y «Uso». Con las dependencias instaladas y sin bajar
imágenes, se puede probar la lógica con datos inventados (unos 30 segundos):

```bash
python src/prototipo_masa_forestal.py demo
```

---

## 3. Dónde está cada cosa

| Qué | Dónde |
| --- | --- |
| Manual de usuario (qué hace cada unidad, paso a paso) | [`MANUAL_DE_USUARIO.md`](MANUAL_DE_USUARIO.md) |
| Código del sistema | `sistema/` |
| Reglas de cada programa, con numeral y línea de las Reglas de Operación | `sistema/reglas/` |
| Modelo de datos (diagramas entidad-relación) | `sistema/docs/modelo_datos.md` |
| Detalle técnico del sistema, usuarios y datos de demostración | `sistema/README.md` |
| Calculadora: código, página y resultados | `src/`, `docs/`, `resultados/` |
| Resumen de cada sprint (PDF con diagramas y capturas) | `entregas/sprint_1/`, `sprint_2/`, `sprint_3/` |
| Avance por tarea y decisiones | `entregas/AVANCE.md`, `entregas/BITACORA.md` |
