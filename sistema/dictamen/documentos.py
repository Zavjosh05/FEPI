"""HU-2.1 y HU-2.2 · Documento formal (PDF) del dictamen técnico y del dictamen jurídico.

Al registrar un dictamen, el sistema expide su documento: folio propio (DT-… o DJ-…), datos de la solicitud, el análisis o
la revisión que sustenta el resultado, el resultado con su motivo y las firmas. El PDF se guarda como ``Documento`` de tipo
«dictamen» del expediente (pestaña «Documentos y acuses») y el dictamen guarda su folio, el documento y la huella SHA-256.
"""
import hashlib

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from nucleo.models import Consecutivo, Documento, TipoDocumento
from recepcion.models import ResultadoValidacion, UbicacionMunicipio

from .comun import datos_dictamen


def _pdf(html):
    """Pasa por el único punto del núcleo que convierte HTML en PDF (``nucleo.acuses._pdf``)."""
    from nucleo import acuses

    return acuses._pdf(html)


def nuevo_folio(clase, expediente):
    conf = datos_dictamen()["documentos"][clase]
    prog, anio = expediente.programa.clave, expediente.ejercicio.anio
    n = Consecutivo.siguiente(f"dictamen-{clase}-{prog}-{anio}")
    return f"{conf['prefijo']}-{prog}-{anio}-{n:04d}"


def croquis_svg(geom, ancho=200, alto=170):
    """Croquis del polígono en SVG (proyección simple lon/lat con corrección por latitud), para el PDF."""
    import math

    if geom is None or geom.empty:
        return ""
    xmin, ymin, xmax, ymax = geom.extent
    k = math.cos(math.radians((ymin + ymax) / 2))
    dx, dy = max((xmax - xmin) * k, 1e-9), max(ymax - ymin, 1e-9)
    escala = min((ancho - 20) / dx, (alto - 30) / dy)
    caminos = []
    for poligono in geom:
        for anillo in poligono:
            puntos = " ".join(f"{10 + (x - xmin) * k * escala:.1f},{alto - 20 - (y - ymin) * escala:.1f}" for x, y in anillo.coords)
            caminos.append(f"M {puntos} Z")
    metros = dx * 111320 if dx else 0
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="100%">'
            f'<rect width="{ancho}" height="{alto}" fill="#f7faf7"/>'
            f'<path d="{" ".join(caminos)}" fill="#7fb08a" fill-opacity=".55" stroke="#1f5130" stroke-width="1.4"/>'
            f'<text x="6" y="{alto - 6}" font-size="8" fill="#555">Croquis del polígono vigente · ancho ≈ {metros:,.0f} m</text>'
            f'<text x="{ancho - 12}" y="14" font-size="10" fill="#1f5130" font-weight="bold">N</text></svg>')


def _contexto(dictamen, clase, folio):
    exp = dictamen.expediente
    validacion = exp.validaciones.filter(resultado=ResultadoValidacion.VALIDADO).order_by("-fecha_hora").first()
    return {
        "dictamen": dictamen, "exp": exp, "conf": datos_dictamen()["documentos"][clase], "folio": folio,
        "fecha_local": timezone.localtime(dictamen.fecha_hora), "unidad": dictamen.usuario.unidad,
        "validacion": validacion,
    }


def _adjuntar(dictamen, clase, folio, html):
    """Genera el PDF, lo adjunta al expediente y guarda folio, documento y huella en el dictamen."""
    conf = datos_dictamen()["documentos"][clase]
    contenido = _pdf(html)
    exp = dictamen.expediente
    doc = Documento(expediente=exp, tipo=TipoDocumento.DICTAMEN, nombre=f"{folio} · {conf['titulo']} ({dictamen.get_resultado_display().lower()})",
                    fecha_entrega=dictamen.fecha_hora, registrado_por=dictamen.usuario, unidad=dictamen.usuario.unidad)
    doc.archivo.save(f"{folio}.pdf", ContentFile(contenido), save=False)
    doc._change_reason = f"{conf['titulo']} expedido"
    doc.save()
    dictamen.folio = folio
    dictamen.documento = doc
    dictamen.huella = hashlib.sha256(contenido).hexdigest()
    dictamen._change_reason = f"Se expide el documento {folio}"
    dictamen.save(update_fields=["folio", "documento", "huella"])
    return doc


def html_tecnico(dictamen, folio, plazo=None):
    analisis = dictamen.analisis or {}
    poligono = None
    if analisis.get("poligono_id"):
        poligono = dictamen.expediente.poligonos.filter(pk=analisis["poligono_id"]).first()
    contexto = _contexto(dictamen, "tecnico", folio)
    contexto.update({
        "analisis": analisis, "verificacion": dictamen.verificacion, "plazo": plazo, "poligono": poligono,
        "ubicacion_texto": dict(UbicacionMunicipio.choices).get(analisis.get("ubicacion_municipio"), "—"),
        "croquis": croquis_svg(poligono.geom) if poligono is not None else "",
    })
    return render_to_string("dictamen/pdf/dictamen_tecnico.html", contexto)


def emitir_tecnico(dictamen, plazo=None):
    folio = nuevo_folio("tecnico", dictamen.expediente)
    return _adjuntar(dictamen, "tecnico", folio, html_tecnico(dictamen, folio, plazo))


def html_juridico(dictamen, folio):
    contexto = _contexto(dictamen, "juridico", folio)
    contexto.update({
        "documentacion": dictamen.documentacion, "propiedad": getattr(dictamen, "propiedad", None),
        "fundamento_propiedad": "Fundamento: " + datos_dictamen()["propiedad"]["fundamento"] + ".",
    })
    return render_to_string("dictamen/pdf/dictamen_juridico.html", contexto)


def emitir_juridico(dictamen):
    folio = nuevo_folio("juridico", dictamen.expediente)
    return _adjuntar(dictamen, "juridico", folio, html_juridico(dictamen, folio))
