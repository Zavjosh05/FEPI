"""Datos de demostración del módulo M6 (idempotente), con los servicios del sistema y en las fechas del calendario de 2026
(reloj simulado, ``nucleo/reloj.py``; fecha de corte 19-nov-2026).

**HU-6.1 · Lista de espera y sustituciones** (lote propio de RHF, ``LOTE``): cuatro solicitudes de Bosques de Agua de 2 ha
registradas en marzo; la sesión de aprobación del 8-sep tiene recurso para dos (Arroyo Seco y Loma del Aire, que firman el 17-sep)
y deja a Paraje El Rocío y Cerro La Mina en lista de espera (lugares 1 y 2).

- Loma del Aire: el 5-oct la Delegación de Amecameca recibe el aviso del fallecimiento de la persona titular (28-sep) y el 9-oct la
  solicitud de sustitución de la segunda persona beneficiaria, en plazo (30 días hábiles desde el fallecimiento).
- Arroyo Seco: el 6-oct la Delegación de Valle de Bravo recibe el desistimiento por escrito, con la firma verificada.
- El área responsable propone las dos al Comité (8 y 12-oct); en la sesión de seguimiento del 22-oct la Secretaría Técnica
  registra los acuerdos y el área los cumple el 23-oct: Loma del Aire sigue con la persona sustituta y Arroyo Seco se da de baja
  y libera su recurso.
- El 26-oct el área propone la reasignación del recurso liberado a la lista de espera: alcanza para el lugar 1. En la sesión del
  10-nov se acuerda, el área lo cumple el 11-nov (Paraje El Rocío pasa a «aprobada») y la Delegación le notifica el resultado el
  13-nov: firma en los 10 días hábiles siguientes. Cerro La Mina sigue en lista de espera.
- MFS: el 16-nov la Delegación de Toluca registra la solicitud de prórroga por causa externa de Aserradero La Cumbre (la entidad
  certificadora pospuso la auditoría), por resolver en el área responsable.

**HU-6.2 · Incumplimientos y reintegros** (``_incumplimientos``): Administración y Finanzas registra el 12-nov las cuentas para
reintegros de CC, PS, RHF y PSAHEM (en PSAHEM, la de la Fiduciaria: duda abierta R-14). En Loma del Aire el área responsable avisa
el 27-oct omisiones por subsanar con fecha límite del 6-nov (la Delegación lo notifica el 28-oct); vence sin subsanarse, el sistema lo
señala el 9-nov y el área confirma el 10-nov la propuesta de cancelación; el Comité la acuerda el 10-nov y la Unidad Jurídica la
cumple el 11-nov (cancelada, inscrita en el Listado de Personas Beneficiarias Incumplidas, requerimiento preparado). El 13-nov la
Unidad Jurídica emite el requerimiento por el valor de la planta no establecida (500 plantas por $7.00 = $3,500, precio de
demostración) a la cuenta de RHF; la Delegación lo notifica el 16-nov y Administración y Finanzas comprueba el depósito el 18-nov
(reintegrada). En la fecha de corte la revisión de plazos señala lo demás (faltantes vencidos de la recepción; los reportes no
entregados de los Guardabosques ya los señaló la evaluación de HU-4.3) para que una persona lo confirme.

**HU-6.3 · Cierre del ejercicio** (``_cierre``): el 19-nov (fecha de corte) el área responsable de RHF cierra el expediente de Loma del
Aire (reintegro depositado), publica el padrón de RHF y envía el informe anual al Comité (la Secretaría Técnica aún no registra su
recepción); la Dirección de Protección Forestal publica el padrón del PEG con sus altas, bajas y sustituciones.
"""
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction

from contrato import contratos, publicacion
from contrato.demo import _delegacion, _firmar_demo, _modelo_validado, dictaminar_lote
from dictamen import seguimiento as dictamen_seguimiento
from dictamen import sesiones
from dictamen.demo import paso, sesion_aprobacion
from dictamen.models import TipoSesion
from nucleo import montos
from nucleo.demo import _pdf_demo, archivo_demo
from nucleo.demo_calendario import cuando, habil, habil_antes
from nucleo.models import Ejercicio, Expediente, Usuario

from . import cierre, incumplimientos, reasignacion

