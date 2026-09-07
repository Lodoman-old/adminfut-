"""Reglas de ascenso/descenso/desaparición para el registro de jugadores.

Cuando un equipo cierra una temporada con un movimiento (sube/baja/desaparece),
sus jugadores quedan restringidos al momento de registrarse en la siguiente
temporada:

* DESCENSO:    no pueden jugar en categorías por encima de la categoría a la
               que bajó el equipo (solo misma o más abajo).
* DESAPARECE:  solo pueden jugar en la categoría donde estaba el equipo o la
               inmediata inferior.
* ASCENSO:     quien se cambie a OTRO equipo solo puede hacerlo a equipos de la
               categoría a la que ascendió o la inmediata inferior, y solo el
               50% de la plantilla (los primeros que se registren).
"""

from .models import MovimientoEquipo


def movimientos_activos(jugador):
    """Último movimiento por equipo para los equipos del jugador (solo los que restringen)."""
    ids = set(jugador.registros_equipo.values_list("equipo_id", flat=True))
    if not ids:
        return []
    qs = (
        MovimientoEquipo.objects
        .filter(equipo_id__in=ids, temporada__aplicar_movimientos=True)
        .select_related("temporada", "origen_categoria", "destino_categoria", "equipo")
    )
    latest = {}
    for m in qs:
        prev = latest.get(m.equipo_id)
        if prev is None or (
            m.temporada.fecha_inicio, m.temporada_id
        ) > (prev.temporada.fecha_inicio, prev.temporada_id):
            latest[m.equipo_id] = m
    return [m for m in latest.values() if m.tipo != "SE_QUEDA"]


def errores_movimiento_jugador(jugador, equipo_destino, categoria_destino):
    """Devuelve lista de mensajes que impiden registrar al jugador (vacío = permitido)."""
    if categoria_destino is None or categoria_destino.nivel is None:
        return []
    nivel_dest = categoria_destino.nivel
    errs = []
    for mov in movimientos_activos(jugador):
        tipo = mov.tipo
        if tipo == "DESCENSO":
            d = mov.destino_categoria
            if d and d.nivel is not None and nivel_dest < d.nivel:
                errs.append(
                    f"{mov.equipo.nombre} descendió a {d.nombre}: sus jugadores no pueden "
                    f"registrarse en categorías por encima de {d.nombre}."
                )
        elif tipo == "DESAPARECE":
            o = mov.origen_categoria
            if nivel_dest < o.nivel:
                errs.append(
                    f"{mov.equipo.nombre} desapareció: sus jugadores solo pueden jugar en "
                    f"{o.nombre} o la inmediata inferior, no por encima."
                )
            elif nivel_dest > o.nivel + 1:
                errs.append(
                    f"{mov.equipo.nombre} desapareció: sus jugadores solo pueden jugar en "
                    f"{o.nombre} o la inmediata inferior (no en {categoria_destino.nombre})."
                )
        elif tipo == "ASCENSO":
            d = mov.destino_categoria
            if equipo_destino and equipo_destino.pk == mov.equipo_id:
                continue
            if d and d.nivel is not None and nivel_dest not in (d.nivel, d.nivel + 1):
                errs.append(
                    f"{mov.equipo.nombre} ascendió: quien se cambia a otro equipo solo puede "
                    f"ir a {d.nombre} o la inmediata inferior (no a {categoria_destino.nombre})."
                )
                continue
            cupo = mov.cupo_50()
            if cupo <= mov.transferidos():
                errs.append(
                    f"{mov.equipo.nombre} ascendió: el cupo del 50% de la plantilla para "
                    f"cambiarse de equipo ya se llenó ({cupo} jugadores)."
                )
    return errs