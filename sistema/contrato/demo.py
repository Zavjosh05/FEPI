"""Datos de demostración para las historias de M3 y M5 (idempotente): dos solicitudes aprobadas de PS, de RHF y
de PSAHEM, cada programa con su sesión de aprobación y su acta. Todo con los servicios de M1, M2 y M3, igual
que la interfaz. Las de CC aprobadas las deja ``dictamen/demo.py``.

HU-3.1: PS y RHF ya publicaron sus resultados (a distintas horas); en PS la Delegación notificó el resultado
y la cita de la primera solicitud, y en RHF solo el resultado; lo demás queda por notificar. PSAHEM y CC
quedan con el acta que autoriza publicar, para mostrar la pantalla de publicación.

HU-3.2: PS y RHF tienen un modelo de Contrato de Adhesión validado por la Unidad Jurídica; CC, PS y PSAHEM tienen
además la plantilla base («BORRADOR – modelo por validar») por validar. El contrato de Plantación Los Pinos (PS)
está elaborado y enviado a la Delegación; el de Barranca Honda (RHF), elaborado y por enviar; Ojo de Agua (RHF)
está notificada y por elaborar.

HU-3.3: un segundo lote por programa (PS y RHF, con su propia sesión de aprobación y publicación) con contratos firmados
en plazo (la firma, con su verificación, deja el expediente en «contratada») y uno sin firma al vencer el plazo, señalado
por ``revisar_plazos`` y por liberar. Los de HU-3.2 siguen igual (Plantación Los Pinos queda por firmar en la
Delegación). Para vencer el plazo sin esperar días, la demostración corre hacia atrás las fechas de la publicación y de la
notificación del contrato que queda sin firma (calendario simulado)."""
from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from contrato import contratos, firma, publicacion
from contrato.models import Contrato, ModeloContrato, Publicacion, TipoModelo
from dictamen import aprobacion, juridico, sesiones, tecnico
from dictamen.demo import _validada
from dictamen.models import SesionComite, TipoSesion
from nucleo.demo import _pdf_demo
from nucleo.models import Ejercicio, Expediente, Hito, Notificacion, Usuario

# programa: [(usuario de la Delegación, municipio, predio, persona, modalidad, hectáreas)]
SOLICITUDES = {
    "PS": [("del_amecameca", "Tlalmanalco", "Plantación Los Pinos", "Abel Contreras Vega", "plantacion_forestal_comercial", 4),
           ("del_toluca", "Zinacantepec", "Rancho La Huerta", "Leticia Mora Garduño", "mantenimiento_plantaciones", 2.5)],
    "RHF": [("del_amecameca", "Ozumba", "Barranca Honda", "Rafael Sánchez Ortega", "rfi_modalidad_dos", 3),
            ("del_valle", "Amanalco", "Ojo de Agua", "Guadalupe Reyes Albarrán", "bosques_de_agua", 2)],
    "PSA": [("del_toluca", "Ocoyoacac", "Bosque El Zarco", "Felipe Hernández Ramos", "cuenca_alta", 30),
            ("del_valle", "Villa Victoria", "Monte La Loma", "Josefina Colín Becerril", "cuenca_media_baja", 25)],
}


@transaction.atomic
def cargar_demo():
    u = {x.username: x for x in Usuario.objects.all()}
    drff, uj, st = u["dir_drff"], u["juridica"], u["comite"]
    creadas = 0
    for clave, solicitudes in SOLICITUDES.items():
        ejercicio = Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()
        if ejercicio is None or SesionComite.objects.filter(ejercicio=ejercicio).exists():
            continue
        for usuario, municipio, predio, persona, modalidad, ha in solicitudes:
            exp = _validada(u[usuario], drff, ejercicio, municipio, predio, persona, modalidad, ha)
            tecnico.dictaminar(drff, exp, "factible", "Cumple los criterios técnicos de elegibilidad de las reglas.")
            juridico.dictaminar(uj, exp, "procedente", "Documentación legal completa y vigente.")
            creadas += 1
        fecha = timezone.localtime(timezone.now()) - timedelta(hours=2)
        sesion = sesiones.crear_sesion(
            st, ejercicio, TipoSesion.APROBACION, fecha, "Sala de juntas de PROBOSQUE, Metepec",
            "Lista de asistencia y declaración de quórum\nPresentación del listado preliminar\n"
            "Aprobación de los listados\nAutorización de la publicación de resultados")
        sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo(f"Listado preliminar {clave} 2026"),
                                                           name="listado_preliminar.pdf"), "Listado preliminar")
        sesiones.enviar_convocatoria(st, sesion, momento=fecha - timedelta(days=21))
        aprobacion.proponer_listados(st, sesion)
        aprobacion.registrar_acta(st, sesion, True, "Se aprueban los listados por unanimidad.",
                                  momento=fecha + timedelta(minutes=30))
    creadas += _publicaciones(u)
    creadas += _contratos(u)
    creadas += _firmas(u)
    return creadas


