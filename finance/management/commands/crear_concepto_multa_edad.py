from django.core.management.base import BaseCommand
from finance.models import ConceptoIngreso


class Command(BaseCommand):
    help = "Crea o restaura el concepto 'Multa por incumplimiento de edad'"

    def handle(self, *args, **kwargs):
        obj, created = ConceptoIngreso.objects.get_or_create(
            nombre="Multa por incumplimiento de edad",
            defaults={
                "descripcion": (
                    "Multa aplicada automáticamente cuando se modifica la fecha de "
                    "nacimiento de un jugador y queda fuera del rango de edad de su categoría."
                ),
                "monto_defecto": 500.00,
                "activo": True,
                "no_eliminar": True,
                "requiere_jugador": True,
                "requiere_equipo": True,
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS("Concepto 'Multa por incumplimiento de edad' creado."))
        else:
            self.stdout.write(self.style.WARNING("El concepto ya existe."))
