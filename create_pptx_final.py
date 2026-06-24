"""Presentación profesional AdminFut - tema claro."""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

SCREENSHOTS = r"C:\Users\lodo1\AppData\Local\Temp\opencode\screenshots"
OUTPUT = r"C:\Users\lodo1\AppData\Local\Temp\opencode\Presentacion_AdminFut.pptx"

BG = RGBColor(0xF5, 0xF5, 0xF5)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
DARK_GREEN = RGBColor(0x1B, 0x5E, 0x20)
MED_GREEN = RGBColor(0x2E, 0x7D, 0x32)
GREEN_ACCENT = RGBColor(0x4C, 0xAF, 0x50)
DARK_TEXT = RGBColor(0x21, 0x21, 0x21)
GRAY_TEXT = RGBColor(0x66, 0x66, 0x66)
GOLD = RGBColor(0xF5, 0x7F, 0x17)
CARD_BG = RGBColor(0xFF, 0xFF, 0xFF)

prs = Presentation()
prs.slide_width = Inches(13.333)
prs.slide_height = Inches(7.5)
W = prs.slide_width
H = prs.slide_height

def set_bg(slide, color=BG):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color

def add_shape(slide, left, top, w, h, color, radius=None):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, left, top, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    if radius:
        shape.adjustments[0] = radius
    return shape

def add_bar(slide, top=0, color=DARK_GREEN):
    s = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, top, W, Inches(0.07))
    s.fill.solid(); s.fill.fore_color.rgb = color; s.line.fill.background()

def add_title_area(slide, number, title, subtitle=None):
    add_shape(slide, Inches(0.6), Inches(0.3), Inches(0.5), Inches(0.5), MED_GREEN, radius=0.05)
    tb = slide.shapes.add_textbox(Inches(0.65), Inches(0.32), Inches(0.4), Inches(0.45))
    tb.text_frame.paragraphs[0].text = str(number).zfill(2)
    tb.text_frame.paragraphs[0].font.size = Pt(18)
    tb.text_frame.paragraphs[0].font.color.rgb = WHITE
    tb.text_frame.paragraphs[0].font.bold = True
    tb.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
    tb.text_frame.paragraphs[0].font.name = "Calibri"
    tb.text_frame.word_wrap = False
    # Center vertically
    tb.text_frame.paragraphs[0].space_before = Pt(2)

    txBox = slide.shapes.add_textbox(Inches(1.3), Inches(0.3), Inches(10), Inches(0.6))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(28)
    p.font.color.rgb = DARK_GREEN
    p.font.bold = True
    p.font.name = "Calibri"
    if subtitle:
        p2 = tf.add_paragraph()
        p2.text = subtitle
        p2.font.size = Pt(14)
        p2.font.color.rgb = GRAY_TEXT
        p2.font.name = "Calibri"

def add_card(slide, left, top, width, height):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    s.fill.solid(); s.fill.fore_color.rgb = WHITE
    s.line.color.rgb = RGBColor(0xE0, 0xE0, 0xE0); s.line.width = Pt(1)
    return s

def add_text(slide, left, top, width, height, lines, font_size=15, align=PP_ALIGN.LEFT, color=DARK_TEXT):
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    for i, item in enumerate(lines):
        if isinstance(item, str):
            text, bold, sz, clr = item, False, font_size, color
        else:
            text = item[0] if item[0] else ""
            bold = item[1] if len(item) > 1 else False
            sz = item[2] if len(item) > 2 else font_size
            clr = item[3] if len(item) > 3 else color
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = text
        p.font.size = Pt(sz)
        p.font.color.rgb = clr
        p.font.bold = bold
        p.font.name = "Calibri"
        p.space_after = Pt(4)
        p.alignment = align
        p.level = 0
    return txBox

def add_img(slide, path, left, top, width=None, height=None):
    if os.path.exists(path):
        kwargs = {"left": left, "top": top}
        if width: kwargs["width"] = width
        if height: kwargs["height"] = height
        slide.shapes.add_picture(path, **kwargs)

