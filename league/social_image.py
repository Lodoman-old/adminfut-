import io
import os
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

_FONTS_DIR = "C:/Windows/Fonts"
_SEGOE = os.path.join(_FONTS_DIR, "segoeui.ttf")
_SEGOEB = os.path.join(_FONTS_DIR, "segoeuib.ttf")
_SEGOE_EMOJI = os.path.join(_FONTS_DIR, "seguiemj.ttf")
_ARIAL = os.path.join(_FONTS_DIR, "arial.ttf")
_ARIALB = os.path.join(_FONTS_DIR, "arialbd.ttf")

COLOR_GREEN = "#2d5a27"
COLOR_GREEN_LIGHT = "#d4edda"
COLOR_WHITE = "#ffffff"
COLOR_BG = "#fafafa"
COLOR_ROW_ALT = "#f2f7f1"
COLOR_BORDER = "#d0d0d0"
COLOR_TEXT = "#222222"
COLOR_TEXT_LIGHT = "#666666"
COLOR_EQUIPO_SIN_LOGO = "#b8b8b8"

WIDTH = 600
MARGIN = 24


def _font(size, bold=False):
    try:
        return ImageFont.truetype(_SEGOEB if bold else _SEGOE, size)
    except (IOError, OSError):
        try:
            return ImageFont.truetype(_ARIALB if bold else _ARIAL, size)
        except (IOError, OSError):
            return ImageFont.load_default()


def _font_emoji(size):
    try:
        return ImageFont.truetype(_SEGOE_EMOJI, size)
    except (IOError, OSError):
        return _font(size)


def _tw(text, font):
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0]


def _th(font):
    bbox = font.getbbox("Ay")
    return bbox[3] - bbox[1]


