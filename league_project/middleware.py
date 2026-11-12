import ipaddress
import re
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import Resolver404, resolve

NGROK_RE = re.compile(r'^https://[a-zA-Z0-9.-]+\.ngrok-free\.(app|dev)$')


class CorsMiddleware:
    """Habilita CORS para los endpoints que consume la APK Android desde el
    WebView de Capacitor (origen https://localhost): el chequeo de conexión
    (/accounts/login/) y las APIs offline con Bearer token (/api/...).
    No expone sesión: las cookies no se envían en requests cross-origin y no
    se activa Access-Control-Allow-Credentials."""

    PREFIJOS = ('/api/', '/accounts/login/')
    HEADERS = {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
        'Access-Control-Allow-Headers': 'Authorization, Content-Type, X-Requested-With, Accept',
        'Access-Control-Max-Age': '86400',
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(self.PREFIJOS):
            return self.get_response(request)

        if request.method == 'OPTIONS':
            response = HttpResponse(status=200, content=b'')
            for key, value in self.HEADERS.items():
                response[key] = value
            return response

        response = self.get_response(request)
        for key, value in self.HEADERS.items():
            response[key] = value
        return response


class BloqueoScrapersMiddleware:
    """Devuelve 403 a scrapers identificados que cosechan datos del sitio.

    Solo bloquea UAs inequívocos (Node sin navegador y el bot
    ``public-data-sync``). Se excluyen ``/api/`` y ``/health/`` para no romper
    integraciones ni el monitoreo. Esto es un paliativo: un scraper puede
    cambiar el UA, pero frena al bot actual y sus variantes.
    """

    UA_BLOQUEADOS = re.compile(
        r'(ligajr|public-data-sync|public-cedula-audit|data-sync|'
        r'wordpress|wp-admin|wp-login|xmlrpc|'
        r'assetnote|nuclei|zgrab|masscan|sqlmap|nikto|dirbuster|gobuster|nmap)',
        re.I,
    )
    UA_EXACTOS = frozenset({'node', 'node.js', 'undici', 'axios'})
    RUTAS_EXENTAS = ('/api/', '/health/')
    RUTAS_BLOQUEADAS = ('/wp-admin', '/wp-login', '/wp-content', '/wp-includes', '/xmlrpc.php')

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _registrar(request, motivo):
        """Guarda el bloqueo para poder monitorearlo en /push-logs/."""
        try:
            from league.models import SolicitudBloqueada
            ip = (request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR') or '').split(',')[0].strip()
            SolicitudBloqueada.objects.create(
                ip=ip or None,
                user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:300],
                path=request.path[:300],
                metodo=request.method,
                motivo=motivo,
            )
        except Exception:
            pass

    @staticmethod
    def _ip(request):
        return (
            request.META.get('HTTP_X_FORWARDED_FOR')
            or request.META.get('REMOTE_ADDR')
            or ''
        ).split(',')[0].strip()

    @staticmethod
    def _ips_bloqueadas():
        from django.core.cache import cache

        lista = cache.get('ips_bloqueadas')
        if lista is None:
            from league.models import IPBloqueada
            lista = list(
                IPBloqueada.objects.filter(activa=True).values_list('valor', flat=True)
            )
            cache.set('ips_bloqueadas', lista, 60)
        return lista

    @classmethod
    def _esta_bloqueada(cls, ip):
        if not ip:
            return False
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        for valor in cls._ips_bloqueadas():
            try:
                if '/' in valor:
                    if addr in ipaddress.ip_network(valor, strict=False):
                        return True
                elif addr == ipaddress.ip_address(valor):
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    def _baneada(ip):
        from django.core.cache import cache
        return bool(ip and cache.get(f'ban:{ip}'))

    @staticmethod
    def _sumar_abuso(ip):
        """Banea 15 min a una IP que acumula bloqueos por UA en un minuto."""
        if not ip:
            return
        from django.core.cache import cache
        clave = f'abuso:{ip}'
        try:
            n = cache.incr(clave)
        except ValueError:
            cache.add(clave, 1, 60)
            n = 1
        if n >= 20:
            cache.set(f'ban:{ip}', 1, 900)

    def __call__(self, request):
        if request.path.startswith(self.RUTAS_EXENTAS):
            return self.get_response(request)
        ip = self._ip(request)
        if self._baneada(ip):
            return HttpResponse(
                'Acceso bloqueado temporalmente por demasiados intentos. '
                'Espera unos minutos e intenta de nuevo.',
                status=429,
                content_type='text/plain; charset=utf-8',
            )
        if self._esta_bloqueada(ip):
            return HttpResponse(
                'Acceso no permitido.',
                status=403,
                content_type='text/plain; charset=utf-8',
            )
        if request.path.startswith(self.RUTAS_BLOQUEADAS):
            self._registrar(request, 'ruta')
            return HttpResponse(
                'Not found.',
                status=404,
                content_type='text/plain; charset=utf-8',
            )
        ua = (request.META.get('HTTP_USER_AGENT') or '').strip().lower()
        if ua in self.UA_EXACTOS or self.UA_BLOQUEADOS.search(ua):
            self._registrar(request, 'ua')
            self._sumar_abuso(ip)
            return HttpResponse(
                'Acceso no permitido.',
                status=403,
                content_type='text/plain; charset=utf-8',
            )
        return self.get_response(request)


class RateLimitMiddleware:
    """Límite de peticiones por IP para frenar ráfagas y bots.

    Se aplica solo a anónimos: los usuarios con sesión (staff, árbitros,
    invitados logueados) no se limitan. Los assets, la API y el health check
    están exentos. Al exceder, responde 429 y registra el evento para la
    pestaña Trafico de /push-logs/.
    """

    VENTANA = 60  # segundos
    LIMITE_GLOBAL = 120
    REGLAS = (
        ('/accounts/login/', 10, 'login'),
        ('/reportes/', 40, 'reportes'),
        ('/cedula-arbitral/', 40, 'cedula'),
        ('/jugador/', 60, 'jugador'),
        ('/equipo/', 60, 'equipo'),
    )
    EXENTOS = (
        '/api/', '/health/', '/static/', '/media/', '/sw.js',
        '/pwa-icon/', '/manifest.webmanifest', '/notificaciones/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _ip(request):
        valor = (request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR') or '')
        return valor.split(',')[0].strip()

    @staticmethod
    def _registrar(request, ip):
        try:
            from league.models import SolicitudBloqueada
            SolicitudBloqueada.objects.create(
                ip=ip or None,
                user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:300],
                path=request.path[:300],
                metodo=request.method,
                motivo='limite',
            )
        except Exception:
            pass

    @staticmethod
    def _sumar_exceso(ip):
        """Banea 1 hora a una IP que reincide en pasarse del límite.

        Un bot que rota ventanas (o que insiste cada minuto) acumula 15
        respuestas 429 en 10 minutos y queda bloqueado sin depender de
        Cloudflare. El bloqueo vive en caché; al expirar vuelve a intentar.
        """
        if not ip or ip == 'sin-ip':
            return
        from django.core.cache import cache
        clave = f'exceso:{ip}'
        try:
            n = cache.incr(clave)
        except ValueError:
            cache.add(clave, 1, 600)
            n = 1
        if n >= 15:
            cache.set(f'ban:{ip}', 1, 3600)

    def __call__(self, request):
        if request.path.startswith(self.EXENTOS):
            return self.get_response(request)
        if getattr(request.user, 'is_authenticated', False):
            return self.get_response(request)

        limite, etiqueta = self.LIMITE_GLOBAL, 'global'
        for prefijo, lim, nombre in self.REGLAS:
            if request.path.startswith(prefijo):
                limite, etiqueta = lim, nombre
                break

        ip = self._ip(request) or 'sin-ip'
        clave = f'rl:{etiqueta}:{ip}'
        from django.core.cache import cache
        try:
            actual = cache.incr(clave)
        except ValueError:
            cache.add(clave, 1, self.VENTANA)
            actual = 1

        if actual > limite:
            self._registrar(request, ip)
            self._sumar_exceso(ip)
            respuesta = HttpResponse(
                'Demasiadas solicitudes. Espera un momento e intenta de nuevo.',
                status=429,
                content_type='text/plain; charset=utf-8',
            )
            respuesta['Retry-After'] = str(self.VENTANA)
            return respuesta
        return self.get_response(request)


class AutoNgrokCSRFMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.META.get('HTTP_ORIGIN', '')
        if origin and origin not in settings.CSRF_TRUSTED_ORIGINS and NGROK_RE.match(origin):
            settings.CSRF_TRUSTED_ORIGINS.append(origin)
        return self.get_response(request)


# ---------------------------------------------------------------------------
# Control de acceso central: exige sesión iniciada y permiso de rol en todas
# las rutas que no sean públicas. Evita que páginas protegidas se vean sin
# autenticarse (p. ej. /finanzas/conceptos/) o con permisos insuficientes.
# ---------------------------------------------------------------------------

RUTAS_PUBLICAS = {
    '/',
    '/tabla-posiciones/',
    '/tabla-goleo/',
    '/tabla-tarjetas/',
    '/tabla-castigados/',
    '/reglamento/descargar/',
    '/apk/descargar/',
    '/suscripcion/',
    '/reportes/registro/',  # reporte de registro: visible para cualquiera (logueado o no)
    '/reportes/altas/',  # reporte público de altas de jugadores
    '/accounts/login/',
    '/accounts/invitado/registro/',
    '/robots.txt',
    '/quiniela/',  # gate anónimo: descargar app / registrarse (la vista decide)
    '/quiniela/historico/',  # mismo gate anónimo que /quiniela/
    '/reporte-semanal/',
    '/reportes/jornadas/',
    '/reportes/jornadas/pdf/',
    '/reportes/jornadas/xlsx/',
    '/reportes/jornadas/completo/',
    '/reportes/jornadas/completo/pdf/',
    '/reportes/jornadas/completo/xlsx/',
    # APIs basadas en token/dispositivo (no usan sesión)
    '/api/register-device/',
    '/api/unregister-device/',
    '/api/register-guest/',
    '/api/update-preferences/',
    '/api/categorias/',
    '/api/vapid-public-key/',
    '/api/cron-notificar-arbitros/',
    '/api/enviar-credenciales-quiniela/',
    '/health/',
    # PWA / Web Push
    '/sw.js',
    '/manifest.webmanifest',
}

PREFIJOS_PUBLICOS = (
    '/media/',
    '/static/',
    '/admin/',
    '/api/offline/',  # autenticación propia con Bearer token
    '/pwa-icon/',
    '/notificaciones/',  # imágenes de marca de las notificaciones push
    '/publicidad/',  # página pública de detalle de anuncios
    '/equipo/',  # ficha pública de equipo
    '/jugador/',  # ficha pública de jugador
    '/compartir/',  # páginas públicas para compartir en redes (OG)
    '/s/',  # enlaces cortos para compartir (OG)
)

# url_name -> permiso(s) requerido(s). '__staff__' exige is_staff.
PERMISO_POR_URL = {
    # Gestión - Categorías
    'categoria_list': 'gestion_categorias',
    'categoria_create': 'categoria_crear',
    'categoria_update': 'categoria_editar',
    'categoria_delete': 'categoria_eliminar',
    # Gestión - Anuncios / Publicidad
    'anuncio_list': 'gestion_publicidad',
    'anuncio_create': 'anuncio_crear',
    'anuncio_update': 'anuncio_editar',
    'anuncio_delete': 'anuncio_eliminar',
    # Gestión - Equipos
    'equipo_list': 'gestion_equipos',
    'equipo_create': 'equipo_crear',
    'equipo_update': 'equipo_editar',
    'equipo_delete': 'equipo_eliminar',
    'marcar_abandono': 'equipo_abandonar',
    'desmarcar_abandono': 'equipo_abandonar',
    # Gestión - Jugadores
    'jugador_list': 'gestion_jugadores',
    'jugador_create': 'jugador_crear',
    'jugador_update': 'jugador_editar',
    'jugador_delete': 'jugador_eliminar',
    'subir_foto_jugador': 'jugador_foto',
    # Gestión - Campos
    'campo_list': 'gestion_campos',
    'campo_create': 'campo_crear',
    'campo_update': 'campo_editar',
    'campo_delete': 'campo_eliminar',
    # Gestión - Temporadas
    'temporada_list': 'gestion_temporadas',
    'temporada_create': 'temporada_crear',
    'temporada_update': 'temporada_editar',
    'iniciar_temporada': 'temporada_iniciar',
    'finalizar_temporada': 'temporada_finalizar',
    'reabrir_temporada': 'temporada_finalizar',
    'reiniciar_temporada': 'temporada_reiniciar',
    'generar_liguilla': 'temporada_liguilla',
    'publicar_campeon': 'temporada_liguilla',
    'temporada_equipos': 'temporada_equipos',
    'asignar_grupos': 'temporada_equipos',
    'confirmar_grupos': 'temporada_equipos',
    'enviar_roles_semana': 'temporada_enviar',
    'enviar_rol_jornada': 'temporada_enviar',
    'enviar_estadisticas': 'temporada_enviar',
    # Gestión - Jornadas
    'jornada_list': 'gestion_jornadas',
    'suspender_jornada': 'jornada_suspender',
    'reactivar_jornada': 'jornada_suspender',
    'publicar_jornada_facebook': 'jornada_publicar',
    'publicar_rol_facebook': 'jornada_publicar',
    'publicar_posiciones_facebook': 'jornada_publicar',
    # Gestión - Períodos de Altas
    'periodoaltas_list': 'gestion_periodosaltas',
    'periodoaltas_create': 'periodoaltas_crear',
    'periodoaltas_update': 'periodoaltas_editar',
    'periodoaltas_delete': 'periodoaltas_eliminar',
    'gestionar_altas_bajas': 'gestion_periodosaltas',
    # Gestión - Partidos
    'partido_list': 'gestion_partidos',
    'partido_create': 'partido_crear',
    'partido_update': 'partido_editar',
    'partido_delete': 'partido_eliminar',
    'reagendar_partido': 'partido_reagendar',
    'guardar_observaciones': 'partido_observaciones',
    'gestionar_indisponibilidad': 'partido_indisponibilidad',
    'modo_offline': 'partido_cedula',
    # Gestión - Árbitros
    'arbitro_list': 'gestion_arbitros',
    'arbitro_create': 'arbitro_crear',
    'arbitro_update': 'arbitro_editar',
    'arbitro_delete': 'arbitro_eliminar',
    # Finanzas
    'concepto_list': 'ver_finanzas',
    'concepto_create': 'concepto_crear',
    'concepto_update': 'concepto_editar',
    'concepto_delete': 'concepto_eliminar',
    'ingreso_list': 'ver_finanzas',
    'ingreso_create': 'ingreso_crear',
    'ingreso_update': 'ingreso_editar',
    'ingreso_delete': 'ingreso_eliminar',
    'ingreso_pos': 'ingreso_pos',
    'ingreso_ticket': 'ver_finanzas',
    'caja_dashboard': 'caja_ver',
    'caja_aperturar': 'caja_aperturar',
    'caja_cerrar': 'caja_cerrar',
    'caja_corte': 'caja_corte',
    'caja_detail': 'caja_ver',
    'reporte_ingresos': 'ver_finanzas',
    'reporte_ingresos_pdf': 'ver_finanzas',
    'reporte_ingresos_xlsx': 'ver_finanzas',
    'reporte_pagos_temporada': 'ver_finanzas',
    'reporte_pagos_pdf': 'ver_finanzas',
    'reporte_pagos_xlsx': 'ver_finanzas',
    # Reportes
    'reporte_suscriptores': 'reporte_suscriptores',
    'reporte_suscriptores_pdf': 'reporte_suscriptores',
    'reporte_suscriptores_xlsx': 'reporte_suscriptores',
    'reporte_credenciales': 'credenciales_ver',
    'reporte_credenciales_pdf': 'credenciales_ver',
    'reporte_posiciones_pdf': 'reporte_posiciones_pdf',
    'reporte_posiciones_xlsx': 'reporte_posiciones_pdf',
    'reporte_goleo_pdf': 'reporte_goleo_pdf',
    'reporte_goleo_xlsx': 'reporte_goleo_pdf',
    'reporte_tarjetas_pdf': 'reporte_tarjetas_pdf',
    'reporte_tarjetas_xlsx': 'reporte_tarjetas_pdf',
    'reporte_castigados_pdf': 'reporte_castigados_pdf',
    'reporte_castigados_xlsx': 'reporte_castigados_pdf',
    # Suspensiones manuales
    'temporada_suspensiones': 'gestion_suspensiones',
    'levantar_suspension': 'gestion_suspensiones',
    # Ascensos/descensos al cerrar temporada
    'temporada_movimientos': 'temporada_movimientos',
    # Módulo de jugadores heredados (solo administrador)
    'alta_jugadores_heredados': 'gestion_jugadores_heredados',
    'reporte_cedula_arbitral_pdf': 'partido_cedula',
    'reporte_cedula_arbitral_xlsx': 'partido_cedula',
    'cedula_escanear': 'partido_cedula',
    'horarios_fijos_report': 'reporte_horarios',
    # Configuración
    'configuracion_liga': 'gestion_configuracion',
    'test_database_connection': 'gestion_configuracion',
    'test_email_connection': 'gestion_configuracion',
    'test_facebook_post': 'gestion_configuracion',
    'usuario_list': 'gestion_usuarios',
    'usuario_create': 'gestion_usuarios',
    'usuario_update': 'gestion_usuarios',
    'usuario_delete': 'gestion_usuarios',
    'rol_list': 'gestion_roles',
    'rol_create': 'gestion_roles',
    'rol_update': 'gestion_roles',
    'rol_delete': 'gestion_roles',
    'admin_push_logs': '__staff__',
    'enviar_rol_por_correo': '__staff__',
}


class ContadorVisitasMiddleware:
    """Registra las visitas a páginas públicas del sitio (GET con respuesta 200).

    No cuenta al personal (staff), ni /admin/, /media/, /static/, /api/,
    ni peticiones de bots/descargadores.

    Agrupa la navegación de un mismo visitante (por IP, o sesión si no hay IP):
    si no hubo otra página del mismo visitante en la última hora, la página se
    marca como inicio de una nueva visita (campo `inicio=True`); si sigue
    navegando antes de esa hora, se considera parte de la misma visita.
    """
    NOS_CONTAR = ('/admin/', '/media/', '/static/', '/api/', '/health/',
                  '/sw.js', '/manifest.webmanifest', '/pwa-icon/', '/notificaciones/')
    BOTS = re.compile(
        r'(bot|spider|crawl|slurp|bingpreview|facebookexternalhit|whatsapp|'
        r'curl|wget|python-requests|python-urllib|go-http-client|ahrefs|mj12|'
        r'semrush|google-inspectiontool|pingdom|uptime|monitor|'
        r'public-data-sync|data-sync|axios|undici|scrapy|okhttp|libwww|'
        r'ligajr|public-cedula-audit|google-lens|wordpress|wp-admin|xmlrpc|'
        r'\bnode\b)', re.I)
    VENTANA_MINUTOS = 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if request.method != 'GET' or response.status_code != 200:
                return response
            path = request.path
            if path.startswith(self.NOS_CONTAR) or self.BOTS.search(request.META.get('HTTP_USER_AGENT', '')):
                return response
            user = getattr(request, 'user', None)
            if user is not None and getattr(user, 'is_staff', False):
                return response
            from league.models import Visita, ConfiguracionLiga
            from datetime import timedelta
            from django.utils import timezone
            ip = (request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR') or '').split(',')[0].strip()
            if ConfiguracionLiga.es_ip_excluida(ip):
                return response
            sesion = ''
            if getattr(request, 'session', None):
                sesion = request.session.get('_session_key') or ''
            # ¿Es el inicio de una visita? (sin otra página del mismo
            # visitante en la última hora)
            clave_q = None
            if ip:
                clave_q = {'ip': ip}
            elif sesion:
                clave_q = {'sesion': sesion}
            inicio = True
            if clave_q:
                ultima = (Visita.objects
                          .filter(**clave_q)
                          .order_by('-fecha')
                          .values_list('fecha', flat=True)
                          .first())
                if ultima is not None and (timezone.now() - ultima) < timedelta(minutes=self.VENTANA_MINUTOS):
                    inicio = False
            gu = user if (user is not None and user.is_authenticated and not user.is_staff) else None
            Visita.objects.create(
                path=path[:255],
                consulta=request.GET.urlencode()[:255],
                ip=ip or None,
                user_agent=request.META.get('HTTP_USER_AGENT', '')[:255],
                referer=request.META.get('HTTP_REFERER', '')[:255],
                sesion=sesion[:64],
                usuario=gu,
                inicio=inicio,
            )
        except Exception:
            pass
        return response


class LoginPermisoMiddleware:
    """Exige sesión iniciada y permiso por rol en toda ruta no pública."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if path.startswith(PREFIJOS_PUBLICOS) or path in RUTAS_PUBLICAS:
            return self.get_response(request)

        if not request.user.is_authenticated:
            login_url = settings.LOGIN_URL
            return HttpResponseRedirect(
                '{}?next={}'.format(login_url, quote(request.get_full_path()))
            )

        try:
            url_name = resolve(path).url_name
        except Resolver404:
            return self.get_response(request)

        permiso = PERMISO_POR_URL.get(url_name)
        if permiso is None:
            return self.get_response(request)
        if permiso == '__staff__':
            if not request.user.is_staff:
                raise PermissionDenied
            return self.get_response(request)
        if not request.user.tiene_permiso(permiso):
            raise PermissionDenied

        return self.get_response(request)