def add_icon_bullet(slide, left, top, icon, text, size=15, bold=False, clr=DARK_TEXT):
    txBox = slide.shapes.add_textbox(left, top, Inches(9), Inches(0.35))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = f"{icon}  {text}"
    p.font.size = Pt(size)
    p.font.color.rgb = clr
    p.font.bold = bold
    p.font.name = "Calibri"

# ================ S1: PORTADA ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s, DARK_GREEN)
add_bar(s, H - Inches(0.08), GREEN_ACCENT)
add_shape(s, Inches(4), Inches(1.2), Inches(5.3), Inches(0.08), GREEN_ACCENT, radius=0.02)
add_text(s, Inches(1), Inches(1.6), Inches(11.3), Inches(1.2),
         [("AdminFut", True, 56, WHITE)], font_size=56, align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(2.8), Inches(11.3), Inches(0.8),
         [("Sistema Integral de Gestión para Ligas de Fútbol", False, 26, RGBColor(0xA5, 0xD6, 0xA7))],
         font_size=26, align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(3.8), Inches(11.3), Inches(0.6),
         [("Automatiza  ·  Controla  ·  Crece", False, 22, GOLD)], font_size=22, align=PP_ALIGN.CENTER)

# Feature badges
features = [("📅  Horarios", 0), ("💰  Pagos", 1), ("📊  Estadísticas", 2), ("📱  Árbitros", 3), ("☁️  Nube", 4)]
for label, i in features:
    x = Inches(1.5 + i * 2.3)
    add_shape(s, x, Inches(4.7), Inches(2), Inches(0.45), RGBColor(0x21, 0x6C, 0x27), radius=0.04)
    add_text(s, x, Inches(4.72), Inches(2), Inches(0.4), [(label, False, 14, WHITE)], align=PP_ALIGN.CENTER)

add_text(s, Inches(1), Inches(5.5), Inches(11.3), Inches(0.4),
         [("Disponible en instalación local o en la nube  ·  Acceso desde cualquier dispositivo", False, 15, RGBColor(0xA5, 0xD6, 0xA7))],
         font_size=15, align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(6.5), Inches(11.3), Inches(0.4),
         [("Presentación Comercial", False, 14, RGBColor(0x81, 0xC7, 0x84))], font_size=14, align=PP_ALIGN.CENTER)

# ================ S2: PROBLEMA ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 1, "¿Por qué tu liga necesita AdminFut?")
problems = [
    ("⏱️", "Pierdes horas armando horarios y rosters manualmente"),
    ("📋", "Registros en hojas sueltas o Excel que se pierden"),
    ("💵", "Sin control sobre pagos, inscripciones y adeudos"),
    ("📞", "Horas comunicando resultados y cambios a los equipos"),
    ("❌", "Errores y conflictos de horarios frecuentes"),
    ("📉", "Sin estadísticas en tiempo real para tomar decisiones"),
    ("📝", "Generar reportes y roles de juego toma horas"),
]
card = add_card(s, Inches(0.6), Inches(1.2), Inches(7.5), Inches(5.8))
for i, (icon, text) in enumerate(problems):
    add_text(s, Inches(0.9), Inches(1.5 + i * 0.7), Inches(7), Inches(0.65),
             [(f"{icon}  {text}", False, 16)], color=DARK_TEXT)
add_img(s, os.path.join(SCREENSHOTS, "02_dashboard.png"), Inches(8.5), Inches(1.2), width=Inches(4.5))

