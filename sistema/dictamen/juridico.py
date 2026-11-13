"""HU-2.2 · Dictamen jurídico y cotejo con el Listado de Personas Beneficiarias Incumplidas y con los
predios con procedimiento o sanción."""
import unicodedata

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from nucleo.acuses import emitir_acuse
from nucleo.models import Evento, TipoUnidad

from .comun import completar_si_ya_hay_dos, exigir_acceso, exigir_unidad
from .models import DictamenJuridico, PersonaIncumplida, PredioSancionado, ResultadoJuridico


def _normal(texto):
    texto = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()
    return " ".join(texto.upper().split())


def cotejar(expediente):
    """Coincidencias del titular y del predio con los catálogos (automático; se muestra en pantalla)."""
    titular = expediente.solicitante
    coincidencias = []
    filtro = Q(persona=titular)
    if titular.curp:
        filtro |= Q(curp__iexact=titular.curp)
    if titular.rfc:
        filtro |= Q(rfc__iexact=titular.rfc)
    candidatos = set(PersonaIncumplida.objects.filter(activa=True).filter(filtro))
    nombre = _normal(titular.nombre)
    for p in PersonaIncumplida.objects.filter(activa=True):
        if _normal(p.nombre) == nombre:
            candidatos.add(p)
    for p in sorted(candidatos, key=lambda x: x.pk):
        criterio = ("persona" if p.persona_id == titular.pk else "CURP" if titular.curp and p.curp.upper() == titular.curp.upper()
                    else "RFC" if titular.rfc and p.rfc.upper() == titular.rfc.upper() else "nombre")
        coincidencias.append({
            "catalogo": "Listado de Personas Beneficiarias Incumplidas", "id": p.pk, "nombre": p.nombre,
            "coincide_por": criterio, "motivo": p.motivo, "fecha": p.fecha_inscripcion.isoformat(),
            "fundamento": "CC 8.1.1.1 inelegibles fr. I y II",
        })
    predio = expediente.predio
    for s in PredioSancionado.objects.filter(activo=True, reintegro_realizado=False).filter(
            Q(predio=predio) | Q(descripcion_predio__iexact=predio.folio)):
        coincidencias.append({
            "catalogo": "Predios con procedimiento o sanción", "id": s.pk, "nombre": s.descripcion_predio,
            "coincide_por": "predio", "motivo": f"{s.get_tipo_display()}: {s.descripcion}", "fecha": s.fecha.isoformat(),
            "fundamento": "CC 8.1.1.1 inelegibles fr. III y V",
        })
    return coincidencias


def dictaminar(usuario, expediente, resultado, motivo):
    """La Unidad Jurídica emite el dictamen jurídico. Con coincidencias en los catálogos no puede ser procedente."""
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    exigir_acceso(usuario, expediente)
    if expediente.estado.clave != "validada":
        raise ValidationError(f"El expediente está «{expediente.estado}»; solo se dictamina un expediente validado.")
    if hasattr(expediente, "dictamen_juridico"):
        raise ValidationError("El expediente ya tiene dictamen jurídico.")
    if resultado not in ResultadoJuridico.values:
        raise ValidationError("El resultado debe ser procedente o no procedente.")
    if not (motivo or "").strip():
        raise ValidationError("El dictamen jurídico debe llevar su motivo.")
    coincidencias = cotejar(expediente)
    if resultado == ResultadoJuridico.PROCEDENTE and coincidencias:
        nombres = "; ".join(f"{c['catalogo']}: {c['nombre']}" for c in coincidencias)
        raise ValidationError(f"No puede ser procedente: el titular o el predio está en {nombres} "
                              "(ROP CC 8.1.1.1, inelegibles).")
    ahora = timezone.now()
    with transaction.atomic():
        dictamen = DictamenJuridico.objects.create(expediente=expediente, resultado=resultado, motivo=motivo.strip(),
                                                   cotejo=coincidencias, usuario=usuario, fecha_hora=ahora)
        renglones = [
            ("Resultado", dictamen.get_resultado_display()), ("Motivo", dictamen.motivo),
            ("Refrendo", "Sí (las ROP piden nuevo dictamen jurídico, CC 10.1 fr. IV)" if expediente.es_refrendo else "No"),
            ("Cotejo con el Listado de Incumplidas y predios sancionados",
             "Sin coincidencias" if not coincidencias else f"{len(coincidencias)} coincidencia(s)"),
        ]
        detalle = [{"clave": c["coincide_por"], "texto": f"{c['catalogo']}: {c['nombre']} — {c['motivo']}"[:200],
                    "estado": c["fecha"]} for c in coincidencias]
        acuse = emitir_acuse(expediente, "dictamen_juridico", "Dictamen jurídico", usuario, renglones, detalle=detalle,
                             encabezado_detalle=["Coincide por", "Registro", "Fecha"])
        dictamen.acuse = acuse
        dictamen.save(update_fields=["acuse"])
        Evento.registrar(expediente, usuario, "dictamen_juridico",
                         f"Dictamen jurídico {dictamen.get_resultado_display().lower()}: {dictamen.motivo}", acuse=acuse,
                         datos={"resultado": resultado, "coincidencias": len(coincidencias)})
        completar_si_ya_hay_dos(expediente, usuario)
    return dictamen


def registrar_incumplida(usuario, **datos):
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    if not datos.get("nombre") or not datos.get("motivo"):
        raise ValidationError("Escriba el nombre y el motivo de la inscripción.")
    return PersonaIncumplida.objects.create(registrado_por=usuario, **datos)


def registrar_predio_sancionado(usuario, **datos):
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    if not datos.get("descripcion_predio") or not datos.get("descripcion"):
        raise ValidationError("Escriba el predio y la descripción del procedimiento o sanción.")
    return PredioSancionado.objects.create(registrado_por=usuario, **datos)


def dar_de_baja(usuario, registro, motivo):
    """Baja del Listado (no se borra: queda en su historial)."""
    exigir_unidad(usuario, TipoUnidad.JURIDICA)
    if not (motivo or "").strip():
        raise ValidationError("Indique el motivo de la baja.")
    if isinstance(registro, PersonaIncumplida):
        registro.activa = False
    else:
        registro.activo = False
    registro._change_reason = motivo
    registro.save()
    return registro
