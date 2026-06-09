from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR_TYPE
from pptx.oxml.ns import qn
import math

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)

# ==== PALETA DE COLORES ====
DARK1   = RGBColor(0x0F, 0x1B, 0x2D)   # fondo oscuro principal
DARK2   = RGBColor(0x1A, 0x2A, 0x44)   # fondo tarjeta oscuro
ACCENT  = RGBColor(0x00, 0xCC, 0x88)   # verde menta
ACCENT2 = RGBColor(0xFF, 0x6B, 0x35)   # naranja
ACCENT3 = RGBColor(0x3B, 0x82, 0xF6)   # azul
ACCENT4 = RGBColor(0xEC, 0x48, 0x99)   # rosa
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
LIGHT   = RGBColor(0xF0, 0xF4, 0xF8)
GRAY    = RGBColor(0x94, 0xA3, 0xB8)
MUTED   = RGBColor(0x64, 0x74, 0x8B)
CARD_BG = RGBColor(0x1E, 0x2D, 0x3D)

# ==== HELPER FUNCTIONS ====

def add_bg(slide, color):
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_rect(slide, left, top, w, h, color, radius=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, left, top, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    if radius:
        shape.adjustments[0] = radius
    return shape


def add_circle(slide, left, top, size, color):
    shape = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, size, size)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def add_txt(slide, left, top, w, h, text, size=18, bold=False, color=WHITE, align=PP_ALIGN.LEFT, font='Calibri Light'):
    tb = slide.shapes.add_textbox(left, top, w, h)
    tb.text_frame.word_wrap = True
    p = tb.text_frame.paragraphs[0]
    p.text = text
    p.font.size = Pt(size)
    p.font.bold = bold
    p.font.color.rgb = color
    p.font.name = font
    p.alignment = align
    return tb


def add_multiline(slide, left, top, w, h, lines, size=16, color=WHITE, spacing=Pt(6), font='Calibri Light', align=PP_ALIGN.LEFT):
    """lines = list of str or list of (str, bold, color) tuples"""
    tb = slide.shapes.add_textbox(left, top, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(lines):
        if isinstance(line, str):
            txt, bld, clr = line, False, color
        else:
            txt, bld, clr = line[0], line[1] if len(line) > 1 else False, line[2] if len(line) > 2 else color
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = txt
        p.font.size = Pt(size)
        p.font.bold = bld
        p.font.color.rgb = clr
        p.font.name = font
        p.space_after = spacing
        p.alignment = align
    return tb


def add_icon_card(slide, left, top, w, h, icon, title, desc, accent_color):
    """Tarjeta con ícono circular + título + descripción"""
    card = add_rect(slide, left, top, w, h, CARD_BG, 0.04)
    # Círculo ícono
    circ = add_circle(slide, left + Inches(0.3), top + Inches(0.25), Inches(0.7), accent_color)
    add_txt(slide, left + Inches(0.3), top + Inches(0.32), Inches(0.7), Inches(0.5), icon, 22, True, DARK1, PP_ALIGN.CENTER)
    add_txt(slide, left + Inches(0.25), top + Inches(1.1), w - Inches(0.5), Inches(0.4), title, 16, True, WHITE, PP_ALIGN.LEFT)
    add_txt(slide, left + Inches(0.25), top + Inches(1.5), w - Inches(0.5), h - Inches(1.7), desc, 12, False, GRAY, PP_ALIGN.LEFT)


def add_deco_line(slide, left, top, w, color=ACCENT):
    add_rect(slide, left, top, w, Pt(3), color)


def add_section_header(slide, title, subtitle=None):
    add_txt(slide, Inches(0.9), Inches(0.35), Inches(11), Inches(0.7), title, 34, True, WHITE)
    add_deco_line(slide, Inches(0.9), Inches(0.95), Inches(2.5))
    if subtitle:
        add_txt(slide, Inches(0.9), Inches(1.15), Inches(11), Inches(0.4), subtitle, 14, False, MUTED)


# ================================================================
# SLIDE 1 — PORTADA
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)

# Patrón decorativo de fondo (círculos semitransparentes)
for i in range(8):
    x = Inches(1 + i * 1.8)
    y = Inches(1 + (i % 3) * 2.5)
    add_circle(slide, x - Inches(0.3), y - Inches(0.3), Inches(1.2), ACCENT)

# Barra superior
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)

