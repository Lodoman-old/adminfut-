from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.style import WD_STYLE_TYPE
import os

doc = Document()

# ─── Estilos ───
style = doc.styles['Normal']
font = style.font
font.name = 'Calibri'
font.size = Pt(11)

for level in range(1, 4):
    hs = doc.styles[f'Heading {level}']
    hs.font.color.rgb = RGBColor(0x1F, 0x49, 0x7D)

# ─── Portada ───
for _ in range(6):
    doc.add_paragraph()
titulo = doc.add_paragraph()
titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = titulo.add_run('MANUAL DE USUARIO')
run.font.size = Pt(36)
run.bold = True
run.font.color.rgb = RGBColor(0x1F, 0x49, 0x7D)

subt = doc.add_paragraph()
subt.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = subt.add_run('Sistema de Gestión Liga de Fútbol\nAdminFut')
run.font.size = Pt(18)
run.font.color.rgb = RGBColor(0x4A, 0x4A, 0x4A)

doc.add_paragraph()
ver = doc.add_paragraph()
ver.alignment = WD_ALIGN_PARAGRAPH.CENTER
ver.add_run('Versión 1.0').font.size = Pt(12)

doc.add_page_break()

# ─── Tabla de contenido (placeholder) ───
doc.add_heading('Índice', level=1)
toc_items = [
    '1. Introducción',
    '2. Acceso al sistema',
    '3. Pantalla principal',
    '4. Categorías',
    '   4.1 Lista de categorías',
    '   4.2 Crear / Editar categoría',
    '   4.3 Campos permitidos',
    '   4.4 Eliminar categoría',
    '5. Equipos',
    '   5.1 Lista de equipos',
    '   5.2 Crear / Editar equipo',
    '   5.3 Horario Fijo por temporada',
    '   5.4 Validación de capacidad de horarios',
    '6. Jugadores',
    '7. Árbitros',
    '8. Campos de juego',
    '9. Temporadas',
    '   9.1 Lista de temporadas',
    '   9.2 Crear / Editar temporada',
    '   9.3 Acciones de temporada',
    '   9.4 Asignación automática de árbitros',
    '   9.5 Resolución de conflictos de campo entre categorías',
    '   9.6 Abandono de equipo',
    '10. Periodos de altas y bajas',
    '11. Jornadas',
    '12. Partidos',
    '   12.1 Lista de partidos',
    '   12.2 Crear / Editar partido',
    '   12.3 Reagendar partido',
    '   12.4 Actualización automática por Horario Fijo',
    '   12.5 Resolución de conflictos de campo',
    '   12.6 Observaciones',
    '13. Cédula arbitral',
    '14. Tabla de posiciones / Goleo / Tarjetas',
    '15. Reportes',
    '16. Finanzas (POS)',
    '   16.1 Conceptos de ingreso',
    '   16.2 Punto de Venta (POS)',
    '   16.3 Reporte de movimientos',
    '17. Usuarios y roles',
    '18. Configuración',
    '19. Publicaciones en Facebook',
    '20. Suscripción por correo',
]
for item in toc_items:
    doc.add_paragraph(item, style='List Bullet')

doc.add_page_break()

# ─── Helper ───
def add_screenshot(desc, width=6):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f'[CAPTURA: {desc}]')
    run.font.size = Pt(9)
    run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)
    run.italic = True
    doc.add_paragraph()

def section(text):
    doc.add_heading(text, level=1)

def subsection(text):
    doc.add_heading(text, level=2)

def sub_subsection(text):
    doc.add_heading(text, level=3)

def para(text):
    doc.add_paragraph(text)

def bullet(text):
    doc.add_paragraph(text, style='List Bullet')

def number(text):
    doc.add_paragraph(text, style='List Number')

# ══════════════════════════════════════════════════════════
#  1. INTRODUCCIÓN
# ══════════════════════════════════════════════════════════
section('1. Introducción')
para(
    'AdminFut es un sistema integral para la gestión de ligas de fútbol '
    'amateurs. Permite administrar categorías, equipos, jugadores, árbitros, '
    'temporadas, jornadas y partidos, así como generar reportes, publicar '
    'resultados en Facebook, gestionar finanzas (POS) y controlar '
    'suspensiones y cédulas arbitrales.'
)
para('El sistema está diseñado para ser usado por:')
bullet('Administradores de la liga (gestión completa)')
bullet('Árbitros (consulta y edición de sus partidos asignados)')
bullet('Público en general (consulta de posiciones, goleo, tarjetas, jornadas)')

para(
    'Los permisos de cada usuario se controlan mediante roles. '
    'Dependiendo del rol, se mostrarán u ocultarán opciones en el menú.'
)

add_screenshot('Vista general del sistema')

