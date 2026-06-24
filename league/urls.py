from django.urls import path
from . import views
from . import api_views

urlpatterns = [
    path("categorias/", views.CategoriaListView.as_view(), name="categoria_list"),
    path("categorias/nueva/", views.CategoriaCreateView.as_view(), name="categoria_create"),
    path("categorias/<int:pk>/editar/", views.CategoriaUpdateView.as_view(), name="categoria_update"),
    path("categorias/<int:pk>/eliminar/", views.CategoriaDeleteView.as_view(), name="categoria_delete"),

    path("equipos/", views.EquipoListView.as_view(), name="equipo_list"),
    path("equipos/nuevo/", views.EquipoCreateView.as_view(), name="equipo_create"),
    path("equipos/<int:pk>/editar/", views.EquipoUpdateView.as_view(), name="equipo_update"),
    path("equipos/<int:pk>/eliminar/", views.EquipoDeleteView.as_view(), name="equipo_delete"),
    path("horarios-fijos/", views.horarios_fijos_report, name="horarios_fijos_report"),

    path("jugadores/", views.JugadorListView.as_view(), name="jugador_list"),
    path("jugadores/nuevo/", views.JugadorCreateView.as_view(), name="jugador_create"),
    path("jugadores/<int:pk>/editar/", views.JugadorUpdateView.as_view(), name="jugador_update"),
    path("jugadores/<int:pk>/eliminar/", views.JugadorDeleteView.as_view(), name="jugador_delete"),

    path("campos/", views.CampoListView.as_view(), name="campo_list"),
    path("campos/nuevo/", views.CampoCreateView.as_view(), name="campo_create"),
    path("campos/<int:pk>/editar/", views.CampoUpdateView.as_view(), name="campo_update"),
    path("campos/<int:pk>/eliminar/", views.CampoDeleteView.as_view(), name="campo_delete"),

    path("temporadas/", views.TemporadaListView.as_view(), name="temporada_list"),
    path("temporadas/nueva/", views.TemporadaCreateView.as_view(), name="temporada_create"),
    path("temporadas/<int:pk>/editar/", views.TemporadaUpdateView.as_view(), name="temporada_update"),
    path("temporadas/<int:pk>/finalizar/", views.finalizar_temporada, name="finalizar_temporada"),
    path("temporadas/<int:pk>/reabrir/", views.reabrir_temporada, name="reabrir_temporada"),
    path("temporadas/<int:pk>/iniciar/", views.iniciar_temporada, name="iniciar_temporada"),
    path("temporadas/<int:pk>/reiniciar/", views.reiniciar_temporada, name="reiniciar_temporada"),
    path("temporadas/<int:pk>/asignar-grupos/", views.asignar_grupos, name="asignar_grupos"),
    path("temporadas/<int:pk>/confirmar-grupos/", views.confirmar_grupos, name="confirmar_grupos"),
    path("temporadas/<int:pk>/generar-liguilla/", views.generar_liguilla_view, name="generar_liguilla"),
    path("temporadas/<int:pk>/publicar-campeon/", views.publicar_campeon_view, name="publicar_campeon"),
    path("temporadas/<int:pk>/equipos/", views.temporada_equipos, name="temporada_equipos"),
    path("temporadas/<int:pk>/abandonar/<int:equipo_pk>/", views.marcar_abandono, name="marcar_abandono"),
    path("temporadas/<int:pk>/reincorporar/<int:equipo_pk>/", views.desmarcar_abandono, name="desmarcar_abandono"),

    path("jornadas/", views.JornadaListView.as_view(), name="jornada_list"),
    path("jornadas/<int:jornada_id>/suspender/", views.suspender_jornada, name="suspender_jornada"),
    path("jornadas/<int:jornada_id>/reactivar/", views.reactivar_jornada, name="reactivar_jornada"),

    path("periodo-altas/", views.PeriodoAltasListView.as_view(), name="periodoaltas_list"),
    path("periodo-altas/nuevo/", views.PeriodoAltasCreateView.as_view(), name="periodoaltas_create"),
    path("periodo-altas/<int:pk>/editar/", views.PeriodoAltasUpdateView.as_view(), name="periodoaltas_update"),
    path("periodo-altas/<int:pk>/eliminar/", views.PeriodoAltasDeleteView.as_view(), name="periodoaltas_delete"),
    path("periodo-altas/<int:pk>/gestionar/", views.gestionar_altas_bajas, name="gestionar_altas_bajas"),

    path("partidos/", views.PartidoListView.as_view(), name="partido_list"),
    path("partidos/nuevo/", views.PartidoCreateView.as_view(), name="partido_create"),
    path("partidos/<int:pk>/editar/", views.PartidoUpdateView.as_view(), name="partido_update"),
    path("partidos/<int:pk>/eliminar/", views.PartidoDeleteView.as_view(), name="partido_delete"),

    path("arbitros/", views.ArbitroListView.as_view(), name="arbitro_list"),
    path("arbitros/nuevo/", views.ArbitroCreateView.as_view(), name="arbitro_create"),
    path("arbitros/<int:pk>/editar/", views.ArbitroUpdateView.as_view(), name="arbitro_update"),
    path("arbitros/<int:pk>/eliminar/", views.ArbitroDeleteView.as_view(), name="arbitro_delete"),

    path("tabla-posiciones/", views.tabla_posiciones, name="tabla_posiciones"),
    path("tabla-goleo/", views.tabla_goleo, name="tabla_goleo"),
    path("tabla-tarjetas/", views.tabla_tarjetas, name="tabla_tarjetas"),
    path("tabla-castigados/", views.tabla_castigados, name="tabla_castigados"),
    path("api/equipos-categoria/", views.api_equipos_categoria, name="api_equipos_categoria"),

    path("cedula-arbitral/<int:partido_id>/", views.cedula_arbitral, name="cedula_arbitral"),

    path("configuracion/", views.configuracion_liga, name="configuracion_liga"),
    path("suscripcion/", views.suscripcion_email, name="suscripcion_email"),
    path("enviar-roles/<int:temporada_id>/", views.enviar_roles_semana, name="enviar_roles_semana"),
    path("enviar-rol-jornada/<int:jornada_id>/", views.enviar_rol_jornada, name="enviar_rol_jornada"),
    path("publicar-jornada-facebook/<int:jornada_id>/", views.publicar_jornada_facebook, name="publicar_jornada_facebook"),
    path("enviar-estadisticas/<int:temporada_id>/", views.enviar_estadisticas, name="enviar_estadisticas"),
    path("partidos/<int:pk>/reagendar/", views.reagendar_partido, name="reagendar_partido"),
    path("partidos/<int:pk>/observaciones/", views.guardar_observaciones, name="guardar_observaciones"),
    path("reporte-semanal/", views.reporte_semanal, name="reporte_semanal"),
    path("gestionar-indisponibilidad/", views.gestionar_indisponibilidad, name="gestionar_indisponibilidad"),
    path("publicar-rol-facebook/<int:temporada_id>/", views.publicar_rol_facebook, name="publicar_rol_facebook"),
    path("publicar-posiciones-facebook/<int:temporada_id>/", views.publicar_posiciones_facebook, name="publicar_posiciones_facebook"),
    path("api/register-device/", api_views.register_device_token, name="register_device_token"),
    path("api/unregister-device/", api_views.unregister_device_token, name="unregister_device_token"),
    path("api/register-guest/", api_views.register_guest_device, name="register_guest_device"),
    path("api/update-preferences/", api_views.update_device_preferences, name="update_device_preferences"),
    path("api/categorias/", api_views.lista_categorias, name="api_categorias"),
    path("api/cron-notificar-arbitros/", api_views.cron_notificar_arbitros, name="cron_notificar_arbitros"),
]
