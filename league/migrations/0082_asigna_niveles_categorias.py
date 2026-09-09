from django.db import migrations


def asigna_niveles(apps, schema_editor):
    Categoria = apps.get_model("league", "Categoria")
    mapeo = {
        "primera fuerza": 1,
        "intermedia": 2,
        "segunda fuerza": 3,
    }
    for nombre, nivel in mapeo.items():
        Categoria.objects.filter(nombre__iexact=nombre, nivel__isnull=True).update(nivel=nivel)


class Migration(migrations.Migration):

    dependencies = [("league", "0081_expulsa_herederos_castigados")]

    operations = [migrations.RunPython(asigna_niveles, migrations.RunPython.noop)]