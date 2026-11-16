"""Datos de demostración para las historias de M3 y M5 (idempotente): dos solicitudes aprobadas de PS, de RHF y
de PSAHEM, cada programa con su sesión de aprobación y su acta. Todo con los servicios de M1, M2 y M3, igual
que la interfaz. Las de CC aprobadas las deja ``dictamen/demo.py``.

**Calendario.** La carga corre con el reloj simulado (``nucleo/reloj.py``) y cada paso ocurre en su fecha del calendario de 2026
(``nucleo/demo_calendario.py``): registro en febrero (recepción del 28-ene al 27-mar), dictámenes en abril y mayo (PS y RHF
hasta el 30-abr; PSAHEM hasta el 30-jun), y la sesión del Comité de PSAHEM el 15-jul (aprobación del 1 al 31-jul). PS y RHF no
tienen fecha límite de aprobación («hasta agotar el recurso»): su primer lote se aprueba en noviembre, para que sus plazos de
firma sigan corriendo en la fecha de corte, y el segundo en septiembre. La fecha de corte (19-nov-2026 por omisión) es el «hoy» de
la demostración: lo vencido se vence por el calendario y lo vigente se arma hacia atrás desde ella.

HU-3.1: PS y RHF ya publicaron sus resultados (a distintas horas); en PS la Delegación notificó el resultado
y la cita de la primera solicitud, y en RHF solo el resultado; lo demás queda por notificar. PSAHEM y CC
quedan con el acta que autoriza publicar, para mostrar la pantalla de publicación.

HU-3.2: PS y RHF tienen un modelo de Contrato de Adhesión validado por la Unidad Jurídica; CC, PS y PSAHEM tienen
además la plantilla base («BORRADOR – modelo por validar») por validar. El contrato de Plantación Los Pinos (PS)
está elaborado y enviado a la Delegación; el de Barranca Honda (RHF), elaborado y por enviar; Ojo de Agua (RHF)
está notificada y por elaborar.

HU-3.3: un segundo lote por programa (PS y RHF, con su propia sesión de aprobación y publicación en septiembre) con contratos
firmados en plazo (la firma, con su verificación, deja el expediente en «contratada») y uno sin firma que venció el plazo
(10 días hábiles), señalado por ``revisar_plazos`` en la fecha de corte y por liberar. Los de HU-3.2 siguen en su plazo
(Plantación Los Pinos queda por firmar en la Delegación, a un día hábil de vencer).

HU-3.4: catálogos de especies y viveros y, sobre los contratos firmados del segundo lote, Vales de Planta: en PS uno
vigente con salidas parciales (Mirador de los Pinos, entregado el 9-nov) y uno vencido, no válido y sin reposición en PS (Ladera
Verde, entregado el 6-oct); en RHF uno vigente con una salida parcial (Arroyo Claro) y uno vencido con salida parcial que ya tiene su
vale de reposición por lo no entregado (Cerro Gordo). Peña Blanca (RFI Modalidad uno) no recibe planta."""
from django.db import transaction

from contrato import contratos, firma, planta, publicacion
from contrato.models import Contrato, Especie, ModeloContrato, TipoModelo, ValePlanta, Vivero
from dictamen import juridico, tecnico
from dictamen.demo import _validada, paso, sesion_aprobacion
from dictamen.models import SesionComite, TipoSesion
from nucleo.demo_calendario import cuando, fecha_corte, habil
from nucleo.models import Ejercicio, Expediente, Usuario

