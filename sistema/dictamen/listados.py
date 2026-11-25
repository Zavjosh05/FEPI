"""Candidatos y beneficiarios: dos vistas separadas de las solicitudes de un programa-ejercicio.

- **Candidatos**: solicitudes que todavía compiten por el apoyo, desde que el expediente se valida hasta que el Comité
  decide: en dictamen, dictaminadas por llevar a la sesión de aprobación y en lista de espera (con su lugar).
- **Beneficiarios**: personas beneficiarias vigentes (aprobadas por el Comité en el acta o por reasignación), con el
  monto, la superficie, cómo entraron, su situación en el trámite (publicada, notificada, contratada, pagada…) y la fecha
  en que se publicó su resultado (M3, HU-3.1); aparte, las que salieron por un acuerdo de seguimiento (baja) o porque la
  Dirección liberó su recurso al no firmarse el contrato en plazo (HU-3.3), y quién entró en su lugar.

Las dos usan ``expedientes_visibles``: la Delegación ve solo los suyos.
"""
import csv
import io
from decimal import Decimal

from .comun import resultado_combinado
from .models import EstadoSesion, MovimientoListado, ResolucionSesion, TipoMovimiento, TipoSesion
from .seguimiento import ESTADOS_CON_BAJA, ESTADOS_CON_PAGO, movimientos_del_ejercicio

CERO = Decimal("0")
SITUACIONES_CANDIDATO = {
    "en_dictamen": ("validada", "En dictamen técnico y jurídico"),
    "por_aprobar": ("dictaminada", "Dictaminada · por llevar a la sesión de aprobación"),
    "lista_espera": ("lista_espera", "Lista de espera"),
}


def _resolucion(expediente):
    return (ResolucionSesion.objects.filter(expediente=expediente, sesion__tipo=TipoSesion.APROBACION,
                                            sesion__estado=EstadoSesion.CELEBRADA)
            .select_related("sesion").order_by("-sesion__fecha_hora", "-pk").first())


def candidatos(ejercicio, expedientes, situacion=""):
    estados = [v[0] for k, v in SITUACIONES_CANDIDATO.items() if not situacion or k == situacion]
    qs = (expedientes.filter(ejercicio=ejercicio, estado__clave__in=estados)
          .select_related("predio__municipio", "solicitante", "estado", "delegacion", "dictamen_tecnico",
                          "dictamen_juridico__propiedad", "modalidad"))
    filas = []
    for exp in qs:
        tecnico = getattr(exp, "dictamen_tecnico", None)
        juridico = getattr(exp, "dictamen_juridico", None)
        propiedad = getattr(juridico, "propiedad", None) if juridico else None
        resultado, texto = resultado_combinado(exp)
        res = _resolucion(exp) if exp.estado.clave == "lista_espera" else None
        filas.append({
            "expediente": exp, "folio": exp.folio, "solicitante": exp.solicitante.nombre, "predio": exp.predio.nombre,
            "municipio": exp.predio.municipio.nombre, "delegacion": exp.delegacion.nombre,
            "superficie_ha": (tecnico.superficie_factible_ha if tecnico and tecnico.superficie_factible_ha
                              else exp.superficie_solicitada_ha),
            "tecnico": tecnico.get_resultado_display() if tecnico else "Pendiente",
            "juridico": juridico.get_resultado_display() if juridico else "Pendiente",
            "propiedad": ("Acreditada" if propiedad.acreditada else "No acreditada") if propiedad else "Pendiente",
            "resultado": resultado, "resultado_texto": {"factible": "Factible", "no_factible": "No factible",
                                                        "pendiente": "Pendiente"}[resultado],
            "situacion": next(k for k, v in SITUACIONES_CANDIDATO.items() if v[0] == exp.estado.clave),
            "situacion_texto": exp.estado.nombre,
            "lugar": res.orden if res else None, "monto": res.monto if res else None,
            "fecha_recepcion": exp.fecha_recepcion,
        })
    orden = {"lista_espera": 0, "por_aprobar": 1, "en_dictamen": 2}
    filas.sort(key=lambda f: (orden[f["situacion"]], f["lugar"] or 0, f["fecha_recepcion"]))
    return filas