# ================ S3: SOLUCIÓN ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 2, "AdminFut: La solución todo-en-uno", "Todo lo que necesitas para gestionar tu liga desde un solo lugar")
card = add_card(s, Inches(0.6), Inches(1.5), Inches(12.1), Inches(5.5))
solutions = [
    ("✅", "Programación automática de horarios sin conflictos"),
    ("✅", "Control de pagos, inscripciones y gastos con POS integrado"),
    ("✅", "Registro digital de jugadores, equipos y múltiples categorías"),
    ("✅", "Tablas de posiciones, goleo y estadísticas en tiempo real"),
    ("✅", "Cédula arbitral desde el celular con actualización al instante"),
    ("✅", "Comunicación automática con equipos vía correo electrónico"),
    ("✅", "Reportes profesionales PDF: roles, recibos, cédulas arbitrales"),
    ("✅", "Acceso por roles: Administrador, Árbitro, Invitado"),
    ("✅", "Funciona en tu propia computadora (local) o en la nube"),
]
cols = [(0.8, 5.2), (6.8, 5.0)]
for i, (icon, text) in enumerate(solutions):
    col = 0 if i < 5 else 1
    row = i if i < 5 else i - 5
    x, w = cols[col]
    add_text(s, Inches(x), Inches(1.8 + row * 0.55), Inches(w), Inches(0.5),
             [(f"  {icon}  {text}", False, 14)], color=DARK_TEXT)

add_text(s, Inches(0.8), Inches(5.9), Inches(11.5), Inches(0.4),
         [("El acceso por internet solo está disponible en la instalación web.", False, 13, GRAY_TEXT)])

# ================ S4: CATEGORÍAS Y TEMPORADAS ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 3, "Organiza tus Categorías y Temporadas")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(5.8), Inches(5.8))
cat_items = [
    "Crea múltiples categorías: Primera Fuerza,",
    "Veteranos, Femenil, Juvenil, etc.",
    "Gestiona temporadas independientes por categoría",
    "Define períodos de altas y bajas de jugadores",
    "Asigna horarios fijos con control de capacidad",
    "Equipos con campo propio no consumen espacios",
    "Visualiza el estatus: activa o finalizada",
]
for i, item in enumerate(cat_items):
    add_text(s, Inches(0.9), Inches(1.5 + i * 0.6), Inches(5.3), Inches(0.55),
             [(f"▸  {item}", False, 15)], color=DARK_TEXT)

add_img(s, os.path.join(SCREENSHOTS, "03_categorias.png"), Inches(6.8), Inches(1.2), width=Inches(6))
add_img(s, os.path.join(SCREENSHOTS, "04_temporadas.png"), Inches(6.8), Inches(4.2), width=Inches(6))

# ================ S5: EQUIPOS Y JUGADORES ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 4, "Control Total de Equipos y Jugadores")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(5.8), Inches(5.8))
team_items = [
    "Registro completo con logo e información",
    "Jugadores con foto, datos personales y número",
    "Gestión de equipos secundarios por jugador",
    "Historial de participación por temporada",
    "Control de cambios en períodos de altas/bajas",
    "Búsqueda y filtros avanzados",
]
for i, item in enumerate(team_items):
    add_text(s, Inches(0.9), Inches(1.5 + i * 0.7), Inches(5.3), Inches(0.65),
             [(f"▸  {item}", False, 16)], color=DARK_TEXT)
add_img(s, os.path.join(SCREENSHOTS, "05_equipos.png"), Inches(6.8), Inches(1.2), width=Inches(6))
add_img(s, os.path.join(SCREENSHOTS, "09_jugadores.png"), Inches(6.8), Inches(4.2), width=Inches(6))

# ================ S6: JORNADAS ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 5, "Programación Inteligente de Jornadas")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(5.8), Inches(5.8))
jorn_items = [
    "Generación automática de fixtures balanceados",
    "Asignación inteligente de campos y horarios",
    "Prevención de conflictos entre categorías",
    "Control de horarios fijos y capacidad",
    "Registro de resultados, goles y tarjetas",
    "Cálculo automático de suspensiones",
]
for i, item in enumerate(jorn_items):
    add_text(s, Inches(0.9), Inches(1.5 + i * 0.7), Inches(5.3), Inches(0.65),
             [(f"▸  {item}", False, 16)], color=DARK_TEXT)
add_img(s, os.path.join(SCREENSHOTS, "06_jornadas.png"), Inches(6.8), Inches(1.2), width=Inches(6))