def _despues(base, minutos):
    """Un momento posterior a ``base`` (nunca en el futuro)."""
    return max(base, min(base + timedelta(minutes=minutos), timezone.now()))


def _publicaciones(u):
    """HU-3.1: publica PS y RHF con la demostración de avisos a distintas horas (idempotente)."""
    hechas = 0
    drff = u["dir_drff"]
    for clave, entregas in (("PS", ("resultados", "cita_firma")), ("RHF", ("resultados",))):
        sesion = (SesionComite.objects.filter(ejercicio__programa__clave=clave, tipo=TipoSesion.APROBACION,
                                              estado="celebrada", autoriza_publicacion=True, publicacion__isnull=True)
                  .order_by("-fecha_hora").first())
        if sesion is None:
            continue
        pub = publicacion.publicar(drff, sesion, momento=_despues(sesion.acta_fecha, 30))
        primera = pub.renglones.order_by("folio").first().expediente
        for minutos, tipo in zip((20, 40), entregas):
            n = primera.notificaciones.get(tipo=tipo)
            publicacion.registrar_entrega(
                _delegacion(u, primera), n, "personal" if tipo == "resultados" else "telefono",
                fecha_hora=_despues(pub.publicada_en, minutos), observaciones="Entregado (demostración).")
        hechas += 1
    return hechas


def _delegacion(u, expediente):
    return next(x for x in u.values() if x.unidad_id == expediente.delegacion_id)


def _modelo_validado(u, ejercicio, nombre):
    """Modelo de Contrato de Adhesión de demostración, registrado por el área responsable y validado por la UJ."""
    existente = ModeloContrato.objects.filter(ejercicio=ejercicio, nombre=nombre).first()
    if existente:
        return existente
    texto = contratos.PLANTILLAS_BASE[TipoModelo.CONTRATO_ADHESION].replace(contratos.MARCA_BORRADOR, "").strip()
    m = contratos.registrar_modelo(u["dir_drff"], ejercicio, TipoModelo.CONTRATO_ADHESION, nombre, texto)
    contratos.validar_version(u["juridica"], m.vigente, "Cláusulas revisadas contra las Reglas de Operación 2026 (demostración).")
    return m


def _contratos(u):
    """HU-3.2: modelos (uno validado y otro por validar), y contratos en distintos puntos (idempotente)."""
    hechos = 0
    drff = u["dir_drff"]
    for clave in ("PS", "RHF", "PSA", "CC"):
        ejercicio = Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()
        if ejercicio is None:
            continue
        if clave in ("PS", "RHF"):
            _modelo_validado(u, ejercicio, f"Contrato de Adhesión {clave} {ejercicio.anio} (modelo de demostración)")
        if clave != "RHF" and not ModeloContrato.objects.filter(ejercicio=ejercicio, es_base=True).exists():
            contratos.crear_plantilla_base(drff, ejercicio)
            hechos += 1
    for clave, predio, enviar in (("PS", "Plantación Los Pinos", True), ("RHF", "Barranca Honda", False)):
        exp = Expediente.objects.filter(ejercicio__programa__clave=clave, predio__nombre=predio).first()
        if exp is None or Contrato.objects.filter(expediente=exp).exists() or exp.estado.clave != "notificada":
            continue
        modelo = contratos.modelos_elegibles(exp)[0]
        contrato = contratos.elaborar_contrato(drff, exp, modelo)
        if enviar:
            contratos.enviar_a_delegacion(drff, contrato)
        hechos += 1
    # Ojo de Agua (RHF): la Delegación ya notificó el resultado y falta elaborar su contrato.
    ojo = Expediente.objects.filter(ejercicio__programa__clave="RHF", predio__nombre="Ojo de Agua",
                                    estado__clave="publicada").first()
    if ojo is not None:
        n = ojo.notificaciones.get(tipo="resultados")
        publicacion.registrar_entrega(_delegacion(u, ojo), n, "correo", fecha_hora=_despues(n.enviada_en, 50),
                                      observaciones="Notificado por correo electrónico (demostración).")
        hechos += 1
    return hechos


