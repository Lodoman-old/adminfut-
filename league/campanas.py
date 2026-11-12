"""Lógica de campañas de publicidad programadas."""
import datetime

from django.conf import settings
from django.utils import timezone


def url_absoluta(url):
    """Convierte la URL de una imagen en absoluta y HTTPS."""
    if not url:
        return None
    if url.startswith("http://"):
        return "https://" + url[7:]
    if url.startswith("https://"):
        return url
    return settings.SITE_URL.rstrip("/") + url


def imagenes_anuncio(anuncio):
    """(imagen grande, icono cuadrado) del anuncio."""
    grande = anuncio.imagen or anuncio.imagen_cuadrada
    cuadrada = anuncio.imagen_cuadrada or anuncio.imagen
    return (
        url_absoluta(grande.url) if grande else None,
        url_absoluta(cuadrada.url) if cuadrada else None,
    )


def contenido(campana):
    """Título y texto por defecto de la campaña (liga + patrocinador)."""
    from .models import ConfiguracionLiga

    anuncio = campana.anuncio
    cfg = ConfiguracionLiga.obtener()
    liga = ((cfg.nombre_liga if cfg else "") or "La liga").strip()
    titulo = (campana.titulo or "").strip() or liga
    cuerpo = (campana.cuerpo or "").strip() or (
        f"La {liga} es patrocinada por {anuncio.titulo}.\n"
        "Toca para ver la promoción."
    )
    return titulo, cuerpo


def audiencia_qs(campana):
    """Dispositivos activos según la audiencia de la campaña."""
    from .models import DeviceToken

    qs = DeviceToken.objects.filter(activo=True)
    if campana.audiencia == "android":
        qs = qs.filter(plataforma="android", webpush_endpoint="")
    elif campana.audiencia == "pwa":
        qs = qs.exclude(webpush_endpoint="")
    return qs.distinct()


def enviar_campana(campana):
    """Envía la notificación de una campaña ahora (si el anuncio está vigente)."""
    from .push import _enviar_push_mixto

    anuncio = campana.anuncio
    if not anuncio.activo or not anuncio.vigente():
        return {"success": 0, "failure": 0, "omitida": "anuncio inactivo o vencido"}

    qs = audiencia_qs(campana)
    if not qs.exists():
        return {"success": 0, "failure": 0, "omitida": "sin dispositivos"}

    titulo, cuerpo = contenido(campana)
    imagen, icono = imagenes_anuncio(anuncio)
    data = {
        "type": "publicidad",
        "ad_id": str(anuncio.id),
        "url": f"/publicidad/{anuncio.id}/?origen=app",
    }
    return _enviar_push_mixto(
        qs, titulo, cuerpo, data, "PUBLICIDAD",
        imagen=imagen, icono=icono,
        extra=f"Campaña={campana.id} Anuncio={anuncio.id}",
    )


def proxima_fecha(campana, base=None):
    """Siguiente envío: base + cada_dias a la hora configurada."""
    tz = timezone.get_current_timezone()
    base = base or timezone.now()
    base_local = timezone.localtime(base, tz)
    dias = max(int(campana.cada_dias or 1), 1)
    objetivo = timezone.make_aware(
        datetime.datetime.combine(
            base_local.date() + datetime.timedelta(days=dias),
            campana.hora,
        ),
        tz,
    )
    ahora = timezone.now()
    while objetivo <= ahora:
        objetivo += datetime.timedelta(days=dias)
    return objetivo


def primer_envio(campana):
    """Primer envío: ahora si el anuncio ya empezó; si no, al inicio a la hora."""
    anuncio = campana.anuncio
    hoy = timezone.localdate()
    if anuncio.fecha_inicio and anuncio.fecha_inicio > hoy:
        tz = timezone.get_current_timezone()
        return timezone.make_aware(
            datetime.datetime.combine(anuncio.fecha_inicio, campana.hora), tz
        )
    return timezone.now()
