"""Cuentas del portal de personas beneficiarias (S2-05, opción 1 con la 2 de respaldo).

- ``dar_acceso``: la Delegación del expediente da de alta a la persona (usuario = su CURP) o, si ya tiene cuenta, le suma
  el expediente. Si la cuenta no se ha activado, emite un **código de un solo uso** para el primer acceso. Siempre deja el
  **código de consulta** del expediente (respaldo sin cuenta: folio + código). Los códigos se imprimen en un acuse con
  fecha y hora (se entrega en persona: no hay correo ni SMS) y en la base solo se guardan cifrados.
- ``al_firmar``: gancho de ``extensiones.AL_FIRMAR``: al registrar la firma del contrato (HU-3.3) se da el acceso a la
  persona beneficiaria (en PEG, el Guardabosque). Sin CURP (persona jurídico colectiva o núcleo agrario) no hay cuenta:
  queda el respaldo.
- ``primer_acceso``: CURP + código + contraseña nueva; el código deja de servir.
- ``expedientes_de`` y ``consultar``: un externo solo ve SUS expedientes; con folio + código, solo ese expediente.
"""
import re
import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from nucleo.acuses import emitir_acuse
from nucleo.models import Evento, Expediente, TipoUnidad

from .models import AccesoExpediente, CodigoConsulta, CuentaExterna, RolAcceso

CURP = re.compile(r"^[A-Z][AEIOUX][A-Z]{2}\d{6}[HM][A-Z]{5}[A-Z0-9]\d$")
ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O ni 1/I/L para dictarlo sin confusión


def nuevo_codigo():
    """Código de 8 caracteres en dos grupos («K7MX-3PQA»)."""
    c = "".join(secrets.choice(ALFABETO) for _ in range(8))
    return f"{c[:4]}-{c[4:]}"


def _normal(codigo):
    return (codigo or "").strip().upper().replace(" ", "")


def es_externo(usuario):
    return bool(usuario and usuario.is_authenticated and hasattr(usuario, "cuenta_externa"))


def curp_valida(curp):
    return bool(CURP.match((curp or "").strip().upper()))


# ----------------------------------------------------------------------------- alta
def dar_acceso(usuario, expediente, persona=None, rol=RolAcceso.BENEFICIARIA, momento=None):
    """La Delegación del expediente da acceso a la persona. Devuelve ``{"cuenta", "codigo_acceso", "codigo_consulta",
    "acuse"}`` (los códigos en claro solo aquí, para imprimirlos; ``None`` si no se emitieron)."""
    if usuario.tipo_unidad != TipoUnidad.DELEGACION or usuario.unidad_id != expediente.delegacion_id:
        raise PermissionDenied("Da el acceso al portal la Delegación del expediente.")
    persona = persona or expediente.beneficiaria
    ahora = momento or timezone.now()
    curp = (persona.curp or "").strip().upper()
    cuenta = codigo_acceso = codigo_consulta = None
    with transaction.atomic():
        if curp_valida(curp):
            Usuario = get_user_model()
            existente = Usuario.objects.filter(username=curp).first()
            if existente is not None and not hasattr(existente, "cuenta_externa"):
                raise ValidationError(f"La CURP {curp} ya es usuario del personal: no se crea la cuenta del portal.")
            if existente is None:
                existente = Usuario(username=curp, first_name=persona.nombre[:150], unidad=None)
                existente.set_unusable_password()
                existente.save()
                cuenta = CuentaExterna.objects.create(usuario=existente, persona=persona, creada_por=usuario, creada_en=ahora)
            else:
                cuenta = existente.cuenta_externa
            if cuenta.activada_en is None:
                codigo_acceso = nuevo_codigo()
                cuenta.codigo_hash = make_password(_normal(codigo_acceso))
                cuenta.codigo_emitido_en = ahora
                cuenta.save(update_fields=["codigo_hash", "codigo_emitido_en"])
        if not CodigoConsulta.objects.filter(expediente=expediente).exists():
            codigo_consulta = nuevo_codigo()
            consulta = CodigoConsulta.objects.create(expediente=expediente, codigo_hash=make_password(_normal(codigo_consulta)),
                                                     creado_en=ahora)
        renglones = [("Persona", persona.nombre), ("Expediente", f"{expediente.folio} · {expediente.programa.nombre}")]
        if cuenta:
            renglones += [("Usuario del portal (CURP)", cuenta.usuario.username)]
            renglones += [("Código de primer acceso (un solo uso)", codigo_acceso)] if codigo_acceso else [
                ("Primer acceso", "La cuenta ya está activa: entre con su contraseña.")]
        else:
            renglones += [("Cuenta del portal", "Sin CURP válida no se crea cuenta: use el folio y el código de consulta.")]
        if codigo_consulta:
            renglones += [("Consulta sin cuenta", f"Folio {expediente.folio} y código {codigo_consulta}")]
        if not (codigo_acceso or codigo_consulta or cuenta):
            return {"cuenta": None, "codigo_acceso": None, "codigo_consulta": None, "acuse": None}
        acuse = emitir_acuse(
            expediente, "alta_portal", "Acceso al portal de personas beneficiarias", usuario, renglones,
            destinatario=persona.nombre,
            nota="Entre en /portal/ (pantalla «Personas beneficiarias»): la primera vez escriba su CURP y el código de "
                 "primer acceso y defina su contraseña. El código sirve una sola vez. Con el folio y el código de consulta "
                 "puede ver este expediente sin cuenta. No comparta estos códigos.")
        if codigo_consulta:
            consulta.acuse = acuse
            consulta.save(update_fields=["acuse"])
        if cuenta:
            acceso, _ = AccesoExpediente.objects.get_or_create(
                cuenta=cuenta, expediente=expediente,
                defaults={"rol": rol, "otorgado_por": usuario, "otorgado_en": ahora, "acuse": acuse})
        Evento.registrar(expediente, usuario, "alta_portal",
                         f"Acceso al portal para {persona.nombre}" + (f" (usuario {cuenta.usuario.username})" if cuenta else
                                                                     " (sin cuenta: folio y código de consulta)"),
                         acuse=acuse)
    return {"cuenta": cuenta, "codigo_acceso": codigo_acceso, "codigo_consulta": codigo_consulta, "acuse": acuse}