# ══════════════════════════════════════════════════════════
#  2. ACCESO AL SISTEMA
# ══════════════════════════════════════════════════════════
section('2. Acceso al sistema')
para('Para acceder al sistema, abra su navegador y diríjase a la URL del sistema.')

subsection('2.1 Inicio de sesión')
para('En la pantalla de login ingrese su nombre de usuario y contraseña:')
bullet('Usuario: el nombre que le asignó el administrador')
bullet('Contraseña: la contraseña proporcionada por el administrador')
add_screenshot('Pantalla de inicio de sesión')

para(
    'Si es la primera vez que ingresa, el administrador le habrá asignado '
    'una contraseña predeterminada. Se recomienda cambiarla desde el menú '
    'de usuario > "Cambiar contraseña".'
)

subsection('2.2 Cierre de sesión')
para(
    'Haga clic en su nombre de usuario (esquina superior derecha) y '
    'seleccione "Cerrar sesión".'
)
add_screenshot('Menú de usuario con opción Cerrar sesión y Cambiar contraseña')

# ══════════════════════════════════════════════════════════
#  3. PANTALLA PRINCIPAL
# ══════════════════════════════════════════════════════════
section('3. Pantalla principal')
para(
    'Una vez dentro, verá la barra de navegación superior con las '
    'siguientes secciones principales (pueden variar según sus permisos):'
)
bullet('Categorías')
bullet('Equipos')
bullet('Jugadores')
bullet('Árbitros')
bullet('Campos')
bullet('Temporadas')
bullet('Periodo Altas')
bullet('Partidos')
bullet('Tablas (Posiciones, Goleo, Tarjetas, Castigados)')
bullet('Finanzas (Conceptos, POS)')
bullet('Reportes')
bullet('Suscripción')
bullet('Configuración (solo administradores)')
add_screenshot('Barra de navegación principal')
para(
    'Si un usuario tiene rol "Árbitro", al entrar a la pantalla de Partidos '
    'solo verá los partidos donde está asignado como árbitro, permitiéndole '
    'editar su cédula arbitral.'
)

# ══════════════════════════════════════════════════════════
#  4. CATEGORÍAS
# ══════════════════════════════════════════════════════════
section('4. Categorías')
para(
    'Las categorías definen los distintos grupos de edad o niveles '
    'de la liga (ej. Infantil A, Juvenil, Libre, Femenil). '
    'Cada categoría puede tener su propio rango de edad, horarios de juego '
    'y equipos compatibles.'
)

subsection('4.1 Lista de categorías')
para('Muestra todas las categorías registradas con su información principal.')
add_screenshot('Lista de categorías')

subsection('4.2 Crear / Editar categoría')
para('Campos principales:')
bullet('Nombre de la categoría')
bullet('Activo (switch para deshabilitar)')
bullet('Edad mínima y máxima (opcional, para control etario)')
bullet('Días de juego (días de la semana disponibles)')
bullet('Horarios disponibles')
bullet('Minuto por default para goles')
bullet('Número mínimo y máximo de jugadores por equipo')
bullet('Categorías compatibles (un jugador puede pertenecer a varias)')
bullet('Indicar si es la categoría principal')
bullet(
    'Campos Permitidos: define en qué campos puede jugar esta categoría. '
    'Al hacer clic en "Gestionar" se abre un modal con checkboxes de todos '
    'los campos activos. Puedes seleccionar uno, varios o ninguno. '
    'Si no seleccionas ninguno, la categoría puede jugar en cualquier campo. '
    'Si seleccionas uno o más, el generador de rol solo usará esos campos '
    'para los partidos de esta categoría.'
)
add_screenshot('Formulario de categoría con modal de campos permitidos')

subsection('4.3 Eliminar categoría')
para(
    'Solo se puede eliminar si no tiene equipos asociados. '
    'Si tiene equipos, deberá eliminarlos primero o reasignarlos.'
)

# ══════════════════════════════════════════════════════════
#  5. EQUIPOS
# ══════════════════════════════════════════════════════════
section('5. Equipos')
para(
    'Cada equipo pertenece a una categoría y puede tener uno o varios '
    'jugadores.'
)

subsection('5.1 Lista de equipos')
para('Muestra los equipos filtrados por categoría.')
add_screenshot('Lista de equipos')

subsection('5.2 Crear / Editar equipo')
para('Campos principales:')
bullet('Nombre del equipo')
bullet('Categoría a la que pertenece')
bullet('Campo Ranchería (opcional): si el equipo es de una comunidad rural, '
     'se le asigna un campo fijo. Al generar el rol, cuando ese equipo sea '
     'local se usará su campo ranchería, liberando campos normales para otros '
     'partidos.')
bullet('Activo')
bullet(
    'Horario Fijo: por cada temporada activa, se puede asignar un horario '
    'fijo de juego. Solo disponible si el equipo ha pagado el concepto '
    '"Horario Fijo" en esa temporada.'
)
add_screenshot('Formulario de equipo - campo ranchería')

