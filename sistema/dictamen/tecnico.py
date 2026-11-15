"""HU-2.1 · Dictamen técnico, análisis cartográfico, plazo de dictaminación y listado preliminar."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from nucleo import dias_habiles, reglas
from nucleo.acuses import emitir_acuse
from nucleo.models import Evento, Expediente, TipoUnidad
from recepcion import geometria
from recepcion.models import Poligono

from .comun import completar_si_ya_hay_dos, datos_dictamen, exigir_acceso, exigir_programa, exigir_unidad, resultado_combinado
from .models import DictamenTecnico, ResultadoTecnico

RESPUESTAS = {"si": "Cumple", "no": "No cumple", "na": "No aplica"}


# ----------------------------------------------------------------------------- lista de verificación
def lista_verificacion(ejercicio, modalidad=None):
    """Criterios del programa (de las reglas) como lista de verificación para el dictamen técnico. El rango de
    superficie es el de la modalidad (concepto en PS, cuenca en PSAHEM) si las reglas lo distinguen."""
    datos = ejercicio.datos or {}
    items = []
    sup = datos.get("superficie")
    if sup:
        rango = reglas.rango_superficie(ejercicio, modalidad)
        items.append({"clave": "superficie", "grupo": "Superficie",
                      "texto": rango["texto"]
                               + (f"; edad mínima {sup['edad_minima_anios']} años" if sup.get("edad_minima_anios") else ""),
                      "numeral": rango["numeral"], "automatico": True})
    for i, c in enumerate(datos.get("criterios_elegibilidad_tecnica", []), 1):
        items.append({"clave": f"elegibilidad-{i}", "grupo": "Criterios técnicos de elegibilidad",
                      "texto": c["texto"], "numeral": c.get("numeral", "")})
    for i, c in enumerate(datos.get("inelegibles", []), 1):
        items.append({"clave": f"inelegible-{i}", "grupo": "No está en los supuestos de inelegibilidad",
                      "texto": c["texto"], "numeral": c.get("numeral", "")})
    for i, c in enumerate(datos.get("criterios_seleccion", []), 1):
        items.append({"clave": f"priorizacion-{i}", "grupo": "Criterios de priorización (para el orden del Comité)",
                      "texto": c["texto"], "numeral": c.get("numeral", ""), "informativo": True})
    return items


# ----------------------------------------------------------------------------- análisis cartográfico
def analisis_cartografico(expediente):
    """Polígono vigente, superficie (EPSG:32614), ubicación en el municipio y traslapes con otros expedientes
    del mismo ejercicio (consulta espacial en PostGIS)."""
    poligono = expediente.poligonos.filter(vigente=True).first()
    resultado = {"tiene_poligono": poligono is not None, "usa_poligono": expediente.programa.usa_poligono,
                 "traslapes": []}
    sup = reglas.rango_superficie(expediente.ejercicio, expediente.modalidad)
    if poligono is None:
        return resultado
    ubicacion, aviso = geometria.ubicacion_en_municipio(poligono.geom, expediente.predio.municipio)
    resultado.update({
        "poligono_id": poligono.pk, "superficie_ha": float(poligono.superficie_ha),
        "ubicacion_municipio": ubicacion, "aviso_municipio": aviso, "municipio": expediente.predio.municipio.nombre,
        "superficie_minima_ha": sup.get("minima_ha"), "superficie_maxima_ha": sup.get("maxima_ha"),
    })
    dentro = reglas.en_rango(sup, poligono.superficie_ha)
    if dentro is not None:
        resultado["superficie_en_rango"] = dentro
    otros = (Poligono.objects.filter(vigente=True, expediente__ejercicio=expediente.ejercicio,
                                     geom__intersects=poligono.geom)
             .exclude(expediente=expediente).select_related("expediente__predio"))
    for otro in otros:
        interseccion = otro.geom.intersection(poligono.geom)
        ha = geometria.superficie_ha(interseccion) if not interseccion.empty else Decimal("0")
        if ha <= 0:
            continue
        resultado["traslapes"].append({
            "folio": otro.expediente.folio, "predio": otro.expediente.predio.nombre, "estado": str(otro.expediente.estado),
            "superficie_ha": float(ha), "porcentaje": round(100 * float(ha) / float(poligono.superficie_ha), 2),
        })
    return resultado


# ----------------------------------------------------------------------------- plazo de dictaminación
def plazo_dictamen(expediente):
    """Plazo de dictaminación de las reglas del programa (el primero que exista de datos/dictamen.json)."""
    for clave in datos_dictamen()["plazos"]["dictamen"]:
        plazo = expediente.ejercicio.plazo(clave)
        if plazo is not None:
            return plazo
    return None


def fecha_limite_dictamen(expediente):
    plazo = plazo_dictamen(expediente)
    if plazo is None:
        return None, None
    if plazo.es_calculable:
        return dias_habiles.vencimiento_de_plazo(plazo, expediente.fecha_recepcion), plazo
    if plazo.fecha_fin:
        return plazo.fecha_fin, plazo
    return None, plazo


def situacion_plazo(expediente, hoy=None):
    """Situación del plazo de dictaminación: en_plazo, por_vencer, vencido, cumplido o fuera_de_plazo."""
    hoy = hoy or timezone.localdate()
    limite, plazo = fecha_limite_dictamen(expediente)
    info = {"limite": limite, "plazo": plazo, "situacion": "sin_plazo", "dias_habiles_restantes": None}
    if limite is None:
        return info
    dictamen = getattr(expediente, "dictamen_tecnico", None)
    if dictamen is not None:
        info["situacion"] = "cumplido" if timezone.localtime(dictamen.fecha_hora).date() <= limite else "fuera_de_plazo"
        return info
    restantes = dias_habiles.dias_habiles_entre(hoy, limite)
    info["dias_habiles_restantes"] = restantes
    umbral = datos_dictamen()["plazos"].get("dictamen_por_vencer_dias_habiles", 5)
    info["situacion"] = "vencido" if hoy > limite else "por_vencer" if restantes <= umbral else "en_plazo"
    return info


TEXTO_SITUACION = {
    "sin_plazo": "Sin plazo en las reglas", "en_plazo": "En plazo", "por_vencer": "Por vencer",
    "vencido": "Plazo vencido sin dictamen", "cumplido": "Dictaminado en plazo", "fuera_de_plazo": "Dictaminado fuera de plazo",
}


# ----------------------------------------------------------------------------- dictamen
def dictaminar(usuario, expediente, resultado, motivo, verificacion=None, superficie_factible_ha=None,
               exigir_revision=False):
    """La Dirección (área responsable del programa) emite el dictamen técnico con su motivo.

    Con `exigir_revision` (el dictamen llega de la pantalla) todo criterio revisable debe quedar marcado."""
    exigir_unidad(usuario, TipoUnidad.DIRECCION)
    exigir_acceso(usuario, expediente)
    exigir_programa(usuario, expediente)
    if expediente.estado.clave != "validada":
        raise ValidationError(f"El expediente está «{expediente.estado}»; solo se dictamina un expediente validado.")
    if hasattr(expediente, "dictamen_tecnico"):
        raise ValidationError("El expediente ya tiene dictamen técnico.")
    if resultado not in ResultadoTecnico.values:
        raise ValidationError("El resultado debe ser factible o no factible.")
    if not (motivo or "").strip():
        raise ValidationError("El dictamen técnico debe llevar su motivo.")
    verificacion = verificacion or {}
    items = []
    for item in lista_verificacion(expediente.ejercicio, expediente.modalidad):
        respuesta = verificacion.get(item["clave"], {})
        items.append({**item, "respuesta": respuesta.get("respuesta", ""), "nota": respuesta.get("nota", "")})
    if exigir_revision:
        faltan = sum(1 for i in items if not i.get("informativo") and i["respuesta"] not in RESPUESTAS)
        if faltan:
            raise ValidationError(f"Falta marcar {faltan} criterio{'s' if faltan != 1 else ''} de la lista de verificación "
                                  "(cumple, no cumple o no aplica): revise todos antes de registrar el dictamen.")
    if resultado == ResultadoTecnico.FACTIBLE and any(i["respuesta"] == "no" and not i.get("informativo") for i in items):
        raise ValidationError("Hay criterios marcados como «no cumple»: el dictamen no puede ser factible.")
    analisis = analisis_cartografico(expediente)
    if superficie_factible_ha is None and analisis.get("superficie_ha") is not None and resultado == ResultadoTecnico.FACTIBLE:
        superficie_factible_ha = Decimal(str(analisis["superficie_ha"]))
    limite, plazo = fecha_limite_dictamen(expediente)
    ahora = timezone.now()
    dentro = None if limite is None else timezone.localtime(ahora).date() <= limite
    with transaction.atomic():
        dictamen = DictamenTecnico.objects.create(
            expediente=expediente, resultado=resultado, motivo=motivo.strip(), superficie_factible_ha=superficie_factible_ha,
            verificacion=items, analisis=analisis, fecha_limite=limite, dentro_de_plazo=dentro, usuario=usuario,
            fecha_hora=ahora,
        )
        renglones = [
            ("Resultado", dictamen.get_resultado_display()), ("Motivo", dictamen.motivo),
            ("Superficie factible", f"{superficie_factible_ha} ha" if superficie_factible_ha else "—"),
            ("Polígono vigente", f"{analisis['superficie_ha']:.4f} ha · {analisis.get('ubicacion_municipio', '')}"
             if analisis.get("tiene_poligono") else "Sin polígono"),
            ("Traslapes con otros expedientes", ", ".join(f"{t['folio']} ({t['superficie_ha']:.2f} ha)"
                                                          for t in analisis["traslapes"]) or "Ninguno"),
            ("Plazo de dictaminación", f"{plazo.texto_plazo} ({plazo.fundamento}); límite {limite:%d/%m/%Y}"
             f" · {'dentro' if dentro else 'fuera'} de plazo" if limite else "Sin plazo en las reglas"),
        ]
        detalle = [{"clave": i["numeral"][:30], "texto": i["texto"][:150], "estado": RESPUESTAS.get(i["respuesta"], "—")}
                   for i in items if not i.get("informativo")]
        acuse = emitir_acuse(expediente, "dictamen_tecnico", "Dictamen técnico", usuario, renglones,
                             detalle=detalle, encabezado_detalle=["Numeral", "Criterio", "Revisión"])
        dictamen.acuse = acuse
        dictamen.save(update_fields=["acuse"])
        Evento.registrar(expediente, usuario, "dictamen_tecnico",
                         f"Dictamen técnico {dictamen.get_resultado_display().lower()}: {dictamen.motivo}", acuse=acuse,
                         datos={"resultado": resultado, "dentro_de_plazo": dentro})
        completar_si_ya_hay_dos(expediente, usuario)
    return dictamen


# ----------------------------------------------------------------------------- listado preliminar
def listado_preliminar(ejercicio, expedientes):
    """Resultado técnico y jurídico de cada solicitud del ejercicio (validadas en adelante)."""
    filas = []
    qs = (expedientes.filter(ejercicio=ejercicio, estado__orden__gte=30).exclude(estado__clave="desechada")
          .select_related("predio__municipio", "solicitante", "estado", "delegacion", "dictamen_tecnico",
                          "dictamen_juridico").order_by("fecha_recepcion"))
    for exp in qs:
        tecnico = getattr(exp, "dictamen_tecnico", None)
        juridico = getattr(exp, "dictamen_juridico", None)
        resultado, texto = resultado_combinado(exp)
        filas.append({
            "expediente": exp, "folio": exp.folio, "predio": exp.predio.nombre, "municipio": exp.predio.municipio.nombre,
            "solicitante": exp.solicitante.nombre, "delegacion": exp.delegacion.nombre,
            "superficie_ha": tecnico.superficie_factible_ha if tecnico else None,
            "tecnico": tecnico.get_resultado_display() if tecnico else "Pendiente",
            "motivo_tecnico": tecnico.motivo if tecnico else "",
            "juridico": juridico.get_resultado_display() if juridico else "Pendiente",
            "motivo_juridico": juridico.motivo if juridico else "",
            "resultado": resultado, "resultado_texto": {"factible": "Factible", "no_factible": "No factible",
                                                        "pendiente": "Pendiente"}[resultado],
            "estado": exp.estado.nombre,
        })
    return filas


COLUMNAS_CSV = [("folio", "Folio"), ("predio", "Predio"), ("municipio", "Municipio"), ("solicitante", "Persona solicitante"),
                ("delegacion", "Delegación"), ("superficie_ha", "Superficie factible (ha)"),
                ("tecnico", "Dictamen técnico"), ("motivo_tecnico", "Motivo técnico"), ("juridico", "Dictamen jurídico"),
                ("motivo_juridico", "Motivo jurídico"), ("resultado_texto", "Resultado preliminar"), ("estado", "Estado")]


def listado_csv(filas):
    """CSV en UTF-8 con BOM (Excel lo abre con acentos)."""
    import csv
    import io

    salida = io.StringIO()
    salida.write("﻿")
    escritor = csv.writer(salida)
    escritor.writerow([t for _, t in COLUMNAS_CSV])
    for f in filas:
        escritor.writerow(["" if f[c] is None else f[c] for c, _ in COLUMNAS_CSV])
    return salida.getvalue()


# ----------------------------------------------------------------------------- revisión diaria
def revisar_plazos_dictamen(hoy):
    """Señala una vez en la bitácora los dictámenes vencidos o por vencer (servicio «plazos»)."""
    avisos = 0
    for exp in Expediente.objects.filter(estado__clave="validada", dictamen_tecnico__isnull=True):
        info = situacion_plazo(exp, hoy)
        if info["situacion"] not in {"vencido", "por_vencer"}:
            continue
        tipo = f"plazo_dictamen_{info['situacion']}"
        if exp.eventos.filter(tipo=tipo).exists():
            continue
        texto = ("Venció" if info["situacion"] == "vencido" else "Está por vencer") + \
            f" el plazo de dictaminación ({info['plazo'].texto_plazo}, {info['plazo'].fundamento}): límite {info['limite']:%d/%m/%Y}."
        Evento.registrar(exp, None, tipo, texto, datos={"fecha_limite": info["limite"].isoformat()})
        avisos += 1
    return avisos