# ================ S7: CÉDULA ARBITRAL ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 6, "Cédula Arbitral en Tiempo Real", "Los árbitros capturan el partido desde su celular")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(12.1), Inches(5.8))
add_text(s, Inches(1), Inches(1.5), Inches(5.5), Inches(5), [
    ("El árbitro accede a la cédula del partido desde su celular", True, 17),
    ("", False, 6),
    ("📱  Al medio tiempo registra el marcador parcial", False, 16),
    ("     y las incidencias (tarjetas, cambios, lesiones)", False, 15),
    ("", False, 6),
    ("✅  Al terminar el partido, finaliza la cédula", False, 16),
    ("     con el resultado oficial", False, 15),
    ("", False, 6),
    ("⚡  La tabla de posiciones, goleo y tarjetas", False, 16),
    ("     se actualizan automáticamente", False, 16),
    ("", False, 6),
    ("Sin esperar a que el administrador capture los datos.", False, 15),
    ("Información disponible para todos al instante.", False, 15),
    ("", False, 6),
    ("* Acceso por internet (solo en instalación web).", False, 13, GRAY_TEXT),
])
add_img(s, os.path.join(SCREENSHOTS, "03_ref_cedula.png"), Inches(7), Inches(1.5), width=Inches(5.5))

# ================ S8: ESTADÍSTICAS ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 7, "Estadísticas en Tiempo Real")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(5.8), Inches(5.8))
stat_items = [
    "Tabla de posiciones automática",
    "Goleo individual con ranking",
    "Tarjetas y jugadores suspendidos",
    "Estadísticas por equipo y jugador",
    "Acceso público para todos los consulten",
]
for i, item in enumerate(stat_items):
    add_text(s, Inches(0.9), Inches(1.5 + i * 0.7), Inches(5.3), Inches(0.65),
             [(f"▸  {item}", False, 16)], color=DARK_TEXT)
add_text(s, Inches(0.9), Inches(5.2), Inches(5.3), Inches(0.6),
         [("Con la cédula arbitral, los datos se reflejan al instante.", False, 14, GRAY_TEXT)])

add_img(s, os.path.join(SCREENSHOTS, "07_tabla_posiciones.png"), Inches(6.8), Inches(1.2), width=Inches(6))

# ================ S9: POS Y COBROS ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 8, "Punto de Venta y Control Financiero")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(5.8), Inches(5.8))
pos_items = [
    "Sistema POS integrado para cobros",
    "Pagos por concepto: inscripción, horario, etc.",
    "Cascada: Categoría → Temporada → Equipo",
    "Detección de pagos duplicados automática",
    "Ticket imprimible (58 mm u 88 mm)",
    "Control de ingresos por temporada",
]
for i, item in enumerate(pos_items):
    add_text(s, Inches(0.9), Inches(1.5 + i * 0.7), Inches(5.3), Inches(0.65),
             [(f"▸  {item}", False, 16)], color=DARK_TEXT)
add_img(s, os.path.join(SCREENSHOTS, "08_pos_finanzas.png"), Inches(6.8), Inches(1.2), width=Inches(6))

# ================ S10: ROLES ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 9, "Administración por Roles", "Divide el trabajo y maximiza resultados")
cards_data = [
    ("👑  Administrador", DARK_GREEN, [
        "Acceso total al sistema",
        "Configuración de liga y categorías",
        "Gestión de equipos y jugadores",
        "Control financiero y POS",
        "Reportes y estadísticas",
    ]),
    ("🛡️  Árbitro", MED_GREEN, [
        "Captura cédula arbitral desde su celular",
        "Registra marcadores y tarjetas",
        "Consulta posiciones y goleo",
        "Ve jugadores suspendidos",
    ]),
    ("👤  Invitado", GREEN_ACCENT, [
        "Consulta posiciones y goleo",
        "Ve tarjetas y castigados",
        "Roles de juego disponibles",
        "Suscripción a notificaciones",
    ]),
    ("⚡  Beneficios de Roles", DARK_GREEN, [
        "Cada quien accede solo a lo que necesita",
        "El admin se enfoca en gestión y finanzas",
        "El árbitro captura sin distracciones",
        "Los invitados consultan sin modificar",
        "Mayor seguridad y organización",
    ]),
]
positions = [0.6, 3.55, 6.5, 9.45]
for i, (title, color, items) in enumerate(cards_data):
    x = Inches(positions[i])
    add_shape(s, x, Inches(1.4), Inches(2.8), Inches(0.5), color, radius=0.03)
    add_text(s, x + Inches(0.05), Inches(1.42), Inches(2.7), Inches(0.45),
             [(title, True, 14, WHITE)], align=PP_ALIGN.CENTER)
    add_card(s, x, Inches(1.9), Inches(2.8), Inches(4.8))
    for j, item in enumerate(items):
        add_text(s, x + Inches(0.15), Inches(2.1 + j * 0.55), Inches(2.5), Inches(0.5),
                 [(f"✓  {item}", False, 13)], color=DARK_TEXT)