# Logo
logo_box = add_rect(slide, Inches(1.2), Inches(1.8), Inches(1.8), Inches(1.8), ACCENT, 0.15)
add_txt(slide, Inches(1.2), Inches(2.1), Inches(1.8), Inches(1.2), "AF", 60, True, DARK1, PP_ALIGN.CENTER)

# Título principal
add_txt(slide, Inches(3.5), Inches(1.6), Inches(9), Inches(1), "AdminFut", 64, True, WHITE)
add_txt(slide, Inches(3.5), Inches(2.6), Inches(9), Inches(0.7), "Sistema Integral de Gestión de Ligas de Fútbol", 24, False, ACCENT)
add_deco_line(slide, Inches(3.5), Inches(3.4), Inches(4), ACCENT)
add_txt(slide, Inches(3.5), Inches(3.7), Inches(9), Inches(0.5), "Plataforma web para administración de torneos, equipos, jugadores y finanzas", 16, False, GRAY)

# Stats / badges
for i, (num, label) in enumerate([("12+", "Módulos"), ("100%", "Web"), ("3", "Formatos Reporte")]):
    x = Inches(1.2 + i * 2.8)
    add_rect(slide, x, Inches(5.0), Inches(2.4), Inches(1.2), CARD_BG, 0.06)
    add_txt(slide, x, Inches(5.1), Inches(2.4), Inches(0.5), num, 28, True, ACCENT, PP_ALIGN.CENTER)
    add_txt(slide, x, Inches(5.6), Inches(2.4), Inches(0.4), label, 13, False, GRAY, PP_ALIGN.CENTER)

# ================================================================
# SLIDE 2 — ARQUITECTURA (más visual)
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)

add_section_header(slide, "Arquitectura del Sistema")

# Diagrama de capas - Frontend
add_rect(slide, Inches(0.9), Inches(1.6), Inches(3.6), Inches(2.2), CARD_BG, 0.05)
add_txt(slide, Inches(0.9), Inches(1.6), Inches(3.6), Inches(0.5), "  FRONTEND", 14, True, ACCENT, PP_ALIGN.LEFT)
items_f = ["HTML5 / CSS3", "Bootstrap 5 (Responsive)", "JavaScript ES6", "Django Templates (Jinja2)"]
add_multiline(slide, Inches(1.1), Inches(2.2), Inches(3.2), Inches(1.5), items_f, size=13, color=GRAY, spacing=Pt(4))

add_txt(slide, Inches(4.6), Inches(2.4), Inches(0.5), Inches(0.4), "\u2192", 28, True, ACCENT, PP_ALIGN.CENTER)

add_rect(slide, Inches(5.0), Inches(1.6), Inches(3.6), Inches(2.2), CARD_BG, 0.05)
add_txt(slide, Inches(5.0), Inches(1.6), Inches(3.6), Inches(0.5), "  BACKEND (Django 6.0)", 14, True, ACCENT3, PP_ALIGN.LEFT)
items_b = ["Python 3.12", "Class-based Views", "ORM / Migrations", "ReportLab + OpenPyXL"]
add_multiline(slide, Inches(5.2), Inches(2.2), Inches(3.2), Inches(1.5), items_b, size=13, color=GRAY, spacing=Pt(4))

add_txt(slide, Inches(8.7), Inches(2.4), Inches(0.5), Inches(0.4), "\u2192", 28, True, ACCENT, PP_ALIGN.CENTER)

add_rect(slide, Inches(9.1), Inches(1.6), Inches(3.3), Inches(2.2), CARD_BG, 0.05)
add_txt(slide, Inches(9.1), Inches(1.6), Inches(3.3), Inches(0.5), "  BASE DE DATOS", 14, True, ACCENT2, PP_ALIGN.LEFT)
items_d = ["SQLite / MySQL", "Consultas optimizadas", "Migraciones automáticas", "20+ modelos relacionales"]
add_multiline(slide, Inches(9.3), Inches(2.2), Inches(2.9), Inches(1.5), items_d, size=13, color=GRAY, spacing=Pt(4))

# Módulos en grid
modulos = [
    ("Categorías", ACCENT), ("Temporadas", ACCENT3), ("Equipos", ACCENT2),
    ("Jugadores", ACCENT4), ("Partidos", ACCENT), ("Sanciones", ACCENT3),
    ("Finanzas", ACCENT2), ("Reportes", ACCENT4), ("Usuarios", ACCENT),
]
for i, (mod, clr) in enumerate(modulos):
    col = i % 3
    row = i // 3
    x = Inches(0.9 + col * 4.1)
    y = Inches(4.2 + row * 1.0)
    add_rect(slide, x, y, Inches(3.8), Inches(0.75), CARD_BG, 0.04)
    dot = add_circle(slide, x + Inches(0.15), y + Inches(0.15), Inches(0.45), clr)
    add_txt(slide, x + Inches(0.75), y + Inches(0.12), Inches(2.8), Inches(0.5), mod, 16, True, WHITE)


