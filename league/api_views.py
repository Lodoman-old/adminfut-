import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.core.management import call_command
from io import StringIO
from .models import DeviceToken, Categoria


def _buscar_o_crear_token(device_id, token):
    """Devuelve el registro del dispositivo por device_id (o por token) o crea uno nuevo."""
    obj = None
    if device_id:
        obj = DeviceToken.objects.filter(device_id=device_id).order_by("-actualizado").first()
    if obj is None:
        obj = DeviceToken.objects.filter(token=token).first()
    created = obj is None
    if obj is None:
        obj = DeviceToken()
    # Liberar el token: no debe quedar duplicado en otro registro
    DeviceToken.objects.filter(token=token).exclude(pk=obj.pk).delete()
    return obj, created


@csrf_exempt
@require_POST
def register_device_token(request):
    """Register or update a device push notification token (un único registro por dispositivo)."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    token = data.get("token", "").strip()
    plataforma = data.get("plataforma", "android")
    device_id = data.get("device_id", "").strip()

    if not token:
        return JsonResponse({"error": "token required"}, status=400)

    obj, created = _buscar_o_crear_token(device_id, token)
    obj.token = token
    obj.plataforma = plataforma
    obj.device_id = device_id
    obj.activo = True
    if request.user.is_authenticated:
        obj.usuario = request.user
        obj.es_invitado = False
        obj.nombre = ""
        obj.telefono = ""
        obj.email = ""
        obj.categorias.clear()
    elif not obj.pk:
        obj.usuario = None
    obj.save()

    # Desactivar otros registros del mismo dispositivo (un solo activo por dispositivo)
    if device_id:
        DeviceToken.objects.filter(device_id=device_id).exclude(pk=obj.pk).update(activo=False)

    return JsonResponse({"ok": True, "created": created, "device_id": device_id})


@csrf_exempt
@require_POST
def register_guest_device(request):
    """Register a device token with guest info and category preferences.

    Al registrarse, crea automáticamente un usuario ligado al dispositivo
    y genera una contraseña para poder acceder a quiniela desde otros dispositivos.
    """
    from django.contrib.auth import get_user_model
    from django.contrib.auth.hashers import make_password
    import random
    import string

    User = get_user_model()

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    token = data.get("token", "").strip()
    plataforma = data.get("plataforma", "android")
    device_id = data.get("device_id", "").strip()
    nombre = data.get("nombre", "").strip()
    telefono = "".join(ch for ch in str(data.get("telefono", "")) if ch.isdigit())
    email = data.get("email", "").strip()
    categoria_ids = data.get("categorias", [])

    if not token:
        return JsonResponse({"error": "token required"}, status=400)

    if not nombre:
        return JsonResponse({"error": "nombre required"}, status=400)

    if not telefono:
        return JsonResponse({"error": "El teléfono es obligatorio para recibir notificaciones."}, status=400)

    if len(telefono) < 10:
        return JsonResponse({"error": "El teléfono debe tener al menos 10 dígitos."}, status=400)

    if email:
        from django.core.exceptions import ValidationError as VE
        from django.core.validators import validate_email
        try:
            validate_email(email)
        except VE:
            return JsonResponse({"error": "El correo electrónico no es válido."}, status=400)

    obj, created = _buscar_o_crear_token(device_id, token)
    obj.token = token
    obj.plataforma = plataforma
    obj.device_id = device_id
    obj.es_invitado = True
    obj.nombre = nombre
    obj.telefono = telefono
    obj.email = email
    obj.usuario = None
    obj.activo = True

    # --- NUEVO: Auto-crear User y generar contraseña ---
    username = device_id or telefono
    # Username debe ser único: si ya existe, añadimos sufijo
    base_username = username
    user = User.objects.filter(username=username).first()
    if not user:
        user = User.objects.create_user(
            username=username,
            email=email or None,
            password=''.join(random.choices(string.ascii_letters + string.digits + '!@#$%^&*', k=12))
        )
    else:
        # Si ya existe (raro en invitado), actualizamos password
        user.password = make_password(''.join(random.choices(string.ascii_letters + string.digits + '!@#$%^&*', k=12)))
    user.save()
    obj.usuario = user
    obj.es_invitado = False  # Ya tiene usuario, ya no es "invitado" estricto
    # ------------------------------------------------

    sub = data.get("subscripcion")
    if sub and isinstance(sub, dict):
        endpoint = (sub.get("endpoint") or "").strip()
        if endpoint:
            obj.webpush_endpoint = endpoint
            obj.webpush_p256dh = (sub.get("p256dh") or "").strip()
            obj.webpush_auth = (sub.get("auth") or "").strip()
            obj.plataforma = "pwa"
            obj.activo = True

    obj.save()

    # Transferir categorías del registro anterior si existe
    transferido = False
    existente = (
        DeviceToken.objects
        .filter(telefono=telefono, es_invitado=True, activo=True)
        .exclude(token=token)
        .exclude(pk=obj.pk)
        .order_by("-actualizado")
        .first()
    )
    if existente:
        transferido = True
        if not categoria_ids:
            obj.categorias.set(existente.categorias.all())
        else:
            obj.categorias.set(categoria_ids)
    elif categoria_ids:
        cats = Categoria.objects.filter(id__in=categoria_ids, activo=True)
        obj.categorias.set(cats)
    else:
        obj.categorias.clear()

    # Deactivate other same-device tokens
    if device_id:
        DeviceToken.objects.filter(device_id=device_id).exclude(pk=obj.pk).update(activo=False)

    # Devolvemos las credenciales para que el modal las muestre
    return JsonResponse({
        "ok": True,
        "created": created,
        "transferido": transferido,
        "device_id": device_id,
        "nombre": obj.nombre,
        "telefono": obj.telefono,
        "email": obj.email,
        "username": user.username,        # <-- Nuevo: usuario para login
        "password": user.password,        # <-- Nuevo: contraseña generada (mostrar una vez)
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
def vapid_public_key(request):
    """Return the VAPID public key (applicationServerKey) for Web Push."""
    from .push import _vapid_keys
    _, public_key = _vapid_keys()
    return JsonResponse({"public_key": public_key})


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
