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

from .models import MovimientoEquipo, JugadorHerencia, SuspensionJugador
from datetime import date


def movimientos_activos(jugador):
    """Último movimiento por equipo para los equipos del jugador (solo los que restringen)."""
    ids = set(jugador.registros_equipo.values_list("equipo_id", flat=True))
    if not ids:
        return []
    qs = (
        MovimientoEquipo.objects
        .filter(equipo_id__in=ids, temporada__aplicar_movimientos=True, regla_activa=True)
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
                    f"{mov.equipo.nombre} ascendió: el cupo del {mov.cupo_porcentaje}% de la plantilla "
                    f"para cambiarse de equipo ya se llenó ({cupo} jugadores)."
                )
    # Herencia del jugador (registros previos al sistema: castigados / ascienden / descienden / baja)
    for he in JugadorHerencia.objects.filter(jugador=jugador, activo=True):
        h_cat = he.categoria
        if h_cat.nivel is None:
            continue
        if he.tipo == "CASTIGADO":
            if he.jornadas > 0:
                errs.append(
                    f"{jugador} es jugador heredado con castigo pendiente en {h_cat.nombre}: "
                    f"no puede registrarse en ningún equipo hasta cumplir (o levantar) su suspensión."
                )
            # Sin jornadas: heredado registrado como expulsado del equipo en su categoría;
            # no se le agrega restricción de movimiento (no hay equipo previo).
        elif he.tipo == "ASCENSO":
            if nivel_dest not in (h_cat.nivel, h_cat.nivel + 1):
                errs.append(
                    f"{jugador} asciende (heredado): solo puede jugar en {h_cat.nombre} "
                    f"o la inmediata inferior, no en {categoria_destino.nombre}."
                )
        elif he.tipo == "DESCENSO":
            if nivel_dest < h_cat.nivel:
                errs.append(
                    f"{jugador} desciende (heredado): solo puede jugar en {h_cat.nombre} "
                    f"o categorías más abajo, no por encima de {h_cat.nombre}."
                )
        elif he.tipo == "DESAPARECE":
            if nivel_dest < h_cat.nivel or nivel_dest > h_cat.nivel + 1:
                errs.append(
                    f"{jugador} proviene de un equipo dado de baja: solo puede jugar en "
                    f"{h_cat.nombre} o la inmediata inferior (no en {categoria_destino.nombre})."
                )
    return errs


def aplicar_movimiento_a_jugador(jugador, tipo, categoria, jornadas=0, motivo=""):
    """Registra en el historial heredado un ascenso/descenso/baja o un castigo
    de un jugador previo al sistema. Para CASTIGADO con jornadas>0 crea además
    una SuspensionJugador activa que bloquea al jugador en toda la liga."""
    he = JugadorHerencia.objects.create(
        jugador=jugador,
        tipo=tipo,
        categoria=categoria,
        jornadas=jornadas,
        motivo=motivo,
    )
    if tipo == "CASTIGADO" and jornadas > 0:
        SuspensionJugador.objects.get_or_create(
            jugador=jugador,
            categoria=categoria,
            activo=True,
            defaults={
                "equipo": None,
                "jornadas": jornadas,
                "motivo": motivo or "Castigo heredado al inicio del sistema.",
                "fecha_inicio": date.today(),
            },
        )
    return he