# ================================================================
# SLIDE 3 — CATEGORÍAS Y TEMPORADAS
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)
add_section_header(slide, "Categorías y Temporadas")

# Tarjetas lado izquierdo
features = [
    ("Categorías Configurables", "Nombre, género, rango de edad (mín/máx), límite de jugadores", ACCENT),
    ("Compatibilidad Cruzada", "Categorías compatibles entre sí (Primera \u2194 Veteranos, etc.)", ACCENT3),
    ("Estados de Temporada", "No iniciada \u2192 Iniciada \u2192 Finalizada con control de acceso", ACCENT2),
    ("Períodos de Altas/Bajas", "Ventanas programables por temporada (ordinario y extraordinario)", ACCENT4),
    ("Validación Automática", "Cupo máximo por equipo verificado en cada registro", ACCENT),
]
for i, (title, desc, clr) in enumerate(features):
    y = Inches(1.5 + i * 1.1)
    add_rect(slide, Inches(0.9), y, Inches(6.5), Inches(0.95), CARD_BG, 0.04)
    dot = add_circle(slide, Inches(1.1), y + Inches(0.2), Inches(0.35), clr)
    add_txt(slide, Inches(1.7), y + Inches(0.08), Inches(5.5), Inches(0.35), title, 16, True, WHITE)
    add_txt(slide, Inches(1.7), y + Inches(0.45), Inches(5.5), Inches(0.4), desc, 12, False, GRAY)

# Sidebar derecho - diagrama de flujo
add_rect(slide, Inches(8.0), Inches(1.5), Inches(4.5), Inches(5.5), CARD_BG, 0.05)
add_txt(slide, Inches(8.0), Inches(1.6), Inches(4.5), Inches(0.5), "  Flujo de Temporada", 18, True, ACCENT)

flow_steps = [
    ("1", "Crear Categoría", "Definir reglas, edades, compatibilidad", ACCENT),
    ("2", "Crear Temporada", "Configurar rol, grupos, liguilla", ACCENT3),
    ("3", "Iniciar Temporada", "Comenzar registro de resultados", ACCENT2),
    ("4", "Período de Altas", "Ventana para registrar/modificar jugadores", ACCENT4),
    ("5", "Finalizar", "Cerrar temporada, liberar jugadores", ACCENT),
]
for i, (num, title, desc, clr) in enumerate(flow_steps):
    y = Inches(2.2 + i * 0.9)
    # Círculo numerado
    add_circle(slide, Inches(8.4), y, Inches(0.45), clr)
    add_txt(slide, Inches(8.4), y + Inches(0.02), Inches(0.45), Inches(0.4), num, 18, True, DARK1, PP_ALIGN.CENTER)
    add_txt(slide, Inches(9.0), y - Inches(0.05), Inches(3.2), Inches(0.3), title, 14, True, WHITE)
    add_txt(slide, Inches(9.0), y + Inches(0.25), Inches(3.2), Inches(0.35), desc, 11, False, GRAY)
    if i < len(flow_steps) - 1:
        add_rect(slide, Inches(8.6), y + Inches(0.5), Pt(2), Inches(0.35), MUTED)


# ================================================================
# SLIDE 4 — GESTIÓN DE JUGADORES
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)
add_section_header(slide, "Gestión Integral de Jugadores")

features = [
    ("Registro Completo", "Foto, posición, dorsal, fecha de nacimiento, equipo principal + secundarios"),
    ("Filtros Inteligentes", "Categoría \u2192 Equipo \u2192 Búsqueda por nombre con filtrado JS en tiempo real"),
    ("Validación de Edad", "La edad se calcula automáticamente y se valida contra el rango de cada categoría"),
    ("Multi-categoría", "Posibilidad de jugar en ligas compatibles simultáneamente (1 principal + N secundarias)"),
    ("Protección de Datos", "No se puede eliminar ni cambiar de equipo si la temporada está en curso"),
]
for i, (title, desc) in enumerate(features):
    y = Inches(1.5 + i * 1.0)
    clr = [ACCENT, ACCENT3, ACCENT2, ACCENT4, ACCENT][i]
    add_rect(slide, Inches(0.9), y, Inches(11.5), Inches(0.85), CARD_BG, 0.04)
    dot = add_circle(slide, Inches(1.1), y + Inches(0.2), Inches(0.35), clr)
    add_txt(slide, Inches(1.7), y + Inches(0.08), Inches(10.5), Inches(0.3), title, 16, True, WHITE)
    add_txt(slide, Inches(1.7), y + Inches(0.42), Inches(10.5), Inches(0.35), desc, 13, False, GRAY)

