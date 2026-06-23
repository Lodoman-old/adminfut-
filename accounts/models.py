from django.contrib.auth.models import AbstractUser
from django.db import models


PERMISOS_MENU = {
    "Gestión": {
        "Categorías": [
            ("gestion_categorias", "Acceso a Categorías"),
            ("categoria_crear", "Crear Categorías"),
            ("categoria_editar", "Editar Categorías"),
            ("categoria_eliminar", "Eliminar Categorías"),
        ],
        "Equipos": [
            ("gestion_equipos", "Acceso a Equipos"),
            ("equipo_crear", "Crear Equipos"),
            ("equipo_editar", "Editar Equipos"),
            ("equipo_eliminar", "Eliminar Equipos"),
            ("equipo_abandonar", "Abandonar / Reincorporar"),
        ],
        "Jugadores": [
            ("gestion_jugadores", "Acceso a Jugadores"),
            ("jugador_crear", "Crear Jugadores"),
            ("jugador_editar", "Editar Jugadores"),
            ("jugador_eliminar", "Eliminar Jugadores"),
        ],
        "Campos": [
            ("gestion_campos", "Acceso a Campos"),
            ("campo_crear", "Crear Campos"),
            ("campo_editar", "Editar Campos"),
            ("campo_eliminar", "Eliminar Campos"),
        ],
        "Temporadas": [
            ("gestion_temporadas", "Acceso a Temporadas"),
            ("temporada_crear", "Crear Temporadas"),
            ("temporada_editar", "Editar Temporadas"),
            ("temporada_iniciar", "Iniciar Temporada"),
            ("temporada_finalizar", "Finalizar Temporada"),
            ("temporada_reiniciar", "Reiniciar Temporada"),
            ("temporada_liguilla", "Generar Liguilla"),
            ("temporada_equipos", "Gestionar Equipos por Temp."),
            ("temporada_enviar", "Enviar Correos (Roles/Stats)"),
        ],
        "Jornadas": [
            ("gestion_jornadas", "Acceso a Jornadas"),
            ("jornada_publicar", "Publicar en Facebook"),
            ("jornada_suspender", "Suspender / Reactivar Jornadas"),
        ],
        "Partidos": [
            ("gestion_partidos", "Acceso a Partidos"),
            ("partido_crear", "Crear Partidos"),
            ("partido_editar", "Editar Partidos"),
            ("partido_eliminar", "Eliminar Partidos"),
            ("partido_cedula", "Cédula Arbitral"),
            ("partido_reagendar", "Reagendar Partidos"),
            ("partido_observaciones", "Observaciones"),
            ("partido_indisponibilidad", "Indisponibilidad Campos"),
            ("partido_aperturar", "Aperturar Partido Finalizado"),
        ],
        "Períodos de Altas": [
            ("gestion_periodosaltas", "Acceso a Períodos de Altas"),
            ("periodoaltas_crear", "Crear Períodos de Altas"),
            ("periodoaltas_editar", "Editar Períodos de Altas"),
            ("periodoaltas_eliminar", "Eliminar Períodos de Altas"),
        ],
        "Árbitros": [
            ("gestion_arbitros", "Acceso a Árbitros"),
            ("arbitro_crear", "Crear Árbitros"),
            ("arbitro_editar", "Editar Árbitros"),
            ("arbitro_eliminar", "Eliminar Árbitros"),
        ],
    },
    "Finanzas": {
        "Acceso General": [
            ("ver_finanzas", "Acceso a Finanzas"),
        ],
        "Conceptos": [
            ("concepto_crear", "Crear Conceptos"),
            ("concepto_editar", "Editar Conceptos"),
            ("concepto_eliminar", "Eliminar Conceptos"),
        ],
        "Ingresos": [
            ("ingreso_crear", "Crear Ingresos"),
            ("ingreso_editar", "Editar Ingresos"),
            ("ingreso_eliminar", "Eliminar Ingresos"),
            ("ingreso_pos", "Punto de Venta"),
        ],
        "Caja": [
            ("caja_ver", "Acceso a Caja"),
            ("caja_aperturar", "Aperturar Caja"),
            ("caja_cerrar", "Cerrar Caja"),
            ("caja_corte", "Corte de Caja"),
        ],
    },
    "Configuración": {
        "General": [
            ("gestion_configuracion", "Configuración de Liga"),
            ("gestion_usuarios", "Usuarios del Sistema"),
            ("gestion_roles", "Roles y Permisos"),
        ],
    },
    "Reportes": {
        "Jornadas": [
            ("reporte_jornadas", "Juegos por Jornada", True),
            ("reporte_jornadas_completo", "Todos los Juegos", True),
            ("reporte_semanal", "Juegos de la Semana", True),
        ],
        "PDFs": [
            ("reporte_posiciones_pdf", "PDF de Posiciones", False),
            ("reporte_goleo_pdf", "PDF de Goleo", False),
            ("reporte_tarjetas_pdf", "PDF de Tarjetas", False),
            ("reporte_castigados_pdf", "PDF de Castigados", False),
            ("reporte_cedula_pdf", "PDF de Cédula Arbitral", False),
        ],
        "Suscriptores": [
            ("reporte_suscriptores", "Reporte de Suscriptores", False),
            ("reporte_horarios", "Reporte de Horarios Fijos", False),
        ],
        "Credenciales": [
            ("credenciales_ver", "Generar Credenciales", False),
        ],
    },
}


def get_permisos_flat():
    """Devuelve lista de (key, label, grupo, recurso, public)"""
    result = []
    for grupo, recursos in PERMISOS_MENU.items():
        for recurso, permisos in recursos.items():
            for entry in permisos:
                if len(entry) == 3:
                    key, label, public = entry
                else:
                    key, label = entry
                    public = False
                result.append((key, label, grupo, recurso, public))
    return result


class Rol(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    permisos = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Rol"
        verbose_name_plural = "Roles"

    def __str__(self):
        return self.nombre


class Usuario(AbstractUser):
    rol = models.ForeignKey(
        Rol, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="usuarios"
    )
    telefono = models.CharField(max_length=20, blank=True)
    categoria_preferida = models.ForeignKey(
        "league.Categoria", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="usuarios_preferencia", verbose_name="Categoría preferida"
    )

    class Meta:
        verbose_name = "Usuario"
        verbose_name_plural = "Usuarios"

    def tiene_permiso(self, permiso):
        if self.is_superuser:
            return True
        if not self.rol:
            return False
        return self.rol.permisos.get(permiso, False)

    @property
    def es_admin(self):
        return self.is_superuser
