import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.core.management import call_command
from io import StringIO
from .models import DeviceToken


@csrf_exempt
@require_POST
def register_device_token(request):
    """Register or update a device push notification token."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    token = data.get("token", "").strip()
    plataforma = data.get("plataforma", "android")

    if not token:
        return JsonResponse({"error": "token required"}, status=400)

    obj, created = DeviceToken.objects.update_or_create(
        token=token,
        defaults={
            "plataforma": plataforma,
            "usuario": request.user if request.user.is_authenticated else None,
            "activo": True,
        },
    )
    return JsonResponse({"ok": True, "created": created})


@csrf_exempt
@require_POST
def unregister_device_token(request):
    """Deactivate a device token."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    token = data.get("token", "").strip()
    if not token:
        return JsonResponse({"error": "token required"}, status=400)

    DeviceToken.objects.filter(token=token).update(activo=False)
    return JsonResponse({"ok": True})


@csrf_exempt
@require_GET
def cron_notificar_arbitros(request):
    """Endpoint llamado por scheduler externo (cron-job.org, Render Cron, etc.)."""
    out = StringIO()
    try:
        call_command("notificar_arbitros", stdout=out)
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e), "output": out.getvalue()}, status=500)
    return JsonResponse({"ok": True, "output": out.getvalue()})