subsection('5.3 Horario Fijo por temporada')
para(
    'En el formulario de edición de equipo, aparece una sección "Horario Fijo" '
    'por cada temporada activa de su categoría. Esta sección permite asignar '
    'un horario fijo de juego al equipo para toda la temporada.'
)
para('Comportamiento:')
bullet(
    'Si el equipo NO ha pagado el concepto "Horario Fijo" en la temporada, '
    'el selector aparece deshabilitado (gris). Primero debe registrar el pago '
    'desde el POS.'
)
bullet(
    'Si YA pagó, se habilita un menú desplegable con los horarios '
    'configurados en la categoría. Cada horario muestra cuántos equipos '
    'lo tienen ocupado vs el total disponible '
    '(ej. 10:00 (4/6 ocupados)).'
)
bullet(
    'Validación de capacidad: si el horario ya alcanzó su límite de equipos '
    '(ocupados = número de campos normales activos), las opciones llenas '
    'aparecen deshabilitadas en el menú con la etiqueta "[LLENO]". '
    'No se puede seleccionar un horario lleno. Además, si un equipo sin '
    'campo_ranchería intenta guardar un horario que ya excede la capacidad, '
    'el sistema lo rechaza con un mensaje de error.'
)
bullet(
    'Si ya tiene un horario asignado, se muestra en texto fijo con candado '
    'y no se puede editar. Para cambiarlo, deberá contactar al administrador.'
)
bullet(
    'Al seleccionar un horario y guardar, el sistema actualiza automáticamente '
    'los partidos PENDientes/SUSPendidos del equipo: cambia la hora al nuevo '
    'horario fijo.'
)
add_screenshot('Sección Horario Fijo en formulario de equipo')

para('Resolución de conflictos de campo al cambiar horario:')
bullet(
    'Si al cambiar la hora de un partido, el campo donde estaba programado '
    'ya está ocupado en ese nuevo horario, el sistema busca automáticamente '
    'un campo alternativo disponible.'
)
bullet(
    'Si el equipo local tiene un "Campo Ranchería" asignado, se intenta '
    'usar ese campo primero.'
)
bullet(
    'Si ningún campo está libre, se omite ese partido y se muestra un '
    'mensaje indicando cuáles no pudieron ser actualizados por falta de '
    'disponibilidad.'
)
add_screenshot('Mensajes de confirmación de horario fijo')

# ══════════════════════════════════════════════════════════
#  6. JUGADORES
# ══════════════════════════════════════════════════════════
section('6. Jugadores')
para(
    'Los jugadores son el corazón del sistema. Se registran con sus datos '
    'personales y se asignan a un equipo principal. Además, pueden tener '
    'equipos secundarios en categorías compatibles.'
)

subsection('6.1 Lista de jugadores')
para(
    'La lista de jugadores permite filtrar por categoría y equipo. '
    'También incluye un buscador por nombre o CURP.'
)
add_screenshot('Lista de jugadores con filtros')

subsection('6.2 Crear / Editar jugador')
para('Campos principales:')
bullet('Nombre y apellido')
bullet('CURP (validado contra nombre y fecha de nacimiento)')
bullet('Fecha de nacimiento')
bullet('Posición (Portero, Defensa, Mediocampista, Delantero)')
bullet('Equipo principal')
bullet('Equipos secundarios en categorías compatibles (vía modal)')
bullet('Dorsal (número de camiseta)')
bullet('Activo')
bullet('Foto (opcional)')
add_screenshot('Formulario de jugador')

para(
    'Validaciones importantes:'
)
bullet('Si el CURP ya existe, se muestra un error.')
bullet(
    'Si no tiene CURP, se valida que no exista otro jugador con el '
    'mismo nombre + apellido + fecha de nacimiento.'
)

subsection('6.3 Equipos secundarios (categorías compatibles)')
para(
    'Un jugador puede pertenecer a múltiples equipos en diferentes '
    'categorías, siempre que estas sean compatibles entre sí. '
    'La compatibilidad es bidireccional: la categoría A debe ser '
    'compatible con la B y viceversa.'
)
para('Desde el botón "Gestionar equipos secundarios" se abre un modal donde:')
bullet(
    'Se muestran todas las categorías compatibles con la categoría '
    'del equipo principal del jugador.'
)
bullet(
    'Si el jugador ya tiene un registro en alguna de esas categorías, '
    'aparece pre-seleccionado y bloqueado si ya ha jugado partidos en '
    'esa temporada activa (no se puede cambiar).'
)
bullet(
    'Si el jugador no ha jugado partidos pero hay un período de altas '
    'abierto, se puede cambiar de equipo secundario libremente.'
)
bullet(
    'Cada categoría compatible tiene su propio selector de equipo. '
    'Se pueden seleccionar tantas categorías como sean compatibles '
    'entre sí (incluso si no son compatibles con una categoría '
    'secundaria existente que se haya desmarcado).'
)
bullet(
    'La validación cruzada en vivo evita seleccionar combinaciones '
    'incompatibles de categorías.'
)
add_screenshot('Modal de equipos secundarios')

