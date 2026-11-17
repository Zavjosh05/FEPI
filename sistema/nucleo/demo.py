"""Datos de demostración: usuarios por unidad y solicitudes de Capturando Carbono 2026 en varios estados.

Las contraseñas son de prueba (documentadas en el README); nunca usar en un servidor real.
Todo se crea con las mismas funciones que usan las pantallas, así que los acuses, la bitácora y
los estados son los que produciría el sistema.
"""
from datetime import timedelta
from decimal import Decimal
import math

from django.contrib.gis.geos import MultiPolygon, Polygon
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from . import reloj
from .demo_calendario import cuando
from .models import Ejercicio, Expediente, Municipio, Predio, TipoUnidad, Unidad, Usuario

CONTRASENA_DEMO = "Probosque2026"

USUARIOS = [
    # usuario, nombre, apellido, clave de unidad, cargo, es_staff
    ("admin", "Administración", "del sistema", None, "Administración de catálogos", True),
    ("del_amecameca", "Laura", "Mendoza Ruiz", "AMECAMECA", "Ventanilla de la Delegación", False),
    ("del_toluca", "Jorge", "Salinas Pérez", "TOLUCA", "Ventanilla de la Delegación", False),
    ("del_valle", "Rosa", "Albarrán Díaz", "VALLE_DE_BRAVO", "Ventanilla de la Delegación", False),
    ("dir_drff", "Martha", "Galindo Torres", "DRFF", "Área técnica de Capturando Carbono", False),
    ("dir_dpf", "Ernesto", "Vargas Lima", "DPF", "Área responsable de Guardabosques", False),
    ("juridica", "Andrea", "Cortés Nava", "UJ", "Dictamen jurídico", False),
    ("comite", "Raúl", "Hernández Sosa", "STC", "Secretaría Técnica del Comité", False),
    ("finanzas", "Sofía", "Reyes Olvera", "DAFGD", "Pagos", False),
    ("vivero", "Tomás", "Pliego Luna", "VIVERO-DEMO", "Entrega de planta", False),
    ("fiduciaria", "Iván", "Montes Cruz", "FIDUCIARIA", "Cheques del FIPASAHEM", False),
]


def _pdf_demo(texto):
    """PDF mínimo de una página (sin WeasyPrint, para no tardar)."""
    contenido = f"BT /F1 14 Tf 60 720 Td ({texto}) Tj ET".encode("latin-1", "replace")
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(contenido)).encode() + b" >>\nstream\n" + contenido + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    salida = bytearray(b"%PDF-1.4\n")
    posiciones = []
    for i, obj in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(salida)
    salida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for p in posiciones:
        salida += f"{p:010d} 00000 n \n".encode()
    salida += f"trailer << /Size {len(objetos) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return bytes(salida)


def archivo_demo(nombre, texto="Documento digitalizado de demostracion"):
    return ContentFile(_pdf_demo(texto), name=nombre)


def cuadro_en_municipio(municipio, hectareas, desplazamiento_m=(0, 0)):
    """Polígono cuadrado de ``hectareas`` dentro del municipio (para la demostración y las pruebas)."""
    centro = municipio.geom.point_on_surface.transform(32614, clone=True)
    lado = math.sqrt(float(hectareas) * 10000)
    x, y = centro.x + desplazamiento_m[0], centro.y + desplazamiento_m[1]
    h = lado / 2
    p = Polygon(((x - h, y - h), (x + h, y - h), (x + h, y + h), (x - h, y + h), (x - h, y - h)), srid=32614)
    p.transform(4326)
    return MultiPolygon(p, srid=4326)


def crear_usuarios():
    for usuario, nombre, apellido, clave_unidad, cargo, staff in USUARIOS:
        unidad = Unidad.objects.filter(clave=clave_unidad).first() if clave_unidad else None
        u, creado = Usuario.objects.get_or_create(username=usuario, defaults={
            "first_name": nombre, "last_name": apellido, "unidad": unidad, "cargo": cargo,
            "is_staff": staff, "is_superuser": staff,
        })
        if creado:
            u.set_password(CONTRASENA_DEMO)
            u.save()
        elif u.unidad != unidad:
            u.unidad = unidad
            u.save()