# Tarjeta destacada - Control de Edad
add_rect(slide, Inches(0.9), Inches(5.6), Inches(11.5), Inches(1.5), RGBColor(0x2D, 0x1B, 0x00), 0.05)
add_rect(slide, Inches(0.9), Inches(5.6), Inches(0.12), Inches(1.5), ACCENT2)
add_txt(slide, Inches(1.3), Inches(5.7), Inches(11), Inches(0.35), "Control de Edad — Multa por Incumplimiento", 17, True, ACCENT2)
add_multiline(slide, Inches(1.3), Inches(6.1), Inches(10.8), Inches(1.0), [
    "Si se modifica la fecha de nacimiento y el jugador queda fuera del rango de edad de su categoría:",
    ("\u279c  Se genera automáticamente una multa de $500", True, ACCENT2),
    ("\u279c  Los partidos PEND/JUG donde participó se marcan como default (walkover)", True, ACCENT2),
    ("\u279c  El jugador queda suspendido hasta liquidar la multa en el POS de Ingresos", True, ACCENT2),
], size=13, color=GRAY, spacing=Pt(3))


# ================================================================
# SLIDE 5 — PARTIDOS Y RESULTADOS
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)
add_section_header(slide, "Partidos y Resultados")

items = [
    ("Programación", "Asignación de fecha, hora, campo y árbitro con validación de conflictos"),
    ("Resultados", "Carga de goles, tarjetas amarillas/rojas con actualización automática de tabla"),
    ("Walkover Automático", "Default por mora o abandono configurable por temporada"),
    ("Liguilla", "Cuartos, semifinales y final con formato ida/vuelta configurable"),
    ("Tabla de Posiciones", "Cálculo automático con puntos, diferencia de goles, racha"),
]
for i, (title, desc) in enumerate(items):
    y = Inches(1.5 + i * 1.1)
    clr = [ACCENT, ACCENT3, ACCENT2, ACCENT4, ACCENT][i]
    add_rect(slide, Inches(0.9), y, Inches(5.5), Inches(0.9), CARD_BG, 0.04)
    add_rect(slide, Inches(0.9), y, Pt(5), Inches(0.9), clr)
    add_txt(slide, Inches(1.2), y + Inches(0.08), Inches(5), Inches(0.3), title, 16, True, WHITE)
    add_txt(slide, Inches(1.2), y + Inches(0.4), Inches(5), Inches(0.4), desc, 12, False, GRAY)

# Visualización de tabla de posiciones mock
add_rect(slide, Inches(7.0), Inches(1.5), Inches(5.5), Inches(5.5), CARD_BG, 0.05)
add_txt(slide, Inches(7.0), Inches(1.6), Inches(5.5), Inches(0.5), "  Tabla de Posiciones (Ejemplo)", 18, True, ACCENT)

# Mock table
headers = ["#", "Equipo", "PJ", "G", "E", "P", "Pts"]
rows_data = [
    ("1", "Real Madrid FC", "10", "8", "1", "1", "25"),
    ("2", "FC Barcelona", "10", "7", "2", "1", "23"),
    ("3", "Atlético", "10", "6", "3", "1", "21"),
    ("4", "Cerro Lagos", "10", "5", "2", "3", "17"),
    ("5", "Deportivo", "10", "4", "4", "2", "16"),
]
col_widths = [Inches(0.4), Inches(2.5), Inches(0.4), Inches(0.4), Inches(0.4), Inches(0.4), Inches(0.5)]
x_start = Inches(7.3)
y_start = Inches(2.3)

# header row
x = x_start
for j, h in enumerate(headers):
    add_txt(slide, x, y_start, col_widths[j], Inches(0.35), h, 11, True, ACCENT, PP_ALIGN.CENTER)
    x += col_widths[j]