def generar_imagen_resumen(
    temporada_nombre,
    jornada_numero,
    partidos,
    tabla,
    castigados,
    ahora_str,
    num_clasificados=0,
    tablas_por_grupo=None,
    por_grupo=0,
):
    ops = []
    y = 20

    def T(x, y, txt, fill, font):
        ops.append(("text", x, y, txt, fill, font))

    def R(x1, y1, x2, y2, fill, r=4):
        ops.append(("rect", x1, y1, x2, y2, fill, r))

    def L(x1, y1, x2, y2, fill, w=1):
        ops.append(("line", x1, y1, x2, y2, fill, w))

    # Title
    fnt_title = _font(22, bold=True)
    T(MARGIN, y, f"\u26bd  RESUMEN JORNADA {jornada_numero}", COLOR_GREEN, fnt_title)
    y += _th(fnt_title) + 2
    fnt_sub = _font(13)
    T(MARGIN, y, f"\u2500\u2500 {temporada_nombre.upper()} \u2500\u2500", COLOR_TEXT_LIGHT, fnt_sub)
    y += _th(fnt_sub) + 18

    # Partidos
    if partidos:
        fnt_sec = _font(16, bold=True)
        T(MARGIN, y, "\U0001f4cb  PARTIDOS", COLOR_GREEN, fnt_sec)
        y += _th(fnt_sec) + 8
        L(MARGIN, y, WIDTH - MARGIN, y, COLOR_GREEN, 2)
        y += 12

        for idx, p in enumerate(partidos):
            bg = COLOR_ROW_ALT if idx % 2 == 1 else COLOR_WHITE
            nlocal = p["local"][:15]
            nvis = p["visitante"][:15]
            score = p["marcador"]
            campo = p["campo"][:18] if p["campo"] else "Por definir"
            fecha = p["fecha"] if p["fecha"] else "Pendiente"
            row_h = 28
            ry = y
            R(MARGIN, ry, WIDTH - MARGIN, ry + row_h, bg)
            fnt = _font(13)
            fnt_b = _font(13, bold=True)
            T(MARGIN + 12, ry + 4, nlocal, COLOR_TEXT, fnt_b if p.get("local_win") else fnt)
            T(MARGIN + 172, ry + 4, score, COLOR_GREEN if p.get("is_fin") else COLOR_TEXT_LIGHT, fnt_b)
            T(MARGIN + 242, ry + 4, nvis, COLOR_TEXT, fnt_b if p.get("vis_win") else fnt)
            fnt_s = _font(11)
            T(MARGIN + 402, ry + 5, campo, COLOR_TEXT_LIGHT, fnt_s)
            T(MARGIN + 540, ry + 5, fecha, COLOR_TEXT_LIGHT, fnt_s)
            y += row_h + 2
        y += 10

    # Tabla
    if tabla or tablas_por_grupo:
        fnt_sec = _font(16, bold=True)
        T(MARGIN, y, "\U0001f3c6  TABLA DE POSICIONES", COLOR_GREEN, fnt_sec)
        y += _th(fnt_sec) + 8
        L(MARGIN, y, WIDTH - MARGIN, y, COLOR_GREEN, 2)
        y += 12

        col_widths = [30, 170, 38, 38, 38, 38, 38, 38, 42]
        headers = ["#", "Equipo", "PJ", "PG", "PE", "PP", "GF", "GC", "PTS"]
        table_w = sum(col_widths) + 8 * 4
        row_h = 28

        def _dibujar_tabla(tabla, n_clasif, y0):
            col_starts = []
            cx = MARGIN
            for w in col_widths:
                col_starts.append(cx)
                cx += w + 4

            R(MARGIN, y0, MARGIN + table_w, y0 + 30, COLOR_GREEN)
            fnt_h = _font(12, bold=True)
            for j, h in enumerate(headers):
                x = col_starts[j] + (col_widths[j] - _tw(h, fnt_h)) // 2
                T(x, y0 + 5, h, COLOR_WHITE, fnt_h)
            y0 += 30

            for i, t in enumerate(tabla):
                ry = y0
                clasif_bg = i < n_clasif
                bg = COLOR_GREEN_LIGHT if clasif_bg else (COLOR_ROW_ALT if i % 2 == 1 else COLOR_WHITE)
                R(MARGIN, ry, MARGIN + table_w, ry + row_h, bg, 3)
                fnt_d = _font(12)
                fnt_db = _font(12, bold=True)
                vals = [
                    str(i + 1), t["nombre"][:18],
                    str(t["pj"]), str(t["pg"]), str(t["pe"]),
                    str(t["pp"]), str(t["gf"]), str(t["gc"]), str(t["pts"]),
                ]
                for j, v in enumerate(vals):
                    f = fnt_db if j == 8 else fnt_d
                    c = COLOR_GREEN if j == 0 else COLOR_TEXT
                    x = col_starts[j] + 4 if j == 1 else col_starts[j] + (col_widths[j] - _tw(v, f)) // 2
                    T(x, ry + 5, v, c, f)
                y0 += row_h

            L(MARGIN, y0, MARGIN + table_w, y0, COLOR_BORDER, 1)
            return y0 + 12

        if tablas_por_grupo:
            for grupo_letra, grupo_tabla in tablas_por_grupo:
                fnt_g = _font(13, bold=True)
                T(MARGIN, y, f"Grupo {grupo_letra}", COLOR_GREEN, fnt_g)
                y += _th(fnt_g) + 4
                y = _dibujar_tabla(grupo_tabla, por_grupo, y) + 4
        else:
            y = _dibujar_tabla(tabla, num_clasificados, y)

    # Castigados
    if castigados:
        fnt_sec = _font(16, bold=True)
        T(MARGIN, y, "\U0001f7e5  CASTIGADOS", COLOR_GREEN, fnt_sec)
        y += _th(fnt_sec) + 8
        L(MARGIN, y, WIDTH - MARGIN, y, COLOR_GREEN, 2)
        y += 12
        fnt_c = _font(13)
        for c in castigados:
            txt = (
                f"\u2022  {c['jugador']} ({c['equipo']})  \u2014  "
                f"Exp. Jor.{c['jornada_expulsion']}  |  Restan {c['restantes']} jor."
            )
            T(MARGIN + 4, y, txt, COLOR_TEXT, fnt_c)
            y += _th(fnt_c) + 4
        y += 4

    # Footer
    y += 8
    fnt_f = _font(11)
    T(MARGIN, y, f"\U0001f550  Generado el {ahora_str}", COLOR_TEXT_LIGHT, fnt_f)
    y += _th(fnt_f) + 20

    return _render_and_save(ops, y, COLOR_BG)


