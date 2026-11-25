"""Generador de datos con semilla (G-02): crea solicitudes con los servicios del sistema, repartidas entre Delegaciones, municipios,
tipos de persona y modalidades, y avanzadas hasta estados distintos del trámite según una distribución fija. Usa el reloj simulado
(``nucleo/reloj.py``) para que cada paso caiga en el calendario de la Convocatoria 2026, igual que la demostración.

``manage.py generar_datos --programa CC --n 200 --semilla 7`` (o ``--programa todos``). La misma semilla da los mismos datos
(nombres, municipios, modalidades, superficies, fechas y estados). No se ejecuta al levantar el sitio: es una herramienta aparte.

Distribución (por solicitud, según su lugar en la lista; ver ``DISTRIBUCION``): recibida con la revisión a medias, recibida completa
con polígono, enviada a la Dirección, con aviso de faltantes, validada (en dictamen), dictaminada por llevar a sesión, y
aprobadas (o en lista de espera / no factibles) por una sesión del Comité, con sus resultados publicados."""
import random
import re
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

from django.db import transaction

from . import acuses, reloj
from .demo import _solicitud, completar_requisitos, cuadro_en_municipio
from .demo_calendario import cuando, habil
from .models import Ejercicio, Municipio, Predio, Usuario

PROGRAMAS = ("CC", "PS", "RHF", "PSA")
# (estado al que se avanza, peso en porcentaje); el orden es el de la lista de solicitudes de cada programa
DISTRIBUCION = (("recibida_a_medias", 12), ("recibida_completa", 10), ("enviada", 12), ("faltantes", 10), ("validada", 14),
                ("dictaminada", 12), ("aprobada", 30))
NOMBRES = ("Alma", "Bruno", "Carla", "Diego", "Elena", "Fausto", "Gloria", "Hugo", "Irma", "Jaime", "Karla", "Luis", "Marta",
           "Nicolás", "Olga", "Pedro", "Rosa", "Saúl", "Tania", "Víctor")
APELLIDOS = ("Aguilar", "Bautista", "Cruz", "Díaz", "Estrada", "Flores", "García", "Hernández", "Ibarra", "Juárez", "López",
             "Mendoza", "Nava", "Ortega", "Pérez", "Quiroz", "Rojas", "Salinas", "Torres", "Vargas")
PARAJES = ("El Mirador", "La Cañada", "Los Pinos", "San Miguel", "El Capulín", "La Loma", "Agua Azul", "El Fresno", "Santa Cruz",
           "Los Encinos", "El Cedro", "La Joya", "Las Palomas", "El Ocotal", "Cerro Alto")
VENTANA_SESION = {"CC": "2026-07-28", "PSA": "2026-07-29", "PS": "2026-08-18", "RHF": "2026-08-19"}


def _pdf_ligero(html):
    """PDF mínimo válido con el texto visible del documento (sustituye a WeasyPrint, que tarda de 4 a 8 s por documento)."""
    from .demo import _pdf_demo

    html = re.sub(r"(?is)<(?:style|head|script)[ >].*?</(?:style|head|script)>", " ", html)
    texto = re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html)).strip()[:400]
    return _pdf_demo(texto.replace("\\", " ").replace("(", "[").replace(")", "]"))


@contextmanager
def pdf_ligero():
    """Dentro del bloque, acuses y documentos se generan con un PDF mínimo (la huella y el texto son propios de cada uno)."""
    original = acuses._render_pdf
    acuses._render_pdf = _pdf_ligero
    try:
        yield
    finally:
        acuses._render_pdf = original


def _estados(n):
    """Lista de ``n`` estados objetivo según ``DISTRIBUCION`` (determinista; el resto va al último)."""
    lista = []
    for estado, peso in DISTRIBUCION:
        lista += [estado] * round(n * peso / 100)
    while len(lista) < n:
        lista.append(DISTRIBUCION[-1][0])
    return lista[:n]


def _paso(fecha, hora=10):
    return reloj.en(cuando(fecha, hora), tic=1)