def completar_requisitos(usuario, exp, faltar=(), fecha_archivo=None):
    """Marca los requisitos: condicionales «no aplica», los demás entregados (o en archivo PROBOSQUE)."""
    from recepcion import servicios
    from recepcion.models import EstadoRevision

    for r in exp.revisiones.select_related("requisito"):
        clave = r.requisito.clave
        if clave in faltar:
            servicios.revisar_requisito(usuario, r, EstadoRevision.FALTANTE, observaciones="No lo presentó")
        elif r.requisito.es_condicional:
            servicios.revisar_requisito(usuario, r, EstadoRevision.NO_APLICA)
        elif not r.requisito.requiere_documento:
            servicios.revisar_requisito(usuario, r, EstadoRevision.ENTREGADO, observaciones="Cumple")
        elif fecha_archivo and servicios.puede_usar_archivo_probosque(r):
            servicios.revisar_requisito(usuario, r, EstadoRevision.ENTREGADO, en_archivo_probosque=True,
                                        fecha_documento=fecha_archivo)
        else:
            servicios.revisar_requisito(usuario, r, EstadoRevision.ENTREGADO,
                                        archivo=archivo_demo(f"{clave}.pdf", f"{clave} - {exp.predio.nombre}"))


def _solicitud(usuario, ejercicio, municipio, predio, persona, tipo, modalidad, superficie, **extra):
    from recepcion import servicios

    tp = ejercicio.tipos_persona.get(clave=tipo)
    mod = ejercicio.modalidades.get(clave=modalidad) if modalidad else None
    datos = servicios.DatosSolicitud(
        ejercicio=ejercicio, municipio=Municipio.objects.get(nombre=municipio), nombre_predio=predio,
        tipo_persona=tp, modalidad=mod, solicitante_nombre=persona,
        solicitante_tipo=tipo if tipo in {"fisica", "juridica_colectiva", "nucleo_agrario"} else "juridica_colectiva",
        superficie_solicitada_ha=Decimal(superficie) if superficie is not None else None,
        observaciones="Solicitud de demostración.", **extra,
    )
    return servicios.registrar_solicitud(usuario, datos)


def paso(fecha, hora=10, minuto=0):
    """Reloj simulado en la fecha (con un tic de 2 s por lectura, para que cada renglón tenga su segundo)."""
    return reloj.en(cuando(fecha, hora, minuto), tic=2)


