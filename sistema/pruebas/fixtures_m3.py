"""Fixtures del módulo M3 (HU-3.x): solicitudes aprobadas por una sesión del Comité, con acta."""
from datetime import timedelta

import pytest
from django.utils import timezone

from dictamen import aprobacion, juridico, sesiones, tecnico
from dictamen.demo import _validada, propiedad_en_regla
from dictamen.models import TipoSesion
from nucleo.models import Ejercicio

from .fixtures_m2 import documento_sesion

__all__ = ["PEG_SOLICITUD", "direccion_de", "elementos_propios", "aprobadas", "notificadas", "en_delegacion", "contratadas", "catalogo_planta", "mfs", "contrato_manual", "modelo_validado", "delegado_de",
           "SOLICITUDES_M3"]

# programa: (usuario Delegación, municipio, predio, persona, modalidad, hectáreas)
SOLICITUDES_M3 = {
    "CC": [("del_amecameca", "Amecameca", "Predio CC Uno", "Beatriz Lara Pineda", "reforestacion", 6),
           ("del_toluca", "Zinacantepec", "Predio CC Dos", "Ramiro Ortega Solís", "reforestacion", 6),
           ("del_valle", "Amanalco", "Predio CC Tres", "Silvia Nava Cruz", "reforestacion", 6)],
    "PS": [("del_amecameca", "Tlalmanalco", "Plantación Los Pinos", "Abel Contreras Vega", "plantacion_forestal_comercial", 4),
           ("del_toluca", "Zinacantepec", "Rancho La Huerta", "Leticia Mora Garduño", "mantenimiento_plantaciones", 2.5)],
    "RHF": [("del_amecameca", "Ozumba", "Barranca Honda", "Rafael Sánchez Ortega", "rfi_modalidad_dos", 3),
            ("del_valle", "Amanalco", "Ojo de Agua", "Guadalupe Reyes Albarrán", "bosques_de_agua", 2)],
    "PSA": [("del_toluca", "Ocoyoacac", "Bosque El Zarco", "Felipe Hernández Ramos", "cuenca_alta", 30),
            ("del_valle", "Villa Victoria", "Monte La Loma", "Josefina Colín Becerril", "cuenca_media_baja", 25)],
    # MFS: monto fijo por concepto; el primero es un Programa de Manejo maderable de 7 a 95 ha (régimen ETF, 70/30), el
    # segundo una certificación FSC de cadena de custodia (50/50). El polígono lo levanta el prestador con RFN (8.1.7 c).
    "MFS": [("del_amecameca", "Amecameca", "Bosque Los Volcanes", "Ejido San Pedro Nexapa", "etf_pmf_maderable_7_95", 40),
            ("del_toluca", "Zinacantepec", "Aserradero La Cumbre", "Maderas La Cumbre", "fsc_certificacion_cadena_custodia", 12)],
    # PEG: solicita el núcleo agrario; la persona beneficiaria es el Guardabosque (sin superficie ni polígono).
    "PEG": [("del_amecameca", "Amecameca", "Ejido San Juan", "Ejido San Juan", "apoyo_monetario_guardabosque", None),
            ("del_valle", "Amanalco", "Ejido San Bartolo", "Ejido San Bartolo", "apoyo_monetario_guardabosque", None)],
}
GUARDABOSQUES = [("Margarito Sánchez Ruiz", "SARM800101HMCNZR09"), ("Juana Colín Esquivel", "COEJ850315MMCLSN02")]
EXTRA_M3 = {
    "MFS": lambda i: {"levantado_por": "prestador"},
    "PEG": lambda i: {"tipo": "nucleo_agrario", "beneficiaria_nombre": GUARDABOSQUES[i][0],
                      "beneficiaria_curp": GUARDABOSQUES[i][1]},
}


def direccion_de(usuarios, ejercicio):
    """Usuario de la Dirección que es Instancia Ejecutora del programa (Protección Forestal en PEG)."""
    return usuarios["dir_dpf"] if ejercicio.programa.clave == "PEG" else usuarios["dir_drff"]


# Guardabosques: la registra el núcleo agrario, en la modalidad única del programa y sin superficie (reglas/PEG.json).
PEG_SOLICITUD = {"tipo": "nucleo_agrario", "modalidad": "apoyo_monetario_guardabosque", "ha": None,
                 "solicitante": "Ejido San Juan", "beneficiaria": "Margarito Sánchez Ruiz",
                 "beneficiaria_curp": "SARM800101HMCNZR09"}


