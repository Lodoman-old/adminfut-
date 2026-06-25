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
        result = {"success": response.success_count, "failure": response.failure_count}
        _add_log({"tipo": "SEND", "detalle": f"Push enviado: {response.success_count} ok, {response.failure_count} fail", "success": response.success_count, "failure": response.failure_count})
        return result
    except Exception as e:
        logger.error("Push send failed: %s", e)
        _add_log({"tipo": "SEND", "detalle": f"Error al enviar push: {e}", "success": 0, "failure": 0, "error": str(e)})
        return None


def notify_partido_finalizado(partido):
    from .models import DeviceToken

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

    tokens = list(qs.values_list("token", flat=True))
    guests = qs.filter(es_invitado=True).count() if tokens else 0

    _add_log({
        "tipo": "PARTIDO_FIN",
        "partido_id": partido.id,
        "categoria": str(categoria) if categoria else "(sin categoría)",
        "detalle": f"Activos totales={total_activos}, tokens_match={len(tokens)}, invitados={guests}",
        "total_activos": total_activos,
        "tokens_encontrados": len(tokens),
        "guests_incluidos": guests,
        "success": 0,
        "failure": 0,
    })

    if not tokens:
        _add_log({
            "tipo": "PARTIDO_FIN",
            "partido_id": partido.id,
            "detalle": "Sin tokens coincidentes, se omite push",
        })
        return

    local = partido.equipo_local.nombre if partido.equipo_local else "Local"
    visit = partido.equipo_visitante.nombre if partido.equipo_visitante else "Visitante"
    score = f"{partido.goles_local} - {partido.goles_visitante}"
    cat_name = str(categoria) if categoria else ""
    title = cat_name
    body = f"{local} vs {visit}\n{score}"
    data = {
        "type": "partido_finalizado",
        "partido_id": str(partido.id),
        "temporada_id": str(partido.temporada_id),
    }

    send_push_notification(tokens, title, body, data)
