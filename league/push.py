"""
Firebase Cloud Messaging integration for push notifications.
Uses Firebase Admin SDK. Requires FIREBASE_SERVICE_ACCOUNT_JSON env var
or secrets/firebase-service-account.json file.
"""
import base64
import json
import os
import logging
from datetime import datetime
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)

_app_initialized = False


MAX_LOGS = 500


def _add_log(entry):
    from .models import PushLog
    try:
        PushLog.objects.create(
            tipo=entry.get("tipo", ""),
            partido_id=entry.get("partido_id"),
            categoria=entry.get("categoria", ""),
            total_activos=entry.get("total_activos"),
            tokens_encontrados=entry.get("tokens_encontrados"),
            guests_incluidos=entry.get("guests_incluidos"),
            success=entry.get("success"),
            failure=entry.get("failure"),
            detalle=entry.get("detalle", ""),
            error=entry.get("error", ""),
        )
        total = PushLog.objects.count()
        if total > MAX_LOGS:
            ids = PushLog.objects.order_by("hora").values_list("pk", flat=True)[:total - MAX_LOGS]
            PushLog.objects.filter(pk__in=list(ids)).delete()
    except Exception as e:
        logger.warning("Error guardando PushLog: %s", e)


def get_push_logs(limit=200):
    from .models import PushLog
    try:
        return list(PushLog.objects.all()[:limit].values(
            "id", "hora", "tipo", "partido_id", "categoria",
            "total_activos", "tokens_encontrados", "guests_incluidos",
            "success", "failure", "detalle", "error"
        ))
    except Exception as e:
        logger.warning("Error leyendo PushLog: %s", e)
        return []


def _try_init():
    global _app_initialized
    if _app_initialized:
        return True

    import firebase_admin
    from firebase_admin import credentials

    if firebase_admin._apps:
        _app_initialized = True
        return True

    try:
        b64 = os.environ.get("FIREBASE_SERVICE_ACCOUNT_BASE64")
        if b64:
            cred = credentials.Certificate(json.loads(base64.b64decode(b64)))
        else:
            raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
            if raw:
                cred = credentials.Certificate(json.loads(raw))
            else:
                try:
                    from .models import ConfiguracionLiga
                    config = ConfiguracionLiga.obtener()
                    if config.firebase_service_account_json:
                        cred = credentials.Certificate(json.loads(config.firebase_service_account_json))
                    else:
                        raise Exception("No hay JSON en la config")
                except Exception:
                    file_path = os.path.join(settings.BASE_DIR, "secrets", "firebase-service-account.json")
                    if os.path.exists(file_path):
                        cred = credentials.Certificate(file_path)
                    else:
                        logger.warning("No Firebase credentials found (FIREBASE_SERVICE_ACCOUNT_BASE64 not set)")
                        return False

        firebase_admin.initialize_app(cred)
        _app_initialized = True
        return True
    except Exception as e:
        logger.error("Firebase init failed: %s", e)
        return False


def send_push_notification(tokens, title, body, data=None):
    if not tokens:
        _add_log({"tipo": "SEND", "detalle": "Sin tokens para enviar", "success": 0, "failure": 0})
        return
    if not _try_init():
        _add_log({"tipo": "SEND", "detalle": "Firebase no inicializado", "success": 0, "failure": 0})
        return

    from firebase_admin import messaging

    if isinstance(tokens, str):
        tokens = [tokens]

    message = messaging.MulticastMessage(
        notification=messaging.Notification(title=title, body=body),
        data=data or {},
        tokens=tokens,
    )

    try:
        response = messaging.send_each_for_multicast(message)
        codigos_invalidos = set(filter(None, [
            getattr(messaging.ErrorCode, "UNREGISTERED", None),
            getattr(messaging.ErrorCode, "INVALID_ARGUMENT", None),
        ]))
        invalid = []
        for resp, tok in zip(response.responses, tokens):
            if not resp.success:
                code = getattr(resp.exception, "code", None)
                es_invalido = (
                    code in codigos_invalidos
                    or (isinstance(code, str) and code.upper() in ("UNREGISTERED", "INVALID_ARGUMENT"))
                )
                if es_invalido:
                    invalid.append(tok)
        detalle = f"Push enviado: {response.success_count} ok, {response.failure_count} fail"
        if invalid:
            try:
                from .models import DeviceToken
                DeviceToken.objects.filter(token__in=invalid).update(activo=False)
                detalle += f", {len(invalid)} token(s) inválidos desactivados"
            except Exception:
                pass
        _add_log({"tipo": "SEND", "detalle": detalle, "success": response.success_count, "failure": response.failure_count})
        return {"success": response.success_count, "failure": response.failure_count}
    except Exception as e:
        logger.error("Push send failed: %s", e)
        _add_log({"tipo": "SEND", "detalle": f"Error al enviar push: {e}", "success": 0, "failure": 0, "error": str(e)})
        return None