@pytest.fixture
def aprobadas(catalogos, usuarios):
    """``aprobadas("PS")`` → (sesión, [expedientes]): solicitudes dictaminadas y aprobadas por una sesión de
    aprobación con acta (autoriza la publicación por omisión). Con ``presupuesto`` solo alcanza para el primero;
    el resto va a lista de espera. ``no_factible`` marca al último como no factible."""
    u = usuarios

    def _crear(programa="PS", autoriza=True, presupuesto=None, no_factible=False, cuantas=None):
        ejercicio = Ejercicio.objects.get(programa__clave=programa, anio=2026)
        datos = SOLICITUDES_M3[programa][:cuantas]
        direccion = direccion_de(u, ejercicio)
        exps = []
        for i, (deleg, municipio, predio, persona, modalidad, ha) in enumerate(datos):
            extra = EXTRA_M3.get(programa, lambda i: {})(i)
            exp = _validada(u[deleg], direccion, ejercicio, municipio, predio, persona, modalidad, ha, **extra)
            malo = no_factible and i == len(datos) - 1
            tecnico.dictaminar(direccion, exp, "no_factible" if malo else "factible", "Dictamen técnico de prueba.")
            juridico.dictaminar(u["juridica"], exp, "procedente", "Documentación completa.",
                                propiedad=propiedad_en_regla(exp))
            exps.append(exp)
        fecha = timezone.localtime(timezone.now()) - timedelta(hours=2)
        sesion = sesiones.crear_sesion(
            u["comite"], ejercicio, TipoSesion.APROBACION, fecha, "Sala de juntas",
            "Quórum\nListado preliminar\nAprobación de listados\nAutorización de publicación")
        sesiones.agregar_documento(u["comite"], sesion, documento_sesion("preliminar.pdf"), "Listado preliminar")
        sesiones.enviar_convocatoria(u["comite"], sesion, momento=fecha - timedelta(days=21))
        aprobacion.proponer_listados(u["comite"], sesion, presupuesto=presupuesto)
        aprobacion.registrar_acta(u["comite"], sesion, autoriza, "Acta de prueba.", momento=fecha + timedelta(minutes=30))
        sesion.refresh_from_db()
        for e in exps:
            e.refresh_from_db()
        return sesion, exps
    return _crear


def delegado_de(usuarios, expediente):
    """Usuario de la Delegación que atiende el expediente."""
    return next(u for u in usuarios.values() if u.unidad_id == expediente.delegacion_id and u.tipo_unidad == "delegacion")


@pytest.fixture
def notificadas(aprobadas, usuarios):
    """``notificadas("PS", cuantas=1)`` → (sesión, [expedientes]) publicados y con el resultado ya notificado."""
    from contrato import publicacion

    def _crear(programa="PS", cuantas=1, **kw):
        sesion, exps = aprobadas(programa, cuantas=cuantas, **kw)
        publicacion.publicar(direccion_de(usuarios, sesion.ejercicio), sesion)
        for e in exps:
            publicacion.registrar_entrega(delegado_de(usuarios, e), e.notificaciones.get(tipo="resultados"), "personal")
            e.refresh_from_db()
        return sesion, exps
    return _crear


@pytest.fixture
def modelo_validado(usuarios):
    """``modelo_validado(ejercicio)`` → modelo de Contrato de Adhesión (o el tipo pedido) validado por la Unidad Jurídica."""
    from contrato import contratos
    from contrato.models import TipoModelo

    def _crear(ejercicio, tipo=TipoModelo.CONTRATO_ADHESION, nombre="Modelo de prueba"):
        texto = contratos.PLANTILLAS_BASE[tipo].replace(contratos.MARCA_BORRADOR, "").strip()
        m = contratos.registrar_modelo(direccion_de(usuarios, ejercicio), ejercicio, tipo, nombre, texto)
        contratos.validar_version(usuarios["juridica"], m.vigente, "Conforme.")
        return m
    return _crear


@pytest.fixture
def en_delegacion(notificadas, modelo_validado, usuarios):
    """``en_delegacion("PS", cuantas=1)`` → (sesión, [expedientes]) con el contrato elaborado y enviado a la Delegación
    (estado ``contrato_en_delegacion``, listos para la firma de HU-3.3)."""
    from contrato import contratos

    def _crear(programa="PS", cuantas=1, **kw):
        sesion, exps = notificadas(programa, cuantas=cuantas, **kw)
        modelo = modelo_validado(exps[0].ejercicio)
        direccion = direccion_de(usuarios, exps[0].ejercicio)
        for e in exps:
            contratos.enviar_a_delegacion(direccion, contratos.elaborar_contrato(direccion, e, modelo))
            e.refresh_from_db()
        return sesion, exps
    return _crear


