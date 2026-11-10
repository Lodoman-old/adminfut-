"""Registro y freno de intentos de login fallidos.

Cada contraseña incorrecta suma un punto por IP. Al llegar a ``LIMITE`` en
15 minutos se banea la IP 30 minutos. Se guarda una sola fila por ventana en
``SolicitudBloqueada`` para que el intento se vea en /push-logs/ (Tráfico)
sin llenar la base con cada tecla.
"""
from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver

LIMITE = 8
VENTANA = 900  # 15 minutos
CASTIGO = 1800  # 30 minutos


def _ip(request):
    meta = request.META
    valor = meta.get("HTTP_X_FORWARDED_FOR") or meta.get("REMOTE_ADDR") or ""
    return valor.split(",")[0].strip()


@receiver(user_login_failed)
def registrar_login_fallido(sender, credentials, request=None, **kwargs):
    if request is None:
        return
    ip = _ip(request)
    if not ip:
        return

    from django.core.cache import cache

    clave = f"login_fail:{ip}"
    try:
        n = cache.incr(clave)
    except ValueError:
        cache.add(clave, 1, VENTANA)
        n = 1

    # Una fila al primer fallo de la ventana y otra cuando se dispara el ban.
    if n in (1, LIMITE):
        try:
            from .models import SolicitudBloqueada

            SolicitudBloqueada.objects.create(
                ip=ip,
                user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:300],
                path=request.path[:300],
                metodo=request.method,
                motivo="login",
            )
        except Exception:
            pass

    if n >= LIMITE:
        cache.set(f"ban:{ip}", 1, CASTIGO)
