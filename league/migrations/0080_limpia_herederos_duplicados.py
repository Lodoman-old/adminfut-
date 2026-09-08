from django.db import migrations


def limpia_herencias_duplicadas_y_desactivadas(apps, schema_editor):
    """Quita los registros desactivados y deja una sola herencia activa por jugador.

    Limpieza solicitada: al corregir una herencia se reemplaza de cero, así que
    los registros previos (duplicados o desactivados) ya no son necesarios.
    """
    JugadorHerencia = apps.get_model("league", "JugadorHerencia")
    JugadorHerencia.objects.filter(activo=False).delete()
    from django.db.models import Count

    duplicados = (
        JugadorHerencia.objects.values("jugador_id")
        .annotate(total=Count("id"))
        .filter(total__gt=1)
    )
    for d in duplicados:
        filas = list(
            JugadorHerencia.objects.filter(jugador_id=d["jugador_id"]).order_by("-creado")
        )
        for extra in filas[1:]:
            extra.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("league", "0079_jugadorherencia"),
    ]

    operations = [
        migrations.RunPython(limpia_herencias_duplicadas_y_desactivadas),
    ]