# ================ S11: DASHBOARD ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 10, "Dashboard Centralizado", "Todo lo que necesitas en un solo panel")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(5.8), Inches(5.8))
dash_items = [
    "Panel principal con resumen de la liga",
    "Acceso rápido a todas las funcionalidades",
    "Navegación intuitiva por módulos",
    "Diseño moderno y responsivo",
    "Disponible 24/7*",
]
for i, item in enumerate(dash_items):
    add_text(s, Inches(0.9), Inches(1.5 + i * 0.7), Inches(5.3), Inches(0.65),
             [(f"▸  {item}", False, 16)], color=DARK_TEXT)
add_text(s, Inches(0.9), Inches(5.2), Inches(5.3), Inches(0.4),
         [("* 24/7 solo en instalación web.", False, 13, GRAY_TEXT)])
add_img(s, os.path.join(SCREENSHOTS, "02_dashboard.png"), Inches(6.8), Inches(1.2), width=Inches(6))

# ================ S12: INSTALACIÓN ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 11, "Instalación Local o en la Nube", "Tú eliges dónde ejecutar el sistema")
cards_inst = [
    ("💻  Instalación Local", [
        "En tu propia computadora o servidor",
        "Sin dependencia de internet para operar",
        "Control total de tus datos",
        "Ideal para ligas con presupuesto limitado",
    ]),
    ("☁️  Instalación en la Nube (Web)", [
        "Acceso desde cualquier lugar y dispositivo",
        "Sin mantenimiento técnico ni respaldos",
        "Actualizaciones automáticas",
        "Los árbitros capturan desde su celular",
        "La información se actualiza en tiempo real",
    ]),
]
for i, (title, items) in enumerate(cards_inst):
    x = Inches(0.6 + i * 6.3)
    add_shape(s, x, Inches(1.4), Inches(5.8), Inches(0.5), MED_GREEN, radius=0.03)
    add_text(s, x + Inches(0.1), Inches(1.42), Inches(5.6), Inches(0.45),
             [(title, True, 17, WHITE)], align=PP_ALIGN.CENTER)
    add_card(s, x, Inches(1.9), Inches(5.8), Inches(3.5))
    for j, item in enumerate(items):
        add_text(s, x + Inches(0.3), Inches(2.1 + j * 0.6), Inches(5.3), Inches(0.55),
                 [(f"✓  {item}", False, 15)], color=DARK_TEXT)

add_text(s, Inches(0.8), Inches(5.8), Inches(11.5), Inches(0.8), [
    ("⚠️  El acceso por internet, la captura desde celular y las funcionalidades en tiempo real", False, 14, GOLD),
    ("    solo están disponibles en la instalación web (nube).", False, 14, GOLD),
    ("El servicio de hosting y dominio se cotizan por separado.", False, 14, GRAY_TEXT),
])

# ================ S13: BENEFICIOS CLAVE ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 12, "Beneficios Clave")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(12.1), Inches(5.8))
benefits = [
    ("⏱️", "Ahorra horas de trabajo administrativo cada semana"),
    ("💰", "Aumenta tus ingresos con control financiero preciso"),
    ("📊", "Decisiones basadas en datos en tiempo real*"),
    ("📱", "Tu liga desde cualquier lugar*"),
    ("🚫", "Elimina errores y conflictos de programación"),
    ("📄", "Reportes profesionales con un clic"),
    ("🔒", "Datos seguros sin pérdidas ni respaldos manuales"),
    ("📢", "Comunicación automática con los equipos"),
    ("👥", "Roles y permisos para dividir el trabajo"),
]
cols_b = [(0.8, 5.5), (6.8, 5.5)]
for i, (icon, text) in enumerate(benefits):
    col = 0 if i < 5 else 1
    row = i if i < 5 else i - 5
    x, w = cols_b[col]
    add_text(s, Inches(x), Inches(1.5 + row * 0.65), Inches(w), Inches(0.6),
             [(f"  {icon}  {text}", False, 15)], color=DARK_TEXT)