def dar_acceso_prestador(usuario, expediente, nombre, curp, rfn=""):
    """La Delegación del expediente da acceso al portal al prestador de servicios forestales (RFN) que atiende el predio: se
    registra como persona (tipo prestador; se reutiliza si ya existe con esa CURP) y entra con el papel «prestador»."""
    from nucleo.models import Persona, TipoPersonaGeneral

    nombre, curp, rfn = (nombre or "").strip(), (curp or "").strip().upper(), (rfn or "").strip()
    if not nombre:
        raise ValidationError("Escriba el nombre del prestador de servicios forestales.")
    if not curp_valida(curp):
        raise ValidationError("La CURP del prestador no es válida: sin ella no se crea la cuenta del portal.")
    if usuario.tipo_unidad != TipoUnidad.DELEGACION or usuario.unidad_id != expediente.delegacion_id:
        raise PermissionDenied("Da el acceso al portal la Delegación del expediente.")
    persona = Persona.objects.filter(curp=curp, tipo=TipoPersonaGeneral.PRESTADOR).first()
    if persona is None:
        persona = Persona.objects.create(tipo=TipoPersonaGeneral.PRESTADOR, nombre=nombre, curp=curp, rfn=rfn)
    elif rfn and persona.rfn != rfn:
        persona.rfn = rfn
        persona.save(update_fields=["rfn"])
    return dar_acceso(usuario, expediente, persona, rol=RolAcceso.PRESTADOR)


def prestadores_de(expediente):
    """Accesos del portal de los prestadores de servicios forestales del expediente."""
    return (AccesoExpediente.objects.filter(expediente=expediente, rol=RolAcceso.PRESTADOR)
            .select_related("cuenta__persona", "cuenta__usuario", "acuse"))


def al_firmar(firma):
    """Gancho de HU-3.3: al registrar la firma se da acceso al portal a la persona beneficiaria (en PEG, el
    Guardabosque)."""
    exp = firma.expediente
    try:
        dar_acceso(firma.registrada_por, exp, exp.beneficiaria)
    except (ValidationError, PermissionDenied) as e:
        Evento.registrar(exp, firma.registrada_por, "alta_portal",
                         f"No se dio acceso al portal: {'; '.join(getattr(e, 'messages', [str(e)]))}")


# ----------------------------------------------------------------------------- entrada
def primer_acceso(curp, codigo, contrasena):
    """Activa la cuenta: la persona define su contraseña con el código de un solo uso."""
    Usuario = get_user_model()
    u = Usuario.objects.filter(username=(curp or "").strip().upper(), cuenta_externa__isnull=False).first()
    cuenta = getattr(u, "cuenta_externa", None)
    if cuenta is None or cuenta.activada_en is not None or not cuenta.codigo_hash \
            or not check_password(_normal(codigo), cuenta.codigo_hash):
        raise ValidationError("La CURP o el código no son válidos, o el código ya se usó.")
    validate_password(contrasena, u)
    with transaction.atomic():
        u.set_password(contrasena)
        u.save(update_fields=["password"])
        cuenta.activada_en = timezone.now()
        cuenta.codigo_hash = ""
        cuenta.save(update_fields=["activada_en", "codigo_hash"])
    return u


def expedientes_de(usuario):
    """Expedientes que ve la cuenta externa (solo los suyos)."""
    if not es_externo(usuario):
        return Expediente.objects.none()
    return (Expediente.objects.filter(accesos_portal__cuenta__usuario=usuario)
            .select_related("ejercicio__programa", "estado", "predio__municipio", "delegacion").distinct())


def consultar(folio, codigo):
    """Respaldo sin cuenta: el expediente si el folio y el código coinciden, o None."""
    c = CodigoConsulta.objects.select_related("expediente").filter(expediente__folio=(folio or "").strip().upper()).first()
    if c is None or not check_password(_normal(codigo), c.codigo_hash):
        return None
    return c.expediente