subsection('6.4 Cambio de equipo en periodo de altas')
para(
    'Durante un periodo de altas habilitado, un jugador puede cambiarse '
    'de equipo (principal o secundario) siempre y cuando NO haya jugado '
    'ningún partido en la temporada activa con su equipo actual. '
    'Si ya apareció en una cédula arbitral como titular o cambio, '
    'el cambio queda bloqueado hasta la siguiente temporada.'
)
para(
    'El mismo criterio aplica a equipos secundarios: la UI bloquea '
    'el checkbox de la categoría si el jugador ya tiene participaciones '
    'registradas, independientemente de si hay período de altas abierto.'
)

# ══════════════════════════════════════════════════════════
#  7. ÁRBITROS
# ══════════════════════════════════════════════════════════
section('7. Árbitros')
para(
    'Los árbitros se registran para asignarlos a los partidos. '
    'El sistema puede auto-asignar árbitros a los partidos de forma '
    'equitativa al generar el rol de juegos.'
)

subsection('7.1 Lista de árbitros')
add_screenshot('Lista de árbitros')

subsection('7.2 Crear / Editar árbitro')
para('Campos principales:')
bullet('Nombre y apellido')
bullet('Teléfono')
bullet('Activo')
add_screenshot('Formulario de árbitro')

para(
    'Al crear un árbitro, aparece el switch "Crear usuario del sistema '
    'con rol Árbitro". Si se activa, se crea automáticamente un usuario '
    'con username basado en su nombre (sin espacios), contraseña "123" '
    'y rol "Árbitro". Ese usuario podrá iniciar sesión y ver solo los '
    'partidos que tiene asignados.'
)
para(
    'Si el árbitro ya tiene un usuario vinculado, el switch aparece marcado '
    'y deshabilitado para evitar duplicados.'
)

# ══════════════════════════════════════════════════════════
#  8. CAMPOS
# ══════════════════════════════════════════════════════════
section('8. Campos de juego')
para('Registro de las canchas donde se juegan los partidos.')
bullet('Nombre del campo')
bullet('Ubicación / dirección')
bullet('¿Es ranchería? Marca campos que pertenecen a comunidades rurales. '
     'Estos campos se asignan directamente al equipo local cuando tiene '
     'campo_ranchería configurado, y NO cuentan en el límite de '
     'disponibilidad de horarios fijos (no se contabilizan en el total '
     'de campos disponibles para el selector de horario).')
bullet('Activo')
para(
    'Además, se puede gestionar la indisponibilidad de campos '
    '(fechas en las que un campo no estará disponible para jugar).'
)
add_screenshot('Gestión de indisponibilidad de campos')

# ══════════════════════════════════════════════════════════
#  9. TEMPORADAS
# ══════════════════════════════════════════════════════════
section('9. Temporadas')
para(
    'Las temporadas agrupan jornadas y partidos dentro de un periodo '
    'específico para una categoría.'
)

subsection('9.1 Lista de temporadas')
add_screenshot('Lista de temporadas')

subsection('9.2 Crear / Editar temporada')
para('Campos principales:')
bullet('Nombre')
bullet('Categoría')
bullet('Fecha de inicio y fin (la fecha de fin se calcula automáticamente '
     'al crear la temporada basado en los días de juego y número de jornadas. '
     'Al generar el rol de juegos, se refina automáticamente con la fecha '
     'real del último partido.)')
bullet('Días de juego')
bullet('Horarios')
bullet('Tipo de rol (GRUPOS o CIRCULAR)')
bullet('Número de grupos (si aplica)')
bullet('Número de clasificados (para liguilla)')
bullet('Minuto default para goles')
bullet('Gol de visitante como desempate')
bullet('Final de ida y vuelta')
bullet('Mínimo de jugadores por equipo')
bullet('Porcentaje mínimo de juegos para liguilla')
bullet('Cambios permitidos por partido')
bullet('Máximo de titulares')
bullet('Activo / Es prueba')
add_screenshot('Formulario de temporada')

subsection('9.3 Acciones de temporada')
para('Cada temporada tiene botones de acción:')
bullet('Iniciar: marca la temporada como iniciada y genera las jornadas')
bullet('Asignar grupos: distribuye los equipos en grupos')
bullet('Generar rol: crea los partidos de la temporada regular')
bullet('Generar liguilla: crea los partidos de liguilla (cuando todos los partidos regulares están finalizados)')
bullet('Finalizar: da por terminada la temporada')
bullet('Reabrir: permite reabrir una temporada finalizada')
bullet('Reiniciar: reinicia la temporada (borra partidos y resultados)')
bullet('Publicar campeón: publica al campeón en Facebook')
add_screenshot('Acciones de temporada')

