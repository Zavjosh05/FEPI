"""Emisión de acuses en PDF (WeasyPrint) con folio, fecha y hora."""
import hashlib

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Acuse


def _pdf(html):
    from weasyprint import HTML  # importación diferida: WeasyPrint tarda en cargar

    return HTML(string=html).write_pdf()


def emitir_acuse(expediente, tipo, titulo, usuario, renglones, destinatario="", detalle=None, nota=""):
    """Crea el Acuse, genera su PDF y lo guarda.

    ``renglones``: lista de pares (etiqueta, valor) del cuerpo del acuse.
    ``detalle``: lista opcional de dicts {"clave", "texto", "estado"} (requisitos, faltantes…).
    """
    ahora = timezone.now()
    acuse = Acuse(
        expediente=expediente, tipo=tipo, titulo=titulo, fecha_hora=ahora, emitido_por=usuario,
        unidad=getattr(usuario, "unidad", None), destinatario=destinatario,
        contenido={"renglones": [[str(a), str(b)] for a, b in renglones], "detalle": detalle or [], "nota": nota},
    )
    acuse.save()  # asigna el folio
    html = render_to_string("nucleo/acuse_pdf.html", {
        "acuse": acuse, "expediente": expediente, "renglones": renglones, "detalle": detalle or [],
        "nota": nota, "fecha_local": timezone.localtime(ahora),
    })
    contenido = _pdf(html)
    acuse.huella = hashlib.sha256(contenido).hexdigest()
    acuse.archivo.save(f"{acuse.folio}.pdf", ContentFile(contenido), save=False)
    acuse.save(update_fields=["archivo", "huella"])
    return acuse
