from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("league", "0115_ventahorario_horariofijoequipo_venta"),
    ]

    operations = [
        migrations.AlterField(
            model_name="ventahorario",
            name="horario",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Se elige desde el equipo una vez que la venta está pagada.",
                max_length=5,
                verbose_name="Horario (HH:MM)",
            ),
        ),
    ]