# programa: [(usuario de la Delegación, municipio, predio, persona, modalidad, hectáreas, fecha de registro)]
SOLICITUDES = {
    "PS": [("del_amecameca", "Tlalmanalco", "Plantación Los Pinos", "Abel Contreras Vega", "plantacion_forestal_comercial", 4, "2026-02-17"),
           ("del_toluca", "Zinacantepec", "Rancho La Huerta", "Leticia Mora Garduño", "mantenimiento_plantaciones", 2.5, "2026-02-18")],
    "RHF": [("del_amecameca", "Ozumba", "Barranca Honda", "Rafael Sánchez Ortega", "rfi_modalidad_dos", 3, "2026-02-19"),
            ("del_valle", "Amanalco", "Ojo de Agua", "Guadalupe Reyes Albarrán", "bosques_de_agua", 2, "2026-02-20")],
    "PSA": [("del_toluca", "Ocoyoacac", "Bosque El Zarco", "Felipe Hernández Ramos", "cuenca_alta", 30, "2026-02-23"),
            ("del_valle", "Villa Victoria", "Monte La Loma", "Josefina Colín Becerril", "cuenca_media_baja", 25, "2026-02-24")],
}
# programa: (fecha de la sesión de aprobación, primer día de dictamen técnico, primer día de dictamen jurídico)
PRIMER_LOTE = {"PS": ("2026-11-03", "2026-04-08", "2026-04-14"), "RHF": ("2026-11-04", "2026-04-09", "2026-04-15"),
               "PSA": ("2026-07-15", "2026-05-12", "2026-05-19")}


def dictaminar_lote(u, ejercicio, filas, tecnico_desde, juridico_desde):
    """Registra, valida y dictamina (técnico y jurídico) las solicitudes de ``filas`` en sus fechas; devuelve ``[(exp, fila)]``."""
    drff, uj = u["dir_drff"], u["juridica"]
    exps = []
    for i, fila in enumerate(filas):
        usuario, municipio, predio, persona, modalidad, ha = fila[:6]
        exp = _validada(u[usuario], drff, ejercicio, municipio, predio, persona, modalidad, ha,
                        registro=fila[6])
        with paso(habil(tecnico_desde, i), 10):
            tecnico.dictaminar(drff, exp, "factible", "Cumple los criterios técnicos de elegibilidad de las reglas.")
        with paso(habil(juridico_desde, i), 10):
            juridico.dictaminar(uj, exp, "procedente", "Documentación legal completa y vigente.")
        exps.append((exp, fila))
    return exps


@transaction.atomic
def cargar_demo():
    u = {x.username: x for x in Usuario.objects.all()}
    st = u["comite"]
    creadas = 0
    for clave, solicitudes in SOLICITUDES.items():
        ejercicio = Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()
        if ejercicio is None or SesionComite.objects.filter(ejercicio=ejercicio).exists():
            continue
        fecha_sesion, tecnico_desde, juridico_desde = PRIMER_LOTE[clave]
        creadas += len(dictaminar_lote(u, ejercicio, solicitudes, tecnico_desde, juridico_desde))
        sesion_aprobacion(st, ejercicio, fecha_sesion, ["Listado preliminar"])
    creadas += _publicaciones(u)
    creadas += _contratos(u)
    creadas += _firmas(u)
    creadas += _vales(u)
    return creadas


# programa: (publicación, [(fecha de la entrega, medio) de cada aviso de la primera solicitud])
PUBLICAR = {"PS": ("2026-11-05", [("2026-11-06", "personal"), ("2026-11-09", "telefono")]),
            "RHF": ("2026-11-06", [("2026-11-09", "personal")])}


def _publicaciones(u):
    """HU-3.1: publica PS y RHF con la demostración de avisos a distintas horas (idempotente)."""
    hechas = 0
    drff = u["dir_drff"]
    for clave, (fecha, entregas) in PUBLICAR.items():
        sesion = (SesionComite.objects.filter(ejercicio__programa__clave=clave, tipo=TipoSesion.APROBACION,
                                              estado="celebrada", autoriza_publicacion=True, publicacion__isnull=True)
                  .order_by("-fecha_hora").first())
        if sesion is None:
            continue
        with paso(fecha, 10, 30):
            pub = publicacion.publicar(drff, sesion)
        primera = pub.renglones.order_by("folio").first().expediente
        for (dia, medio), tipo in zip(entregas, ("resultados", "cita_firma")):
            n = primera.notificaciones.get(tipo=tipo)
            with paso(dia, 11):
                publicacion.registrar_entrega(_delegacion(u, primera), n, medio, observaciones="Entregado (demostración).")
        hechas += 1
    return hechas


def _delegacion(u, expediente):
    return next(x for x in u.values() if x.unidad_id == expediente.delegacion_id)


