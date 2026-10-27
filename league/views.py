
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
    if temp:
        ultimos = list(
            partidos.filter(estado="FIN")
            .order_by("-fecha_hora")[:5]
        )

    # Próximos
    proximos = []
    if temp:
        proximos = list(
            partidos.filter(estado__in=("PEND", "PROG"))
            .order_by("fecha_hora")[:5]
        )

    # Goles por jugador
    goles_jug = []
    if temp:
        goles_jug = list(
            Gol.objects.filter(partido__temporada=temp, equipo=equipo)
            .values("jugador_id", "jugador__nombre", "jugador__apellido", "jugador__foto", "jugador__dorsal")
            .annotate(total=Count("id"))
            .order_by("-total", "jugador__apellido", "jugador__nombre")
        )
        for g in goles_jug:
            g["foto_url"] = url_para_nombre(g.get("jugador__foto"))

    # Tarjetas
    tarjetas_jug = []
    if temp:
        amar = (
            Tarjeta.objects.filter(partido__temporada=temp, equipo=equipo, tipo="AMARILLA")
            .values("jugador_id", "jugador__nombre", "jugador__apellido", "jugador__foto", "jugador__dorsal")
            .annotate(total=Count("id"))
        )
        rojas = (
            Tarjeta.objects.filter(partido__temporada=temp, equipo=equipo, tipo="ROJA")
            .values("jugador_id", "jugador__nombre", "jugador__apellido", "jugador__foto", "jugador__dorsal")
            .annotate(total=Count("id"))
        )
        acc_t = {}
        for t in amar:
            key = t["jugador_id"]
            acc_t[key] = dict(t, amarillas=t["total"], rojas=0)
            acc_t[key]["foto_url"] = url_para_nombre(t.get("jugador__foto"))
        for t in rojas:
            key = t["jugador_id"]
            if key in acc_t:
                acc_t[key]["rojas"] = t["total"]
            else:
                acc_t[key] = dict(t, amarillas=0, rojas=t["total"])
                acc_t[key]["foto_url"] = url_para_nombre(t.get("jugador__foto"))
        tarjetas_jug = sorted(acc_t.values(), key=lambda x: (-(x["amarillas"] + x["rojas"]), x["jugador__apellido"] or ""))

    # Foto de jugadores
    jugadores_list = []
    for j in jugadores:
        jugadores_list.append({
            "obj": j,
            "foto_url": url_para_nombre(j.foto.name if j.foto else None),
            "edad": j.edad(),
        })

    return render(request, "league/equipo_ficha.html", {
        "equipo": equipo,
        "categoria": categoria,
        "temporada": temp,
        "jugadores": jugadores_list,
        "pj": pj, "pg": pg, "pe": pe, "pp": pp, "gf": gf, "gc": gc, "dif": dif, "pts": pts,
        "ultimos": ultimos,
        "proximos": proximos,
        "goleadores": goles_jug,
        "tarjetas": tarjetas_jug,
    })