for i, row in enumerate(rows_data):
    y = y_start + Inches(0.4 + i * 0.5)
    bg = CARD_BG if i % 2 == 0 else DARK2
    add_rect(slide, x_start - Inches(0.1), y, Inches(5.1), Inches(0.42), bg, 0.02)
    x = x_start
    for j, val in enumerate(row):
        is_bold = (j == 0 or j == 6)
        add_txt(slide, x, y + Inches(0.02), col_widths[j], Inches(0.35), val, 12, is_bold, WHITE, PP_ALIGN.CENTER)
        x += col_widths[j]

add_txt(slide, Inches(7.3), Inches(5.0), Inches(5), Inches(0.4), "* Cálculo automático al finalizar cada partido", 10, False, MUTED)


# ================================================================
# SLIDE 6 — SANCIONES
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)
add_section_header(slide, "Sanciones y Suspensiones")

items = [
    ("Registro de Tarjetas", "Amarillas y rojas por partido con detalle de minuto y tipo"),
    ("Doble Amarilla", "Acumulación de 2 amarillas = suspensión automática de 1 jornada"),
    ("Roja Directa", "Suspensión configurable (N jornadas) según la falta"),
    ("Reporte Castigados", "PDF imprimible y XLSX editable con orden por jornada"),
    ("Prevención", "Notificaciones visuales de próximas suspensiones en la ficha del jugador"),
]
for i, (title, desc) in enumerate(items):
    y = Inches(1.5 + i * 1.1)
    clr = [ACCENT2, ACCENT, ACCENT3, ACCENT4, ACCENT][i]
    add_rect(slide, Inches(0.9), y, Inches(6.5), Inches(0.9), CARD_BG, 0.04)
    add_rect(slide, Inches(0.9), y, Pt(5), Inches(0.9), clr)
    add_txt(slide, Inches(1.2), y + Inches(0.08), Inches(6), Inches(0.3), title, 16, True, WHITE)
    add_txt(slide, Inches(1.2), y + Inches(0.4), Inches(6), Inches(0.4), desc, 12, False, GRAY)

# Sidebar - ejemplo visual de tarjetas
add_rect(slide, Inches(8.0), Inches(1.5), Inches(4.5), Inches(5.5), CARD_BG, 0.05)
add_txt(slide, Inches(8.0), Inches(1.6), Inches(4.5), Inches(0.5), "  Tipos de Sanción", 18, True, ACCENT2)

sanctions = [
    ("Amarilla", "Acumulación (2 = 1 fecha)", ACCENT2),
    ("Doble Amarilla", "1 fecha de suspensión", ACCENT),
    ("Roja Directa", "N fechas configurables", ACCENT3),
    ("Roja + Amarilla", "1 fecha + lo que reste de roja", ACCENT4),
]
for i, (title, desc, clr) in enumerate(sanctions):
    y = Inches(2.3 + i * 1.1)
    card = add_rect(slide, Inches(8.3), y, Inches(3.9), Inches(0.85), DARK2, 0.04)
    # Tarjeta visual
    card_w = Inches(0.6)
    card_h = Inches(0.4)
    cx = Inches(8.5)
    cy = y + Inches(0.2)
    tc = add_rect(slide, cx, cy, card_w, card_h, clr, 0.04)
    add_txt(slide, cx, cy + Inches(0.02), card_w, card_h, title[0], 22, True, DARK1, PP_ALIGN.CENTER)
    add_txt(slide, Inches(9.3), y + Inches(0.05), Inches(2.7), Inches(0.3), title, 14, True, WHITE)
    add_txt(slide, Inches(9.3), y + Inches(0.4), Inches(2.7), Inches(0.35), desc, 11, False, GRAY)


# ================================================================
# SLIDE 7 — FINANZAS / POS
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)
add_section_header(slide, "Módulo Financiero — Punto de Venta")

add_icon_card(slide, Inches(0.9), Inches(1.5), Inches(2.8), Inches(2.5), "$", "Conceptos", "Configurables: nombre, monto default, requiere jugador/equipo", ACCENT)
add_icon_card(slide, Inches(3.9), Inches(1.5), Inches(2.8), Inches(2.5), "\u23FA", "POS Rápido", "Interfaz tipo punto de venta con cambio automático", ACCENT3)
add_icon_card(slide, Inches(6.9), Inches(1.5), Inches(2.8), Inches(2.5), "\u2630", "Filtros", "Por concepto, fecha, rango de fechas, equipo", ACCENT2)
add_icon_card(slide, Inches(9.9), Inches(1.5), Inches(2.8), Inches(2.5), "\u2699", "Multa Edad", "Automática al cambiar fecha de nacimiento (suspende jugador)", ACCENT4)