def _modelo_validado(u, ejercicio, nombre):
    """Modelo de Contrato de Adhesión de demostración, registrado por el área responsable y validado por la UJ (en octubre,
    antes de los primeros contratos; si ya hay contratos anteriores, el que se da por registrado)."""
    existente = ModeloContrato.objects.filter(ejercicio=ejercicio, nombre=nombre).first()
    if existente:
        return existente
    texto = contratos.PLANTILLAS_BASE[TipoModelo.CONTRATO_ADHESION].replace(contratos.MARCA_BORRADOR, "").strip()
    with paso("2026-06-01", 10):
        m = contratos.registrar_modelo(u["dir_drff"], ejercicio, TipoModelo.CONTRATO_ADHESION, nombre, texto)
    with paso("2026-06-02", 11):
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
            with paso("2026-06-03", 10):
                contratos.crear_plantilla_base(drff, ejercicio)
            hechos += 1
    for clave, predio, enviar, elaborado, enviado in (("PS", "Plantación Los Pinos", True, "2026-11-10", "2026-11-11"),
                                                      ("RHF", "Barranca Honda", False, "2026-11-12", None)):
        exp = Expediente.objects.filter(ejercicio__programa__clave=clave, predio__nombre=predio).first()
        if exp is None or Contrato.objects.filter(expediente=exp).exists() or exp.estado.clave != "notificada":
            continue
        modelo = contratos.modelos_elegibles(exp)[0]
        with paso(elaborado, 10):
            contrato = contratos.elaborar_contrato(drff, exp, modelo)
        if enviar:
            with paso(enviado, 11):
                contratos.enviar_a_delegacion(drff, contrato)
        hechos += 1
    # Ojo de Agua (RHF): la Delegación ya notificó el resultado y falta elaborar su contrato.
    ojo = Expediente.objects.filter(ejercicio__programa__clave="RHF", predio__nombre="Ojo de Agua",
                                    estado__clave="publicada").first()
    if ojo is not None:
        n = ojo.notificaciones.get(tipo="resultados")
        with paso("2026-11-10", 12):
            publicacion.registrar_entrega(_delegacion(u, ojo), n, "correo",
                                          observaciones="Notificado por correo electrónico (demostración).")
        hechos += 1
    return hechos


# ----------------------------------------------------------------------------- HU-3.3
# programa: [(usuario de la Delegación, municipio, predio, persona, modalidad, hectáreas, registro, destino)]; destino:
# «firmado» (contrato firmado en plazo), «sin_firma» (vence sin firma y queda señalado) o «sin_planta» (firmado).
LOTE_FIRMAS = {
    "PS": [("del_amecameca", "Amecameca", "Mirador de los Pinos", "Hilda Maldonado Cruz", "plantacion_forestal_comercial", 5, "2026-02-25", "firmado"),
           ("del_toluca", "Zinacantepec", "Ladera Verde", "Octavio Rangel Mena", "plantacion_forestal_comercial", 3, "2026-02-26", "firmado"),
           ("del_valle", "Amanalco", "Cañada Seca", "Mireya Solís Ibarra", "mantenimiento_plantaciones", 2, "2026-02-27", "sin_firma")],
    "RHF": [("del_amecameca", "Ozumba", "Arroyo Claro", "Esteban Quiroz Lara", "bosques_de_agua", 4, "2026-02-25", "firmado"),
            ("del_valle", "Amanalco", "Cerro Gordo", "Carmen Téllez Roa", "rfi_modalidad_dos", 3, "2026-02-26", "firmado"),
            ("del_toluca", "Zinacantepec", "Peña Blanca", "Ignacio Lugo Ferrer", "rfi_modalidad_uno", 2, "2026-02-27", "sin_planta")],
}
# programa: (sesión de aprobación, publicación, notificación del resultado, elaboración del primer contrato, firma del primero)
CALENDARIO_FIRMAS = {"PS": ("2026-09-22", "2026-09-24", "2026-09-25", "2026-09-28", "2026-10-02"),
                     "RHF": ("2026-09-23", "2026-09-25", "2026-09-28", "2026-10-01", "2026-10-06")}


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
    drff, st = u["dir_drff"], u["comite"]
    for clave, solicitudes in LOTE_FIRMAS.items():
        ejercicio = Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()
        if ejercicio is None or Expediente.objects.filter(ejercicio=ejercicio, predio__nombre=solicitudes[0][2]).exists():
            continue
        fecha_sesion, fecha_pub, fecha_notif, fecha_contrato, fecha_firma = CALENDARIO_FIRMAS[clave]
        exps = dictaminar_lote(u, ejercicio, [f[:7] for f in solicitudes], "2026-04-21", "2026-04-27")
        destinos = [f[7] for f in solicitudes]
        sesion = sesion_aprobacion(st, ejercicio, fecha_sesion, ["Listado preliminar (segundo lote)"])
        with paso(fecha_pub, 10):
            publicacion.publicar(drff, sesion)
        modelo = contratos.modelos_elegibles(exps[0][0])[0]
        for i, ((exp, _), destino) in enumerate(zip(exps, destinos)):
            with paso(fecha_notif, 11):
                publicacion.registrar_entrega(_delegacion(u, exp), exp.notificaciones.get(tipo="resultados"), "personal",
                                              observaciones="Entregado (demostración).")
            exp.refresh_from_db()
            if destino == "sin_firma":
                continue
            with paso(habil(fecha_contrato, i), 10):
                contrato = contratos.elaborar_contrato(drff, exp, modelo)
            with paso(habil(fecha_contrato, i + 1), 10):
                contratos.enviar_a_delegacion(drff, contrato)
            exp.refresh_from_db()
            with paso(habil(fecha_firma, i), 12):
                _firmar_demo(u, exp)
            hechas += 1
        hechas += destinos.count("sin_firma")
    # El contrato sin firma venció su plazo (10 días hábiles): la revisión de plazos de la fecha de corte lo señala.
    with paso(fecha_corte(), 9):
        firma.revisar_firmas(fecha_corte())
    return hechas


