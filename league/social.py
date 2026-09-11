import json
import logging

import requests
from django.contrib import messages

from .models import ConfiguracionLiga

logger = logging.getLogger(__name__)

FACEBOOK_GRAPH_URL = "https://graph.facebook.com/v25.0"

FALLBACK_SITE_URL = "https://www.juventinorosasliga.com"


def _site_url(request=None):
    """Devuelve la URL pública del sitio (dominio clicable) para el post."""
    # En producción siempre usamos el dominio canonical.
    return "https://www.juventinorosasliga.com"


def _get_config():
    cfg = ConfiguracionLiga.obtener()
    if not cfg.facebook_page_id or not cfg.facebook_access_token:
        return None, "Facebook no configurado. Ve a Configuración → Redes Sociales e ingresa el ID de página y Access Token."
    return cfg, None


def _get_page_token(page_id, sys_token, request=None):
    url = f"{FACEBOOK_GRAPH_URL}/{page_id}?fields=access_token&access_token={sys_token}"
    resp = requests.get(url, timeout=15)
    data = resp.json()
    if "error" in data:
        err = data["error"].get("message", str(data))
        logger.error("Error al obtener page token: %s", err)
        if request:
            messages.error(request, f"Error al obtener Page Token: {err}")
        return None
    return data.get("access_token")


def publicar_en_facebook(mensaje, request=None):
    cfg, error = _get_config()
    if error:
        if request:
            messages.warning(request, error)
        return False

    page_token = _get_page_token(cfg.facebook_page_id, cfg.facebook_access_token, request)
    if not page_token:
        return False

    url = f"{FACEBOOK_GRAPH_URL}/{cfg.facebook_page_id}/feed"
    resp = requests.post(url, data={"message": mensaje, "access_token": page_token}, timeout=15)

    if resp.status_code != 200:
        err = resp.json().get("error", {}).get("message", str(resp.text))
        logger.error("Error al publicar en Facebook: %s", err)
        if request:
            messages.error(request, f"Error al publicar en Facebook: {err}")
        return False

    post_id = resp.json().get("id", "")
    logger.info("Publicado en Facebook exitosamente: %s", post_id)
    if request:
        messages.success(request, f"Publicado en Facebook exitosamente (ID: {post_id})")
    return True


def publicar_post_prueba(page_id, sys_token, request=None):
    """Publica un post de prueba REAL en la página de Facebook con la config que está en pantalla."""
    if not page_id or not sys_token:
        return False, "Facebook no configurado. Ingresa el ID de página y el Access Token."
    page_token = _get_page_token(page_id, sys_token, request)
    if not page_token:
        return False, "No se pudo obtener el Page Token."
    url = f"{FACEBOOK_GRAPH_URL}/{page_id}/feed"
    mensaje = ("Post de prueba de AdminFut. Si ves este mensaje en tu página, "
               "la publicación en Facebook funciona correctamente.")
    resp = requests.post(url, data={"message": mensaje, "access_token": page_token}, timeout=15)
    if resp.status_code != 200:
        err = resp.json().get("error", {}).get("message", str(resp.text))
        logger.error("Error en post de prueba de Facebook: %s", err)
        return False, f"Error al publicar: {err}"
    post_id = resp.json().get("id", "")
    logger.info("Post de prueba publicado en Facebook: %s", post_id)
    return True, f"Post de prueba publicado (ID: {post_id})"


def publicar_varias_imagenes_en_facebook(imagenes_captions, request=None, mensaje=""):
    """Publica multiples imagenes en un solo post de Facebook.

    Args:
        imagenes_captions: lista de tuplas (imagen_bytes, caption_segment)
        request: opcional, para mensajes
        mensaje: texto principal del post
    """
    cfg, error = _get_config()
    if error:
        if request:
            messages.warning(request, error)
        return False

    page_token = _get_page_token(cfg.facebook_page_id, cfg.facebook_access_token, request)
    if not page_token:
        return False

    media_ids = []
    for img_bytes, seg_caption in imagenes_captions:
        url = f"{FACEBOOK_GRAPH_URL}/{cfg.facebook_page_id}/photos"
        files = {"source": ("image.png", img_bytes, "image/png")}
        data = {"published": "false", "access_token": page_token}
        resp = requests.post(url, files=files, data=data, timeout=30)
        if resp.status_code != 200:
            err = resp.json().get("error", {}).get("message", str(resp.text))
            logger.error("Error al subir imagen a Facebook: %s", err)
            if request:
                messages.error(request, f"Error al subir imagen: {err}")
            return False
        media_ids.append(resp.json().get("id"))
        if seg_caption:
            full_caption_parts.append(seg_caption)

    # Create post with all images
    post_url = f"{FACEBOOK_GRAPH_URL}/{cfg.facebook_page_id}/feed"
    attached_media = [{"media_fbid": mid} for mid in media_ids]
    post_data = {
        "attached_media": json.dumps(attached_media),
        "message": mensaje,
        "access_token": page_token,
    }
    resp = requests.post(post_url, data=post_data, timeout=30)
    if resp.status_code != 200:
        err = resp.json().get("error", {}).get("message", str(resp.text))
        logger.error("Error al crear post multiple en Facebook: %s", err)
        if request:
            messages.error(request, f"Error al crear post multiple: {err}")
        return False

    post_id = resp.json().get("id", "")
    logger.info("Post multiple publicado en Facebook exitosamente: %s", post_id)
    if request:
        messages.success(request, f"Post multiple publicado en Facebook (ID: {post_id})")
    return True


def publicar_imagen_en_facebook(imagen_bytes, caption, request=None):
    cfg, error = _get_config()
    if error:
        if request:
            messages.warning(request, error)
        return False

    page_token = _get_page_token(cfg.facebook_page_id, cfg.facebook_access_token, request)
    if not page_token:
        return False

    site = _site_url(request)
    caption_text = (caption or "").rstrip()
    caption_text = f"{caption_text}\n\n\U0001f310 {site}" if caption_text else f"\U0001f310 {site}"

    url = f"{FACEBOOK_GRAPH_URL}/{cfg.facebook_page_id}/photos"
    files = {"source": ("resumen.png", imagen_bytes, "image/png")}
    data = {"message": caption_text, "link": site, "access_token": page_token}
    resp = requests.post(url, files=files, data=data, timeout=30)

    if resp.status_code != 200:
        err = resp.json().get("error", {}).get("message", str(resp.text))
        logger.error("Error al publicar imagen en Facebook: %s", err)
        if request:
            messages.error(request, f"Error al publicar imagen en Facebook: {err}")
        return False

    post_id = resp.json().get("id", "")
    logger.info("Imagen publicada en Facebook exitosamente: %s", post_id)
    if request:
        messages.success(request, f"Imagen publicada en Facebook exitosamente (ID: {post_id})")
    return True
