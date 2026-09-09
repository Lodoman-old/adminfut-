from django.db import migrations


def _fracases_herencia(herencias, cat_nivel):
    """¿La categoría (por nivel) viola alguna herencia activa no-castigado?"""
    if cat_nivel is None:
        return False
    for he in herencias:
        h = he.categoria.nivel
        if h is None:
            continue
        if he.tipo == "ASCENSO" and cat_nivel not in (h, h + 1):
            return True
        if he.tipo == "DESCENSO" and cat_nivel < h:
            return True
        if he.tipo == "DESAPARECE" and (cat_nivel < h or cat_nivel > h + 1):
            return True
    return False


def baja_registros_incompatibles(apps, schema_editor):
    Jugador = apps.get_model("league", "Jugador")
    JugadorEquipo = apps.get_model("league", "JugadorEquipo")
    JugadorHerencia = apps.get_model("league", "JugadorHerencia")
    jugadores_ids = set(
        JugadorHerencia.objects.filter(activo=True)
        .exclude(tipo="CASTIGADO")
        .values_list("jugador_id", flat=True)
    )
    for jid in jugadores_ids:
        jug = Jugador.objects.filter(pk=jid).first()
        if not jug:
            continue
        herencias = list(JugadorHerencia.objects.filter(jugador=jug, activo=True))
        for r in JugadorEquipo.objects.filter(jugador=jug, activo=True).select_related("equipo__categoria"):
            if not _fracases_herencia(herencias, r.equipo.categoria.nivel):
                continue
            r.activo = False
            r.es_principal = False
            r.save(update_fields=["activo", "es_principal"])
            if jug.equipo_id == r.equipo_id:
                jug.equipo = None
                jug.save(update_fields=["equipo"])


class Migration(migrations.Migration):

    dependencies = [("league", "0082_asigna_niveles_categorias")]

    operations = [migrations.RunPython(baja_registros_incompatibles, migrations.RunPython.noop)]