add_text(s, Inches(0.8), Inches(5.8), Inches(11), Inches(0.4),
         [("* Funcionalidades disponibles solo en instalación web.", False, 13, GRAY_TEXT)])

# ================ S14: POR QUÉ ADMINFUT ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 13, "¿Por qué elegir AdminFut?")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(12.1), Inches(5.5))
reasons = [
    "🎯  Creado por administradores de ligas, para administradores",
    "💻  Funciona local o en la nube — tú decides",
    "🔧  Actualizaciones y mejoras constantes sin costo",
    "📞  Soporte técnico incluido",
    "🔒  Datos seguros con respaldos automáticos",
    "📈  Escalable: de 4 a 100+ equipos",
    "🎨  Personalizable: pagos, horarios y reglas a tu medida",
    "🤝  Integración con imágenes y redes sociales",
    "👥  Múltiples roles para eficientar el trabajo",
]
cols_r = [(0.8, 5.5), (6.8, 5.5)]
for i, item in enumerate(reasons):
    col = 0 if i < 5 else 1
    row = i if i < 5 else i - 5
    x, w = cols_r[col]
    add_text(s, Inches(x), Inches(1.5 + row * 0.6), Inches(w), Inches(0.55),
             [(item, False, 15)], color=DARK_TEXT)

# ================ S15: HOSTING (NUEVO) ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 14, "Consideraciones de Instalación Web", "Todo lo necesario para operar el sistema")
card = add_card(s, Inches(0.6), Inches(1.2), Inches(12.1), Inches(5.8))

add_text(s, Inches(1), Inches(1.6), Inches(5.5), Inches(4.5), [
    ("El sistema incluye:", True, 17),
    ("", False, 6),
    ("✓  Licencia de uso del software", False, 16),
    ("✓  Instalación y configuración inicial", False, 16),
    ("✓  Capacitación básica", False, 16),
    ("✓  Soporte técnico", False, 16),
    ("✓  Actualizaciones gratuitas", False, 16),
])
add_text(s, Inches(6.8), Inches(1.6), Inches(5.5), Inches(4.5), [
    ("Se cotiza por separado:", True, 17),
    ("", False, 6),
    ("⚠️  Hosting (servidor en la nube)", False, 16),
    ("⚠️  Nombre de dominio (www.tuliga.com)", False, 16),
    ("⚠️  Certificado SSL (https)", False, 16),
    ("", False, 6),
    ("Opcional: podemos gestionarlo todo por ti", False, 15),
    ("con costos transparentes y sin sorpresas.", False, 15),
])

# ================ S16: ESPECIFICACIONES HOSTING ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 15, "Especificaciones del Servidor", "Infraestructura para 2 clientes")

card = add_card(s, Inches(0.6), Inches(1.2), Inches(12.1), Inches(5.8))

specs = [
    ("Procesador", "2 núcleos dedicados"),
    ("Memoria RAM", "4 GB"),
    ("Almacenamiento", "80 GB SSD"),
    ("Transferencia", "4 TB / mes"),
    ("SSL", "Automático (Let's Encrypt)"),
    ("Panel de administración", "Coolify (autogestionado)"),
    ("Base de datos", "PostgreSQL (instancias ilimitadas)"),
    ("Dominio .com", "1 año incluido"),
]
for i, (label, value) in enumerate(specs):
    y = Inches(1.6 + i * 0.55)
    add_shape(s, Inches(1), y, Inches(3.5), Inches(0.45), MED_GREEN, radius=0.02)
    add_text(s, Inches(1.1), y + Inches(0.02), Inches(3.3), Inches(0.4),
             [(label, True, 14, WHITE)])
    add_text(s, Inches(4.8), y + Inches(0.02), Inches(5), Inches(0.4),
             [(value, False, 14)])

