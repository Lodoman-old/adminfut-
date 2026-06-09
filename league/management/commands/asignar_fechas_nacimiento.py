import random
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from league.models import Jugador, JugadorEquipo, Categoria


class Command(BaseCommand):
    help = "Asigna fecha de nacimiento a jugadores sin ella, basada en la categoría del equipo"

    def handle(self, *args, **options):
        hoy = date.today()
        jugadores = Jugador.objects.filter(fecha_nacimiento__isnull=True)
        total = 0
        for j in jugadores:
            cats = set()
            if j.equipo and j.equipo.categoria_id:
                cats.add(j.equipo.categoria)
            for r in j.registros_equipo.filter(activo=True).select_related("equipo__categoria"):
                if r.equipo.categoria:
                    cats.add(r.equipo.categoria)
            if not cats:
                continue
            # Usar la categoría con el rango más restrictivo
            min_edad = None
            max_edad = None
            for c in cats:
                if c.edad_minima is not None:
                    min_edad = c.edad_minima if min_edad is None else max(min_edad, c.edad_minima)
                if c.edad_maxima is not None:
                    max_edad = c.edad_maxima if max_edad is None else min(max_edad, c.edad_maxima)
            if min_edad is None and max_edad is None:
                continue
            if min_edad is None:
                edad = max_edad
            elif max_edad is None:
                edad = min_edad
            else:
                edad = random.randint(min_edad, max_edad)
            # Calcular fecha de nacimiento para que tenga esa edad hoy
            try:
                fecha = hoy.replace(year=hoy.year - edad)
            except ValueError:
                fecha = hoy.replace(year=hoy.year - edad, day=1)
            j.fecha_nacimiento = fecha
            j.save(update_fields=["fecha_nacimiento"])
            total += 1
            self.stdout.write(f"{j} -> {fecha} (edad {j.edad()})")
        self.stdout.write(self.style.SUCCESS(f"{total} jugadores actualizados"))