def generar(programa, n, semilla, pdf_real=False, escribir=lambda texto: None):
    """Genera ``n`` solicitudes de ``programa`` con la ``semilla``; devuelve cuántas creó (las que ya existían no se repiten)."""
    ejercicio = Ejercicio.objects.filter(programa__clave=programa, reglas_cargadas__isnull=False).order_by("-anio").first()
    if ejercicio is None:
        raise ValueError(f"{programa} no tiene reglas cargadas (cargar_reglas).")
    azar = random.Random(f"{semilla}-{programa}")
    usuarios = {u.username: u for u in Usuario.objects.select_related("unidad")}
    drff, uj, st = usuarios["dir_drff"], usuarios["juridica"], usuarios["comite"]
    delegaciones = [u for u in usuarios.values() if u.unidad and u.unidad.tipo == "delegacion"]
    por_unidad = {u.unidad_id: u for u in delegaciones}
    municipios = list(Municipio.objects.filter(delegacion_id__in=por_unidad).order_by("clave"))
    tipos = [t for t in ejercicio.tipos_persona.order_by("clave") if t.clave in ("fisica", "juridica_colectiva", "nucleo_agrario")]
    modalidades = [m for m in ejercicio.modalidades.order_by("clave") if m.seleccionable and m.clave != "refrendo"]
    estados = _estados(n)
    contexto = _nulo() if pdf_real else pdf_ligero()
    creadas = 0
    aprobables, dictaminadas_pendientes = [], []
    # Todo lo que se sortea se decide primero, en el orden de la lista, para que la semilla fije los datos
    especificaciones = []
    for i, objetivo in enumerate(estados):
        municipio = azar.choice(municipios)
        especificaciones.append(dict(
            i=i, objetivo=objetivo, municipio=municipio, tipo=azar.choice(tipos), modalidad=azar.choice(modalidades),
            predio=f"Predio G{semilla}-{programa}-{i + 1:04d} ({azar.choice(PARAJES)})",
            persona=f"{azar.choice(NOMBRES)} {azar.choice(APELLIDOS)} {azar.choice(APELLIDOS)}",
            hectareas=Decimal(str(round(azar.uniform(1.5, 12), 1)))))
    # Las que la sesión aprueba se dictaminan primero (la sesión toma todo lo dictaminado); las demás, después de la sesión
    orden = [e for e in especificaciones if e["objetivo"] == "aprobada"] + [e for e in especificaciones if e["objetivo"] != "aprobada"]
    aprobadas = sum(1 for e in orden if e["objetivo"] == "aprobada")
    with contexto, transaction.atomic():
        for k, spec in enumerate(orden):
            if k == aprobadas and aprobables:
                _sesion_y_publicacion(st, drff, ejercicio, programa, aprobables)
            creadas += _avanzar(spec, ejercicio, por_unidad, drff, uj, aprobables, dictaminadas_pendientes)
        if aprobables and aprobadas == len(orden):
            _sesion_y_publicacion(st, drff, ejercicio, programa, aprobables)
        escribir(f"{programa}: {creadas} solicitudes creadas ({len(aprobables)} aprobadas y publicadas, "
                 f"{len(dictaminadas_pendientes)} dictaminadas por llevar a sesión).")
    return creadas


def _sesion_y_publicacion(st, drff, ejercicio, programa, aprobables):
    from contrato import publicacion
    from dictamen.demo import sesion_aprobacion

    sesion = sesion_aprobacion(st, ejercicio, VENTANA_SESION[programa], ["Listado preliminar (generador)"],
                               presupuesto=Decimal(len(aprobables)) * Decimal("15000"))
    with _paso(habil(VENTANA_SESION[programa], 2), 10):
        publicacion.publicar(drff, sesion)


def _avanzar(spec, ejercicio, por_unidad, drff, uj, aprobables, dictaminadas_pendientes):
    """Registra la solicitud y la lleva hasta su estado objetivo; devuelve 1 si la creó (0 si ya existía)."""
    from dictamen import juridico, tecnico
    from dictamen.demo import propiedad_en_regla
    from recepcion import servicios

    i, objetivo, municipio, tipo, modalidad = spec["i"], spec["objetivo"], spec["municipio"], spec["tipo"], spec["modalidad"]
    nombre_predio, persona, hectareas = spec["predio"], spec["persona"], spec["hectareas"]
    if Predio.objects.filter(nombre=nombre_predio, expedientes__ejercicio=ejercicio).exists():
        return 0
    desplazamiento = ((i % 25) * 450, (i // 25) * 450)
    delegado = por_unidad[municipio.delegacion_id]
    registro = habil("2026-01-29", i % 40)                # recepción: del 29-ene al 25-mar
    extra = {"curp": f"{persona[:2].upper()}XX{700101 + i % 9000:06d}HMCXXX{i % 100:02d}"} if tipo.clave == "fisica" else {}
    with _paso(registro, 9):
        exp = _solicitud(delegado, ejercicio, municipio.nombre, nombre_predio, persona, tipo.clave, modalidad.clave,
                         str(hectareas), **extra)
    if objetivo == "recibida_a_medias":
        with _paso(registro, 11):
            for r in list(exp.revisiones.select_related("requisito"))[:3]:
                servicios.revisar_requisito(delegado, r, "entregado", archivo=_archivo(r, nombre_predio))
        return 1
    with _paso(registro, 12):
        completar_requisitos(delegado, exp)
    with _paso(habil(registro, 1), 10):
        servicios.registrar_poligono(delegado, exp, cuadro_en_municipio(municipio, hectareas, desplazamiento), "dibujo",
                                     "delegacion", "Brigada de la Delegación", reloj_hoy())
    if objetivo == "recibida_completa":
        return 1
    with _paso(habil(registro, 2), 10):
        servicios.enviar_a_direccion(delegado, exp)
    if objetivo == "enviada":
        return 1
    with _paso(habil(registro, 5), 11):
        if objetivo == "faltantes":
            plano = exp.revisiones.order_by("pk").first()
            servicios.validar_expediente(drff, exp, [plano.pk], "Falta el documento señalado (generador).",
                                         observaciones_requisitos={plano.pk: "El plano no es legible (generador)."})
            return 1
        servicios.validar_expediente(drff, exp)
    if objetivo == "validada":
        return 1
    with _paso(habil("2026-04-20", i % 30), 10):
        tecnico.dictaminar(drff, exp, "factible", "Cumple los criterios técnicos (generador).")
    with _paso(habil("2026-05-18", i % 30), 10):
        juridico.dictaminar(uj, exp, "procedente", "Documentación completa (generador).", propiedad=propiedad_en_regla(exp))
    (aprobables if objetivo == "aprobada" else dictaminadas_pendientes).append(exp)
    return 1


def reloj_hoy():
    """Fecha de levantamiento del polígono: el día anterior en el reloj simulado."""
    from django.utils import timezone

    return timezone.localdate() - timedelta(days=1)


def _archivo(revision, predio):
    from .demo import archivo_demo

    return archivo_demo(f"{revision.requisito.clave}.pdf", f"{revision.requisito.clave} - {predio}")


@contextmanager
def _nulo():
    yield