subsection('9.4 Asignación automática de árbitros')
para(
    'Al generar el rol de partidos, el sistema asigna automáticamente '
    'los árbitros disponibles a los partidos, balanceando la carga '
    'de trabajo y evitando que un mismo árbitro tenga dos partidos '
    'en el mismo horario. Se prefiere mantener al mismo árbitro en '
    'el mismo campo cuando sea posible.'
)

subsection('9.5 Resolución de conflictos de campo entre categorías')
para(
    'Cuando se genera el rol de una temporada, el sistema revisa todos los '
    'partidos de otras temporadas ya existentes para evitar que dos partidos '
    'de diferentes categorías se programen en el mismo campo y horario. '
    'Si detecta un conflicto, asigna automáticamente un campo alternativo '
    'disponible en ese horario.'
)
para(
    'El orden de preferencia al asignar campo es:'
)
bullet(
    '1. Campos permitidos de la categoría (si están configurados). '
    'Si la categoría tiene campos permitidos seleccionados, solo se usan esos.'
)
bullet(
    '2. Campo ranchería del equipo local (si tiene uno asignado y está '
    'disponible en ese horario).'
)
bullet(
    '3. Campos normales libres, balanceando el uso entre equipos y evitando '
    'que un mismo campo sea usado por varios partidos en la misma jornada.'
)
bullet(
    '4. Si ningún campo está disponible, el partido se crea sin campo '
    'asignado para que el administrador lo ajuste manualmente.'
)
add_screenshot('Generación de rol sin conflictos de campo')

subsection('9.6 Abandono de equipo')
para(
    'Durante una temporada, se puede marcar a un equipo como abandonado. '
    'Esto congela sus partidos restantes y afecta la tabla de posiciones. '
    'También se puede reincorporar si la situación se resuelve.'
)
add_screenshot('Marcar abandono de equipo')

# ══════════════════════════════════════════════════════════
#  10. PERIODOS DE ALTAS Y BAJAS
# ══════════════════════════════════════════════════════════
section('10. Periodos de altas y bajas')
para(
    'Los periodos de altas permiten registrar movimientos de jugadores '
    'entre equipos durante una temporada en curso.'
)

subsection('10.1 Lista de periodos')
add_screenshot('Lista de periodos de altas')

subsection('10.2 Crear periodo')
para('Campos:')
bullet('Temporada')
bullet('Tipo (Altas, Bajas, Ambos)')
bullet('Fecha de inicio y fin')
bullet('Jornada de inicio y fin')
bullet('Extraordinario (marca si es un periodo especial)')
bullet('Activo')
add_screenshot('Formulario de periodo de altas')

subsection('10.3 Gestionar altas y bajas')
para(
    'Desde este panel se pueden dar de alta jugadores existentes en nuevos '
    'equipos, o dar de baja jugadores de sus equipos actuales. '
    'Se muestra el cupo disponible de cada equipo.'
)
para(
    'Si un jugador ya tiene participaciones registradas en la temporada '
    'activa (apareció en una cédula arbitral), no podrá cambiarse de equipo '
    'aunque haya un periodo de altas abierto.'
)
add_screenshot('Panel de gestión de altas y bajas')

# ══════════════════════════════════════════════════════════
#  11. JORNADAS
# ══════════════════════════════════════════════════════════
section('11. Jornadas')
para(
    'Cada temporada tiene jornadas que agrupan los partidos por fecha. '
    'En el listado de jornadas se muestran primero las que tienen partidos '
    'pendientes por jugar, ordenadas por fecha ascendente, y al final '
    'las jornadas completadas.'
)
para(
    'Cada jornada tiene botones para enviar el rol por correo, publicar '
    'en Facebook, y ver los partidos.'
)
add_screenshot('Lista de jornadas')

# ══════════════════════════════════════════════════════════
#  12. PARTIDOS
# ══════════════════════════════════════════════════════════
section('12. Partidos')
para(
    'Los partidos son el elemento central. En ellos se registran los '
    'resultados, goles, tarjetas y participaciones de jugadores.'
)

subsection('12.1 Lista de partidos')
para(
    'Muestra todos los partidos con filtros por temporada y jornada. '
    'Las temporadas finalizadas aparecen agrupadas bajo "Finalizados".'
)
para(
    'El orden de los partidos es: pendientes/suspendidos primero (por fecha ASC), '
    'luego jugándose, y finalmente los finalizados (por fecha DESC).'
)
add_screenshot('Lista de partidos')

para(
    'Si el usuario tiene rol Árbitro, la lista muestra únicamente los '
    'partidos donde está asignado como árbitro.'
)