def _enviar_webpush(devices, title, body, data=None):
    """Envía una notificación Web Push (PWA) a los DeviceToken dados.

    Cada device debe tener webpush_endpoint/p256dh/auth. Los endpoints que el
    push service marca como 404/410 (suscripción inválida) se desactivan.
    """
    from .models import DeviceToken

    if not devices:
        return {"success": 0, "failure": 0}

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush no instalado; omitiendo Web Push")
        return {"success": 0, "failure": len(devices)}

    private_key, _ = _vapid_keys()
    claims_sub = _vapid_claims_sub()
    payload = json.dumps({
        "title": title,
        "body": body,
        "data": data or {},
    }, ensure_ascii=False)

    def _enviar_uno(dt):
        if not dt.webpush_endpoint or not dt.webpush_p256dh or not dt.webpush_auth:
            return "fail"
        try:
            webpush(
                {
                    "endpoint": dt.webpush_endpoint,
                    "keys": {"p256dh": dt.webpush_p256dh, "auth": dt.webpush_auth},
                },
                payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": claims_sub},
                ttl=86400,
                timeout=15,
            )
            return "ok"
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            if status in (404, 410):
                return "gone"
            return "fail"
        except Exception as e:
            logger.warning("Web push falló: %s", e)
            return "fail"

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=8) as pool:
        resultados = list(pool.map(_enviar_uno, devices))

    ok = 0
    invalid = []
    for dt, estado in zip(devices, resultados):
        if estado == "ok":
            ok += 1
        elif estado == "gone":
            invalid.append(dt.pk)

    if invalid:
        try:
            DeviceToken.objects.filter(pk__in=invalid).update(activo=False)
        except Exception:
            pass

    return {"success": ok, "failure": len(devices) - ok}


def _generar_claves_vapid():
    """Genera el par de claves VAPID (formato py_vapid).

    Devuelve (clave_privada, clave_publica) en base64url:
      - privada: 32 bytes crudos de la clave ECDSA P-256
      - pública: 65 bytes del punto (applicationServerKey del navegador)
    """
    from cryptography.hazmat.primitives.asymmetric import ec
    priv = ec.generate_private_key(ec.SECP256R1())
    raw_priv = priv.private_numbers().private_value.to_bytes(32, "big")
    pub = priv.public_key().public_numbers()
    raw_pub = b"\x04" + pub.x.to_bytes(32, "big") + pub.y.to_bytes(32, "big")
    private_b64 = base64.urlsafe_b64encode(raw_priv).rstrip(b"=").decode()
    public_b64 = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode()
    return private_b64, public_b64


def _vapid_keys():
    """Devuelve (clave_privada, clave_publica) VAPID, generándolas si faltan."""
    from .models import ConfiguracionLiga
    config = ConfiguracionLiga.obtener()
    if config.webpush_vapid_private_key and config.webpush_vapid_public_key:
        return config.webpush_vapid_private_key, config.webpush_vapid_public_key
    private_b64, public_b64 = _generar_claves_vapid()
    config.webpush_vapid_private_key = private_b64
    config.webpush_vapid_public_key = public_b64
    config.save(update_fields=["webpush_vapid_private_key", "webpush_vapid_public_key"])
    return private_b64, public_b64


def _vapid_claims_sub():
    from .models import ConfiguracionLiga
    config = ConfiguracionLiga.obtener()
    email = config.correo_electronico or config.email_from or "notificaciones@juventinorosasliga.com"
    return "mailto:{}".format(email)