# ----------------------------------------------------------------------------- HU-3.4
# predio: (fecha de entrega del vale, [(especie, cantidad, fecha de la salida)])
def _vales(u):
    """HU-3.4: catálogos y vales (vigentes, vencido, con salidas parciales y una reposición); idempotente."""
    with paso("2026-09-01", 10):
        planta.cargar_catalogo()
    if ValePlanta.objects.exists():
        return 0
    vivero = Vivero.objects.filter(unidad__isnull=False).first()
    if vivero is None:
        return 0
    esp = {e.nombre: e for e in Especie.objects.all()}
    usuario_vivero = u["vivero"]

    def exp_de(predio):
        return Expediente.objects.filter(predio__nombre=predio, estado__clave="contratada").first()

    def vale(predio, fecha, renglones, **kw):
        exp = exp_de(predio)
        if exp is None:
            return None
        with paso(fecha, 10):
            return planta.emitir_vale(_delegacion(u, exp), exp, vivero, [(esp[n], c) for n, c in renglones],
                                      motivo_ajuste="Ajuste de demostración a la disponibilidad del vivero.", **kw)

    def salida(v, especie, cantidad, fecha, **kw):
        with paso(fecha, 12):
            planta.registrar_salida(usuario_vivero, v, esp[especie], cantidad, **kw)

    hechos = 0
    v = vale("Mirador de los Pinos", "2026-11-09", [("Pino patula", 3000), ("Oyamel", 2500)])          # vigente hasta el 9-dic
    if v:
        salida(v, "Pino patula", 1200, "2026-11-12", observaciones="Primera entrega (demostración).")
        salida(v, "Oyamel", 500, "2026-11-12")
        hechos += 1
    v = vale("Ladera Verde", "2026-10-06", [("Pino moctezuma", 3300)])                                  # venció el 5-nov
    if v:
        hechos += 1
    v = vale("Arroyo Claro", "2026-11-10", [("Oyamel", 1400), ("Encino", 1000)])                        # 15 días hábiles: al 1-dic
    if v:
        salida(v, "Oyamel", 700, "2026-11-13")
        hechos += 1
    v = vale("Cerro Gordo", "2026-10-12", [("Pino moctezuma", 1800)])                                   # venció el 3-nov
    if v:
        salida(v, "Pino moctezuma", 600, "2026-10-14")
        exp = v.expediente
        with paso("2026-11-17", 10):
            planta.emitir_vale(_delegacion(u, exp), exp, vivero, [(esp["Pino moctezuma"], 1200)], planta_disponible=True)
        hechos += 1
    return hechos
