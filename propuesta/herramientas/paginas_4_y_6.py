"""Rehace las páginas 4 (modelo de datos y estudio de factibilidad) y 6 (requerimientos, riesgos y flujo entre
módulos) de la propuesta con una redacción neutral sobre cómo se desarrolla. Se aplicó una vez, el 18-nov-2026, a
`original/docs/Propuesta_solucion_modular_PROBOSQUE_2026.pdf`; `actualizar_propuesta.py` lleva las páginas al PDF
vigente. Volver a correrlo da el mismo resultado.
Se corre como `actualizar_propuesta.py` (imagen de pruebas del sistema)."""
import io
import pathlib

from playwright.sync_api import sync_playwright
from pypdf import PdfReader, PdfWriter

CARPETA = pathlib.Path(__file__).resolve().parents[1]
PDF = CARPETA / "original" / "docs" / "Propuesta_solucion_modular_PROBOSQUE_2026.pdf"

ESTILO = """
@page { size: Letter; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: "DejaVu Sans", sans-serif; color: #1c1c1c; font-size: 9.6pt; line-height: 1.42; }
.pagina { width: 8.5in; height: 11in; padding: 0.62in 0.6in 0.7in; position: relative; overflow: hidden;
          page-break-after: always; }
.pie { position: absolute; bottom: 0.3in; left: 0; right: 0; text-align: center; font-size: 6.6pt; color: #333; }
h3 { font-size: 12pt; color: #1e4d2b; margin: 14pt 0 4pt; }
p { margin: 0 0 6pt; } ul, ol { margin: 0 0 6pt; padding-left: 16pt; } li { margin-bottom: 3pt; }
table { width: 100%; border-collapse: collapse; font-size: 8.4pt; margin: 0 0 8pt; }
th { background: #1e4d2b; color: #fff; text-align: left; padding: 3pt 5pt; }
td { border: 1px solid #d5d9d6; padding: 3pt 5pt; vertical-align: top; }
td.el { color: #1e4d2b; font-weight: bold; } td.capa { font-weight: bold; }
tr:nth-child(even) td { background: #fafbfa; }
"""
FILAS = [
    ("Usuario, unidad y rol", "Quién entra al sistema y qué puede hacer", "Núcleo"),
    ("Predio", "Municipio, Delegación, polígono (geometría) y Diagnóstico Técnico", "M1, M4"),
    ("Persona", "Persona solicitante o beneficiaria, Guardabosque, núcleo agrario y prestador de servicios forestales (RFN)", "M1, M3, M6"),
    ("Expediente", "Solicitud, programa, estado del trámite y acuse de recepción", "M1 a M6"),
    ("Documento", "Archivo, tipo, fecha y hora de entrega y acuse", "Todos"),
    ("Dictamen", "Técnico o jurídico, resultado y motivo", "M2"),
    ("Sesión y acuerdo", "Comité, fecha, orden del día, acuerdos y expedientes a los que aplican", "M2"),
    ("Contrato", "Modelo validado, firmas, fecha y hora de la firma, ampliaciones", "M3"),
    ("Vale y salida de planta", "Especie, cantidad, vivero, vigencia y fecha de entrega", "M3"),
    ("Envío", "Avisos, informes, bitácoras y reportes con su fecha y hora", "M4"),
    ("Verificación e incidencia", "Superficie verificada, ajuste e incidencias con su documento", "M4"),
    ("Ministración y pago", "Solicitud, soportes, pago o cheque y fechas", "M5"),
    ("Caso de seguimiento", "Reasignación, sustitución, incumplimiento, devolución y reintegro", "M6"),
    ("Bitácora", "Quién hizo qué, con fecha y hora", "Núcleo"),
]
P4 = ("<table><tr><th style='width:19%'>Entidad</th><th>Qué guarda</th><th style='width:11%'>Módulos</th></tr>"
      + "".join(f"<tr><td>{a}</td><td>{b}</td><td>{c}</td></tr>" for a, b, c in FILAS) + """</table>
<p>Cómo se mueven los datos:</p>
<ul><li><b>Carga inicial:</b> catálogos de programas, requisitos, plazos, montos y municipios (capa de municipios de IDEFOR).</li>
<li><b>Operación:</b> cada función escribe en el mismo expediente; ningún módulo guarda su propia copia.</li>
<li><b>Historial:</b> cada cambio queda registrado con fecha y hora (django-simple-history).</li>
<li><b>Salida:</b> listados y padrón exportables a Excel o CSV para el Comité y para transparencia.</li>
<li><b>Respaldos:</b> copia diaria de la base (pg_dump) y de la carpeta de documentos.</li>
<li><b>Calculadora:</b> no usa base de datos. El procesamiento anual genera archivos que la página lee: cifras por
municipio, tipo de bosque y año (JSON), límites municipales (TopoJSON) y la cuadrícula de masa forestal de 90 m (COG o
PNG). No comparte datos con el sistema de programas.</li></ul>
<h3>2.3 Estudio de factibilidad técnica</h3>
<p>Para cada capa se compararon opciones con cinco criterios: que sea libre (sin costo de licencia), madura y
documentada, rápida de prototipar, capaz de manejar datos geográficos y que se pueda construir y probar por completo con
código. Este último criterio pesa porque todo el desarrollo debe poder comprobarse con pruebas automáticas y revisarse
en equipo: se prefieren herramientas muy difundidas, configuradas en archivos del repositorio y no en pantallas, y con
pocos servicios que mantener. La tabla da las opciones evaluadas, la elegida y por qué es factible.</p>""")
P6 = """<table><tr><th style='width:16%'>Capa</th><th style='width:29%'>Opciones evaluadas</th><th style='width:18%'>Elegida</th>
<th>Por qué es factible</th></tr>
<tr><td class='capa'>Infraestructura</td><td>Docker Compose en servidor propio o VPS; plataforma administrada (Render,
Railway); instalación directa</td><td class='el'>Docker Compose</td><td>Todo el entorno queda descrito en archivos del
repositorio y se levanta con un comando en el servidor de PROBOSQUE o en un VPS.</td></tr>
<tr><td class='capa'>Maquetas</td><td>Maquetas en HTML con Bootstrap; Penpot; Figma</td><td class='el'>Maquetas en HTML
con Bootstrap</td><td>Se hacen con el mismo código del prototipo, así que la maqueta aprobada se convierte en la pantalla
real. Son tarea futura (sección 8).</td></tr></table>
<p><b>Requerimientos estimados.</b> Un servidor con 4 núcleos, 8 GB de RAM y 200 GB de disco aloja el sistema de
programas, la base de datos y los documentos del prototipo. La Calculadora se procesa una vez al año fuera del servidor
(cerca de 5 minutos por municipio, unas 10 horas para los 125 municipios) y solo se publican sus archivos de
resultados.</p>
<p><b>Riesgos y cómo se atienden:</b></p>
<ul><li><b>Revisión de lo que se desarrolla:</b> el equipo revisa cada entrega; las pruebas automáticas comprueban los
criterios de aceptación y todo el código queda en GitHub.</li>
<li><b>Servidor sin definir:</b> el sistema de programas necesita un servidor (de PROBOSQUE o un VPS) para las
demostraciones; con Docker pasa de uno a otro sin cambios. La Calculadora, al ser estática, se publica sin servidor.</li>
<li><b>Datos externos de la Calculadora:</b> dependen de CONAFOR y del INEGI (incendios de 2025, uso del suelo
reciente); los años sin datos quedan señalados.</li>
<li><b>Tamaño de la página de la Calculadora:</b> hoy los datos van dentro del HTML (2.7 MB); al separarlos en archivos
por año, la página solo carga lo que se consulta.</li>
<li><b>Conectividad en las Delegaciones:</b> las pantallas son ligeras (HTML generado en el servidor) y la entrega en
persona queda registrada igual que la del portal.</li></ul>
<p><b>Conclusión:</b> el sistema es técnicamente factible con herramientas libres, sin costo de licencias, con un solo
lenguaje (Python) para los dos subsistemas y con herramientas que se pueden construir y probar por completo con
código.</p>
<h3>2.4 Flujo entre módulos</h3>
<p>Los módulos se encadenan en el orden del proceso. Cada uno recibe el expediente en un estado, hace su parte y lo deja
listo para el siguiente:</p>
<ol><li><b>Recepción</b> (M1): la Delegación registra la solicitud, revisa el expediente y ubica el predio; la Dirección
lo valida.</li>
<li><b>Dictamen y aprobación</b> (M2): dictámenes técnico y jurídico y sesión de aprobación del Comité.</li>
<li><b>Publicación y contrato</b> (M3): se publican los resultados, se firma el contrato y, en PS y RHF, se entrega la
planta.</li>
<li><b>Primer pago</b> (M5): se solicita y paga la primera ministración.</li>
<li><b>Ejecución</b> (M4): la persona beneficiaria envía sus comprobaciones y la Delegación verifica en campo.</li>
<li><b>Segundo pago</b> (M5): con la verificación, se paga la segunda ministración o la parte proporcional.</li>
<li><b>Cierre</b> (M6): resultados finales, informe anual y padrón.</li></ol>"""


