def equipo_ficha(request, pk):
    """Ficha pública de equipo: estadísticas, plantilla, goleadores, tarjetas, resultados."""
    from django.db.models import Count, Q, Sum
    from collections import Counter, defaultdict

    equipo = get_object_or_404(Equipo, pk=pk)
    categoria = equipo.categoria

    # Temporada activa o más reciente de esta categoría
    temp = (
        Temporada.objects.filter(categoria=categoria)
        .order_by("-iniciada", "-fecha_inicio", "-id")
        .first()
    )

    # Plantilla: jugadores con registro activo en este equipo (principal o secundario)
    jug_ids_reg = JugadorEquipo.objects.filter(equipo=equipo, activo=True).values_list(
        "jugador_id", flat=True
    )
    jugadores = (
        Jugador.objects.filter(
            Q(pk__in=jug_ids_reg) | Q(equipo=equipo)
        )
        .filter(activo=True)
        .select_related("equipo")
        .distinct()
        .order_by("apellido", "nombre")
    )

    # Partidos del equipo en esa temporada
    partidos = Partido.objects.none()
    if temp:
        partidos = (
            Partido.objects.filter(temporada=temp)
            .filter(Q(equipo_local=equipo) | Q(equipo_visitante=equipo))
            .select_related("equipo_local", "equipo_visitante", "jornada", "campo")
            .order_by("fecha_hora")
        )

    pj = pg = pe = pp = gf = gc = 0
    for p in partidos.filter(estado="FIN"):
        pj += 1
        gl, gv = p.goles_local or 0, p.goles_visitante or 0
        if p.equipo_local_id == equipo.id:
            gf += gl
            gc += gv
            if gl > gv:
                pg += 1
            elif gl == gv:
                pe += 1
            else:
                pp += 1
        else:
            gf += gv
            gc += gl
            if gv > gl:
                pg += 1
            elif gv == gl:
                pe += 1
            else:
                pp += 1

    dif = gf - gc
    pts = pg * 3 + pe * 1

    # Últimos resultados
    ultimos = []
   