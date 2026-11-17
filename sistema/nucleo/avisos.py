"""Avisos de plazo de M4 y M6 (S3-02d): antes de vencer (5 días hábiles o menos) y al vencer, sin ejecutar nada (P-08).

``datos/sistema.json`` → ``avisos_de_plazo.avisos``: cada aviso nombra un uso de plazo (``nucleo.plazos``), los estados
del expediente en que importa y las unidades a las que se avisa. ``revisar(hoy)`` (lo corre ``manage.py revisar_plazos``)
deja un renglón en la bitácora una sola vez por expediente, uso, situación y fecha de vencimiento; ``por_vencer(usuario)``
alimenta el panel «Por vencer» de la bandeja de cada unidad. Las historias que registran los eventos (siniestro,
fallecimiento de la persona titular, aviso de omisión, reportes entregados) no tocan este servicio: basta su hito.
"""
from django.urls import reverse
from django.utils import timezone

from . import dias_habiles, plazos
from .catalogos import datos_sistema
from .models import Evento, Expediente, expedientes_visibles

SITUACIONES = ("por vencer", "vencido")


def configuracion():
    return datos_sistema().get("avisos_de_plazo", {}).get("avisos", [])


def _candidatos(aviso, qs=None):
    qs = (qs if qs is not None else Expediente.objects.all()).filter(estado__clave__in=aviso["estados"])
    return qs.select_related("ejercicio__programa", "estado", "delegacion", "solicitante")


def _situacion(expediente, uso, hoy):
    v = plazos.vencimiento(expediente, uso)
    if v is None or not v.tiene_fecha:
        return None, v
    situacion = v.estado(hoy)
    return (situacion if situacion in SITUACIONES else None), v


def revisar(hoy=None):
    """Señala en la bitácora los plazos por vencer o vencidos de los avisos configurados. Devuelve cuántos señaló."""
    hoy = hoy or timezone.localdate()
    n = 0
    with dias_habiles.inhabiles_en_memoria():
        n = _revisar(hoy)
    return n


def _revisar(hoy):
    n = 0
    for aviso in configuracion():
        for exp in _candidatos(aviso):
            situacion, v = _situacion(exp, aviso["uso"], hoy)
            if situacion is None:
                continue
            datos = {"uso": aviso["uso"], "situacion": situacion, "vence": v.vencimiento.isoformat()}
            if exp.eventos.filter(tipo="aviso_plazo", datos__uso=datos["uso"], datos__situacion=situacion,
                                  datos__vence=datos["vence"]).exists():
                continue
            verbo = "vence" if situacion == "por vencer" else "venció"
            Evento.registrar(exp, None, "aviso_plazo",
                             f"{v.nombre}: {verbo} el {v.vencimiento:%d/%m/%Y} ({v.texto_plazo} desde {v.nombre_evento}). "
                             "Solo aviso: la unidad decide qué sigue.", datos=datos)
            n += 1
    return n


def por_vencer(usuario, hoy=None):
    """Plazos por vencer o vencidos de los expedientes que ve el usuario, para los avisos que tocan a su unidad."""
    tipo = usuario.tipo_unidad
    if tipo is None:
        return []
    hoy = hoy or timezone.localdate()
    visibles = expedientes_visibles(usuario)
    filas = []
    with dias_habiles.inhabiles_en_memoria():
        for aviso in configuracion():
            if tipo not in aviso.get("unidades", []):
                continue
            for exp in _candidatos(aviso, visibles):
                situacion, v = _situacion(exp, aviso["uso"], hoy)
                if situacion:
                    filas.append({"expediente": exp, "vencimiento": v, "situacion": situacion})
    filas.sort(key=lambda f: (f["vencimiento"].vencimiento, f["expediente"].folio))
    return filas


def panel_por_vencer(request):
    filas = por_vencer(request.user)
    if not filas:
        return None
    return {"plantilla": "nucleo/_panel_por_vencer.html", "contexto": {
        "total": len(filas),
        "filas": [{"url": reverse("recepcion:expediente", args=[f["expediente"].folio]), "folio": f["expediente"].folio,
                   "nombre": f["vencimiento"].nombre, "situacion": f["situacion"],
                   "vence": f["vencimiento"].vencimiento} for f in filas[:10]]}}
