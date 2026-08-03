from datetime import date

from django.test import TestCase

from .models import Campo, Categoria, Equipo, Partido, Temporada


class FixtureDescansoTest(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre="Libre", dias_juego=["SAB"])
        self.campo = Campo.objects.create(nombre="Campo 1", activo=True)
        self.equipos = [
            Equipo.objects.create(nombre=f"Equipo {i}", categoria=self.cat, activo=True)
            for i in range(5)
        ]
        self.fecha_inicio = date.today()

    def test_round_robin_impar_genera_descanso(self):
        t = Temporada(categoria=self.cat, nombre="Temp", fecha_inicio=self.fecha_inicio)
        fixture = t._generar_fixture_round_robin(self.equipos)

        self.assertEqual(len(fixture), 5)  # 5 jornadas con 5 equipos
        descansan = []
        for ronda in fixture:
            self.assertEqual(len(ronda), 2)  # (5-1)/2 partidos por jornada
            jugaron = []
            for local, visit in ronda:
                jugaron.extend([local.id, visit.id])
            descansan.append([e.id for e in self.equipos if e.id not in jugaron])

        # Cada equipo descansa exactamente una vez en la vuelta
        for d in descansan:
            self.assertEqual(len(d), 1)
        rests = [d[0] for d in descansan]
        self.assertEqual(len(set(rests)), 5)

        # Todos contra todos: cada pareja aparece exactamente una vez
        parejas = []
        for ronda in fixture:
            for local, visit in ronda:
                parejas.append(tuple(sorted([local.id, visit.id])))
        self.assertEqual(len(parejas), 10)
        self.assertEqual(len(set(parejas)), 10)

    def test_generar_rol_con_descanso_y_equipos_descansan(self):
        t = Temporada.objects.create(
            categoria=self.cat, nombre="Temp", fecha_inicio=self.fecha_inicio,
            tipo_rol="TODOS", vueltas=1,
        )
        t.generar_rol()

        jornadas = list(t.jornadas.order_by("numero"))
        self.assertEqual(len(jornadas), 5)

        for j in jornadas:
            partidos = Partido.objects.filter(jornada=j)
            self.assertEqual(partidos.count(), 2)
            jugaron = set(partidos.values_list("equipo_local_id", flat=True))
            jugaron.update(partidos.values_list("equipo_visitante_id", flat=True))
            descansan = t.equipos_descansan(j)
            self.assertEqual([e.id for e in descansan], [e.id for e in self.equipos if e.id not in jugaron])
            self.assertEqual(len(descansan), 1)