# (usuario de la Delegación, municipio, predio, persona, modalidad, hectáreas)
LOTE = [("del_valle", "Amanalco", "Arroyo Seco", "Inés Bernal Castro", "bosques_de_agua", 2),
        ("del_amecameca", "Tlalmanalco", "Loma del Aire", "Fermín Robles Gil", "bosques_de_agua", 2),
        ("del_toluca", "Zinacantepec", "Paraje El Rocío", "Celia Durán Mejía", "bosques_de_agua", 2),
        ("del_valle", "Villa Victoria", "Cerro La Mina", "Óscar Peralta Nieto", "bosques_de_agua", 2)]
NOMBRES_LOTE = [f[2] for f in LOTE]
CALENDARIO = dict(registro="2026-03-18", tecnico="2026-04-23", juridico="2026-04-29", sesion="2026-09-08",
                  publicacion="2026-09-10", notificacion="2026-09-11", contrato="2026-09-14", firma="2026-09-17",
                  fallecimiento="2026-09-28", aviso="2026-10-05", desistimiento="2026-10-06", propuesta_baja="2026-10-08",
                  sustitucion="2026-10-09", propuesta_sustitucion="2026-10-12", sesion_1="2026-10-22", cumplir_1="2026-10-23",
                  propuesta_reasignacion="2026-10-26", sesion_2="2026-11-10", cumplir_2="2026-11-11",
                  notificacion_reasignada="2026-11-13", prorroga="2026-11-16", omision="2026-10-27",
                  notificacion_omision="2026-10-28", vence_omision="2026-11-06", revision="2026-11-09",
                  propuesta_cancelacion="2026-11-10", cumplir_cancelacion="2026-11-11", cuentas="2026-11-12",
                  requerimiento="2026-11-13", notificacion_requerimiento="2026-11-16", deposito="2026-11-18")
CUENTAS = {"CC": "PROBOSQUE", "PS": "PROBOSQUE", "RHF": "PROBOSQUE", "PSA": "Fiduciaria del FIPASAHEM"}


def _ejercicio(clave):
    return Ejercicio.objects.filter(programa__clave=clave, reglas_cargadas__isnull=False).order_by("-anio").first()


def _sesion_seguimiento(st, ejercicio, fecha, tema):
    fecha = habil(fecha)
    with paso(habil_antes(fecha, 7), 12):
        s = sesiones.crear_sesion(st, ejercicio, TipoSesion.SEGUIMIENTO, cuando(fecha, 11), "Sala de juntas de PROBOSQUE, Metepec",
                                  f"Lista de asistencia y declaración de quórum\n{tema}\nAsuntos generales")
        sesiones.agregar_documento(st, s, ContentFile(_pdf_demo(tema), name="propuestas.pdf"), tema)
    with paso(habil_antes(fecha, 5), 10):
        sesiones.enviar_convocatoria(st, s)
    return s


