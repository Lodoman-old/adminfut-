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
    '/accounts/login/',
    '/accounts/invitado/registro/',
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
)

# url_name -> permiso(s) requerido(s). '__staff__' exige is_staff.
PERMISO_POR_URL = {
    # Gestión - Categorías
    'categoria_list': 'gestion_categorias',
    'categoria_create': 'categoria_crear',
    'categoria_update': 'categoria_editar',
    'categoria_delete': 'categoria_eliminar',
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
    'cedula_arbitral': 'partido_cedula',
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
    'reporte_cedula_arbitral_pdf': 'partido_cedula',
    'reporte_cedula_arbitral_xlsx': 'partido_cedula',
    'horarios_fijos_report': 'reporte_horarios',
    # Configuración
    'configuracion_liga': 'gestion_configuracion',
    'test_database_connection': 'gestion_configuracion',
    'usuario_list': 'gestion_usuarios',
    'usuario_create': 'gestion_usuarios',
    'usuario_update': 'gestion_usuarios',
    'usuario_delete': 'gestion_usuarios',
    'rol_list': 'gestion_roles',
    'rol_create': 'gestion_roles',
    'rol_update': 'gestion_roles',
    'rol_delete': 'gestion_roles',
    'admin_push_logs': '__staff__',
}


class LoginPermisoMiddleware:
    """Exige sesión iniciada y permiso por rol en toda ruta no pública."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if path.startswith(PREFIJOS_PUBLICOS) or path in RUTAS_PUBLICAS:
            return self.get_response(request)

        # Invitados: pueden ver la cédula de partidos finalizados (solo lectura,
        # se valida dentro de la vista). Usuarios autenticados siguen pasando
        # por el control de permisos normal.
        if path.startswith('/cedula-arbitral/') and not request.user.is_authenticated:
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