def _enviar_push_mixto(qs, title, body, data, tipo, partido_id=None, categoria=""):
    """Envía a tokens FCM y suscripciones Web Push (PWA) de un queryset y registra un único log."""
    from .models import DeviceToken

    total_activos = DeviceToken.objects.filter(activo=True).count()
    fcm_tokens = list(qs.filter(webpush_endpoint="").values_list("token", flat=True))
    pwa = list(qs.exclude(webpush_endpoint=""))
    guests = qs.filter(es_invitado=True).count()

    ok_fcm = fail_fcm = 0
    ok_pwa = fail_pwa = 0
    if fcm_tokens:
        r = send_push_notification(fcm_tokens, title, body, data)
        if r:
            ok_fcm = r.get("success", 0)
            fail_fcm = r.get("failure", 0)
    if pwa:
        r = _enviar_webpush(pwa, title, body, data)
        ok_pwa = r.get("success", 0)
        fail_pwa = r.get("failure", 0)

    _add_log({
        "tipo": tipo,
        "partido_id": partido_id,
        "categoria": str(categoria) if categoria else "",
        "detalle": "Activos={}, FCM={}, PWA={}, invitados={}".format(
            total_activos, len(fcm_tokens), len(pwa), guests
        ),
        "total_activos": total_activos,
        "tokens_encontrados": len(fcm_tokens) + len(pwa),
        "guests_incluidos": guests,
        "success": ok_fcm + ok_pwa,
        "failure": fail_fcm + fail_pwa,
    })


def notify_suspension(titulo, cuerpo, categoria=None, partido_id=None, data_tipo="suspension"):
    """Push a invitados cuando un partido queda pendiente o se suspende una jornada."""
    from .models import DeviceToken

    qs = DeviceToken.objects.filter(activo=True, es_invitado=True)
    if categoria:
        qs = qs.filter(
            models.Q(categorias=categoria) | models.Q(categorias__isnull=True)
        )
    qs = qs.distinct()

    if not qs.exists():
        _add_log({
            "tipo": "SUSPENSION",
            "partido_id": partido_id,
            "categoria": str(categoria) if categoria else "(todas)",
            "detalle": "Sin tokens de invitados, se omite push",
        })
        return

    data = {"type": data_tipo, "partido_id": str(partido_id) if partido_id else ""}
    if categoria:
        data["categoria_id"] = str(categoria.id)
    _enviar_push_mixto(
        qs, titulo, cuerpo, data, "SUSPENSION",
        partido_id=partido_id,
        categoria=str(categoria) if categoria else "(todas)",
    )


def notify_partido_finalizado(partido):
    from .models import DeviceToken

    if getattr(partido, "es_amistoso", False):
        return

    categoria = None
    try:
        categoria = partido.jornada.temporada.categoria
    except AttributeError:
        pass

    qs = DeviceToken.objects.filter(activo=True)
    total_activos = qs.count()
    if categoria:
        qs = qs.filter(
            models.Q(categorias=categoria) | models.Q(categorias__isnull=True) | models.Q(es_invitado=False, usuario__isnull=False)
        )
    qs = qs.distinct()

    if not qs.exists():
        _add_log({
            "tipo": "PARTIDO_FIN",
            "partido_id": partido.id,
            "categoria": str(categoria) if categoria else "(sin categoría)",
            "detalle": "Sin tokens coincidentes, se omite push. Activos={}".format(total_activos),
            "total_activos": total_activos,
        })
        return

    local = partido.equipo_local.nombre if partido.equipo_local else "Local"
    visit = partido.equipo_visitante.nombre if partido.equipo_visitante else "Visitante"
    cat_name = str(categoria) if categoria else ""
    title = cat_name
    sufijo = "Finalizado"
    if partido.default_visitante or partido.default_team:
        sufijo += " (Default)"
    body = f"{local} {partido.goles_local} vs {visit} {partido.goles_visitante}\n{sufijo}"
    data = {
        "type": "partido_finalizado",
        "partido_id": str(partido.id),
        "temporada_id": str(partido.temporada_id),
    }

    _enviar_push_mixto(
        qs, title, body, data, "PARTIDO_FIN",
        partido_id=partido.id,
        categoria=str(categoria) if categoria else "(sin categoría)",
    )
