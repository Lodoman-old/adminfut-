from django.db.models import Count, Q

from .models import Partido, Jugador, Gol, Tarjeta, JugadorPartido, JugadorEquipo


def procesar_cedula(partido, post_data, user):
    """Procesa el guardado de una cédula arbitral.

    post_data: objeto con .get(key, default) e .items() (dict o QueryDict).
    Retorna dict con ok, errors, warnings, finalizado, default_local, default_visitante.
    """
    errors = []
    warnings = []

    if partido.estado == "FIN" and not (user and user.tiene_permiso("partido_aperturar")):
        errors.append("No tienes permiso para modificar un partido finalizado.")
        return {"ok": False, "errors": errors, "warnings": warnings, "finalizado": False}

    arbitro_id = post_data.get("arbitro") or None
    if arbitro_id and partido.fecha_hora:
        duplicado = Partido.objects.filter(
            fecha_hora=partido.fecha_hora,
            arbitro_id=arbitro_id,
        ).exclude(pk=partido.pk).exists()
        if duplicado:
            errors.append(
                "El árbitro seleccionado ya está asignado a otro partido "
                "en esa fecha y horario."
            )
            return {"ok": False, "errors": errors, "warnings": warnings, "finalizado": False}

    default_local = post_data.get("defaultLocalCheck") == "on"
    default_visit = post_data.get("defaultVisitCheck") == "on"

    # Jugadores del equipo local (principal o secundario)
    local_jugador_ids = JugadorEquipo.objects.filter(
        equipo=partido.equipo_local, activo=True
    ).values_list("jugador_id", flat=True)
    jugadores_local = list(Jugador.objects.filter(
        Q(pk__in=local_jugador_ids) | Q(equipo=partido.equipo_local), activo=True
    ).select_related("equipo").distinct())

    # Jugadores del equipo visitante (principal o secundario)
    visit_jugador_ids = JugadorEquipo.objects.filter(
        equipo=partido.equipo_visitante, activo=True
    ).values_list("jugador_id", flat=True)
    jugadores_visit = list(Jugador.objects.filter(
        Q(pk__in=visit_jugador_ids) | Q(equipo=partido.equipo_visitante), activo=True
    ).select_related("equipo").distinct())

    jugadores_local_ids = {str(j.id) for j in jugadores_local}
    jugadores_visit_ids = {str(j.id) for j in jugadores_visit}

    # Suspensiones manuales: la categoría del partido no puede alinear a un jugador
    # suspendido (escalera → toda la escalera del mismo género; no escalera → su categoría).
    cat_partido = partido.temporada.categoria if partido.temporada_id else None
    if cat_partido is not None:
        suspendidos = {
            int(j.id): j
            for j in (jugadores_local + jugadores_visit)
            if j.suspension_que_bloquea(cat_partido)
        }
        if suspendidos:
            nombres = []
            for key, value in post_data.items():
                if key.startswith("participacion_") and value:
                    try:
                        jid = int(key.split("_")[1])
                    except (ValueError, IndexError):
                        continue
                else:
                    continue
                if jid in suspendidos:
                    j = suspendidos[jid]
                    nombres.append(f"{j.nombre} {j.apellido}".strip())
            if nombres:
                errors.append(
                    "No se puede registrar la participación de jugadores "
                    "suspendidos: " + ", ".join(sorted(set(nombres))) + "."
                )
                return {"ok": False, "errors": errors, "warnings": warnings, "finalizado": False}

    cuenta_local = 0
    cuenta_visit = 0
    for key, value in post_data.items():
        if key.startswith("participacion_") and value:
            jid = key.split("_")[1]
            if jid in jugadores_local_ids:
                cuenta_local += 1
            elif jid in jugadores_visit_ids:
                cuenta_visit += 1

    max_cambios = partido.temporada.limite_cambios_efectivo() if (partido.temporada_id and not partido.es_amistoso) else 99
    max_cambios = max_cambios if max_cambios is not None else 99
    max_tits = 99
    min_jugs = 0
    if not partido.es_amistoso and partido.temporada_id:
        min_jugs = partido.temporada.min_jugadores
        max_tits = partido.temporada.max_titulares or 11
        if not default_local and not default_visit:
            if cuenta_local < min_jugs:
                errors.append(f"{partido.equipo_local.nombre} solo tiene {cuenta_local} jugadores en cédula (mínimo {min_jugs}). Activa Default para este equipo o agrega más jugadores.")
            if cuenta_visit < min_jugs:
                errors.append(f"{partido.equipo_visitante.nombre} solo tiene {cuenta_visit} jugadores en cédula (mínimo {min_jugs}). Activa Default para este equipo o agrega más jugadores.")
            if errors:
                return {"ok": False, "errors": errors, "warnings": warnings, "finalizado": False}

    cambios_local = 0
    cambios_visit = 0
    for key, value in post_data.items():
        if key.startswith("participacion_") and value == "cambio":
            jid = key.split("_")[1]
            if jid in jugadores_local_ids:
                cambios_local += 1
            elif jid in jugadores_visit_ids:
                cambios_visit += 1
    if not default_local and cambios_local > max_cambios:
        default_local = True
        warnings.append(f"{partido.equipo_local.nombre} excede el límite de {max_cambios} cambios por partido. Se marca como Default.")
    if not default_visit and cambios_visit > max_cambios:
        default_visit = True
        warnings.append(f"{partido.equipo_visitante.nombre} excede el límite de {max_cambios} cambios por partido. Se marca como Default.")

    titulares_local = 0
    titulares_visit = 0
    for key, value in post_data.items():
        if key.startswith("participacion_") and value == "titular":
            jid = key.split("_")[1]
            if jid in jugadores_local_ids:
                titulares_local += 1
            elif jid in jugadores_visit_ids:
                titulares_visit += 1

    default_forzado_local = False
    default_forzado_visit = False
    if not default_local and titulares_local > max_tits:
        default_local = True
        default_forzado_local = True
        warnings.append(f"{partido.equipo_local.nombre} tiene {titulares_local} titulares (máximo {max_tits}). Alineación indebida. Se marca como Default.")
    if not default_visit and titulares_visit > max_tits:
        default_visit = True
        default_forzado_visit = True
        warnings.append(f"{partido.equipo_visitante.nombre} tiene {titulares_visit} titulares (máximo {max_tits}). Alineación indebida. Se marca como Default.")

    Gol.objects.filter(partido=partido).delete()
    for key, value in post_data.items():
        if key.startswith("gol_"):
            partes = key.split("_")
            jugador_id = int(partes[1])
            if value and str(value).strip():
                cantidad = int(value) if str(value).isdigit() else 0
                for _ in range(cantidad):
                    Gol.objects.create(
                        partido=partido,
                        jugador_id=jugador_id,
                        equipo_id=post_data.get(f"equipo_{jugador_id}"),
                        minuto=0,
                    )

    Tarjeta.objects.filter(partido=partido).delete()
    for key, value in post_data.items():
        if key.startswith("tarjeta_") and value:
            partes = key.split("_")
            if len(partes) < 3:
                continue
            jugador_id = int(partes[1])
            tipo = partes[2]
            if tipo in ("AMARILLA", "ROJA"):
                Tarjeta.objects.create(
                    partido=partido,
                    jugador_id=jugador_id,
                    equipo_id=post_data.get(f"equipo_{jugador_id}"),
                    tipo=tipo,
                    minuto=0,
                )

    duplas = (Tarjeta.objects.filter(partido=partido, tipo="AMARILLA")
              .values("jugador_id")
              .annotate(cnt=Count("id"))
              .filter(cnt__gte=2))
    for entry in duplas:
        if not Tarjeta.objects.filter(partido=partido, jugador_id=entry["jugador_id"], tipo="ROJA").exists():
            equipo_id = Jugador.objects.get(id=entry["jugador_id"]).equipo_id
            Tarjeta.objects.create(partido=partido, jugador_id=entry["jugador_id"], equipo_id=equipo_id, tipo="ROJA", minuto=0)

    for key, value in post_data.items():
        if key.startswith("suspension_") and value and str(value).strip():
            jid = int(key.split("_")[1])
            try:
                roja = Tarjeta.objects.get(partido=partido, jugador_id=jid, tipo="ROJA")
                roja.suspension_jornadas = int(value)
                roja.save()
            except (Tarjeta.DoesNotExist, ValueError):
                pass

    JugadorPartido.objects.filter(partido=partido).delete()
    for key, value in post_data.items():
        if key.startswith("participacion_") and value:
            jid = int(key.split("_")[1])
            JugadorPartido.objects.create(
                partido_id=partido.id,
                jugador_id=jid,
                equipo_id=post_data.get(f"equipo_{jid}"),
                titular=value == "titular",
            )

    goles_local = Gol.objects.filter(partido=partido, equipo=partido.equipo_local).count()
    goles_visit = Gol.objects.filter(partido=partido, equipo=partido.equipo_visitante).count()
    Partido.objects.filter(pk=partido.pk).update(goles_local=goles_local, goles_visitante=goles_visit)

    if not default_forzado_local:
        default_local = post_data.get("defaultLocalCheck") == "on"
    if not default_forzado_visit:
        default_visit = post_data.get("defaultVisitCheck") == "on"

    if default_forzado_local:
        motivo_default_local = "Alineación indebida"
    else:
        motivo_default_local = str(post_data.get("motivo_default_local", "")).strip()
    if default_forzado_visit:
        motivo_default_visit = "Alineación indebida"
    else:
        motivo_default_visit = str(post_data.get("motivo_default_visitante", "")).strip()

    goles_default = partido.temporada.goles_default if partido.temporada_id else 1
    if default_local or default_visit:
        if default_forzado_local or default_forzado_visit:
            update_kwargs = {}
        else:
            update_kwargs = {"estado": "FIN"}
        # El partido por default no se juega: liberar el campo
        update_kwargs["campo"] = None
        # Las dos banderas se escriben SIEMPRE, no solo la de la casilla marcada:
        # antes solo se escribía la marcada y la otra quedaba pegada del guardado
        # anterior, dejando partidos con default en los dos equipos (los dos
        # perdian puntos y la leyenda anunciaba al ganador equivocado).
        update_kwargs["default_team"] = "local" if default_local else None
        update_kwargs["default_visitante"] = bool(default_visit)
        motivos = [m for m in (motivo_default_local, motivo_default_visit) if m]
        update_kwargs["motivo_default"] = " / ".join(motivos)
        if default_local and default_visit:
            # Ambos equipos pierden por default: nadie gana.
            update_kwargs["goles_local"] = 0
            update_kwargs["goles_visitante"] = 0
        elif default_local:
            update_kwargs["goles_local"] = 0
            update_kwargs["goles_visitante"] = goles_default
        else:
            update_kwargs["goles_visitante"] = 0
            update_kwargs["goles_local"] = goles_default
        Partido.objects.filter(pk=partido.pk).update(**update_kwargs)
        if default_forzado_local or default_forzado_visit:
            Partido.objects.filter(pk=partido.pk).update(estado=partido.estado if partido.estado != "FIN" else "PEND")
        Gol.objects.filter(partido=partido).delete()
        Tarjeta.objects.filter(partido=partido).delete()
    else:
        Partido.objects.filter(pk=partido.pk).update(
            default_team=None,
            default_visitante=False,
            motivo_default="",
        )

    if arbitro_id:
        Partido.objects.filter(pk=partido.pk).update(arbitro_id=arbitro_id)
    finalizado = False
    if post_data.get("finalizar") == "1" and not (default_forzado_local or default_forzado_visit):
        Partido.objects.filter(pk=partido.pk).update(estado="FIN")
        finalizado = True
        try:
            from .push import notify_partido_finalizado
            partido.refresh_from_db()
            notify_partido_finalizado(partido)
        except Exception:
            pass

    return {
        "ok": True,
        "errors": errors,
        "warnings": warnings,
        "finalizado": finalizado,
        "default_local": default_local,
        "default_visitante": default_visit,
    }