subsection('12.2 Crear / Editar partido')
para('Campos principales:')
bullet('Temporada')
bullet('Jornada')
bullet('Equipo local y visitante')
bullet('Campo')
bullet('Árbitro')
bullet('Grupo (si aplica liguilla por grupos)')
bullet('Fecha y hora')
bullet('Estado (PENDiente, JUGándose, FINalizado, SUSPendido)')
bullet('Goles local y visitante')
bullet('Agregado global (para liguilla)')
bullet('Equipo que avanza (en liguilla)')
bullet('Observaciones')
add_screenshot('Formulario de partido')

subsection('12.3 Reagendar partido')
para(
    'Si un partido está suspendido, se puede reagendar desde el botón '
    'correspondiente, seleccionando una nueva fecha, hora y campo.'
)
add_screenshot('Reagendar partido')

subsection('12.4 Actualización automática por Horario Fijo')
para(
    'Cuando se asigna o cambia el horario fijo de un equipo (desde la '
    'edición del equipo), el sistema actualiza automáticamente todos sus '
    'partidos pendientes o suspendidos:'
)
bullet('Cambia la hora del partido al nuevo horario fijo.')
bullet(
    'Si el campo donde estaba programado el partido ya está ocupado '
    'en ese nuevo horario, busca un campo alternativo disponible. '
    'Prefiere primero el Campo Ranchería del equipo local si aplica.'
)
bullet(
    'Si no encuentra campo libre, mantiene el partido sin cambios '
    'y muestra un mensaje de advertencia indicando qué partidos '
    'no pudieron actualizarse.'
)

subsection('12.5 Observaciones')
para(
    'Cada partido puede tener observaciones (ej. incidentes, expulsiones, '
    'comentarios del árbitro) que se guardan mediante un modal.'
)
add_screenshot('Modal de observaciones')

# ══════════════════════════════════════════════════════════
#  13. CÉDULA ARBITRAL
# ══════════════════════════════════════════════════════════
section('13. Cédula arbitral')
para(
    'La cédula arbitral es la pantalla donde se registra la información '
    'detallada del partido: alineaciones, goles, tarjetas, cambios y '
    'resultado final.'
)
add_screenshot('Cédula arbitral - cabecera')

subsection('13.1 Registrar alineación')
para(
    'Seleccione los jugadores titulares y suplentes de cada equipo. '
    'Los jugadores disponibles son los que pertenecen al equipo en la '
    'temporada actual.'
)
add_screenshot('Selección de jugadores titulares')

subsection('13.2 Registrar goles')
para(
    'Para cada gol, indique:'
)
bullet('Jugador que anotó')
bullet('Tipo (gol de campo, penal, autogol, etc.)')
bullet('Minuto')
add_screenshot('Registro de goles')

subsection('13.3 Registrar tarjetas')
para('Indique:')
bullet('Jugador amonestado o expulsado')
bullet('Tipo (amarilla, doble amarilla, roja directa)')
bullet('Minuto')
bullet('Suspensión en jornadas (si aplica)')
add_screenshot('Registro de tarjetas')

subsection('13.4 Finalizar partido')
para(
    'Una vez registrados todos los datos, haga clic en "Finalizar partido". '
    'El sistema valida que los datos sean consistentes y guarda todo. '
    'Si la liguilla se completa, la temporada se finaliza automáticamente.'
)

# ══════════════════════════════════════════════════════════
#  14. TABLA DE POSICIONES / GOLEO / TARJETAS
# ══════════════════════════════════════════════════════════
section('14. Tabla de posiciones / Goleo / Tarjetas')
para(
    'Estas pantallas son de consulta pública. No requieren autenticación '
    'para verlas.'
)

subsection('14.1 Tabla de posiciones')
para(
    'Muestra la clasificación de equipos filtrada por categoría y temporada. '
    'Si no se selecciona temporada, elige automáticamente una activa '
    '(no finalizada). Si la temporada es por grupos, se muestran tablas '
    'separadas por grupo.'
)
add_screenshot('Tabla de posiciones')

subsection('14.2 Tabla de goleo')
para(
    'Muestra los máximos goleadores filtrados por categoría y temporada.'
)
add_screenshot('Tabla de goleo')

subsection('14.3 Tabla de tarjetas')
para('Muestra el registro de tarjetas por jugador.')
add_screenshot('Tabla de tarjetas')

subsection('14.4 Tabla de castigados')
para(
    'Muestra los jugadores suspendidos (por tarjetas o adeudos), con su '
    'saldo de jornadas pendientes y el logo de la liga en la parte superior '
    'izquierda.'
)
add_screenshot('Tabla de castigados')

