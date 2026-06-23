from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from .models import Categoria, Equipo, Jugador, JugadorEquipo, Campo, Temporada, Partido, Gol, Jornada, PeriodoAltas, Tarjeta, CampoIndisponibilidad, ConfiguracionLiga, DeviceToken


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
    list_display = ["nombre", "activo"]


@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "categoria", "activo"]
    list_filter = ["categoria"]


@admin.register(Jugador)
class JugadorAdmin(admin.ModelAdmin):
    list_display = ["nombre", "apellido", "curp", "posicion", "equipo", "dorsal", "suspendido_pago", "equipos_extra"]
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


@admin.register(CampoIndisponibilidad)
class CampoIndisponibilidadAdmin(admin.ModelAdmin):
    list_display = ["campo", "fecha_desde", "fecha_hasta", "motivo"]
    list_filter = ["campo"]


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ["token_short", "nombre", "es_invitado", "usuario", "plataforma", "activo", "creado"]
    list_filter = ["plataforma", "activo", "es_invitado"]
    search_fields = ["token", "usuario__username", "nombre"]
    filter_horizontal = ["categorias"]

    def token_short(self, obj):
        return obj.token[:30] + "..."
    token_short.short_description = "Token"
