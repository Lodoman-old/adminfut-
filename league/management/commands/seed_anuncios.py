from django.core.management.base import BaseCommand
from league.models import Anuncio


ANUNCIOS_EJEMPLO = [
    {
        "titulo": "Estadio Municipal — Alquiler de cancha",
        "descripcion": "Reserva tu espacio para entrenamientos y partidos. Más de 40 turnos semanales disponibles.",
        "color_fondo": "#1f6f4a",
        "enlace": "https://example.com/estadio",
        "tamano": "PREMIUM",
    },
    {
        "titulo": "Deportes MVP — Tienda deportiva",
        "descripcion": "Implementos, uniformes y balones con 15% de descuento para equipos de la liga.",
        "color_fondo": "#1a3d7c",
        "enlace": "https://example.com/deportes",
        "tamano": "MEDIO",
    },
    {
        "titulo": "Nutrición GOL — Suplementos y asesoría",
        "descripcion": "Planes alimenticios para futbolistas.",
        "color_fondo": "#7c3a1a",
        "enlace": "https://example.com/nutricion",
        "tamano": "ECONOMICO",
    },
]


class Command(BaseCommand):
    help = "Crea/actualiza los anuncios de ejemplo (idempotente, por título)."

    def handle(self, *args, **options):
        creados = actualizados = 0
        for datos in ANUNCIOS_EJEMPLO:
            obj, created = Anuncio.objects.get_or_create(
                titulo=datos["titulo"],
                defaults=datos,
            )
            if created:
                creados += 1
                self.stdout.write(self.style.SUCCESS(f"Anuncio creado: {datos['titulo']}"))
            else:
                cambios = False
                for k, v in datos.items():
                    if getattr(obj, k) != v:
                        setattr(obj, k, v)
                        cambios = True
                if cambios:
                    obj.save()
                    actualizados += 1
                    self.stdout.write(self.style.WARNING(f"Anuncio actualizado: {datos['titulo']}"))
                else:
                    self.stdout.write(f"Anuncio ya existente (sin cambios): {datos['titulo']}")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"seed_anuncios listo: {creados} creados, {actualizados} actualizados."
        ))