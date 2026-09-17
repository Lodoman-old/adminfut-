from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Categoria, Equipo, Jugador, JugadorEquipo, Campo, Temporada, Partido, Gol, Jornada, PeriodoAltas, Tarjeta, SuspensionJugador, MovimientoEquipo, CampoIndisponibilidad, ConfiguracionLiga, DeviceToken, PushLog, JugadorHerencia, Anuncio, AnuncioClick, AnuncioImpresion, PronosticoQuiniela, Descarga


@admin.register(ConfiguracionLiga)
class ConfiguracionLigaAdmin(admin.ModelAdmin):
    list_display = ["nombre_liga", "correo_electronico"]

    def has_add_permission(self, request):
        # Solo permitir crear si no existe ya
        return not ConfiguracionLiga.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "activo", "curp_obligatoria"]


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "categoria", "activo"]
    list_filter = ["categoria"]


@admin.register(Jugador)
class JugadorAdmin(admin.ModelAdmin):
    list_display = ["nombre", "apellido", "tipo_documento", "curp", "posicion", "equipo", "dorsal", "suspendido_pago", "equipos_extra"]
    list_filter = ["equipo__categoria", "posicion", "suspendido_pago"]
    search_fields = ["curp", "nombre", "apellido"]

    def equipos_extra(self, obj):
        extras = obj.registros_equipo.filter(es_principal=False)
        if extras:
            return ", ".join(r.equipo.nombre for r in extras)
        return "-"
    equipos_extra.short_description = "Equipos compatibles"


@admin.register(JugadorEquipo)
class JugadorEquipoAdmin(admin.ModelAdmin):
    list_display = ["jugador", "equipo", "es_principal", "activo"]
    list_filter = ["equipo__categoria", "es_principal"]


@admin.register(Campo)
class CampoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "precio_hora", "activo"]


@admin.register(Jornada)
class JornadaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "temporada", "numero"]
    list_filter = ["temporada"]


@admin.register(PeriodoAltas)
class PeriodoAltasAdmin(admin.ModelAdmin):
    list_display = ["temporada", "tipo", "activo", "extraordinario"]
    list_filter = ["temporada"]


@admin.register(Temporada)
class TemporadaAdmin(admin.ModelAdmin):
    list_display = ["nombre", "categoria", "fecha_inicio", "fecha_fin", "activa", "iniciada", "btn_iniciar"]
    list_filter = ["categoria", "tipo_competencia", "ida_vuelta"]
    fieldsets = [
        (None, {
            "fields": ["nombre", "categoria", "fecha_inicio", "fecha_fin", "activa", "es_prueba"],
        }),
        ("Configuración de Juego", {
            "fields": ["goles_default", "min_jugadores", "cambios_permitidos", "max_titulares", "jornadas_limite_pago"],
        }),
        ("Fixture", {
            "fields": ["tipo_rol", "vueltas", "num_grupos", "tipo_competencia", "num_clasificados"],
        }),
        ("Liguilla y Desempates (Nuevo)", {
            "fields": ["ida_vuelta", "gol_visitante_desempate", "posicion_tabla_desempate"],
        }),
        ("Finalización", {
            "fields": ["finalizada", "fecha_finalizacion", "motivo_finalizacion"],
        }),
    ]

    def btn_iniciar(self, obj):
        if not obj.iniciada:
            url = reverse("iniciar_temporada", args=[obj.pk])
            return format_html('<a class="button" href="{}">Iniciar Temporada</a>', url)
        return "Iniciada"
    btn_iniciar.short_description = "Acción"


class GolInline(admin.TabularInline):
    model = Gol
    extra = 1


class TarjetaInline(admin.TabularInline):
    model = Tarjeta
    extra = 1


@admin.register(Partido)
class PartidoAdmin(admin.ModelAdmin):
    list_display = [
        "jornada", "equipo_local", "equipo_visitante", "marcador", "campo",
        "fecha_hora", "temporada", "estado"
    ]
    list_filter = ["temporada", "jornada", "estado"]
    inlines = [GolInline, TarjetaInline]

    def marcador(self, obj):
        return f"{obj.goles_local} - {obj.goles_visitante}"
    marcador.short_description = "Marcador"


@admin.register(Gol)
class GolAdmin(admin.ModelAdmin):
    list_display = ["jugador", "equipo", "partido", "minuto", "tipo"]


@admin.register(Tarjeta)
class TarjetaAdmin(admin.ModelAdmin):
    list_display = ["jugador", "tipo", "partido", "minuto"]
    list_filter = ["tipo"]


@admin.register(SuspensionJugador)
class SuspensionJugadorAdmin(admin.ModelAdmin):
    list_display = ["jugador", "categoria", "equipo", "jornadas", "restantes", "activo", "creado"]
    list_filter = ["categoria", "activo"]
    search_fields = ["jugador__nombre", "jugador__apellido"]

    @admin.display(description="Restantes")
    def restantes(self, obj):
        return obj.restantes()


@admin.register(JugadorHerencia)
class JugadorHerenciaAdmin(admin.ModelAdmin):
    list_display = ["jugador", "tipo", "categoria", "jornadas", "activo", "creado"]
    list_filter = ["tipo", "categoria", "activo"]
    search_fields = ["jugador__nombre", "jugador__apellido"]


