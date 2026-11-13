"""Carga de catálogos y reglas desde archivos JSON (los usan los comandos y las pruebas)."""
import json
import unicodedata
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.gis.geos import GEOSGeometry, MultiPolygon
from django.core.management.base import CommandError
from django.db import transaction
from django.utils import timezone

from .models import (
    DiaInhabil, Ejercicio, Estado, Formato, Ministracion, Modalidad, MontoApoyo, Municipio, Plazo, Programa,
    Requisito, TipoPersona, TipoUnidad, Transicion, Unidad,
)


def leer_json(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        raise CommandError(f"No existe el archivo {ruta}")
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return " ".join(texto.lower().replace(".", " ").replace(",", " ").split())


def datos_sistema():
    return leer_json(settings.DATOS_DIR / "sistema.json")


# ----------------------------------------------------------------------------- municipios
def cargar_municipios(ruta=None):
    ruta = ruta or settings.DATOS_DIR / "municipios_edomex.geojson"
    capa = leer_json(ruta)
    n = 0
    for f in capa["features"]:
        geom = GEOSGeometry(json.dumps(f["geometry"]), srid=4326)
        if geom.geom_type == "Polygon":
            geom = MultiPolygon(geom, srid=4326)
        p = f["properties"]
        Municipio.objects.update_or_create(clave=p["clave"], defaults={"nombre": p["nombre"], "geom": geom})
        n += 1
    return n


def empatar_municipio(nombre, por_normal):
    """Busca el municipio de IDEFOR que corresponde a un nombre de la tabla de las ROP."""
    clave = normalizar(nombre)
    if clave in por_normal:
        return por_normal[clave]
    candidatos = [m for k, m in por_normal.items() if k.startswith(clave + " ")]
    if len(candidatos) == 1:
        return candidatos[0]
    return None


# ----------------------------------------------------------------------------- unidades
def cargar_unidades(catalogos, sistema):
    tipos = sistema.get("tipos_de_unidad", {})
    programas = {p.clave: p for p in Programa.objects.all()}
    for u in catalogos.get("unidades", []):
        conf = tipos.get(u["clave"], {})
        unidad, _ = Unidad.objects.update_or_create(
            clave=u["clave"],
            defaults={"nombre": u["nombre"], "tipo": conf.get("tipo", TipoUnidad.OTRA)},
        )
        if conf.get("programas"):
            unidad.programas.set([programas[c] for c in conf["programas"] if c in programas])
    for u in sistema.get("unidades_extra", []):
        Unidad.objects.update_or_create(clave=u["clave"], defaults={"nombre": u["nombre"], "tipo": u["tipo"]})


def cargar_delegaciones(catalogos):
    """Delegaciones y municipios que atiende cada una. Falla si algún nombre no empata."""
    municipios = list(Municipio.objects.all())
    if not municipios:
        raise CommandError("Primero hay que cargar los municipios.")
    por_normal = {normalizar(m.nombre): m for m in municipios}
    asignados = {}
    errores = []
    nota = catalogos.get("fuente", {}).get("documento", "")
    with transaction.atomic():
        for d in catalogos["delegaciones"]:
            unidad, _ = Unidad.objects.update_or_create(
                clave=d["clave"],
                defaults={
                    "nombre": d["nombre"], "tipo": TipoUnidad.DELEGACION, "sede": d.get("sede") or "",
                    "domicilio": d.get("domicilio") or "", "telefono": d.get("telefono") or "",
                    "asignacion_confirmada": bool(d.get("confirmada_con_cliente")),
                    "fuente_asignacion": f"Convocatoria 2026, base cuarta (líneas {d.get('lineas')}); {nota[:150]}",
                },
            )
            for nombre in d["municipios"]:
                m = empatar_municipio(nombre, por_normal)
                if m is None:
                    errores.append(f"«{nombre}» ({d['nombre']}) no empata con ningún municipio de IDEFOR")
                    continue
                if m.pk in asignados and asignados[m.pk] != unidad.pk:
                    errores.append(f"«{m.nombre}» está asignado a dos Delegaciones")
                asignados[m.pk] = unidad.pk
                m.delegacion = unidad
                m.save(update_fields=["delegacion"])
        sin_asignar = [m.nombre for m in municipios if m.pk not in asignados]
        if sin_asignar:
            errores.append("Municipios sin Delegación: " + ", ".join(sin_asignar))
        if errores:
            raise CommandError("No se pudo cargar la asignación de municipios:\n- " + "\n- ".join(errores))
    return len(asignados)


# ----------------------------------------------------------------------------- flujo y calendario
def cargar_flujo(ruta=None):
    datos = leer_json(ruta or settings.DATOS_DIR / "flujo_tramite.json")
    for e in datos["estados"]:
        Estado.objects.update_or_create(clave=e["clave"], defaults={
            "nombre": e["nombre"], "descripcion": e.get("descripcion", ""),
            "tipo_unidad_bandeja": e.get("tipo_unidad_bandeja", ""), "flujo_alterno": e.get("flujo_alterno", ""),
            "visible_para": e.get("visible_para", ""),
            "final": e.get("final", False), "color": e.get("color", "secondary"), "orden": e.get("orden", 0),
        })
    estados = {e.clave: e for e in Estado.objects.all()}
    vigentes = []
    for t in datos["transiciones"]:
        programa = Programa.objects.get(clave=t["programa"]) if t.get("programa") else None
        transicion, _ = Transicion.objects.update_or_create(
            programa=programa, origen=estados[t["origen"]], destino=estados[t["destino"]],
            tipo_unidad=t["tipo_unidad"],
            defaults={"accion": t["accion"], "requiere_motivo": t.get("requiere_motivo", False)},
        )
        vigentes.append(transicion.pk)
    # Las transiciones que ya no están en el archivo dejan de estar permitidas.
    Transicion.objects.exclude(pk__in=vigentes).delete()


def cargar_dias_inhabiles(ruta=None):
    datos = leer_json(ruta or settings.DATOS_DIR / "dias_inhabiles_2026.json")
    for d in datos["dias"]:
        DiaInhabil.objects.update_or_create(
            fecha=d["fecha"], defaults={"descripcion": d["descripcion"], "fuente": datos.get("fuente", "")[:200]},
        )
    return len(datos["dias"])


def cargar_grupos():
    for clave, nombre in TipoUnidad.choices:
        Group.objects.get_or_create(name=nombre)


def cargar_programas(sistema):
    anio = sistema["ejercicio_vigente"]
    for p in sistema["programas"]:
        programa, _ = Programa.objects.update_or_create(
            clave=p["clave"], defaults={"nombre": p["nombre"], "usa_poligono": p.get("usa_poligono", True)},
        )
        Ejercicio.objects.get_or_create(programa=programa, anio=anio)


def cargar_catalogos():
    sistema = datos_sistema()
    catalogos = leer_json(settings.REGLAS_DIR / "catalogos.json")
    with transaction.atomic():
        cargar_grupos()
        cargar_programas(sistema)
        n_mun = cargar_municipios()
        cargar_unidades(catalogos, sistema)
        n_asig = cargar_delegaciones(catalogos)
        cargar_flujo()
        n_dias = cargar_dias_inhabiles()
    return {"municipios": n_mun, "asignados": n_asig, "dias_inhabiles": n_dias}


# ----------------------------------------------------------------------------- reglas de un programa
def _numeral(d):
    return (d.get("numeral") or "")[:200]


def cargar_reglas_programa(ruta, sistema=None):
    """Carga (o actualiza) las reglas de un programa-ejercicio desde ``reglas/<CLAVE>.json``."""
    sistema = sistema or datos_sistema()
    datos = leer_json(ruta)
    programa = Programa.objects.get(clave=datos["clave"])
    ajustes = sistema.get("ajustes_reglas", {}).get(programa.clave, {})
    no_seleccionables = set(ajustes.get("modalidades_no_seleccionables", []))
    sin_documento = set(ajustes.get("requisitos_sin_documento", []))
    with transaction.atomic():
        ejercicio, _ = Ejercicio.objects.get_or_create(programa=programa, anio=int(datos["ejercicio"]))
        fuente = datos.get("fuente", {})
        ejercicio.fuente = fuente.get("documento", "") if isinstance(fuente, dict) else str(fuente)
        ejercicio.archivo_reglas = Path(ruta).name
        ejercicio.datos = {k: v for k, v in datos.items() if k not in {
            "requisitos", "plazos", "formatos", "tipos_persona", "modalidades", "montos", "ministraciones"}}
        ejercicio.reglas_cargadas = timezone.now()
        ejercicio.save()

        tipos = {}
        for i, t in enumerate(datos.get("tipos_persona", [])):
            tipos[t["clave"]], _ = TipoPersona.objects.update_or_create(
                ejercicio=ejercicio, clave=t["clave"],
                defaults={"nombre": t["nombre"], "fundamento": _numeral(t), "orden": i},
            )
        modalidades = {}
        for i, m in enumerate(datos.get("modalidades", [])):
            modalidades[m["clave"]], _ = Modalidad.objects.update_or_create(
                ejercicio=ejercicio, clave=m["clave"],
                defaults={"nombre": m["nombre"], "descripcion": m.get("descripcion", ""), "fundamento": _numeral(m),
                          "seleccionable": m.get("seleccionable", m["clave"] not in no_seleccionables), "orden": i},
            )
        claves = []
        for i, r in enumerate(datos.get("requisitos", [])):
            req, _ = Requisito.objects.update_or_create(
                ejercicio=ejercicio, clave=r["clave"],
                defaults={
                    "texto": r["texto"], "aplica_en_refrendo": r.get("aplica_en_refrendo"),
                    "requiere_documento": r.get("requiere_documento", r["clave"] not in sin_documento),
                    "es_documento_legal": bool(r.get("es_documento_legal")), "opcional": bool(r.get("opcional")),
                    "condicion": (r.get("condicion") or "")[:300], "nota_refrendo": (r.get("nota_refrendo") or "")[:300],
                    "formato": (r.get("formato") or "")[:80], "fundamento": _numeral(r),
                    "linea_rop": r.get("linea"), "orden": i,
                },
            )
            req.tipos_persona.set([tipos[c] for c in r.get("tipos_persona", []) if c in tipos])
            req.modalidades.set([modalidades[c] for c in r.get("modalidades", []) if c in modalidades])
            claves.append(r["clave"])
        Requisito.objects.filter(ejercicio=ejercicio).exclude(clave__in=claves).filter(
            revisiones__isnull=True).delete()

        for p in datos.get("plazos", []):
            Plazo.objects.update_or_create(ejercicio=ejercicio, clave=p["clave"], defaults={
                "descripcion": p.get("descripcion", ""), "cantidad": p.get("cantidad"),
                "unidad": p.get("unidad") or "otro", "fecha_fin": p.get("fecha_fin"),
                "corre_desde": (p.get("corre_desde") or "")[:300], "responsable": (p.get("responsable") or "")[:200],
                "fundamento": _numeral(p), "linea_rop": p.get("linea"),
                "datos": {k: v for k, v in p.items() if k not in {
                    "clave", "descripcion", "cantidad", "unidad", "fecha_fin", "corre_desde", "responsable",
                    "numeral", "linea"}},
            })
        ejercicio.formatos.all().delete()
        for i, f in enumerate(datos.get("formatos", [])):
            Formato.objects.create(ejercicio=ejercicio, clave=f.get("clave") or "", nombre=f["nombre"][:300],
                                   uso=f.get("uso", ""), linea_rop=f.get("linea"), orden=i)
        ejercicio.montos.all().delete()
        for m in datos.get("montos", []):
            MontoApoyo.objects.create(
                ejercicio=ejercicio, concepto=m["concepto"],
                monto=Decimal(str(m["monto"])) if m.get("monto") is not None else None,
                unidad=(m.get("unidad") or "")[:120], fundamento=_numeral(m),
            )
        ejercicio.ministraciones.all().delete()
        for m in datos.get("ministraciones", []):
            Ministracion.objects.create(
                ejercicio=ejercicio, numero=m["numero"], porcentaje=Decimal(str(m["porcentaje"])),
                regimen=m.get("regimen", ""), condicion=m.get("condicion", ""), fundamento=_numeral(m),
            )
    return ejercicio


def cargar_reglas_disponibles():
    """Carga los archivos reglas/<CLAVE>.json que existan. Devuelve (cargados, faltantes)."""
    sistema = datos_sistema()
    cargados, faltantes = [], []
    for p in sistema["programas"]:
        ruta = settings.REGLAS_DIR / p["archivo_reglas"]
        if ruta.exists():
            cargados.append(cargar_reglas_programa(ruta, sistema))
        else:
            faltantes.append(p["clave"])
    return cargados, faltantes
