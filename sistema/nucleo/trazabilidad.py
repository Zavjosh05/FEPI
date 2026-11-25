"""Trazabilidad de la información en la base de datos.

Cada modelo del trámite guarda su historial con django-simple-history (una tabla ``historical<modelo>`` por modelo):
cada alta, cambio o baja deja un renglón con los valores de ese momento, el usuario, la fecha y la hora y el motivo.

- ``con_usuario`` / ``registra_usuario``: los servicios se llaman desde las pantallas (el middleware de simple-history ya
  sabe quién es el usuario), pero también desde las pruebas, la demostración y los comandos. Con esto el usuario que hace
  la acción queda en el historial aunque no haya una petición web.
- ``historial_expediente``: junta el historial de todos los registros de un expediente (los de cada módulo se agregan con
  ``extensiones.TRAZABILIDAD``) y lo devuelve campo por campo (antes → después), para la pestaña «Trazabilidad».
"""
import functools
from contextlib import contextmanager
from types import SimpleNamespace

from django.contrib.gis.geos import GEOSGeometry
from django.db import models
from django.utils import timezone
from simple_history.models import HistoricalRecords

TIPOS = {"+": "Alta", "~": "Cambio", "-": "Baja"}
# Campos que no se muestran en el detalle (técnicos o que cambian solos).
OMITIR = {"id", "actualizado", "history_id", "history_date", "history_change_reason", "history_type", "history_user",
          "history_user_id"}


@contextmanager
def con_usuario(usuario):
    """Durante el bloque, el historial registra a ``usuario`` si no hay ya una petición web con usuario."""
    contexto = HistoricalRecords.context
    previa = getattr(contexto, "request", None)
    ya_hay = previa is not None and getattr(getattr(previa, "user", None), "is_authenticated", False)
    if ya_hay or usuario is None or not getattr(usuario, "is_authenticated", False):
        yield
        return
    contexto.request = SimpleNamespace(user=usuario)
    try:
        yield
    finally:
        if previa is None:
            try:
                del contexto.request
            except AttributeError:
                pass
        else:
            contexto.request = previa


def registra_usuario(funcion):
    """Decorador para los servicios cuyo primer argumento es el usuario que hace la acción."""
    @functools.wraps(funcion)
    def envoltura(usuario, *args, **kwargs):
        with con_usuario(usuario):
            return funcion(usuario, *args, **kwargs)
    return envoltura


# ----------------------------------------------------------------------------- historial del expediente
def _texto(campo, valor, cache):
    if valor is None or valor == "":
        return "—"
    if isinstance(campo, models.ForeignKey):
        clave = (campo.related_model, valor)
        if clave not in cache:
            obj = campo.related_model._default_manager.filter(pk=valor).first()
            cache[clave] = str(obj) if obj is not None else f"#{valor}"
        return cache[clave]
    if getattr(campo, "choices", None):
        return str(dict(campo.flatchoices).get(valor, valor))
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, GEOSGeometry):
        return "(geometría)"
    if isinstance(valor, (list, dict)):
        return f"({len(valor)} elemento{'s' if len(valor) != 1 else ''})" if valor else "—"
    if hasattr(valor, "tzinfo") and hasattr(valor, "hour"):
        return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M:%S")
    if hasattr(valor, "strftime"):
        return valor.strftime("%d/%m/%Y")
    texto = str(valor)
    return texto if len(texto) <= 160 else texto[:157] + "…"


def _campos(modelo):
    return [f for f in modelo._meta.concrete_fields if f.attname not in OMITIR and f.name not in OMITIR]


def renglones(etiqueta, historial, cache=None):
    """Renglones legibles de un queryset de historial: uno por alta, cambio o baja, con los campos que cambiaron."""
    cache = {} if cache is None else cache
    filas = []
    registros = list(historial.select_related("history_user").order_by("history_date", "history_id"))
    previos = {}
    for h in registros:
        modelo = h.instance_type
        campos = _campos(modelo)
        anterior = previos.get(h.id)
        cambios = []
        for c in campos:
            nuevo = getattr(h, c.attname, None)
            if anterior is None:
                if h.history_type == "+" and nuevo not in (None, "", [], {}, False):
                    cambios.append({"campo": str(c.verbose_name), "antes": "", "despues": _texto(c, nuevo, cache)})
                continue
            viejo = getattr(anterior, c.attname, None)
            if isinstance(nuevo, GEOSGeometry) or isinstance(viejo, GEOSGeometry):
                distinto = (nuevo is None) != (viejo is None) or (nuevo is not None and not nuevo.equals_exact(viejo))
            else:
                distinto = nuevo != viejo
            if distinto:
                cambios.append({"campo": str(c.verbose_name), "antes": _texto(c, viejo, cache), "despues": _texto(c, nuevo, cache)})
        previos[h.id] = h
        if anterior is not None and h.history_type == "~" and not cambios:
            continue  # se guardó sin cambiar nada visible
        usuario = h.history_user
        filas.append({
            "fecha_hora": h.history_date, "usuario": usuario, "unidad": getattr(usuario, "unidad", None) if usuario else None,
            "registro": etiqueta, "objeto": f"{modelo._meta.verbose_name} #{h.id}", "tipo": TIPOS.get(h.history_type, h.history_type),
            "motivo": h.history_change_reason or "", "cambios": cambios, "tabla": h._meta.db_table,
        })
    return filas


def historial_expediente(expediente):
    """Historial de todos los registros del expediente, del más reciente al más antiguo."""
    from .extensiones import TRAZABILIDAD

    cache, filas = {}, []
    for fuente in TRAZABILIDAD:
        for etiqueta, historial in fuente(expediente):
            filas.extend(renglones(etiqueta, historial, cache))
    filas.sort(key=lambda f: f["fecha_hora"], reverse=True)
    return filas


def fuentes_nucleo(expediente):
    """Registros del núcleo: el expediente, su predio, la persona solicitante y los documentos."""
    from .models import Documento, Expediente, Persona, Predio

    return [
        ("Expediente", Expediente.history.filter(id=expediente.pk)),
        ("Predio", Predio.history.filter(id=expediente.predio_id)),
        ("Persona solicitante", Persona.history.filter(id=expediente.solicitante_id)),
        ("Documento", Documento.history.filter(expediente_id=expediente.pk)),
    ]