# ══════════════════════════════════════════════════════════
#  15. REPORTES
# ══════════════════════════════════════════════════════════
section('15. Reportes')
para('El sistema genera varios reportes descargables en PDF y Excel:')
bullet('Reporte de jornadas (juegos por jornada)')
bullet('Reporte completo de todas las jornadas')
bullet('Juegos de la semana')
bullet('Reporte de ingresos')
bullet('Reporte de pagos por temporada')
bullet('Reporte de suscriptores (con permiso especial)')
bullet('Envío de roles por correo (semanal o por jornada)')
bullet('Publicación en Facebook')
add_screenshot('Sección de reportes')

# ══════════════════════════════════════════════════════════
#  16. FINANZAS (POS)
# ══════════════════════════════════════════════════════════
section('16. Finanzas (POS)')
para(
    'El módulo de finanzas permite gestionar ingresos, conceptos de pago '
    'y un punto de venta (POS).'
)

subsection('16.1 Conceptos de ingreso')
para('Definición de los tipos de ingreso:')
bullet('Nombre')
bullet('Monto por defecto')
bullet('Tipo (INGRESO o EGRESO)')
bullet('Protegido (no se puede eliminar si tiene movimientos asociados)')
bullet(
    'Requiere jugador: al activarlo, en el POS se mostrará el campo '
    'Jugador al seleccionar este concepto.'
)
bullet(
    'Requiere equipo: al activarlo, en el POS se mostrará el campo '
    'Equipo como obligatorio.'
)
bullet(
    'Requiere categoría/temporada: al activarlo, en el POS aparecerán '
    'los campos Categoría → Temporada → Equipo en cascada. El pago '
    'quedará vinculado a la temporada seleccionada.'
)
para(
    'Los conceptos "Horario Fijo" e "Inscripción de Equipo" están '
    'marcados como Protegidos y no se pueden eliminar.'
)
add_screenshot('Formulario de concepto con toggles')

subsection('16.2 Punto de Venta (POS)')
para('Pantalla para registrar pagos e ingresos rápidos:')
bullet('Seleccionar concepto de ingreso (botones visuales o menú desplegable).')
bullet('Cantidad y precio unitario (auto-cálculo del total).')
bullet(
    'Si el concepto tiene activado "Requiere categoría/temporada", '
    'aparecen los campos: Categoría (seleccionar) → Temporada activa '
    '(se filtra automáticamente) → Equipo (se filtra por los equipos '
    'de esa temporada).'
)
bullet('Si el concepto requiere jugador, aparece el campo Jugador.')
bullet('Genera ticket imprimible.')
bullet(
    'Validación en cliente: al hacer clic en "Registrar y abrir ticket", '
    'el sistema valida en el navegador que los campos requeridos estén '
    'completos ANTES de enviar. Si falta algún campo (categoría, '
    'temporada, equipo según el concepto), se marca en rojo y no se envía '
    'el formulario, evitando recargar la página.'
)
add_screenshot('Punto de venta con cascada de categoría/temporada/equipo')

subsection('16.3 Reporte de movimientos')
para(
    'Muestra todos los ingresos/egresos con filtros por categoría, '
    'temporada, concepto, tipo y rango de fechas. Por defecto muestra '
    'todos los movimientos.'
)
add_screenshot('Reporte de movimientos')

# ══════════════════════════════════════════════════════════
#  17. USUARIOS Y ROLES
# ══════════════════════════════════════════════════════════
section('17. Usuarios y Roles')
para(
    'El sistema cuenta con un control de acceso granular basado en roles. '
    'El administrador puede crear roles personalizados con permisos '
    'específicos para cada sección del sistema. Cada usuario tiene un rol '
    'asignado que determina qué pantallas puede ver y qué acciones puede '
    'realizar.'
)

subsection('17.1 Roles y permisos')
para(
    'Un rol agrupa un conjunto de permisos. Al crear o editar un rol, '
    'se muestra una lista completa de todos los permisos disponibles, '
    'organizados por sección. El administrador puede activar o desactivar '
    'cada permiso individualmente.'
)
para('Ejemplos de permisos disponibles:')
bullet('Gestión de categorías: crear, editar, eliminar, ver')
bullet('Gestión de equipos: crear, editar, eliminar')
bullet('Gestión de jugadores: crear, editar, eliminar, ver datos sensibles')
bullet('Gestión de árbitros: crear, editar, eliminar')
bullet('Gestión de temporadas: crear, editar, eliminar, iniciar, finalizar, generar rol')
bullet('Gestión de partidos: crear, editar, eliminar, aperturar finalizados')
bullet('Cédula arbitral: acceso a la cédula para registrar resultados')
bullet('Gestión de campos: crear, editar, eliminar')
bullet('Gestión de periodos de altas: crear, editar')
bullet('Finanzas: ver finanzas, crear conceptos, POS, reportes')
bullet('Reportes: reporte semanal, reporte de jornadas, reporte de suscriptores')
bullet('Configuración: gestionar configuración de la liga')
bullet('Usuarios y roles: gestionar usuarios y roles del sistema')
bullet('Publicaciones Facebook: publicar resultados')
bullet('Envios de correo: enviar roles y estadísticas por email')