def beneficiarios(ejercicio, expedientes):
    """(vigentes, bajas): las personas beneficiarias vigentes, en cualquier etapa desde la aprobación hasta el pago, y
    las que salieron (baja por acuerdo del Comité o recurso liberado por falta de firma en plazo)."""
    vigentes = []
    for exp in (expedientes.filter(ejercicio=ejercicio, estado__clave__in=ESTADOS_CON_BAJA + ESTADOS_CON_PAGO)
                .select_related("predio__municipio", "solicitante", "delegacion", "dictamen_tecnico", "estado")):
        entrada = (MovimientoListado.objects.filter(expediente=exp, movimiento=TipoMovimiento.ENTRA)
                   .select_related("acuerdo__sesion").order_by("-fecha_hora").first())
        res = _resolucion(exp)
        if entrada is not None:
            via = f"Reasignación · acuerdo {entrada.acuerdo.numero} (lugar {entrada.lugar_lista_espera} de la lista de espera)"
            fecha, monto = entrada.fecha_hora, entrada.monto
        elif res is not None:
            via = f"Acta de la sesión {res.sesion.numero}" + (f" · lugar {res.orden}" if res.orden else "")
            fecha, monto = res.sesion.acta_fecha or res.sesion.fecha_hora, res.monto
        else:
            via, fecha, monto = "—", None, None
        tecnico = getattr(exp, "dictamen_tecnico", None)
        # Publicación de su resultado (M3); la relación la agrega la app de contrato.
        publicado = (exp.resultados_publicados.select_related("publicacion").order_by("-publicacion__publicada_en").first()
                     if hasattr(exp, "resultados_publicados") else None)
        vigentes.append({
            "expediente": exp, "folio": exp.folio, "beneficiario": exp.solicitante.nombre, "curp": exp.solicitante.curp,
            "predio": exp.predio.nombre, "municipio": exp.predio.municipio.nombre, "delegacion": exp.delegacion.nombre,
            "superficie_ha": tecnico.superficie_factible_ha if tecnico else exp.superficie_solicitada_ha,
            "monto": monto, "via": via, "reasignada": entrada is not None, "fecha": fecha,
            "situacion": exp.estado.nombre, "publicada_en": publicado.publicacion.publicada_en if publicado else None,
        })
    vigentes.sort(key=lambda f: (f["reasignada"], f["folio"]))
    bajas = []
    for m in (movimientos_del_ejercicio(ejercicio).filter(movimiento=TipoMovimiento.SALE, expediente__in=expedientes)
              .select_related("acuerdo", "expediente__solicitante", "expediente__predio")):
        entraron = ([x.expediente.folio for x in m.acuerdo.movimientos.filter(movimiento=TipoMovimiento.ENTRA)
                     .select_related("expediente")] if m.acuerdo_id else [])
        bajas.append({"expediente": m.expediente, "folio": m.expediente.folio, "beneficiario": m.expediente.solicitante.nombre,
                      "predio": m.expediente.predio.nombre, "acuerdo": m.acuerdo,
                      "causa": m.acuerdo.causa if m.acuerdo_id else m.motivo,
                      "monto": m.monto, "fecha": m.fecha_hora, "entraron": entraron})
    return vigentes, bajas


def totales(filas):
    return {"n": len(filas), "monto": sum((f["monto"] for f in filas if f.get("monto") is not None), CERO),
            "superficie": sum((f["superficie_ha"] for f in filas if f.get("superficie_ha") is not None), CERO)}


def csv_de(filas, columnas):
    salida = io.StringIO()
    salida.write("﻿")
    escritor = csv.writer(salida)
    escritor.writerow([t for _, t in columnas])
    for f in filas:
        escritor.writerow(["" if f.get(c) is None else f[c] for c, _ in columnas])
    return salida.getvalue()


COLUMNAS_CANDIDATOS = [("folio", "Folio"), ("solicitante", "Persona solicitante"), ("predio", "Predio"),
                       ("municipio", "Municipio"), ("delegacion", "Delegación"), ("superficie_ha", "Superficie (ha)"),
                       ("tecnico", "Dictamen técnico"), ("juridico", "Dictamen jurídico"), ("propiedad", "Propiedad"),
                       ("resultado_texto", "Resultado preliminar"), ("situacion_texto", "Situación"),
                       ("lugar", "Lugar en la lista de espera"), ("monto", "Monto")]
COLUMNAS_BENEFICIARIOS = [("folio", "Folio"), ("beneficiario", "Persona beneficiaria"), ("curp", "CURP"),
                          ("predio", "Predio"), ("municipio", "Municipio"), ("delegacion", "Delegación"),
                          ("superficie_ha", "Superficie (ha)"), ("monto", "Monto"), ("via", "Cómo entró"),
                          ("situacion", "Situación"), ("publicada_en", "Publicada")]