add_text(s, Inches(1), Inches(6), Inches(11), Inches(0.5), [
    ("Costo total: ~$2,880 MXN/año  ·  ≈ $240 MXN/mes  ·  Primer año con dominio incluido", False, 15, MED_GREEN),
])

# ================ S17: CAPACIDAD DE TRANSACCIONES ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s); add_bar(s)
add_title_area(s, 16, "Capacidad de Transacciones Mensuales", "Rendimiento estimado para 2 clientes")

card = add_card(s, Inches(0.6), Inches(1.2), Inches(12.1), Inches(5.8))

# Per-client estimate
add_text(s, Inches(0.8), Inches(1.4), Inches(5.5), Inches(2.5), [
    ("Transacciones estimadas por cliente al mes:", True, 15),
    ("", False, 4),
    ("Consultas de tablas y estadísticas     15,000", False, 13),
    ("Inicios de sesión                          1,000", False, 13),
    ("Captura de cédulas arbitrales              200", False, 13),
    ("Registro de pagos POS                      300", False, 13),
    ("Reportes PDF generados                     100", False, 13),
    ("Navegación general                       5,000", False, 13),
    ("", False, 4),
    ("Total por cliente                     ~21,600/mes", True, 14),
    ("Total 2 clientes                       ~43,200/mes", True, 14),
])

# Server capacity
add_text(s, Inches(6.8), Inches(1.4), Inches(5.5), Inches(2.5), [
    ("Capacidad del servidor:", True, 15),
    ("", False, 4),
    ("Transacciones/mes soportadas    2,000,000+", False, 13),
    ("Usuarios concurrentes                 ~150", False, 13),
    ("Reportes PDF simultáneos              8-10", False, 13),
    ("Clientes soportados                   3-4+", False, 13),
])

# Conclusion
add_shape(s, Inches(0.8), Inches(4.5), Inches(11.5), Inches(2.2), RGBColor(0xE8, 0xF5, 0xE9), radius=0.03)
add_text(s, Inches(1), Inches(4.6), Inches(11), Inches(2), [
    ("Conclusión", True, 17, MED_GREEN),
    ("", False, 4),
    ("43,200 transacciones/mes reales vs 2,000,000+ de capacidad = menos del 3% de uso.", False, 14),
    ("El servidor opera con amplio margen, garantizando respuestas rápidas incluso en", False, 14),
    ("horarios pico (días de partido) y con espacio para crecer a más clientes.", False, 14),
    ("Suficiente para el propósito actual y futuro inmediato.", True, 15, MED_GREEN),
])

# ================ S18: CIERRE ================
s = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(s, DARK_GREEN)
add_bar(s, 0, GREEN_ACCENT)
add_bar(s, H - Inches(0.07), GREEN_ACCENT)
add_text(s, Inches(1), Inches(2), Inches(11.3), Inches(1.2),
         [("¿Listo para transformar tu liga?", True, 40, WHITE)], font_size=40, align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(3.5), Inches(11.3), Inches(0.6),
         [("Solicita una demostración hoy", False, 24, GOLD)], font_size=24, align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(4.3), Inches(11.3), Inches(0.5),
         [("https://adminfut.onrender.com", False, 18, RGBColor(0xA5, 0xD6, 0xA7))], font_size=18, align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(5.0), Inches(11.3), Inches(0.5),
         [("Automatiza  ·  Controla  ·  Crece", False, 16, RGBColor(0x81, 0xC7, 0x84))], font_size=16, align=PP_ALIGN.CENTER)
add_text(s, Inches(1), Inches(6.0), Inches(11.3), Inches(0.4),
         [("* Acceso por internet solo disponible en instalación web.", False, 12, RGBColor(0x81, 0xC7, 0x84))],
         font_size=12, align=PP_ALIGN.CENTER)

prs.save(OUTPUT)
print(f"Presentación guardada: {OUTPUT}")
