"""Lecturas de las reglas del programa que dependen del expediente (modalidad, condiciones).

Las reglas de cada programa traen la superficie con forma distinta: CC un rango general; PS un rango por
concepto (``por_concepto``); PSAHEM uno por categoría de cuenca (``por_categoria``, con máximo mayor si hay
certificación FSC); RHF solo mínimo. ``rango_superficie`` lo resuelve igual para todos.
"""


def rango_superficie(ejercicio, modalidad=None, condiciones=()):
    """``{"minima_ha", "maxima_ha", "numeral", "texto"}`` para la modalidad (None = sin límite en las reglas)."""
    sup = (ejercicio.datos or {}).get("superficie") or {}
    rango = {"minima_ha": sup.get("minima_ha"), "maxima_ha": sup.get("maxima_ha"), "numeral": sup.get("numeral", "")}
    clave = getattr(modalidad, "clave", modalidad)
    propio = None
    for nombre in ("por_concepto", "por_categoria"):
        if clave and clave in (sup.get(nombre) or {}):
            propio = sup[nombre][clave]
    if propio:
        rango["minima_ha"] = propio.get("minima_ha", rango["minima_ha"])
        rango["maxima_ha"] = propio.get("maxima_ha", rango["maxima_ha"])
        if "certificacion_FSC" in set(condiciones) and propio.get("maxima_ha_con_FSC") is not None:
            rango["maxima_ha"] = propio["maxima_ha_con_FSC"]
        rango["numeral"] = propio.get("numeral") or rango["numeral"]
    mn, mx = rango["minima_ha"], rango["maxima_ha"]
    if mn is not None and mx is not None:
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
    return (mn is None or s >= mn) and (mx is None or s <= mx)