# Tabla de conceptos
add_rect(slide, Inches(0.9), Inches(4.3), Inches(11.5), Inches(2.8), CARD_BG, 0.05)
add_txt(slide, Inches(0.9), Inches(4.4), Inches(11.5), Inches(0.4), "  Ejemplos de Conceptos de Ingreso", 17, True, ACCENT)

concept_headers = ["Concepto", "Monto Default", "Requiere", "Descripción"]
concept_rows = [
    ("Inscripción Equipo", "$2,000.00", "Equipo", "Pago anual por equipo participante"),
    ("Multa por Edad", "$500.00", "Jugador + Equipo", "Incumplimiento de rango de edad"),
    ("Renta de Campo", "$150.00", "—", "Uso de cancha por partido"),
    ("Pago Arbitraje", "$300.00", "—", "Honorarios arbitrales"),
]

cx = Inches(1.2)
cw = [Inches(3), Inches(1.5), Inches(1.8), Inches(5)]
for j, h in enumerate(concept_headers):
    add_txt(slide, cx, Inches(4.85), cw[j], Inches(0.3), h, 12, True, ACCENT)
    cx += cw[j]

for i, row in enumerate(concept_rows):
    cy = Inches(5.2 + i * 0.4)
    bg = DARK2 if i % 2 == 0 else CARD_BG
    add_rect(slide, Inches(1.2), cy, Inches(11), Inches(0.35), bg, 0.02)
    cx = Inches(1.2)
    for j, val in enumerate(row):
        add_txt(slide, cx, cy + Inches(0.02), cw[j], Inches(0.3), val, 11, False, WHITE if j == 0 else GRAY)
        cx += cw[j]


# ================================================================
# SLIDE 8 — ALTAS Y BAJAS
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)
add_section_header(slide, "Gestión de Altas y Bajas")

items = [
    ("Períodos Programables", "Ventanas de altas/bajas por temporada (ordinario y extraordinario)"),
    ("Alta con Búsqueda", "Selector de jugador existente con búsqueda por texto y filtro por categorías compatibles"),
    ("Asignación Flexible", "Registro como titular o secundario según la categoría destino"),
    ("Baja por Categoría", "Desactiva al jugador solo en esa categoría (no lo elimina del sistema)"),
    ("Dashboard en Vivo", "Barra de progreso x / max_jugadores por equipo con validación de cupo"),
]
for i, (title, desc) in enumerate(items):
    y = Inches(1.5 + i * 1.1)
    clr = [ACCENT, ACCENT3, ACCENT2, ACCENT4, ACCENT][i]
    add_rect(slide, Inches(0.9), y, Inches(7.0), Inches(0.9), CARD_BG, 0.04)
    add_rect(slide, Inches(0.9), y, Pt(5), Inches(0.9), clr)
    add_txt(slide, Inches(1.2), y + Inches(0.08), Inches(6.5), Inches(0.3), title, 16, True, WHITE)
    add_txt(slide, Inches(1.2), y + Inches(0.4), Inches(6.5), Inches(0.4), desc, 12, False, GRAY)

# Sidebar visual - barra de cupo
add_rect(slide, Inches(8.5), Inches(1.5), Inches(4.0), Inches(5.5), CARD_BG, 0.05)
add_txt(slide, Inches(8.5), Inches(1.6), Inches(4.0), Inches(0.5), "  Cupo por Equipo", 18, True, ACCENT)

team_data = [
    ("Real Madrid FC", 18, 22, ACCENT),
    ("FC Barcelona", 15, 22, ACCENT3),
    ("Atlético", 20, 22, ACCENT2),
    ("Cerro Lagos", 22, 22, ACCENT4),
]

for i, (name, current, max_val, clr) in enumerate(team_data):
    y = Inches(2.3 + i * 1.1)
    add_txt(slide, Inches(8.7), y, Inches(3.5), Inches(0.3), name, 14, True, WHITE)
    add_txt(slide, Inches(8.7), y + Inches(0.3), Inches(1.5), Inches(0.3), f"{current} / {max_val}", 12, False, GRAY)
    # Barra de progreso
    bar_bg = add_rect(slide, Inches(10.2), y + Inches(0.35), Inches(2.0), Inches(0.25), DARK2, 0.03)
    pct = current / max_val
    bar_fill = add_rect(slide, Inches(10.2), y + Inches(0.35), Inches(2.0 * pct), Inches(0.25), clr, 0.03)
    # botón acción
    add_rect(slide, Inches(8.7), y + Inches(0.6), Inches(3.5), Inches(0.3), clr, 0.04)
    add_txt(slide, Inches(8.7), y + Inches(0.63), Inches(3.5), Inches(0.25), "Dar de Alta +", 10, True, DARK1, PP_ALIGN.CENTER)


