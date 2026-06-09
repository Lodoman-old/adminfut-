from django.shortcuts import render
from django.db.models import Sum, Count
from league.models import Partido, Gol, Categoria, Temporada, Equipo, Tarjeta
from finance.models import Ingreso


def home(request):
    categorias = Categoria.objects.filter(activo=True)

    cat_id = request.GET.get("categoria")
    default_cat = Categoria.objects.filter(es_principal=True).first()
    if cat_id:
        categoria_sel = Categoria.objects.filter(id=cat_id).first()
    else:
        categoria_sel = default_cat or categorias.first()

    if categoria_sel:
        temp_activa = Temporada.objects.filter(
            categoria=categoria_sel, activa=True
        ).first()
    else:
        temp_activa = None

    # Próximos partidos: solo de la jornada activa (la primera con partidos pendientes)
    from league.models import Jornada
    if temp_activa:
        jornada_activa = (
            Jornada.objects.filter(temporada=temp_activa, partidos__estado="PEND")
            .distinct()
            .order_by("numero")
            .first()
        )
        if jornada_activa:
            proximos = Partido.objects.filter(
                temporada=temp_activa, jornada=jornada_activa, estado="PEND"
            ).select_related(
                "equipo_local", "equipo_visitante", "campo", "jornada"
            ).order_by("fecha_hora")
        else:
            proximos = []
    else:
        proximos = []

    # Resultados recientes de la categoría
    res_filter = Partido.objects.filter(estado="FIN")
    if categoria_sel:
        res_filter = res_filter.filter(temporada__categoria=categoria_sel)

    resultados = res_filter.select_related(
        "equipo_local", "equipo_visitante"
    ).order_by("-fecha_hora")[:5]

    # Stats por categoría seleccionada
    stats = {}
    if categoria_sel:
        temp_id = temp_activa.id if temp_activa else None
        stats[categoria_sel] = {
            "equipos": Equipo.objects.filter(categoria=categoria_sel, activo=True).count(),
            "partidos_fin": Partido.objects.filter(
                temporada__categoria=categoria_sel, estado="FIN"
            ).count(),
            "partidos_pend": Partido.objects.filter(
                temporada__categoria=categoria_sel, estado="PEND"
            ).count(),
            "jugadores": Equipo.objects.filter(
                categoria=categoria_sel, activo=True
            ).aggregate(total=Count("jugadores"))["total"] or 0,
            "categoria": categoria_sel,
            "temporada_activa": temp_activa,
            "temp_id": temp_id,
        }

    # Top goleadores con datos para cards (separados por liguilla)
    def _build_top_goleadores(es_liguilla):
        qs = Gol.objects.filter(partido__es_liguilla=es_liguilla)
        if categoria_sel:
            qs = qs.filter(partido__temporada__categoria=categoria_sel)
        return list(
            qs
            .values(
                "jugador__id", "jugador__nombre", "jugador__apellido",
                "jugador__foto", "jugador__dorsal",
                "equipo__nombre", "equipo__logo",
            )
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )

    top_goleadores = _build_top_goleadores(False)   # temporada regular
    top_goleadores_finales = _build_top_goleadores(True)  # liguilla / finales

    # Top tarjetas amarillas
    amar_filter = Tarjeta.objects.filter(tipo="AMARILLA")
    rojas_filter = Tarjeta.objects.filter(tipo="ROJA")
    if categoria_sel:
        amar_filter = amar_filter.filter(partido__temporada__categoria=categoria_sel)
        rojas_filter = rojas_filter.filter(partido__temporada__categoria=categoria_sel)

    top_amarillas = (
        amar_filter
        .values(
            "jugador__id", "jugador__nombre", "jugador__apellido",
            "jugador__foto", "jugador__dorsal",
            "equipo__nombre", "equipo__logo",
        )
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    top_rojas = (
        rojas_filter
        .values(
            "jugador__id", "jugador__nombre", "jugador__apellido",
            "jugador__foto", "jugador__dorsal",
            "equipo__nombre", "equipo__logo",
        )
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    # Castigados — jugadores con roja y suspension_jornadas > 0
    cast_filter = Tarjeta.objects.filter(tipo="ROJA", suspension_jornadas__gt=0)
    if categoria_sel:
        cast_filter = cast_filter.filter(partido__temporada__categoria=categoria_sel)
    castigados = (
        cast_filter
        .select_related("jugador", "equipo", "partido__jornada")
        .order_by("-partido__fecha_hora")
    )

    finanzas_visible = (
        request.user.is_authenticated
        and request.user.rol
        and request.user.rol.permisos.get("ver_finanzas", False)
    )

    ingresos_data = None
    if finanzas_visible:
        ingresos_mes = (
            Ingreso.objects.filter(fecha__month=1)
            .aggregate(total=Sum("monto"))
        )
        ingresos_data = {
            "total_mes": ingresos_mes["total"] or 0,
            "por_concepto": (
                Ingreso.objects.values("concepto__nombre")
                .annotate(total=Sum("monto"))
                .order_by("-total")[:5]
            ),
        }

    return render(request, "home.html", {
        "proximos": proximos,
        "resultados": resultados,
        "stats": stats,
        "top_goleadores": top_goleadores,
        "top_goleadores_finales": top_goleadores_finales,
        "top_amarillas": top_amarillas,
        "top_rojas": top_rojas,
        "castigados": castigados,
        "categorias": categorias,
        "categoria_sel": categoria_sel,
        "finanzas_visible": finanzas_visible,
        "ingresos_data": ingresos_data,
    })