def _lote_reasignacion(u, ejercicio):
    c = CALENDARIO
    drff, st = u["dir_drff"], u["comite"]
    filas = [(*f, habil(c["registro"], i)) for i, f in enumerate(LOTE)]
    exps = [exp for exp, _ in dictaminar_lote(u, ejercicio, filas, c["tecnico"], c["juridico"])]
    # Recurso para las dos primeras (en el orden de registro); las otras dos quedan en lista de espera.
    presupuesto = sum((montos.monto_aprobado(e, montos.superficie_aprobada(e)).total for e in exps[:2]), Decimal("0"))
    sesion = sesion_aprobacion(st, ejercicio, c["sesion"], ["Listado preliminar RHF (lista de espera)"], presupuesto=presupuesto)
    with paso(c["publicacion"], 10):
        publicacion.publicar(drff, sesion)
    modelo = _modelo_validado(u, ejercicio, f"Contrato de Adhesión RHF {ejercicio.anio} (modelo de demostración)")
    for exp in exps[:2]:
        exp.refresh_from_db()
        with paso(c["notificacion"], 11):
            publicacion.registrar_entrega(_delegacion(u, exp), exp.notificaciones.get(tipo="resultados"), "personal",
                                          observaciones="Entregado (demostración).")
        exp.refresh_from_db()
        with paso(c["contrato"], 10):
            contrato = contratos.elaborar_contrato(drff, exp, modelo)
        with paso(c["contrato"], 15):
            contratos.enviar_a_delegacion(drff, contrato)
        exp.refresh_from_db()
        with paso(c["firma"], 12):
            _firmar_demo(u, exp)
    arroyo, loma = exps[0], exps[1]
    # Sustitución por fallecimiento (Loma del Aire) y desistimiento (Arroyo Seco), cada una con su acuse.
    with paso(c["aviso"], 10):
        reasignacion.registrar_solicitud(_delegacion(u, loma), loma, "fallecimiento", archivo_demo("acta_defuncion.pdf",
                                         "Acta de defuncion"), "Rosa Robles Díaz (hija)", fecha_hecho=habil(c["fallecimiento"]))
    with paso(c["desistimiento"], 12):
        reasignacion.registrar_solicitud(_delegacion(u, arroyo), arroyo, "desistimiento", archivo_demo("desistimiento.pdf",
                                         "Escrito de desistimiento"), motivo="No podrá atender las actividades del programa este "
                                         "año por cambio de residencia.", firmas=reasignacion.puntos_firma(arroyo))
    with paso(c["propuesta_baja"], 10):
        baja = reasignacion.proponer(drff, arroyo, "desistimiento")
    with paso(c["sustitucion"], 11):
        reasignacion.registrar_solicitud(_delegacion(u, loma), loma, "sustitucion", archivo_demo("interes_segunda.pdf",
                                         "Escrito de la segunda persona beneficiaria"), causa="fallecimiento",
                                         segunda={"nombre": "Rosa Robles Díaz", "curp": "RODR900212MMCBZS01",
                                                  "telefono": "722 555 0142", "parentesco": "Hija"})
    with paso(c["propuesta_sustitucion"], 10):
        sustituir = reasignacion.proponer(drff, loma, "sustitucion")
    s1 = _sesion_seguimiento(st, ejercicio, c["sesion_1"], "Sustituciones y desistimientos")
    with paso(c["sesion_1"], 12):
        a_baja = reasignacion.llevar_a_sesion(st, baja, s1)
        a_sus = reasignacion.llevar_a_sesion(st, sustituir, s1)
    with paso(c["cumplir_1"], 10):
        dictamen_seguimiento.cumplir(drff, a_baja, "Baja registrada; recurso liberado para la lista de espera.")
        dictamen_seguimiento.cumplir(drff, a_sus, "Persona sustituta registrada en el expediente.")
    # Reasignación del recurso liberado a la lista de espera, en su orden.
    with paso(c["propuesta_reasignacion"], 10):
        prop = reasignacion.proponer_reasignacion(drff, ejercicio, "Recurso liberado por el desistimiento de Arroyo Seco.")
    s2 = _sesion_seguimiento(st, ejercicio, c["sesion_2"], "Reasignación del recurso liberado a la lista de espera")
    with paso(c["sesion_2"], 12):
        a_reas = reasignacion.llevar_a_sesion(st, prop, s2)
    with paso(c["cumplir_2"], 10):
        dictamen_seguimiento.cumplir(drff, a_reas, "Se envía el resultado a la Delegación para notificar.")
    rocio = Expediente.objects.get(pk=exps[2].pk)
    with paso(c["notificacion_reasignada"], 11):
        publicacion.registrar_entrega(_delegacion(u, rocio), rocio.notificaciones.filter(tipo="resultados")
                                      .order_by("-enviada_en").first(), "personal", observaciones="Entregado (demostración).")
    return len(exps)


def _prorroga_mfs(u):
    mfs = _ejercicio("MFS")
    exp = Expediente.objects.filter(ejercicio=mfs, predio__nombre="Aserradero La Cumbre", estado__clave="pagada").first() \
        if mfs else None
    if exp is None or exp.prorrogas.exists():
        return 0
    with paso(CALENDARIO["prorroga"], 10):
        reasignacion.solicitar_prorroga(
            _delegacion(u, exp), exp, "La entidad certificadora pospuso la auditoría de cadena de custodia por causas ajenas a la "
            "persona beneficiaria.", habil("2027-02-26"), archivo_demo("prorroga.pdf", "Escrito de solicitud de prorroga"),
            habil("2026-12-15"))
    return 0


