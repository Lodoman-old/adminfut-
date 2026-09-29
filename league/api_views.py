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
    # Username limpio: nombre (sin espacios/acentos) + últimos 4 dígitos del teléfono
    base = "".join(ch for ch in nombre.lower() if ch.isalnum())
    sufijo = telefono[-4:] if len(telefono) >= 4 else telefono
    username = f"{base}{sufijo}"[:30]  # max 30 chars

    # Contraseña aleatoria corta (8 chars: letras + dígitos)
    plain_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

    user = User.objects.filter(username=username).first()
    if not user:
        user = User.objects.create_user(
            username=username,
            email=email or None,
            password=plain_password
        )
    else:
        # Si ya existe (raro en invitado), actualizamos password
        user.password = make_password(plain_password)
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

    # Auto-login del usuario recién creado
    from django.contrib.auth import login
    login(request, user)

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
        "username": user.username,
        "password": plain_password,
        "categorias": list(obj.categorias.values_list("id", flat=True)),
        "redirect_url": "/",   # Dashboard/home
    })


@csrf_exempt
@require_POST
def enviar_credenciales_quiniela(request):
    """Envía por correo las credenciales de quiniela a un invitado."""
    try:
        # Todo el cuerpo en try para garantizar JSON response
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        email = data.get("email", "").strip()
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()

        if not email:
            return JsonResponse({"error": "email requerido"}, status=400)
        if not username or not password:
            return JsonResponse({"error": "credenciales requeridas"}, status=400)

        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({"error": "email inválido"}, status=400)

        from .models import ConfiguracionLiga
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        from django.core.mail import EmailMultiAlternatives

        # Usar la misma función que ya funciona para otros emails
        from .views import _enviar_correo_suscriptores
        
        # Crear un objeto tipo suscriptor temporal con el email
        class _TmpSuscriptor:
            def __init__(self, email):
                self.email = email
                self.token = ""
        
        suscriptor_tmp = _TmpSuscriptor(email)
        
        html = render_to_string("emails/credenciales_quiniela.html", {
            "username": username,
            "password": password,
            "config": ConfiguracionLiga.obtener(),
        })
        text = strip_tags(html)
        
        try:
            _enviar_correo_suscriptores(
                [suscriptor_tmp], 
                ConfiguracionLiga.obtener(),
                "Tus credenciales para Quiniela - AdminFut",
                "emails/credenciales_quiniela.html", 
                {"username": username, "password": password},
                None,  # request
                []     # adjuntos
            )
            return JsonResponse({"ok": True})
        except Exception as e:
            import traceback
            traceback.print_exc()
            return JsonResponse({"error": f"Error enviando correo: {e}"}, status=500)
    except Exception as e:
        # Cualquier error inesperado -> JSON, no HTML
        import traceback
        traceback.print_exc()
        return JsonResponse({"error": f"Error interno: {e}"}, status=500)


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
@require_POST
def delete_device_token(request):
    """Permanently delete a device token (not just deactivate)."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    token = data.get("token", "").strip()
    if not token:
        return JsonResponse({"error": "token required"}, status=400)

    DeviceToken.objects.filter(token=token).delete()
    return JsonResponse({"ok": True})


@csrf_exempt
@require_POST
def update_device_field(request):
    """Update a specific field of a device token (nombre, telefono, email)."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    token = data.get("token", "").strip()
    field = data.get("field", "").strip()
    value = data.get("value", "").strip()

    if not token:
        return JsonResponse({"error": "token required"}, status=400)
    if field not in ("nombre", "telefono", "email"):
        return JsonResponse({"error": "field must be nombre, telefono, or email"}, status=400)

    try:
        obj = DeviceToken.objects.get(token=token)
    except DeviceToken.DoesNotExist:
        return JsonResponse({"error": "device not found"}, status=404)

    if field == "telefono":
        value = "".join(ch for ch in value if ch.isdigit())
    elif field == "email" and value:
        from django.core.validators import validate_email
        from django.core.exceptions import ValidationError
        try:
            validate_email(value)
        except ValidationError:
            return JsonResponse({"error": "email inválido"}, status=400)

    setattr(obj, field, value)
    obj.save()
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