# ================================================================
# SLIDE 9 — REPORTES
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)
add_section_header(slide, "Reportes y Exportación")

icons_reports = [
    ("\U0001F4C4", "Tabla de Posiciones", "Puntos, dif. goles, racha", ACCENT),
    ("\U0001F6A9", "Jugadores Castigados (PDF)", "Formato imprimible con firmas", ACCENT2),
    ("\U0001F4CA", "Jugadores Castigados (XLSX)", "Editable en Excel", ACCENT3),
    ("\U0001F4D1", "Cédula de Partido (PDF)", "Alineaciones, resultado, firmas", ACCENT4),
    ("\U0001F4E4", "Exportación General", "Todas las tablas a Excel", ACCENT),
    ("\U0001F4CA", "Dashboard Visual", "Indicadores clave de la liga", ACCENT3),
]
for i, (icon, title, desc, clr) in enumerate(icons_reports):
    col = i % 3
    row = i // 3
    x = Inches(0.9 + col * 4.1)
    y = Inches(1.5 + row * 2.8)
    add_rect(slide, x, y, Inches(3.8), Inches(2.4), CARD_BG, 0.05)
    # Icono
    ic = add_circle(slide, x + Inches(1.4), y + Inches(0.25), Inches(0.9), clr)
    add_txt(slide, x + Inches(1.4), y + Inches(0.35), Inches(0.9), Inches(0.6), icon, 28, True, DARK1, PP_ALIGN.CENTER)
    add_txt(slide, x + Inches(0.2), y + Inches(1.3), Inches(3.4), Inches(0.4), title, 15, True, WHITE, PP_ALIGN.CENTER)
    add_txt(slide, x + Inches(0.2), y + Inches(1.7), Inches(3.4), Inches(0.5), desc, 12, False, GRAY, PP_ALIGN.CENTER)


# ================================================================
# SLIDE 10 — SEGURIDAD
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)
add_section_header(slide, "Seguridad y Control de Acceso")

items = [
    ("Autenticación Django", "Login seguro con sesiones, protección CSRF en todos los formularios"),
    ("Roles y Permisos", "Permisos granulares por módulo: crear, editar, eliminar, ver"),
    ("Protección de Conceptos", "Campo no_eliminar evita borrado accidental de conceptos críticos"),
    ("Validaciones Cruzadas", "Reglas a nivel formulario + base de datos + vistas"),
    ("Bloqueo por Temporada", "Operaciones restringidas cuando la categoría tiene temporada en curso"),
]
for i, (title, desc) in enumerate(items):
    y = Inches(1.5 + i * 1.1)
    clr = [ACCENT, ACCENT3, ACCENT2, ACCENT4, ACCENT][i]
    add_rect(slide, Inches(0.9), y, Inches(11.5), Inches(0.9), CARD_BG, 0.04)
    add_rect(slide, Inches(0.9), y, Pt(5), Inches(0.9), clr)
    add_txt(slide, Inches(1.2), y + Inches(0.08), Inches(11), Inches(0.3), title, 16, True, WHITE)
    add_txt(slide, Inches(1.2), y + Inches(0.4), Inches(11), Inches(0.4), desc, 12, False, GRAY)

# Mapa de permisos
add_rect(slide, Inches(0.9), Inches(5.6), Inches(11.5), Inches(1.5), CARD_BG, 0.05)
add_txt(slide, Inches(0.9), Inches(5.7), Inches(11.5), Inches(0.35), "  Matriz de Permisos (ejemplo)", 16, True, ACCENT)

perm_headers = ["Módulo", "Ver", "Crear", "Editar", "Eliminar"]
perm_rows = [
    ("Jugadores", "Sí", "Sí", "Sí", "Solo sin temp. activa"),
    ("Partidos", "Sí", "Sí", "Sí", "Sí"),
    ("Finanzas", "Sí", "Sí", "Sí", "No (protegido)"),
    ("Configuración", "Admin", "Admin", "Admin", "Admin"),
]

px = Inches(1.2)
pw = [Inches(2), Inches(1.8), Inches(1.8), Inches(2.2), Inches(3)]
for j, h in enumerate(perm_headers):
    add_txt(slide, px, Inches(6.1), pw[j], Inches(0.3), h, 11, True, ACCENT)
    px += pw[j]