def crear_solicitudes():
    """Lote de CC 2026 de la recepción: cada paso en su fecha del calendario de la Convocatoria (recepción del 28-ene al
    27-mar; la validación de la Dirección se hace en el plazo de la ventanilla)."""
    from recepcion import servicios

    ejercicio = Ejercicio.objects.filter(programa__clave="CC", reglas_cargadas__isnull=False).order_by("-anio").first()
    if ejercicio is None:
        return 0
    u = {x.username: x for x in Usuario.objects.all()}
    creadas = 0

    def existe(nombre):
        return Predio.objects.filter(nombre=nombre, expedientes__ejercicio=ejercicio).exists()

    # 1) Recibida, revisión a medias (Amecameca): se registró en los últimos días de la recepción y el plazo de 5 días hábiles
    #    de la ventanilla (topado a la fecha límite de recepción, 27-mar) venció sin que la Delegación completara la revisión.
    if not existe("Los Ocotes"):
        with paso("2026-03-23", 9, 30):
            exp = _solicitud(u["del_amecameca"], ejercicio, "Amecameca", "Los Ocotes", "María Elena Castillo Rojas",
                             "fisica", "reforestacion", "6.5", curp="CARM700312MMCSJR05", localidad="San Pedro Nexapa")
        with paso("2026-03-23", 11):
            revs = list(exp.revisiones.select_related("requisito"))[:4]
            for r in revs:
                servicios.revisar_requisito(u["del_amecameca"], r, "entregado", archivo=archivo_demo(f"{r.requisito.clave}.pdf"))
        creadas += 1

    # 2) Recibida, completa y con polígono: lista para enviar (Tlalmanalco, núcleo agrario)
    if not existe("Ejido San Rafael, paraje El Mirador"):
        with paso("2026-02-10", 10):
            exp = _solicitud(u["del_amecameca"], ejercicio, "Tlalmanalco", "Ejido San Rafael, paraje El Mirador",
                             "Ejido San Rafael", "nucleo_agrario", "plantacion_maderable", "48",
                             representante="Comisariado ejidal: Pedro Ramírez Solís", con_representante_legal=True)
            completar_requisitos(u["del_amecameca"], exp)
        with paso("2026-02-12", 12):
            servicios.registrar_poligono(u["del_amecameca"], exp, cuadro_en_municipio(exp.predio.municipio, 47.2),
                                         "dibujo", "delegacion", "Ing. Carlos Ortega (Delegación Amecameca)",
                                         timezone.localdate() - timedelta(days=1))
        creadas += 1

    # 3) Enviada a la Dirección (Atlautla)
    if not existe("La Cañada"):
        with paso("2026-02-16", 10):
            exp = _solicitud(u["del_amecameca"], ejercicio, "Atlautla", "La Cañada", "Juan Carlos Pérez Galicia",
                             "fisica", "plantacion_navidena", "3.2", curp="PEGJ810523HMCRLN08")
            completar_requisitos(u["del_amecameca"], exp)
        with paso("2026-02-18", 12):
            servicios.registrar_poligono(u["del_amecameca"], exp, cuadro_en_municipio(exp.predio.municipio, 3.1),
                                         "dibujo", "prestador", "Servicios Técnicos Forestales del Oriente, S.C.",
                                         timezone.localdate() - timedelta(days=2))
        with paso("2026-02-19", 10):
            servicios.enviar_a_direccion(u["del_amecameca"], exp)
        creadas += 1

    # 4) Aviso de faltantes notificado (Valle de Bravo, Amanalco), dentro de su plazo de 5 días hábiles
    if not existe("Rancho El Capulín"):
        with paso("2026-02-23", 10):
            exp = _solicitud(u["del_valle"], ejercicio, "Amanalco", "Rancho El Capulín", "Agroforestal Amanalco, S.P.R. de R.L.",
                             "juridica_colectiva", "reforestacion", "12", rfc="AAM120415K21",
                             representante="Lic. Beatriz Nava Ortiz", con_representante_legal=True)
            completar_requisitos(u["del_valle"], exp)
        with paso("2026-02-25", 10):
            servicios.enviar_a_direccion(u["del_valle"], exp)
        with paso("2026-03-04", 11):
            plano = exp.revisiones.filter(requisito__clave="CC-REQ-13").first()
            servicios.validar_expediente(u["dir_drff"], exp, [plano.pk] if plano else [],
                                         "El plano no trae la coordenada de un vértice del predio.")
        with paso("2026-03-05", 12):
            servicios.registrar_notificacion(u["del_valle"], servicios.aviso_vigente(exp))
        creadas += 1

    # 5) Refrendo validado con documentación vigente en PROBOSQUE y cambio de lugar del polígono (Zinacantepec)
    if not existe("Predio Agua Blanca"):
        with paso("2026-02-03", 10):
            exp = _solicitud(u["del_toluca"], ejercicio, "Zinacantepec", "Predio Agua Blanca", "Hilario Gómez Becerril",
                             "fisica", "reforestacion", "8", es_refrendo=True, curp="GOBH650101HMCMCL02")
            hoy = timezone.localdate()
            completar_requisitos(u["del_toluca"], exp, fecha_archivo=hoy.replace(year=hoy.year - 2))
        municipio = exp.predio.municipio
        with paso("2026-02-05", 12):
            servicios.registrar_poligono(u["del_toluca"], exp, cuadro_en_municipio(municipio, 8.4), "dibujo",
                                         "delegacion", "Téc. Ana Laura Zepeda", timezone.localdate() - timedelta(days=1))
        with paso("2026-02-10", 12):
            servicios.registrar_poligono(u["del_toluca"], exp, cuadro_en_municipio(municipio, 7.9, (900, 600)),
                                         "dibujo", "delegacion", "Téc. Ana Laura Zepeda", timezone.localdate() - timedelta(days=1),
                                         motivo_cambio="La persona beneficiaria cambió el área por un incendio en la parte baja.")
        with paso("2026-02-11", 10):
            servicios.enviar_a_direccion(u["del_toluca"], exp)
        with paso("2026-02-17", 11):
            servicios.validar_expediente(u["dir_drff"], exp, [], "Refrendo: documentación legal vigente en archivo.")
        creadas += 1

    # 6) Desechada: no completó la documentación en los 5 días hábiles (vencían el 4-mar) (flujo alterno A) (Ozumba)
    if not existe("El Tecolote"):
        with paso("2026-02-24", 10):
            exp = _solicitud(u["del_amecameca"], ejercicio, "Ozumba", "El Tecolote", "Gregorio Linares Peña",
                             "fisica", "reforestacion", "2")
            completar_requisitos(u["del_amecameca"], exp, faltar=("CC-REQ-10",))
        with paso("2026-03-05", 10):
            exp.cambiar_estado("desechada", u["del_amecameca"],
                               motivo="No presentó el documento de propiedad dentro de los 5 días hábiles (8.1.1.2 fr. XIV).")
        creadas += 1
    return creadas


@transaction.atomic
def cargar_demo():
    crear_usuarios()
    return crear_solicitudes()
