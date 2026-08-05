"""
Almacenamiento de media con fallback entre nubes de Cloudinary.

La nube principal se toma de la configuración de la liga (BD). Varios archivos
históricos (fotos de jugadores, logos de equipos, fondos de credenciales)
quedaron en una nube anterior (la de MEDIA_URL). Este storage genera la URL y,
si el archivo no existe en la nube principal, devuelve la URL de la nube
alternativa. El resultado se cachea en memoria para no repetir peticiones HEAD.
"""
import threading
import urllib.request

from cloudinary_storage.storage import MediaCloudinaryStorage
from django.conf import settings

_cache = {}
_lock = threading.Lock()

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; AdminFut)"}


def _existe(url, timeout=6):
    try:
        req = urllib.request.Request(url, method="HEAD", headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


class MediaCloudinaryStorageConFallback(MediaCloudinaryStorage):
    def url(self, name):
        if not name:
            return ""
        base = super().url(name)
        if not base.startswith("http"):
            return base
        with _lock:
            destino = _cache.get(name)
        if destino == "alt":
            return self._url_alt(name)
        if destino == "base":
            return base
        if _existe(base):
            with _lock:
                _cache[name] = "base"
            return base
        alt = self._url_alt(name)
        if alt and alt != base and _existe(alt):
            with _lock:
                _cache[name] = "alt"
            return alt
        with _lock:
            _cache[name] = "base"
        return base

    def _url_alt(self, name):
        media_url = getattr(settings, "MEDIA_URL", "") or ""
        if media_url.startswith("http"):
            return media_url.rstrip("/") + "/" + name.lstrip("/")
        return super().url(name)