for i, row in enumerate(perm_rows):
    py = Inches(6.4 + i * 0.3)
    bg = DARK2 if i % 2 == 0 else CARD_BG
    add_rect(slide, Inches(1.2), py, Inches(11), Inches(0.28), bg, 0.02)
    px = Inches(1.2)
    for j, val in enumerate(row):
        clr = WHITE if j == 0 else (ACCENT if val == "Sí" else (ACCENT2 if "No" in val or "Solo" in val else MUTED))
        add_txt(slide, px, py + Inches(0.01), pw[j], Inches(0.25), val, 11, False, clr)
        px += pw[j]


# ================================================================
# SLIDE 11 — STACK TECNOLÓGICO
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)

add_section_header(slide, "Stack Tecnológico")

techs = [
    ("\U0001F40D", "Python 3.12", "Lenguaje principal del backend", ACCENT),
    ("\U0001F3AF", "Django 6.0", "Framework web MTV con ORM potente", ACCENT3),
    ("\U0001F3A8", "Bootstrap 5", "Diseño responsive y componentes UI modernos", ACCENT2),
    ("\U0001F5C3", "SQLite / MySQL", "Base de datos relacional con migraciones", ACCENT4),
    ("\U0001F4C4", "ReportLab", "Generación de PDF con estilo", ACCENT),
    ("\U0001F4CA", "OpenPyXL", "Exportación a Excel con formato", ACCENT3),
]
for i, (icon, name, desc, clr) in enumerate(techs):
    col = i % 3
    row = i // 3
    x = Inches(0.9 + col * 4.1)
    y = Inches(1.6 + row * 2.6)
    add_rect(slide, x, y, Inches(3.8), Inches(2.2), CARD_BG, 0.05)
    ic = add_circle(slide, x + Inches(1.4), y + Inches(0.2), Inches(0.85), clr)
    add_txt(slide, x + Inches(1.4), y + Inches(0.3), Inches(0.85), Inches(0.6), icon, 30, True, DARK1, PP_ALIGN.CENTER)
    add_txt(slide, x + Inches(0.2), y + Inches(1.2), Inches(3.4), Inches(0.4), name, 18, True, WHITE, PP_ALIGN.CENTER)
    add_txt(slide, x + Inches(0.2), y + Inches(1.6), Inches(3.4), Inches(0.5), desc, 12, False, GRAY, PP_ALIGN.CENTER)


# ================================================================
# SLIDE 12 — CIERRE
# ================================================================
slide = prs.slides.add_slide(prs.slide_layouts[6])
add_bg(slide, DARK1)
add_rect(slide, Inches(0), Inches(0), Inches(13.333), Inches(0.12), ACCENT)

# Círculos decorativos
for i in range(5):
    x = Inches(2 + i * 2.2)
    y = Inches(1.5 + (i % 2) * 1.5)
    add_circle(slide, x, y, Inches(1.5), ACCENT)

add_txt(slide, Inches(1), Inches(2.2), Inches(11), Inches(1.2), "Gracias", 64, True, WHITE, PP_ALIGN.CENTER)
add_deco_line(slide, Inches(5.5), Inches(3.5), Inches(2.3), ACCENT)
add_txt(slide, Inches(1), Inches(3.8), Inches(11), Inches(0.6), "AdminFut — Sistema Integral de Gestión de Ligas de Fútbol", 20, False, ACCENT, PP_ALIGN.CENTER)
add_txt(slide, Inches(1), Inches(4.6), Inches(11), Inches(0.5), "Preguntas y respuestas", 18, False, GRAY, PP_ALIGN.CENTER)

# Contacto ficticio
add_rect(slide, Inches(4), Inches(5.5), Inches(5.3), Inches(1.2), CARD_BG, 0.06)
add_txt(slide, Inches(4.3), Inches(5.6), Inches(4.7), Inches(0.4), "Contacto", 16, True, WHITE, PP_ALIGN.CENTER)
add_multiline(slide, Inches(4.3), Inches(6.0), Inches(4.7), Inches(0.6), [
    "Desarrollado con Python + Django",
], size=12, color=GRAY, spacing=Pt(2))


# ================================================================
# GUARDAR
# ================================================================
prs.save("C:\\Users\\lodo1\\Desktop\\PROYECTOS\\PROYECTOS\\Personal\\AdminFut\\Presentacion_AdminFut.pptx")
print("Presentación creada exitosamente!")
