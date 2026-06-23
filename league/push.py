"""
Firebase Cloud Messaging integration for push notifications.
Uses Firebase Admin SDK. Requires FIREBASE_SERVICE_ACCOUNT_JSON env var
or secrets/firebase-service-account.json file.
"""
import base64
import json
import os
import logging
from django.conf import settings
from django.db import models

logger = logging.getLogger(__name__)

_app_initialized = False


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
        return
    if not _try_init():
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
        return {"success": response.success_count, "failure": response.failure_count}
    except Exception as e:
        logger.error("Push send failed: %s", e)
        return None


def notify_partido_finalizado(partido):
    from .models import DeviceToken

    categoria = None
    try:
        categoria = partido.jornada.temporada.categoria
    except AttributeError:
        pass

    qs = DeviceToken.objects.filter(activo=True)
    if categoria:
        qs = qs.filter(
            models.Q(categorias=categoria) | models.Q(categorias__isnull=True) | models.Q(es_invitado=False, usuario__isnull=False)
        )
    qs = qs.distinct()

    tokens = list(qs.values_list("token", flat=True))
    if not tokens:
        return

    local = partido.equipo_local.nombre if partido.equipo_local else "Local"
    visit = partido.equipo_visitante.nombre if partido.equipo_visitante else "Visitante"
    score = f"{partido.goles_local} - {partido.goles_visitante}"
    title = f"{local} vs {visit}"
    body = f"Resultado final: {score}"
    data = {
        "type": "partido_finalizado",
        "partido_id": str(partido.id),
        "temporada_id": str(partido.temporada_id),
    }

    send_push_notification(tokens, title, body, data)
