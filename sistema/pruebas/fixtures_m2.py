"""Fixtures del módulo M2 (se importan en cada archivo de pruebas de HU-2.x)."""
from datetime import datetime, time, timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from nucleo import dias_habiles
from nucleo.demo import _pdf_demo, completar_requisitos, cuadro_en_municipio
from nucleo.models import Ejercicio, Ministracion, Municipio, Plazo, Requisito, TipoPersona, TipoPersonaGeneral
from dictamen.demo import propiedad_en_regla
from recepcion import servicios as recepcion

__all__ = ["validada", "dictaminada", "peg", "psa", "registrar_validada", "registrar_peg", "fecha_sesion", "despues_de",
           "documento_sesion", "propiedad_en_regla"]


def registrar_validada(usuarios, ejercicio, municipio="Amecameca", nombre="Predio M2", ha=6, desplazamiento=(0, 0),
                       usuario="del_amecameca", direccion="dir_drff", tipo="fisica", modalidad="reforestacion",
                       refrendo=False, curp="", solicitante="Persona Solicitante M2", solicitante_tipo=None,
                       beneficiaria="", beneficiaria_curp=""):
    """Solicitud registrada, completa, con polígono, enviada y validada (con los servicios del sistema)."""
    deleg = usuarios[usuario]
    datos = recepcion.DatosSolicitud(
        ejercicio=ejercicio, municipio=Municipio.objects.get(nombre=municipio), nombre_predio=nombre,
        tipo_persona=ejercicio.tipos_persona.get(clave=tipo),
        modalidad=ejercicio.modalidades.filter(clave=modalidad).first() if modalidad else None,
        solicitante_nombre=solicitante, solicitante_tipo=solicitante_tipo or (tipo if tipo in TipoPersonaGeneral.values else "fisica"), es_refrendo=refrendo, curp=curp,
        superficie_solicitada_ha=Decimal(ha) if ha is not None else None,
        beneficiaria_nombre=beneficiaria, beneficiaria_curp=beneficiaria_curp,
    )
    exp = recepcion.registrar_solicitud(deleg, datos)
    completar_requisitos(deleg, exp, fecha_archivo=timezone.localdate() - timedelta(days=300) if refrendo else None)
    if exp.programa.usa_poligono:
        recepcion.registrar_poligono(deleg, exp, cuadro_en_municipio(exp.predio.municipio, ha, desplazamiento), "dibujo",
                                     "delegacion", "Brigada", timezone.localdate())
    recepcion.enviar_a_direccion(deleg, exp)
    recepcion.validar_expediente(usuarios[direccion], exp)
    exp.refresh_from_db()
    return exp


@pytest.fixture
def validada(cc, usuarios):
    def _crear(**kw):
        return registrar_validada(usuarios, kw.pop("ejercicio", cc), **kw)
    return _crear


@pytest.fixture
def dictaminada(validada, usuarios):
    """Expediente con dictamen técnico y jurídico (por omisión, factible y procedente)."""
    from dictamen import juridico, tecnico

    def _crear(tecnico_resultado="factible", juridico_resultado="procedente", **kw):
        exp = validada(**kw)
        tecnico.dictaminar(usuarios["dir_drff"], exp, tecnico_resultado, "Motivo técnico de prueba")
        juridico.dictaminar(usuarios["juridica"], exp, juridico_resultado, "Motivo jurídico de prueba",
                            propiedad=propiedad_en_regla(exp))
        exp.refresh_from_db()
        return exp
    return _crear


def _reglas_minimas(clave, catalogos):
    """Programa sin archivo de reglas: tipo de persona, un requisito y el plazo de faltantes (para las pruebas)."""
    ej = Ejercicio.objects.get(programa__clave=clave, anio=2026)
    ej.reglas_cargadas = timezone.now()
    ej.save()
    tp, _ = TipoPersona.objects.get_or_create(ejercicio=ej, clave="fisica", defaults={"nombre": "Persona física"})
    req, _ = Requisito.objects.get_or_create(ejercicio=ej, clave=f"{clave}-REQ-01",
                                             defaults={"texto": "Solicitud Única", "fundamento": "prueba"})
    Plazo.objects.get_or_create(ejercicio=ej, clave="complemento_documentacion_faltante",
                                defaults={"descripcion": "Faltantes", "cantidad": 5, "unidad": "dias_habiles"})
    return ej


@pytest.fixture
def peg(catalogos):
    """PEG 2026 con sus reglas reales (``reglas/PEG.json``): quien solicita es el núcleo agrario, la persona
    beneficiaria es el Guardabosque, sin polígono; dictamen en 45 días hábiles (Convocatoria base quinta, fr. II)."""
    ej = Ejercicio.objects.get(programa__clave="PEG", anio=2026)
    assert ej.tiene_reglas and ej.tipos_persona.filter(clave="nucleo_agrario").exists()
    return ej


def registrar_peg(usuarios, ejercicio, nombre="Ejido San Juan", solicitante="Ejido San Juan", **kw):
    """Solicitud de Guardabosques validada: la registra el núcleo agrario (tipo de las reglas), en la modalidad única
    del programa, sin superficie ni polígono, y la valida la Dirección de Protección Forestal."""
    kw.setdefault("direccion", "dir_dpf")
    kw.setdefault("tipo", "nucleo_agrario")
    kw.setdefault("modalidad", "apoyo_monetario_guardabosque")
    kw.setdefault("ha", None)
    kw.setdefault("beneficiaria", "Margarito Sánchez Ruiz")
    kw.setdefault("beneficiaria_curp", "SARM800101HMCNZR09")
    return registrar_validada(usuarios, ejercicio, nombre=nombre, solicitante=solicitante, **kw)


@pytest.fixture
def psa(catalogos):
    """PSAHEM 2026 con sus dos ministraciones (70 % y 30 %, numeral 10.1 fr. X)."""
    ej = _reglas_minimas("PSA", catalogos)
    Ministracion.objects.get_or_create(ejercicio=ej, numero=1, defaults={"porcentaje": Decimal("70")})
    Ministracion.objects.get_or_create(ejercicio=ej, numero=2, defaults={"porcentaje": Decimal("30")})
    return ej


def fecha_sesion(dias=6):
    hoy = timezone.localtime(timezone.now())
    return timezone.make_aware(datetime.combine(dias_habiles.sumar_dias_habiles(hoy, dias), time(11, 0)))


def despues_de(sesion, horas=2):
    """Un momento posterior a la hora de la sesión (para registrar el acta o cerrar la sesión en pruebas)."""
    return sesion.fecha_hora + timedelta(hours=horas)


def documento_sesion(nombre="listado.pdf"):
    return ContentFile(_pdf_demo(nombre), name=nombre)