@pytest.fixture
def mfs(catalogos):
    """MFS 2026 con sus reglas reales (``reglas/MFS.json``; firma en 10 días hábiles desde la notificación)."""
    ej = Ejercicio.objects.get(programa__clave="MFS", anio=2026)
    assert ej.tiene_reglas and ej.plazo("firma_contrato").cantidad == 10
    return ej


@pytest.fixture
def contrato_manual(usuarios):
    """``contrato_manual(ejercicio, direccion="dir_drff", **kw)`` → expediente de un programa sin reglas completas
    (MFS, PEG) en ``contrato_en_delegacion``, con su contrato ya enviado. Se arma directo en la base (para PEG, con
    ``**PEG_SOLICITUD``)."""
    from django.core.files.base import ContentFile
    from django.utils import timezone

    from contrato.models import Contrato, EstadoContrato
    from nucleo.demo import _pdf_demo
    from nucleo.models import Estado
    from nucleo.plazos import registrar_hito

    from .fixtures_m2 import registrar_validada

    def _crear(ejercicio, direccion="dir_drff", nombre="Predio M3", **kw):
        exp = registrar_validada(usuarios, ejercicio, direccion=direccion, nombre=nombre, **kw)
        from contrato.models import EstadoVersion, ModeloContrato, TipoModelo, VersionModelo
        from nucleo.models import Expediente
        modelo, _ = ModeloContrato.objects.get_or_create(
            ejercicio=ejercicio, tipo=TipoModelo.CONTRATO_ADHESION, nombre="Modelo de prueba",
            defaults={"creado_por": usuarios[direccion]})
        VersionModelo.objects.get_or_create(modelo=modelo, numero=1, defaults={
            "texto": "Contrato de prueba", "estado": EstadoVersion.VALIDADA, "creada_por": usuarios[direccion],
            "revisada_por": usuarios["juridica"], "revisada_en": timezone.now()})
        Expediente.objects.filter(pk=exp.pk).update(estado=Estado.objects.get(clave="contrato_en_delegacion"))
        ahora = timezone.now()
        contrato = Contrato(expediente=exp, folio=f"CTO-{ejercicio.programa.clave}-2026-0001",
                            version_modelo=modelo.vigente, tipo=modelo.tipo, texto="Contrato de prueba",
                            elaborado_por=usuarios[direccion], enviado_por=usuarios[direccion],
                            enviado_en=ahora - timedelta(minutes=30), estado=EstadoContrato.ENVIADO)
        contrato.archivo.save("contrato.pdf", ContentFile(_pdf_demo("Contrato")), save=False)
        contrato.save()
        registrar_hito(exp, "publicacion_resultados", usuarios[direccion], ahora - timedelta(days=2))
        exp.refresh_from_db()
        return exp
    return _crear


@pytest.fixture
def contratadas(en_delegacion, usuarios):
    """``contratadas("PS", cuantas=1)`` → (sesión, [expedientes]) con el contrato firmado (estado ``contratada``)."""
    from contrato import firma
    from nucleo.demo import archivo_demo

    def _crear(programa="PS", cuantas=1, **kw):
        sesion, exps = en_delegacion(programa, cuantas=cuantas, **kw)
        for e in exps:
            firma.registrar_firma(delegado_de(usuarios, e), e, None, "persona", e.beneficiaria.nombre,
                                  archivo_demo("firmado.pdf"), [p["clave"] for p in firma.puntos_de_verificacion(e)],
                                  elementos_propios(e))
            e.refresh_from_db()
        return sesion, exps
    return _crear


def elementos_propios(expediente, dato="RFN-PRUEBA-01"):
    """Los elementos de formalización propia del programa (MFS: contrato de servicios técnicos y carta compromiso; PEG:
    credencial), con un archivo y su dato, para registrar la firma completa."""
    from contrato import firma
    from nucleo.demo import archivo_demo

    return {e["clave"]: {"archivo": archivo_demo(f"{e['clave']}.pdf"), "dato": dato if e.get("dato") else ""}
            for e in firma.formalizacion_propia(expediente)["elementos"]}


@pytest.fixture
def catalogo_planta(catalogos):
    """Especies y viveros de demostración; devuelve ``(vivero_con_usuario, {nombre: especie})``."""
    from contrato import planta
    from contrato.models import Especie, Vivero

    planta.cargar_catalogo()
    return Vivero.objects.get(clave="VIV-DEMO-01"), {e.nombre: e for e in Especie.objects.all()}