def generar_imagen_posiciones(
    temporada_nombre,
    tabla,
    ahora_str,
    num_clasificados=0,
    tablas_por_grupo=None,
    por_grupo=0,
):
    ops = []
    y = 20

    def T(x, y, txt, fill, font):
        ops.append(("text", x, y, txt, fill, font))

    def R(x1, y1, x2, y2, fill, r=4):
        ops.append(("rect", x1, y1, x2, y2, fill, r))

    def L(x1, y1, x2, y2, fill, w=1):
        ops.append(("line", x1, y1, x2, y2, fill, w))

    fnt_title = _font(24, bold=True)
    T(MARGIN, y, f"\U0001f3c6  TABLA DE POSICIONES", COLOR_GREEN, fnt_title)
    y += _th(fnt_title) + 2
    fnt_sub = _font(13)
    T(MARGIN, y, f"\u2500\u2500 {temporada_nombre.upper()} \u2500\u2500", COLOR_TEXT_LIGHT, fnt_sub)
    y += _th(fnt_sub) + 20

    col_widths = [30, 180, 38, 38, 38, 38, 38, 38, 42]
    headers = ["#", "Equipo", "PJ", "PG", "PE", "PP", "GF", "GC", "PTS"]
    table_w = sum(col_widths) + 8 * 4
    row_h = 28

    def _dibujar_tabla(tabla, n_clasif, y0):
        col_starts = []
        cx = MARGIN
        for w in col_widths:
            col_starts.append(cx)
            cx += w + 4

        R(MARGIN, y0, MARGIN + table_w, y0 + 30, COLOR_GREEN)
        fnt_h = _font(12, bold=True)
        for j, h in enumerate(headers):
            x = col_starts[j] + (col_widths[j] - _tw(h, fnt_h)) // 2
            T(x, y0 + 5, h, COLOR_WHITE, fnt_h)
        y0 += 30

        for i, t in enumerate(tabla):
            ry = y0
            clasif_bg = i < n_clasif
            bg = COLOR_GREEN_LIGHT if clasif_bg else (COLOR_ROW_ALT if i % 2 == 1 else COLOR_WHITE)
            R(MARGIN, ry, MARGIN + table_w, ry + row_h, bg, 3)
            fnt_d = _font(12)
            fnt_db = _font(12, bold=True)
            vals = [
                str(i + 1), t["nombre"][:18],
                str(t["pj"]), str(t["pg"]), str(t["pe"]),
                str(t["pp"]), str(t["gf"]), str(t["gc"]), str(t["pts"]),
            ]
            for j, v in enumerate(vals):
                f = fnt_db if j == 8 else fnt_d
                c = COLOR_GREEN if j == 0 else COLOR_TEXT
                x = col_starts[j] + 4 if j == 1 else col_starts[j] + (col_widths[j] - _tw(v, f)) // 2
                T(x, ry + 5, v, c, f)
            y0 += row_h

        L(MARGIN, y0, MARGIN + table_w, y0, COLOR_BORDER, 1)
        return y0 + 14

    if tablas_por_grupo:
        for grupo_letra, grupo_tabla in tablas_por_grupo:
            fnt_grupo = _font(14, bold=True)
            T(MARGIN, y, f"Grupo {grupo_letra}", COLOR_GREEN, fnt_grupo)
            y += _th(fnt_grupo) + 6
            y = _dibujar_tabla(grupo_tabla, por_grupo, y) + 6
    else:
        y = _dibujar_tabla(tabla, num_clasificados, y)

        if num_clasificados > 0:
            fnt_nota = _font(11)
            T(MARGIN, y, f"\U0001f512  Top {num_clasificados} clasifican a liguilla", COLOR_TEXT_LIGHT, fnt_nota)
            y += _th(fnt_nota) + 10

    fnt_f = _font(11)
    T(MARGIN, y, f"\U0001f550  Generado el {ahora_str}", COLOR_TEXT_LIGHT, fnt_f)
    y += _th(fnt_f) + 20

    return _render_and_save(ops, y, COLOR_BG)