def _incumplimientos(u):
    from dictamen.models import SesionComite
    from nucleo.demo_calendario import fecha_corte
    from nucleo.models import Programa

    c = CALENDARIO
    with paso(c["cuentas"], 9):
        for clave, titular in CUENTAS.items():
            p = Programa.objects.filter(clave=clave).first()
            if p is not None and incumplimientos.cuenta_vigente(p) is None:
                incumplimientos.registrar_cuenta(u["finanzas"], p, titular, "Banco de demostración", f"CUENTA-DEMO-{clave}",
                                                 f"REINTEGRO-{clave}-2026", "Cuenta de demostración.")
    loma = Expediente.objects.filter(predio__nombre="Loma del Aire", estado__clave="contratada").first()
    if loma is not None and not loma.avisos_omision.exists():
        drff = u["dir_drff"]
        with paso(c["omision"], 12):
            aviso = incumplimientos.avisar_omision(drff, loma, "Entregar el programa de trabajo actualizado con la persona "
                                                   "sustituta y la evidencia del inicio de los trabajos de conservación.",
                                                   habil(c["vence_omision"]))
        with paso(c["notificacion_omision"], 11):
            publicacion.registrar_entrega(_delegacion(u, loma), aviso.notificacion, "personal", observaciones="Entregado (demostración).")
        with paso(c["revision"], 7):
            incumplimientos.revisar(habil(c["revision"]))
        with paso(c["propuesta_cancelacion"], 10):
            s = loma.senalamientos.get(tipo="omision_vencida")
            incumplimientos.confirmar(drff, s)
        s.refresh_from_db()
        sesion = SesionComite.objects.filter(ejercicio=loma.ejercicio, tipo="seguimiento",
                                             fecha_hora__date=habil(c["sesion_2"])).first()
        with paso(c["sesion_2"], 12, 30):
            acuerdo = reasignacion.llevar_a_sesion(u["comite"], s.propuesta, sesion)
        with paso(c["cumplir_cancelacion"], 10):
            dictamen_seguimiento.cumplir(u["juridica"], acuerdo, "Cancelación registrada e inscripción en el Listado.")
        req = loma.requerimientos.get()
        with paso(c["requerimiento"], 11):
            incumplimientos.emitir_requerimiento(u["juridica"], req, 500, "7.00",
                                                 "Precio de demostración (listado oficial de la Secretaría de Finanzas por confirmar)")
        req.refresh_from_db()
        with paso(c["notificacion_requerimiento"], 11):
            publicacion.registrar_entrega(_delegacion(u, loma), req.notificacion, "personal", observaciones="Entregado (demostración).")
        with paso(c["deposito"], 10):
            incumplimientos.comprobar_deposito(u["finanzas"], req, habil(c["deposito"]), req.monto_total, "DEP-DEMO-0001",
                                               archivo_demo("deposito.pdf", "Comprobante de deposito"))
    with paso(fecha_corte(), 8):
        incumplimientos.revisar(fecha_corte())


def _cierre(u):
    """HU-6.3: el día de corte el área responsable de RHF cierra Loma del Aire (reintegro depositado), publica el padrón de RHF
    (con la baja de Arroyo Seco y la cancelación de Loma del Aire) y envía el informe anual al Comité, que la Secretaría Técnica aún no
    recibe; la Dirección de Protección Forestal publica el padrón del PEG (con sus altas, bajas y sustituciones)."""
    from nucleo.demo_calendario import fecha_corte

    corte = fecha_corte()
    rhf = _ejercicio("RHF")
    if rhf is not None:
        loma = Expediente.objects.filter(ejercicio=rhf, predio__nombre="Loma del Aire", estado__clave="reintegrada").first()
        if loma is not None:
            with paso(corte, 10):
                cierre.cerrar_expediente(u["dir_drff"], loma)
        if cierre.padron_publicado(rhf) is None and cierre.expedientes_de(rhf).exists():
            with paso(corte, 10, 30):
                cierre.publicar_padron(u["dir_drff"], rhf)
        if cierre.informe_de(rhf) is None and cierre.expedientes_de(rhf).exists():
            with paso(corte, 11):
                cierre.enviar_informe(u["dir_drff"], rhf)
    peg = _ejercicio("PEG")
    if peg is not None and cierre.padron_publicado(peg) is None and cierre.expedientes_de(peg).exists():
        with paso(corte, 11, 30):
            cierre.publicar_padron(u["dir_dpf"], peg)


@transaction.atomic
def cargar_demo():
    u = {x.username: x for x in Usuario.objects.all()}
    hechas = 0
    rhf = _ejercicio("RHF")
    if rhf is not None and not Expediente.objects.filter(ejercicio=rhf, predio__nombre=LOTE[0][2]).exists():
        hechas += _lote_reasignacion(u, rhf)
    _prorroga_mfs(u)
    _incumplimientos(u)
    _cierre(u)
    return hechas
