import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.core.management import call_command
from io import StringIO
from .models import DeviceToken, Categoria


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
    device_id = data.get("device_id", "").strip()

    if not token:
        return JsonResponse({"error": "token required"}, status=400)

    defaults = {
        "plataforma": plataforma,
        "device_id": device_id,
        "usuario": request.user if request.user.is_authenticated else None,
        "activo": True,
    }

    if request.user.is_authenticated:
        defaults["es_invitado"] = False
        defaults["nombre"] = ""

    obj, created = DeviceToken.objects.update_or_create(
        token=token,
        defaults=defaults,
    )

    if request.user.is_authenticated:
        obj.categorias.clear()

    # Desactivar tokens viejos del mismo dispositivo (mismo device_id, token diferente)
    if device_id:
        DeviceToken.objects.filter(device_id=device_id).exclude(token=token).update(activo=False)

    return JsonResponse({"ok": True, "created": created, "device_id": device_id})


@csrf_exempt
@require_POST
def register_guest_device(request):
    """Register a device token with guest info and category preferences.

    El teléfono es obligatorio y actúa como identidad del invitado: si ya
    existe otro registro activo con el mismo teléfono, el dispositivo nuevo
    hereda nombre y categorías y el registro anterior se desactiva.
    """
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    token = data.get("token", "").strip()
    plataforma = data.get("plataforma", "android")
    device_id = data.get("device_id", "").strip()
    nombre = data.get("nombre", "").strip()
    telefono = "".join(ch for ch in str(data.get("telefono", "")) if ch.isdigit())
    categoria_ids = data.get("categorias", [])

    if not token:
        return JsonResponse({"error": "token required"}, status=400)

    if not nombre:
        return JsonResponse({"error": "nombre required"}, status=400)

    if not telefono:
        return JsonResponse({"error": "El teléfono es obligatorio para recibir notificaciones."}, status=400)

    if len(telefono) < 10:
        return JsonResponse({"error": "El teléfono debe tener al menos 10 dígitos."}, status=400)

    obj, created = DeviceToken.objects.update_or_create(
        token=token,
        defaults={
            "plataforma": plataforma,
            "device_id": device_id,
            "es_invitado": True,
            "nombre": nombre,
            "telefono": telefono,
            "usuario": None,
            "activo": True,
        },
    )

    transferido = False
    existente = (
        DeviceToken.objects
        .filter(telefono=telefono, es_invitado=True, activo=True)
        .exclude(token=token)
        .order_by("-actualizado")
        .first()
    )
    if existente:
        transferido = True
        if not categoria_ids:
            obj.categorias.set(existente.categorias.all())
        else:
            obj.categorias.set(categoria_ids)
        existente.activo = False
        existente.save()
        obj.save()
    elif categoria_ids:
        cats = Categoria.objects.filter(id__in=categoria_ids, activo=True)
        obj.categorias.set(cats)
    else:
        obj.categorias.clear()

    # Desactivar tokens viejos del mismo dispositivo
    if device_id:
        DeviceToken.objects.filter(device_id=device_id).exclude(token=token).update(activo=False)

    return JsonResponse({
        "ok": True,
        "created": created,
        "transferido": transferido,
        "device_id": device_id,
        "nombre": obj.nombre,
        "telefono": obj.telefono,
        "categorias": list(obj.categorias.values_list("id", flat=True)),
    })


@csrf_exempt
@require_POST
def update_device_preferences(request):
    """Update guest name and category preferences for a device token."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    token = data.get("token", "").strip()
    if not token:
        return JsonResponse({"error": "token required"}, status=400)

    try:
        obj = DeviceToken.objects.get(token=token, activo=True)
    except DeviceToken.DoesNotExist:
        return JsonResponse({"error": "device not found"}, status=404)

    nombre = data.get("nombre", "").strip()
    if nombre:
        obj.nombre = nombre

    telefono = data.get("telefono")
    if telefono is not None:
        obj.telefono = str(telefono).strip()

    obj.save()

    categoria_ids = data.get("categorias")
    if categoria_ids is not None:
        cats = Categoria.objects.filter(id__in=categoria_ids, activo=True)
        obj.categorias.set(cats)

    return JsonResponse({
        "ok": True,
        "nombre": obj.nombre,
        "categorias": list(obj.categorias.values_list("id", flat=True)),
    })


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
def lista_categorias(request):
    """Return active categories for guest registration."""
    cats = Categoria.objects.filter(activo=True).values("id", "nombre")
    return JsonResponse({"categorias": list(cats)})


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