def generar_imagen_rol(
    temporada_nombre,
    jornadas,
    ahora_str,
):
    SCALE = 3
    ROL_WIDTH = 600 * SCALE
    ROL_MARGIN = 20 * SCALE
    ops = []
    y = 20 * SCALE
    gap = 6 * SCALE
    col_w = (ROL_WIDTH - ROL_MARGIN * 2 - gap) // 2

    def _s(v):
        return int(v * SCALE)

    def T(x, y, txt, fill, font):
        ops.append(("text", x, y, txt, fill, font))

    def R(x1, y1, x2, y2, fill, r=4):
        ops.append(("rect", x1, y1, x2, y2, fill, _s(r)))

    def L(x1, y1, x2, y2, fill, w=1):
        ops.append(("line", x1, y1, x2, y2, fill, _s(w)))

    def draw_match(ox, oy, p, w):
        bg = COLOR_ROW_ALT if p["idx"] % 2 == 1 else COLOR_WHITE
        rh = _s(24)
        R(ox, oy, ox + w, oy + rh, bg)
        fnt = _font(10 * SCALE)
        fnt_b = _font(10 * SCALE, bold=True)
        local = p["local"][:14]
        vis = p["visitante"][:14]
        score = p["marcador"]
        campo = p["campo"][:12]
        fecha = p["fecha"][:12]
        dft = p.get("default_win")
        local_win = (p.get("is_fin") and p.get("local_win")) or dft == "local"
        vis_win = (p.get("is_fin") and p.get("vis_win")) or dft == "visitante"
        T(ox + _s(5), oy + _s(4), local, COLOR_TEXT, fnt_b if local_win else fnt)
        if p.get("susp"):
            T(ox + _s(115), oy + _s(4), "SUSP", "#b00020", fnt_b)
        elif dft and not p.get("is_fin"):
            T(ox + _s(115), oy + _s(4), "DFT", "#c2410c", fnt_b)
        else:
            T(ox + _s(115), oy + _s(4), score, COLOR_GREEN if p.get("is_fin") else COLOR_TEXT_LIGHT, fnt_b)
        T(ox + _s(140), oy + _s(4), vis, COLOR_TEXT, fnt_b if vis_win else fnt)
        T(ox + _s(245), oy + _s(4), campo, COLOR_TEXT_LIGHT, fnt)
        T(ox + _s(340), oy + _s(4), fecha, COLOR_TEXT_LIGHT, fnt)
        return oy + rh + _s(2)

    fnt_title = _font(22, bold=True)
    T(ROL_MARGIN, y, f"\U0001f4cb  ROL DE JUEGOS", COLOR_GREEN, fnt_title)
    y += _th(fnt_title) + 2
    fnt_sub = _font(12)
    T(ROL_MARGIN, y, f"\u2500\u2500 {temporada_nombre.upper()} \u2500\u2500", COLOR_TEXT_LIGHT, fnt_sub)
    y += _th(fnt_sub) + 16

    for j_idx, j in enumerate(jornadas):
        fnt_sec = _font(13, bold=True)
        T(ROL_MARGIN, y, f"\u26bd  {j['nombre']}", COLOR_GREEN, fnt_sec)
        y += _th(fnt_sec) + 5

        partidos = j["partidos"]
        n = len(partidos)
        half = (n + 1) // 2
        col1 = partidos[:half]
        col2 = partidos[half:]

        # assign idx for alternating bg per column
        for i, p in enumerate(col1):
            p["idx"] = i
        for i, p in enumerate(col2):
            p["idx"] = i

        left_x = ROL_MARGIN
        right_x = ROL_MARGIN + col_w + gap
        max_rows = max(len(col1), len(col2))
        col1_y = col2_y = y
        for i in range(max_rows):
            if i < len(col1):
                col1_y = draw_match(left_x, col1_y, col1[i], col_w)
            if i < len(col2):
                col2_y = draw_match(right_x, col2_y, col2[i], col_w)

        y = max(col1_y, col2_y)
        descansan = j.get("descansan") or []
        if descansan:
            fnt_desc = _font(9)
            T(ROL_MARGIN, y + 4, "Descansan: " + ", ".join(descansan), COLOR_TEXT_LIGHT, fnt_desc)
            y += _th(fnt_desc) + 10
        else:
            y += 6

    y += 4
    fnt_f = _font(11)
    T(ROL_MARGIN, y, f"\U0001f550  Generado el {ahora_str}", COLOR_TEXT_LIGHT, fnt_f)
    y += _th(fnt_f) + 20

    img = Image.new("RGB", (ROL_WIDTH, y), COLOR_BG)
    draw = ImageDraw.Draw(img)
    for op in ops:
        if op[0] == "text":
            _, x, y, txt, fill, font = op
            draw.text((x, y), txt, fill=fill, font=font)
        elif op[0] == "rect":
            _, x1, y1, x2, y2, fill, r = op
            draw.rounded_rectangle((x1, y1, x2, y2), radius=r, fill=fill)
        elif op[0] == "line":
            _, x1, y1, x2, y2, fill, w = op
            draw.line((x1, y1, x2, y2), fill=fill, width=w)

    # Resize to fit Facebook feed (max portrait height)
    max_h = 1600
    if y > max_h:
        ratio = max_h / y
        new_w = int(ROL_WIDTH * ratio)
        img = img.resize((new_w, max_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, compress_level=9)
    buf.seek(0)
    return buf


def _cargar_logo(filefield):
    """Devuelve una imagen PIL RGBA del logo (archivo local o Cloudinary) o None."""
    if not filefield:
        return None
    try:
        path = filefield.path
        if os.path.exists(path):
            return Image.open(path).convert("RGBA")
    except NotImplementedError:
        pass
    try:
        import requests
        r = requests.get(filefield.url, timeout=10)
        if r.status_code == 200 and r.content:
            return Image.open(io.BytesIO(r.content)).convert("RGBA")
    except Exception:
        pass
    return None


def generar_imagen_rol_dashboard(secciones, ahora_str):
    """Imagen 'Próximos partidos' estilo dashboard con todas las categorías."""
    W = 900
    M = 20
    ops = []
    y = 20

    def T(x, y, txt, fill, font):
        ops.append(("text", x, y, txt, fill, font))

    def R(x1, y1, x2, y2, fill, r=4):
        ops.append(("rect", x1, y1, x2, y2, fill, r))

    sec0 = secciones[0] if secciones else {}
    nombre_liga = (sec0.get("nombre_liga") or "").upper() or "MI LIGA"
    logo_liga = sec0.get("logo_liga")

    fnt_title = _font(24, bold=True)
    tx = M + 8
    if logo_liga:
        ll = logo_liga.copy()
        ll.thumbnail((52, 52), Image.LANCZOS)
        ops.append(("image", M + 8, y + 4, ll))
        tx = M + 70
    T(tx, y + 2, "PRÓXIMOS PARTIDOS", COLOR_GREEN, fnt_title)
    y += _th(fnt_title) + 4
    fnt_sub = _font(13, bold=True)
    T(tx, y, f"{nombre_liga}   ·   Todas las categorías   ·   Jornadas en curso", COLOR_TEXT, fnt_sub)
    # Separar la cabecera del primer bloque de categorías.
    y += _th(fnt_sub) + 30

    if not secciones:
        fnt_none = _font(14)
        T(M, y, "No hay partidos programados.", COLOR_TEXT_LIGHT, fnt_none)
        y += _th(fnt_none) + 10

    fnt_sec = _font(15, bold=True)
    fnt_eq = _font(12, bold=True)
    fnt_fecha = _font(11, bold=True)
    fnt_lugar = _font(9, bold=True)
    fnt_vs = _font(14, bold=True)
    row_h = 68

    for sec in secciones:
        cab = f"{sec['categoria'].upper()}   ·   {sec['temporada'].upper()}   ·   {sec['jornada']}"
        R(M, y, W - M, y + 30, COLOR_GREEN, 6)
        T(M + 12, y + 6, cab, "#ffffff", fnt_sec)
        y += 30 + 8

        for idx, p in enumerate(sec["partidos"]):
            bg = COLOR_ROW_ALT if idx % 2 == 1 else COLOR_WHITE
            R(M, y, W - M, y + row_h, bg)
            # Equipo local
            if p.get("logo_local"):
                logo = p["logo_local"].copy()
                logo.thumbnail((46, 46), Image.LANCZOS)
                ops.append(("image", M + 10, y + (row_h - logo.size[1]) // 2, logo))
                name_x = M + 64
            else:
                R(M + 10, y + 19, M + 53, y + 49, COLOR_EQUIPO_SIN_LOGO, 6)
                T(M + 21, y + 26,      "?", "#ffffff", fnt_eq)
                name_x = M + 64
            tw_local = _tw(p["local"][:24], fnt_eq)
            T(name_x, y + 27, p["local"][:24], COLOR_TEXT, fnt_eq)
            if p.get("default_win") == "local":
                ddb = _tw("DFT", fnt_eq) + 8
                R(name_x + tw_local + 8, y + 19, name_x + tw_local + 8 + ddb, y + 35, "#c2410c", 6)
                T(name_x + tw_local + 12, y + 22, "DFT", "#ffffff", fnt_eq)
            # Centro
            cx = W // 2
            fecha_txt = p["fecha"]
            fw = _tw(fecha_txt, fnt_fecha)
            R(cx - fw // 2 - 9, y + 3, cx + fw // 2 + 9, y + 21, COLOR_GREEN_LIGHT, 9)
            T(cx - fw // 2, y + 6, fecha_txt, COLOR_GREEN, fnt_fecha)
            T(cx - _tw("VS", fnt_vs) // 2, y + 22, "VS", COLOR_GREEN, fnt_vs)
            if p["campo"]:
                lugar_txt = f"Lugar: {p['campo'][:26]}"
                lw = _tw(lugar_txt, fnt_lugar)
                R(cx - lw // 2 - 9, y + 42, cx + lw // 2 + 9, y + 60, "#eaf1e6", 9)
                T(cx - lw // 2, y + 45, lugar_txt, COLOR_TEXT, fnt_lugar)
            # Equipo visitante
            if p.get("logo_visitante"):
                logo = p["logo_visitante"].copy()
                logo.thumbnail((46, 46), Image.LANCZOS)
                ops.append(("image", W - M - 10 - logo.size[0], y + (row_h - logo.size[1]) // 2, logo))
                name_x = W - M - 64 - _tw(p["visitante"][:24], fnt_eq)
            else:
                R(W - M - 53, y + 19, W - M - 10, y + 49, COLOR_EQUIPO_SIN_LOGO, 6)
                T(W - M - 30 - _tw("?", fnt_eq) // 2, y + 26, "?", "#ffffff", fnt_eq)
                name_x = W - M - 64 - _tw(p["visitante"][:24], fnt_eq)
            tw_vis = _tw(p["visitante"][:24], fnt_eq)
            T(name_x, y + 27, p["visitante"][:24], COLOR_TEXT, fnt_eq)
            if p.get("default_win") == "visitante":
                ddb = _tw("DFT", fnt_eq) + 8
                R(W - M - 10 - tw_vis - 8 - ddb, y + 19, W - M - 10 - tw_vis - 8, y + 35, "#c2410c", 6)
                T(W - M - 10 - tw_vis - 8 - ddb + 4, y + 22, "DFT", "#ffffff", fnt_eq)
            y += row_h + 2

        descansan = sec.get("descansan") or []
        if descansan:
            fnt_d = _font(10)
            fnt_estado = _font(10, bold=True)
            fnt_chip = _font(9, bold=True)
            T(M, y + 2, "Descansan:", COLOR_TEXT_LIGHT, fnt_d)
            xs = M + _tw("Descansan:", fnt_d) + 12
            chip_y = y
            for eq in descansan:
                nombre = eq[:20]
                tw = _tw(nombre, fnt_chip) + 16
                if xs + tw > W - M:
                    xs = M
                    chip_y += 18
                R(xs, chip_y, xs + tw, chip_y + 18, "#6c757d", 9)
                T(xs + 8, chip_y + 4, nombre, "#ffffff", fnt_chip)
                xs += tw + 6
            y = chip_y + 18 + 6
        else:
            y += 8

    y += 6
    fnt_f = _font(11)
    T(M, y, f"\U0001f550  Generado el {ahora_str}", COLOR_TEXT_LIGHT, fnt_f)
    y += _th(fnt_f) + 20

    # Leyenda de victorias por default (walkover) si alguna sección tiene DFT.
    if any(p.get("default_win") for sec in secciones for p in sec.get("partidos", [])):
        fnt_ley = _font(10)
        T(M, y, "DFT = victoria por default (walkover)", "#c2410c", fnt_ley)
        y += _th(fnt_ley) + 20

    img = Image.new("RGB", (W, y), COLOR_BG)
    draw = ImageDraw.Draw(img)
    for op in ops:
        if op[0] == "text":
            _, x, yt, txt, fill, font = op
            draw.text((x, yt), txt, fill=fill, font=font)
        elif op[0] == "rect":
            _, x1, y1, x2, y2, fill, r = op
            draw.rounded_rectangle((x1, y1, x2, y2), radius=r, fill=fill)
        elif op[0] == "line":
            _, x1, y1, x2, y2, fill, w = op
            draw.line((x1, y1, x2, y2), fill=fill, width=w)
        elif op[0] == "image":
            _, x, yt, logo_img = op
            img.paste(logo_img, (x, yt), logo_img)

    max_h = 2400
    if y > max_h:
        ratio = max_h / y
        new_w = int(W * ratio)
        img = img.resize((new_w, max_h), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, compress_level=9)
    buf.seek(0)
    return buf


def generar_imagen_campeon(temporada_nombre, equipo_nombre, logo_path, ahora_str, categoria_nombre=""):
    """Imagen de celebracion del campeon con escudo y estilo dorado."""
    ops = []
    y = 20

    def T(x, y, txt, fill, font):
        ops.append(("text", x, y, txt, fill, font))

    def R(x1, y1, x2, y2, fill, r=4):
        ops.append(("rect", x1, y1, x2, y2, fill, r))

    GOLD = "#FFD700"

    R(MARGIN, y, WIDTH - MARGIN, 300, "#1a1a2e", 12)

    # Trofeo con fuente emoji
    fnt_emoji_big = _font_emoji(64)
    cx = WIDTH // 2 - _tw("\U0001f3c6", fnt_emoji_big) // 2
    T(cx, y + 30, "\U0001f3c6", GOLD, fnt_emoji_big)
    y += 100

    # "CAMPEON" con coronas a los lados usando fuente emoji
    fnt_campeon = _font(36, bold=True)
    fnt_crown = _font_emoji(36)
    crown_txt = "\U0001f451"
    label = "CAMPEON"
    crown_w = _tw(crown_txt, fnt_crown)
    label_w = _tw(label, fnt_campeon)
    gap = 14
    total_w = crown_w + gap + label_w + gap + crown_w
    start_x = WIDTH // 2 - total_w // 2
    T(start_x, y, crown_txt, GOLD, fnt_crown)
    T(start_x + crown_w + gap, y, label, GOLD, fnt_campeon)
    T(start_x + crown_w + gap + label_w + gap, y, crown_txt, GOLD, fnt_crown)
    y += _th(fnt_campeon) + 10

    fnt_equipo = _font(32, bold=True)
    cx = WIDTH // 2 - _tw(equipo_nombre.upper(), fnt_equipo) // 2
    T(cx, y, equipo_nombre.upper(), COLOR_WHITE, fnt_equipo)
    y += _th(fnt_equipo) + 6

    fnt_temp = _font(18)
    cx = WIDTH // 2 - _tw(temporada_nombre, fnt_temp) // 2
    T(cx, y, temporada_nombre, COLOR_TEXT_LIGHT, fnt_temp)
    y += _th(fnt_temp) + 2
    if categoria_nombre:
        fnt_cat = _font(14)
        cx = WIDTH // 2 - _tw(categoria_nombre, fnt_cat) // 2
        T(cx, y, categoria_nombre, COLOR_TEXT_LIGHT, fnt_cat)
        y += _th(fnt_cat) + 16
    else:
        y += 16

    # Mensaje de felicitacion
    fnt_felicidades = _font(16)
    feliz = f"¡Felicidades {equipo_nombre}!"
    cx = WIDTH // 2 - _tw(feliz, fnt_felicidades) // 2
    T(cx, y, feliz, GOLD, fnt_felicidades)
    y += _th(fnt_felicidades) + 4
    fnt_sub = _font(13)
    sub = "¡Campeones!"
    cx = WIDTH // 2 - _tw(sub, fnt_sub) // 2
    T(cx, y, sub, GOLD, fnt_sub)
    y += 20

    y = max(y, 220)
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            logo.thumbnail((120, 120), Image.LANCZOS)
            logo_w, logo_h = logo.size
            logo_x = (WIDTH - logo_w) // 2
            ops.append(("image", logo_x, y, logo))
            y += logo_h + 20
        except Exception:
            pass
    else:
        R(WIDTH // 2 - 60, y, WIDTH // 2 + 60, y + 120, "#333355", 60)
        fnt_q = _font(48, bold=True)
        cx = WIDTH // 2 - _tw("?", fnt_q) // 2
        T(cx, y + 20, "?", COLOR_WHITE, fnt_q)
        y += 140

    y = max(y, 320)
    y += 10
    fnt_f = _font(11)
    T(MARGIN, y, f"\U0001f550  {ahora_str}", COLOR_TEXT_LIGHT, fnt_f)
    y += _th(fnt_f) + 20

    return _render_and_save(ops, y, "#0d0d1a")


def generar_imagen_castigados(temporada_nombre, jornada_numero, castigados, ahora_str):
    ops = []
    y = 20

    def T(x, y, txt, fill, font):
        ops.append(("text", x, y, txt, fill, font))

    def R(x1, y1, x2, y2, fill, r=4):
        ops.append(("rect", x1, y1, x2, y2, fill, r))

    fnt_title = _font(22, bold=True)
    T(MARGIN, y, "\U0001f7e5  CASTIGADOS", COLOR_GREEN, fnt_title)
    y += _th(fnt_title) + 2
    fnt_sub = _font(12)
    T(MARGIN, y, f"\u2500\u2500 {temporada_nombre.upper()} - Jornada {jornada_numero} \u2500\u2500", COLOR_TEXT_LIGHT, fnt_sub)
    y += _th(fnt_sub) + 18

    if castigados:
        fnt_c = _font(14)
        for idx, c in enumerate(castigados):
            bg = COLOR_ROW_ALT if idx % 2 == 1 else COLOR_WHITE
            txt = f"\u2022  {c['jugador']} ({c['equipo']})  \u2014  {('Exp. Jor.' + str(c['jornada_expulsion'])) if c['jornada_expulsion'] else 'Susp. manual'}  |  Restan {c['restantes']} jor."
            rh = 28
            R(MARGIN, y, WIDTH - MARGIN, y + rh, bg)
            T(MARGIN + 8, y + 5, txt, COLOR_TEXT, fnt_c)
            y += rh + 3
    else:
        fnt_none = _font(14)
        T(MARGIN, y, "No hay jugadores castigados.", COLOR_TEXT_LIGHT, fnt_none)
        y += _th(fnt_none) + 10

    y += 8
    fnt_f = _font(11)
    T(MARGIN, y, f"\U0001f550  Generado el {ahora_str}", COLOR_TEXT_LIGHT, fnt_f)
    y += _th(fnt_f) + 20

    return _render_and_save(ops, y, COLOR_BG)


def _render_and_save(ops, height, bg_color):
    img = Image.new("RGB", (WIDTH, height), bg_color)
    draw = ImageDraw.Draw(img)
    for op in ops:
        if op[0] == "text":
            _, x, y, txt, fill, font = op
            draw.text((x, y), txt, fill=fill, font=font)
        elif op[0] == "rect":
            _, x1, y1, x2, y2, fill, r = op
            draw.rounded_rectangle((x1, y1, x2, y2), radius=r, fill=fill)
        elif op[0] == "line":
            _, x1, y1, x2, y2, fill, w = op
            draw.line((x1, y1, x2, y2), fill=fill, width=w)
        elif op[0] == "image":
            _, x, y, logo_img = op
            img.paste(logo_img, (x, y), logo_img)

    # Resize if too tall for Facebook feed
    max_h = 2400
    if height > max_h:
        ratio = max_h / height
        new_w = int(WIDTH * ratio)
        img = img.resize((new_w, max_h), Image.LANCZOS)
        logger.info("Imagen redimensionada a %dx%d para Facebook", new_w, max_h)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True, compress_level=9)
    buf.seek(0)
    return buf