add_screenshot('Pantalla de edición de rol con todos los permisos')

para(
    'Ejemplos de configuración de roles:'
)
bullet(
    'Rol "Administrador": todos los permisos activados. Acceso completo '
    'al sistema.'
)
bullet(
    'Rol "Árbitro": permisos limitados a ver sus partidos asignados, '
    'acceso a cédula arbitral y cambio de contraseña. Al iniciar sesión, '
    'la lista de partidos se filtra automáticamente para mostrar solo '
    'aquellos donde está asignado.'
)
bullet(
    'Rol "Capturista": permisos para editar partidos y cédulas arbitrales, '
    'pero sin acceso a finanzas, configuración ni usuarios.'
)
bullet(
    'Rol "Consulta": solo permisos de lectura en posiciones, goleo, '
    'tarjetas y jornadas. Sin acceso a crear o editar.'
)
bullet(
    'Rol "Finanzas": solo acceso al módulo de finanzas (POS, conceptos, '
    'reportes de ingresos). Sin acceso a configuración ni usuarios.'
)

subsection('17.2 Usuarios')
para('Para crear o editar un usuario:')
bullet('Nombre de usuario: con el que iniciará sesión')
bullet('Nombres y apellidos')
bullet('Rol: seleccionar el rol creado previamente (Árbitro, Capturista, etc.)')
bullet('Activo: si está marcado, el usuario puede iniciar sesión')
add_screenshot('Formulario de creación/edición de usuario')
para(
    'Al crear un árbitro desde el módulo de Árbitros, también se puede '
    'marcar "Crear usuario del sistema con rol Árbitro" para generar '
    'automáticamente el usuario con credenciales predeterminadas.'
)

subsection('17.3 Asignación de permisos por rol')
para(
    'Cada vez que un usuario inicia sesión, el sistema verifica su rol '
    'y muestra únicamente las opciones del menú para las que tiene permiso. '
    'Por ejemplo:'
)
bullet('Un usuario sin permiso "ver_finanzas" no verá el menú de Finanzas.')
bullet('Un usuario sin permiso "gestion_usuarios" no podrá acceder a la lista de usuarios.')
bullet('Un usuario con permiso "partido_cedula" pero sin "partido_editar" solo podrá ver la cédula, no editar el partido.')
add_screenshot('Menú visible para un usuario con permisos limitados')

subsection('17.4 Cambio de contraseña')
para(
    'Cualquier usuario autenticado puede cambiar su contraseña desde '
    'el menú desplegable de usuario (esquina superior derecha) > '
    '"Cambiar contraseña".'
)
add_screenshot('Pantalla de cambio de contraseña')

# ══════════════════════════════════════════════════════════
#  18. CONFIGURACIÓN
# ══════════════════════════════════════════════════════════
section('18. Configuración')
para('Pantalla de configuración general de la liga (solo administradores):')
bullet('Nombre de la liga')
bullet('Logo')
bullet('Correo electrónico para envío de roles')
bullet('Token de acceso a Facebook para publicaciones')
bullet('ID de página de Facebook')
bullet('Configuración de ticket (ancho en mm, nombre, logo)')
bullet('Envío automático de roles')
add_screenshot('Pantalla de configuración')

# ══════════════════════════════════════════════════════════
#  19. PUBLICACIONES EN FACEBOOK
# ══════════════════════════════════════════════════════════
section('19. Publicaciones en Facebook')
para(
    'El sistema puede publicar automáticamente en Facebook:'
)
bullet('Rol de juegos (partidos, posiciones y castigados)')
bullet('Resultados de jornada')
bullet('Campeón de temporada')
bullet('Tabla de posiciones')

para(
    'Las imágenes se generan automáticamente con el formato de la liga. '
    'Se publican 3 imágenes en un solo post: partidos, posiciones y '
    'castigados.'
)
add_screenshot('Publicación en Facebook')

# ══════════════════════════════════════════════════════════
#  20. SUSCRIPCIÓN
# ══════════════════════════════════════════════════════════
section('20. Suscripción por correo')
para(
    'Los interesados pueden suscribirse para recibir información '
    'de la liga por correo electrónico. La pantalla de suscripción '
    'está disponible para todo público (sin autenticación).'
)
bullet('Nombre')
bullet('Correo electrónico')
bullet('Activo')
add_screenshot('Formulario de suscripción')

# ─── Guardar ───
output = os.path.join(os.path.dirname(__file__), 'Manual_Usuario_AdminFut.docx')
doc.save(output)
print(f'Manual generado: {output}')
