from django.db import migrations


def expulsar_castigados(apps, schema_editor):
    Jugador = apps.get_model("league", "Jugador")
    JugadorEquipo = apps.get_model("league", "JugadorEquipo")
    JugadorHerencia = apps.get_model("league", "JugadorHerencia")
    for he in JugadorHerencia.objects.filter(activo=True, tipo="CASTIGADO"):
        jug = Jugador.objects.filter(pk=he.jugador_id).first()
        if not jug:
            continue
        JugadorEquipo.objects.filter(jugador=jug).update(activo=False, es_principal=False)
        if jug.equipo_id:
            jug.equipo = None
            jug.save(update_fields=["equipo"])


class Migration(migrations.Migration):

    dependencies = [("league", "0080_limpia_herederos_duplicados")]

    operations = [migrations.RunPython(expulsar_castigados, migrations.RunPython.noop)]