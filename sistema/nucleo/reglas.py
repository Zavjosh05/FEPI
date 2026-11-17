"""Lecturas de las reglas del programa que dependen del expediente (modalidad, condiciones).

Las reglas de cada programa traen la superficie con forma distinta: CC un rango general; PS un rango por
concepto (``por_concepto``); PSAHEM uno por categoría de cuenca (``por_categoria``, con máximo mayor si hay
certificación FSC); RHF solo mínimo; MFS una lista de rangos por modalidad (``rangos_etf``: desde, exclusivo, y hasta,
inclusivo; las modalidades que no están en la lista no tienen rango, ``ajustes_reglas.MFS.rango_superficie``).
``rango_superficie`` lo resuelve igual para todos.

Quién solicita y quién recibe el apoyo (S3-02): en casi todos los programas es la misma persona; en PEG solicita el
núcleo agrario y la persona beneficiaria es el Guardabosque que designa su Asamblea
(``ajustes_reglas.PEG.persona_beneficiaria``). ``persona_beneficiaria_distinta`` y ``tipos_persona_seleccionables`` lo
leen de ``datos/sistema.json``.
"""
from .catalogos import datos_sistema


def _ajustes(ejercicio):
    return datos_sistema().get("ajustes_reglas", {}).get(ejercicio.programa.clave, {})


def persona_beneficiaria_distinta(ejercicio):
    """Configuración de la persona beneficiaria cuando no es quien solicita (``{"tipo_persona", "etiqueta",
    "obligatoria", "fundamento"}``) o None."""
    return _ajustes(ejercicio).get("persona_beneficiaria")


def tipos_persona_seleccionables(ejercicio):
    """Tipos de persona que pueden registrar una solicitud (PEG: el Guardabosque no solicita, lo designa el núcleo)."""
    fuera = set(_ajustes(ejercicio).get("tipos_persona_no_seleccionables", []))
    return ejercicio.tipos_persona.exclude(clave__in=fuera)


def rango_superficie(ejercicio, modalidad=None, condiciones=()):
    """``{"minima_ha", "maxima_ha", "numeral", "texto"}`` para la modalidad (None = sin límite en las reglas)."""
    sup = (ejercicio.datos or {}).get("superficie") or {}
    rango = {"minima_ha": sup.get("minima_ha"), "maxima_ha": sup.get("maxima_ha"), "numeral": sup.get("numeral", "")}
    clave = getattr(modalidad, "clave", modalidad)
    propio = None
    for nombre in ("por_concepto", "por_categoria"):
        if clave and clave in (sup.get(nombre) or {}):
            propio = sup[nombre][clave]
    conf_lista = _ajustes(ejercicio).get("rango_superficie", {}) if hasattr(ejercicio, "programa") else {}
    if conf_lista.get("lista"):
        fila = next((f for f in sup.get(conf_lista["lista"]) or [] if f.get("modalidad") == clave), None)
        if fila is not None:
            propio = {"minima_ha": fila.get("desde_ha_exclusivo"), "maxima_ha": fila.get("hasta_ha_inclusivo"),
                      "numeral": sup.get("numeral")}
            rango["minima_exclusiva"] = fila.get("desde_ha_exclusivo") is not None
        elif conf_lista.get("sin_rango_fuera_de_la_lista"):
            rango.update({"minima_ha": None, "maxima_ha": None})
    if propio:
        rango["minima_ha"] = propio.get("minima_ha", rango["minima_ha"])
        rango["maxima_ha"] = propio.get("maxima_ha", rango["maxima_ha"])
        if "certificacion_FSC" in set(condiciones) and propio.get("maxima_ha_con_FSC") is not None:
            rango["maxima_ha"] = propio["maxima_ha_con_FSC"]
        rango["numeral"] = propio.get("numeral") or rango["numeral"]
    mn, mx = rango["minima_ha"], rango["maxima_ha"]
    if sup.get("aplica") is False:
        rango["texto"] = "El programa no usa superficie (las reglas pagan por persona)"
    elif rango.get("minima_exclusiva") and mx is not None:
        rango["texto"] = f"Superficie mayor de {mn} y hasta {mx} ha"
    elif rango.get("minima_exclusiva"):
        rango["texto"] = f"Superficie mayor de {mn} ha (las reglas no fijan máximo)"
    elif mn is not None and mx is not None:
        rango["texto"] = f"Superficie de {mn} a {mx} ha"
    elif mn is not None:
        rango["texto"] = f"Superficie de al menos {mn} ha (las reglas no fijan máximo)"
    elif mx is not None:
        rango["texto"] = f"Superficie de hasta {mx} ha"
    else:
        rango["texto"] = "Superficie (las reglas no fijan rango)"
    return rango


def en_rango(rango, superficie):
    """True/False si hay al menos un límite; None si las reglas no fijan ninguno."""
    mn, mx = rango["minima_ha"], rango["maxima_ha"]
    if mn is None and mx is None:
        return None
    s = float(superficie)
    minimo = mn is None or (s > mn if rango.get("minima_exclusiva") else s >= mn)
    return minimo and (mx is None or s <= mx)