def pagina(n, contenido):
    return (f"<section class='pagina'>{contenido}<div class='pie'>Propuesta de solución modular — PROBOSQUE 2026 · "
            f"{n} / 26</div></section>")


documento = (f"<!doctype html><html lang='es'><head><meta charset='utf-8'><style>{ESTILO}</style></head><body>"
             + pagina(4, P4) + pagina(6, P6) + "</body></html>")
with sync_playwright() as p:
    navegador = p.chromium.launch()
    pag = navegador.new_page()
    pag.set_content(documento)
    assert pag.evaluate("[...document.querySelectorAll('.pagina')].every(s => s.scrollHeight <= s.clientHeight)")
    nuevas = PdfReader(io.BytesIO(pag.pdf(format="Letter", print_background=True, prefer_css_page_size=True)))
    navegador.close()
assert len(nuevas.pages) == 2
original = PdfReader(PDF)
salida = PdfWriter()
for i, pag_original in enumerate(original.pages):
    salida.add_page(nuevas.pages[0] if i == 3 else nuevas.pages[1] if i == 5 else pag_original)
salida.add_metadata({"/Title": "Propuesta de solución modular — PROBOSQUE 2026"})
datos = io.BytesIO()
salida.write(datos)
PDF.write_bytes(datos.getvalue())
print("páginas 4 y 6 rehechas en", PDF.name)