@csrf_exempt
@require_POST
def api_equipos_compatibles(request):
    """API: retorna equipos compatibles para una categoría (para modal equipo secundario)."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    cat_id = data.get("categoria_id")
    jugador_id = data.get("jugador_id")

    if not cat_id:
        return JsonResponse({"error": "categoria_id requerido"}, status=400)

    try:
        cat = Categoria.objects.get(id=cat_id)
    except Categoria.DoesNotExist:
        return JsonResponse({"error": "Categoría no encontrada"}, status=404)

    # Obtener categorías compatibles
    compat_ids = list(cat.categorias_compatibles.values_list("id", flat=True))
    # Incluir la propia categoría
    compat_ids = list(set(compat_ids + [cat.id]))

    jugador = None
    if jugador_id:
        try:
            jugador = Jugador.objects.get(id=jugador_id)
        except Jugador.DoesNotExist:
            jugador = None

    # Obtener edad del jugador
    edad_jugador = jugador.edad() if jugador else 0

    # Obtener equipos de categorías compatibles
    equipos = Equipo.objects.filter(
        categoria_id__in=compat_ids, activo=True
    ).select_related("categoria").order_by("categoria__nombre", "nombre")

    equipos_data = []
    for eq in equipos:
        edad_min = eq.categoria.edad_minima or 0
        edad_max = eq.categoria.edad_maxima or 99
        edad_ok = True
        edad_msg = ""
        if edad_jugador:
            if edad_jugador < eq.categoria.edad_minima or edad_jugador > eq.categoria.edad_maxima:
                edad_ok = False
                edad_msg = "El jugador tiene " + str(edad_jugador) + " años. " + eq.categoria.nombre + " requiere edad entre " + str(eq.categoria.edad_minima) + " y " + str(eq.categoria.edad_maxima) + " años."

        equipos_data.append({
            "id": eq.id,
            "nombre": eq.nombre,
            "categoria_id": eq.categoria_id,
            "categoria_nombre": eq.categoria.nombre,
            "edad_minima": eq.categoria.edad_minima or 0,
            "edad_maxima": eq.categoria.edad_maxima or 99,
            "edad_ok": edad_ok,
            "edad_msg": edad_msg,
        })

    return JsonResponse({
        "equipos": equipos_data,
    })


@csrf_exempt
@require_POST
def api_agregar_equipo_secundario(request):
    """API: agrega un equipo secundario a un jugador (bypassa validación de temporada activa)."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    jugador_id = data.get("jugador_id")
    equipo_id = data.get("equipo_id")

    if not jugador_id or not equipo_id:
        return JsonResponse({"error": "jugador_id y equipo_id requeridos"}, status=400)

    try:
        jugador = Jugador.objects.get(id=jugador_id)
    except Jugador.DoesNotExist:
        return JsonResponse({"error": "Jugador no encontrado"}, status=404)

    try:
        equipo = Equipo.objects.get(id=equipo_id)
    except Equipo.DoesNotExist:
        return JsonResponse({"error": "Equipo no encontrado"}, status=404)

    # Verificar que no esté ya registrado en ese equipo
    if JugadorEquipo.objects.filter(jugador=jugador, equipo=equipo, activo=True).exists():
        return JsonResponse({"error": "El jugador ya está registrado en ese equipo"}, status=400)

    # Verificar compatibilidad de categorías
    cat_principal = jugador.equipo.categoria if jugador.equipo else None
    if cat_principal and cat_principal != equipo.categoria:
        if equipo.categoria not in cat_principal.categorias_compatibles.all():
            return JsonResponse({
                "error": "La categoría " + equipo.categoria.nombre + " no es compatible con " + cat_principal.nombre
            }, status=400)

    # Verificar edad
    if jugador.edad():
        edad = jugador.edad()
        if equipo.categoria.edad_minima and edad < equipo.categoria.edad_minima:
            return JsonResponse({
                "error": "El jugador tiene " + str(jugador.edad()) + " años. La categoría " + equipo.categoria.nombre + " requiere edad mínima de " + str(equipo.categoria.edad_minima) + " años."
            }, status=400)
        if equipo.categoria.edad_maxima and edad > equipo.categoria.edad_maxima:
            return JsonResponse({
                "error": "El jugador tiene " + str(jugador.edad()) + " años. La categoría " + equipo.categoria.nombre + " requiere edad máxima de " + str(equipo.categoria.edad_maxima) + " años."
            }, status=400)

    # Verificar límite de jugadores en el equipo
    max_jug = equipo.categoria.max_jugadores
    actuales = JugadorEquipo.objects.filter(equipo=equipo, activo=True).count()
    if actuales >= max_jug:
        return JsonResponse({
            "error": "El equipo " + equipo.nombre + " ya tiene " + str(actuales) + " jugadores (máximo " + str(max_jug) + ")"
        }, status=400)

    # Verificar que no esté en otro equipo de la MISMA categoría con temporada activa
    cat_destino = equipo.categoria
    temp_activa = Temporada.objects.filter(
        categoria=cat_destino, iniciada=True, finalizada=False
    ).first()

    if temp_activa:
        # Verificar si ya está en otro equipo de la misma categoría con temporada activa
        en_otro = JugadorEquipo.objects.filter(
            jugador=jugador,
            equipo__categoria=cat_destino,
            activo=True,
            es_principal=False
        ).exclude(equipo=equipo).exists()

        if en_otro:
            return JsonResponse({
                "error": "El jugador ya está en otro equipo de " + cat_destino.nombre + " con temporada activa"
            }, status=400)

    # Crear el registro
    JugadorEquipo.objects.create(
        jugador=jugador,
        equipo=equipo,
        es_principal=False,
        activo=True,
    )

    return JsonResponse({
        "ok": True,
        "mensaje": "Equipo secundario '" + equipo.nombre + "' agregado correctamente",
        "equipo": {
            "id": equipo.id,
            "nombre": equipo.nombre,
            "categoria": equipo.categoria.nombre,
        }
    })