@admin.register(CampoIndisponibilidad)
class CampoIndisponibilidadAdmin(admin.ModelAdmin):
    list_display = ["campo", "fecha_desde", "fecha_hasta", "motivo"]
    list_filter = ["campo"]


@admin.register(MovimientoEquipo)
class MovimientoEquipoAdmin(admin.ModelAdmin):
    list_display = ["equipo", "temporada", "tipo", "origen_categoria", "destino_categoria", "jugadores_plantilla", "regla_activa", "cupo_porcentaje"]
    list_filter = ["temporada", "tipo", "origen_categoria", "regla_activa"]
    search_fields = ["equipo__nombre"]
    list_editable = ["regla_activa", "cupo_porcentaje"]


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ["token_short", "device_id_short", "nombre", "es_invitado", "usuario", "plataforma", "activo", "creado"]
    list_filter = ["plataforma", "activo", "es_invitado"]
    search_fields = ["token", "device_id", "usuario__username", "nombre"]
    filter_horizontal = ["categorias"]

    def token_short(self, obj):
        return obj.token[:30] + "..."
    token_short.short_description = "Token"

    def device_id_short(self, obj):
        return obj.device_id[:8] + "..." if obj.device_id else "-"
    device_id_short.short_description = "Device"


@admin.register(PushLog)
class PushLogAdmin(admin.ModelAdmin):
    list_display = ["hora", "tipo", "partido_id", "categoria", "success", "failure"]
    list_filter = ["tipo"]
    readonly_fields = ["hora", "tipo", "partido_id", "categoria", "total_activos", "tokens_encontrados", "guests_incluidos", "success", "failure", "detalle", "error"]
    has_add_permission = lambda self, request: False
    has_change_permission = lambda self, request, obj=None: False
    has_delete_permission = lambda self, request, obj=None: False


@admin.register(Anuncio)
class AnuncioAdmin(admin.ModelAdmin):
    list_display = ["titulo", "tamano", "activo", "vigencia", "impresiones", "clics", "clic_ratio", "orden"]
    list_filter = ["tamano", "activo"]
    search_fields = ["titulo", "descripcion"]
    list_editable = ["tamano", "activo", "orden"]
    readonly_fields = ["impresiones", "clics"]

    def vigencia(self, obj):
        if obj.fecha_inicio and obj.fecha_fin:
            return f"{obj.fecha_inicio:%d/%m/%Y} - {obj.fecha_fin:%d/%m/%Y}"
        if obj.fecha_inicio:
            return f"Desde {obj.fecha_inicio:%d/%m/%Y}"
        if obj.fecha_fin:
            return f"Hasta {obj.fecha_fin:%d/%m/%Y}"
        return "Sin límite"
    vigencia.short_description = "Vigencia"

    def clic_ratio(self, obj):
        if not obj.impresiones:
            return "0%"
        return f"{obj.clics / obj.impresiones * 100:.1f}%"
    clic_ratio.short_description = "CTR"


@admin.register(AnuncioClick)
class AnuncioClickAdmin(admin.ModelAdmin):
    list_display = ["anuncio", "fecha", "ip", "sesion"]
    list_filter = ["anuncio"]
    readonly_fields = ["anuncio", "ip", "sesion", "fecha"]
    has_add_permission = lambda self, request: False
    has_change_permission = lambda self, request, obj=None: False
    has_delete_permission = lambda self, request, obj=None: False


@admin.register(AnuncioImpresion)
class AnuncioImpresionAdmin(admin.ModelAdmin):
    list_display = ["anuncio", "fecha", "clave", "creado"]
    list_filter = ["anuncio"]
    readonly_fields = ["anuncio", "fecha", "clave", "creado"]
    date_hierarchy = "fecha"
    has_add_permission = lambda self, request: False
    has_change_permission = lambda self, request, obj=None: False
    has_delete_permission = lambda self, request, obj=None: False


@admin.register(Descarga)
class DescargaAdmin(admin.ModelAdmin):
    list_display = ["tipo", "fecha", "usuario", "ip"]
    list_filter = ["tipo"]
    search_fields = ["ip", "user_agent"]
    readonly_fields = ["tipo", "ip", "user_agent", "referer", "sesion", "usuario", "fecha"]
    date_hierarchy = "fecha"
    has_add_permission = lambda self, request: False
    has_change_permission = lambda self, request, obj=None: False
    has_delete_permission = lambda self, request, obj=None: False


@admin.register(PronosticoQuiniela)
class PronosticoQuinielaAdmin(admin.ModelAdmin):
    list_display = ["usuario", "partido", "goles_local", "goles_visitante", "puntos", "creado", "actualizado"]
    list_filter = ["partido__temporada__categoria"]
    search_fields = ["usuario__username", "partido__equipo_local__nombre", "partido__equipo_visitante__nombre"]
    readonly_fields = ["goles_local", "goles_visitante", "puntos"]
    date_hierarchy = "creado"
    list_per_page = 25

    @admin.display(description="Puntos")
    def puntos(self, obj):
        return obj.puntos
