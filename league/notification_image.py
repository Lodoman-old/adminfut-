"""Imágenes de marca para las notificaciones push.

Genera, a partir del logo configurado de la liga, tres piezas cacheadas y
servidas públicamente:

- ``banner.png``: 1024x512 (2:1), imagen grande de la notificación (Android
  la muestra al expandir; el Web Push la usa como ``image``).
- ``icono.png``: 512x512, icono de la notificación Web Push.
- ``badge.png``: 96x96 monocromo, insignia del Web Push.

Se dibujan sobre el verde de la liga para que el logo transparente se vea
limpio y con márgenes adecuados (nunca recortado).
"""
import io
import textwrap
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageColor, ImageDraw

VERDE_ARRIBA = (255, 255, 255)
VERDE_ABAJO = (231, 242, 232)
ORO = (45, 107, 46)


def _logo_imagen():
    """Devuelve el logo de la liga como RGBA, o None si no hay."""
    from .models import ConfiguracionLiga

    try:
        config = ConfiguracionLiga.obtener()
        if config and config.logo:
            archivo = config.logo
            archivo.open("rb")
            try:
                img = Image.open(archivo)
                img.load()
            finally:
                archivo.close()
            return img.convert("RGBA")
    except Exception:
        pass

    for nombre in ("LogoSinFondoLiga.png", "LogoLiga.png"):
        ruta = Path(settings.BASE_DIR) / nombre
        if ruta.exists():
            try:
                return Image.open(ruta).convert("RGBA")
            except Exception:
                continue
    return None


def _fondo(w, h):
    """Degradado vertical verde con una línea dorada inferior."""
    canvas = Image.new("RGBA", (w, h))
    draw = ImageDraw.Draw(canvas)
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(a + (b - a) * t) for a, b in zip(VERDE_ARRIBA, VERDE_ABAJO))
        draw.line([(0, y), (w, y)], fill=color + (255,))
    alto_linea = max(4, h // 64)
    draw.rectangle([0, h - alto_linea, w, h], fill=ORO + (255,))
    return canvas


def _pegar_centrado(canvas, logo, max_w, max_h, cy=None):
    pieza = logo.copy()
    pieza.thumbnail((max_w, max_h), Image.LANCZOS)
    x = (canvas.width - pieza.width) // 2
    y = (canvas.height - pieza.height) // 2 if cy is None else cy - pieza.height // 2
    canvas.alpha_composite(pieza, (x, max(0, y)))


def _png(canvas):
    buf = io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def generar_banner():
    """Imagen grande 2:1 para la notificación."""
    logo = _logo_imagen()
    if logo is None:
        return None
    canvas = _fondo(1024, 512)
    _pegar_centrado(canvas, logo, int(1024 * 0.82), int(512 * 0.76), 512 // 2)
    return _png(canvas)


def generar_icono():
    """Icono cuadrado para Web Push / PWA."""
    logo = _logo_imagen()
    if logo is None:
        return None
    canvas = _fondo(512, 512)
    _pegar_centrado(canvas, logo, int(512 * 0.86), int(512 * 0.86))
    return _png(canvas)


def generar_badge():
    """Insignia monocroma (blanca) con la silueta del logo."""
    logo = _logo_imagen()
    if logo is None:
        return None
    alfa = logo.getchannel("A")
    bbox = alfa.getbbox()
    if bbox:
        logo = logo.crop(bbox)
        alfa = logo.getchannel("A")
    silueta = Image.new("RGBA", logo.size, (255, 255, 255, 0))
    silueta.putalpha(alfa)
    canvas = Image.new("RGBA", (96, 96), (0, 0, 0, 0))
    _pegar_centrado(canvas, silueta, 84, 84)
    return _png(canvas)


def generar(formato):
    if formato == "banner":
        return generar_banner()
    if formato == "icono":
        return generar_icono()
    if formato == "badge":
        return generar_badge()
    return None


def _imagen_anuncio(anuncio):
    """Imagen subida del anuncio (franja/banner; si no hay, la cuadrada)."""
    campo = anuncio.imagen or anuncio.imagen_cuadrada
    if not campo:
        return None
    try:
        campo.open("rb")
        try:
            img = Image.open(campo)
            img.load()
        finally:
            campo.close()
        return img.convert("RGBA")
    except Exception:
        return None


def _fondo_anuncio(anuncio, w, h):
    color = (anuncio.color_fondo or "").strip()
    if color:
        try:
            rgb = ImageColor.getrgb(color)
            return Image.new("RGBA", (w, h), rgb + (255,))
        except ValueError:
            pass
    return _fondo(w, h)


def _texto_anuncio(canvas, anuncio):
    """Tarjeta de respaldo cuando el anuncio no tiene imagen."""
    from .social_image import _font

    fill = (255, 255, 255)
    color = (anuncio.color_fondo or "").strip()
    if color:
        try:
            r, g, b = ImageColor.getrgb(color)[:3]
            if 0.299 * r + 0.587 * g + 0.114 * b > 140:
                fill = (25, 40, 25)
        except ValueError:
            pass
    draw = ImageDraw.Draw(canvas)
    titulo = (anuncio.titulo or "").strip()
    while titulo and draw.textlength(titulo, font=_font(64, bold=True)) > canvas.width * 0.82:
        titulo = titulo[:-1]
    draw.text(
        (canvas.width // 2, canvas.height // 2 - 10),
        titulo, font=_font(64, bold=True), fill=fill, anchor="mm",
    )
    if anuncio.descripcion:
        lineas = textwrap.wrap(anuncio.descripcion, width=46)[:2]
        draw.multiline_text(
            (canvas.width // 2, canvas.height // 2 + 62),
            "\n".join(lineas), font=_font(30), fill=fill,
            anchor="ma", align="center", spacing=8,
        )


def _jpeg(canvas, calidad=88):
    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="JPEG", quality=calidad, optimize=True)
    return buf.getvalue()


def generar_anuncio(anuncio, formato="banner"):
    """Imagen 2:1 (o icono cuadrado) optimizada para la notificación del anuncio."""
    if formato == "banner":
        w, h = 1024, 512
    elif formato == "icono":
        w, h = 512, 512
    else:
        return None

    canvas = _fondo_anuncio(anuncio, w, h)
    img = _imagen_anuncio(anuncio)
    if img is None:
        _texto_anuncio(canvas, anuncio)
        return _jpeg(canvas)

    margen = 0.06 if formato == "banner" else 0.08
    img.thumbnail((int(w * (1 - 2 * margen)), int(h * (1 - 2 * margen))), Image.LANCZOS)
    x = (w - img.width) // 2
    y = (h - img.height) // 2
    canvas.alpha_composite(img, (x, y))
    return _jpeg(canvas)