# ----------------------------------------------------------------------------- HU-3.3
# programa: [(usuario de la Delegación, municipio, predio, persona, modalidad, hectáreas, destino)]; destino:
# «firmado» (contrato firmado en plazo), «sin_firma» (vence sin firma y queda señalado) o «sin_planta» (firmado).
LOTE_FIRMAS = {
    "PS": [("del_amecameca", "Amecameca", "Mirador de los Pinos", "Hilda Maldonado Cruz", "plantacion_forestal_comercial", 5, "firmado"),
           ("del_toluca", "Zinacantepec", "Ladera Verde", "Octavio Rangel Mena", "plantacion_forestal_comercial", 3, "firmado"),
           ("del_valle", "Amanalco", "Cañada Seca", "Mireya Solís Ibarra", "mantenimiento_plantaciones", 2, "sin_firma")],
    "RHF": [("del_amecameca", "Ozumba", "Arroyo Claro", "Esteban Quiroz Lara", "bosques_de_agua", 4, "firmado"),
            ("del_valle", "Amanalco", "Cerro Gordo", "Carmen Téllez Roa", "rfi_modalidad_dos", 3, "firmado"),
            ("del_toluca", "Zinacantepec", "Peña Blanca", "Ignacio Lugo Ferrer", "rfi_modalidad_uno", 2, "sin_planta")],
}


def _envejecer(exp, dias):
    """Calendario simulado: la publicación y la notificación del resultado fueron hace ``dias`` días."""
    Hito.objects.filter(expediente=exp, clave="publicacion_resultados").update(fecha_hora=timezone.now() - timedelta(days=dias))
    Notificacion.objects.filter(expediente=exp, tipo="resultados").update(
        notificada_en=timezone.now() - timedelta(days=dias), enviada_en=timezone.now() - timedelta(days=dias + 1))


def _firmar_demo(u, exp, pdf=None):
    """Registra la firma con todos los puntos verificados (y la formalización propia si la hubiera)."""
    from nucleo.demo import archivo_demo

    elementos = {e["clave"]: {"archivo": archivo_demo(f"{e['clave']}.pdf"), "dato": "RFN-DEMO" if e.get("dato") else ""}
                 for e in firma.formalizacion_propia(exp)["elementos"]}
    return firma.registrar_firma(
        _delegacion(u, exp), exp, None, "persona", exp.solicitante.nombre, archivo_demo(f"contrato_firmado_{exp.folio}.pdf"),
        [p["clave"] for p in firma.puntos_de_verificacion(exp)], elementos, "Firmó en la Delegación (demostración).")


def _firmas(u):
    """HU-3.3: segundo lote de PS y RHF con contratos firmados y uno señalado sin firma (idempotente)."""
    hechas = 0
    drff, uj, st = u["dir_drff"], u["juridica"], u["comite"]
    for clave, solicitudes in LOTE_FIRMAS.items():
        ejercicio = Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()
        if ejercicio is None or Expediente.objects.filter(ejercicio=ejercicio, predio__nombre=solicitudes[0][2]).exists():
            continue
        exps = []
        for usuario, municipio, predio, persona, modalidad, ha, destino in solicitudes:
            exp = _validada(u[usuario], drff, ejercicio, municipio, predio, persona, modalidad, ha)
            tecnico.dictaminar(drff, exp, "factible", "Cumple los criterios técnicos de elegibilidad de las reglas.")
            juridico.dictaminar(uj, exp, "procedente", "Documentación legal completa y vigente.")
            exps.append((exp, destino))
        fecha = timezone.localtime(timezone.now()) - timedelta(hours=1)
        sesion = sesiones.crear_sesion(
            st, ejercicio, TipoSesion.APROBACION, fecha, "Sala de juntas de PROBOSQUE, Metepec",
            "\n".join(["Lista de asistencia y declaración de quórum", "Presentación del listado preliminar",
                       "Aprobación de los listados", "Autorización de la publicación de resultados"]))
        sesiones.agregar_documento(st, sesion, ContentFile(_pdf_demo(f"Listado preliminar {clave} (segundo lote)"),
                                                           name="listado_preliminar.pdf"), "Listado preliminar")
        sesiones.enviar_convocatoria(st, sesion, momento=fecha - timedelta(days=21))
        aprobacion.proponer_listados(st, sesion)
        aprobacion.registrar_acta(st, sesion, True, "Se aprueban los listados por unanimidad.", momento=fecha + timedelta(minutes=20))
        sesion.refresh_from_db()
        pub = publicacion.publicar(drff, sesion, momento=_despues(sesion.acta_fecha, 10))
        modelo = contratos.modelos_elegibles(exps[0][0])[0]
        for exp, destino in exps:
            publicacion.registrar_entrega(_delegacion(u, exp), exp.notificaciones.get(tipo="resultados"), "personal",
                                          fecha_hora=_despues(pub.publicada_en, 15), observaciones="Entregado (demostración).")
            exp.refresh_from_db()
            if destino == "sin_firma":
                continue
            contrato = contratos.elaborar_contrato(drff, exp, modelo)
            contratos.enviar_a_delegacion(drff, contrato)
            exp.refresh_from_db()
            _firmar_demo(u, exp)
            hechas += 1
        for exp, destino in exps:
            if destino == "sin_firma":
                _envejecer(exp, 40)
                firma.revisar_firmas(timezone.localdate())
                hechas += 1
    return hechas
