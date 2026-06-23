"""
Firebase Cloud Messaging integration for push notifications.
Uses Firebase Admin SDK. Requires FIREBASE_SERVICE_ACCOUNT_JSON env var
or secrets/firebase-service-account.json file.
"""
import json
import os
from django.conf import settings
import firebase_admin
from firebase_admin import credentials, messaging


def _get_credential():
    json_str = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
    if json_str:
        return credentials.Certificate(json.loads(json_str))
    file_path = os.path.join(settings.BASE_DIR, "secrets", "firebase-service-account.json")
    if os.path.exists(file_path):
        return credentials.Certificate(file_path)
    raise RuntimeError(
        "FIREBASE_SERVICE_ACCOUNT_JSON not set and "
        "secrets/firebase-service-account.json not found"
    )


def _init_app():
    if firebase_admin._apps:
        return
    cred = _get_credential()
    firebase_admin.initialize_app(cred)


def send_push_notification(tokens, title, body, data=None):
    if not tokens:
        return
    _init_app()

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
    except Exception:
        return None


def notify_partido_finalizado(partido):
    from .models import DeviceToken

    tokens = list(DeviceToken.objects.filter(activo=True).values_list("token", flat=True))
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
