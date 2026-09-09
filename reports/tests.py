from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import Rol
from league.models import Categoria, Equipo, Jugador, JugadorEquipo, SuspensionJugador

User = get_user_model()


class CredencialJugadorMultiEquipoTest(TestCase):
    def setUp(self):
        self.cat1 = Categoria.objects.create(nombre="Libre A")
        self.cat2 = Categoria.objects.create(nombre="Libre B")
        self.eq1 = Equipo.objects.create(nombre="Rojos", categoria=self.cat1, activo=True)
        self.eq2 = Equipo.objects.create(nombre="Azules", categoria=self.cat2, activo=True)

        rol = Rol.objects.create(nombre="AdminCred", permisos={"credenciales_ver": True})
        self.user = User.objects.create_user(
            username="credadmin", password="x", rol=rol
        )
        self.client.force_login(self.user)

        self.j = Jugador.objects.create(
            nombre="José Luis", apellido="García Hernández",
            equipo=self.eq1, activo=True, posicion="DEL",
            tipo_documento="CURP", curp="GAHL900101HDFRCR00",
            fecha_nacimiento=date(1990, 1, 1), dorsal=10,
        )
        JugadorEquipo.objects.create(jugador=self.j, equipo=self.eq2)

    def test_pantalla_muestra_jugador_en_ambos_equipos(self):
        r = self.client.get(
            reverse("reporte_credenciales"),
            {"categoria": self.cat1.id, "equipo": self.eq1.id},
        )
        self.assertContains(r, "García Hernández")

        r2 = self.client.get(
            reverse("reporte_credenciales"),
            {"categoria": self.cat2.id, "equipo": self.eq2.id},
        )
        self.assertContains(r2, "García Hernández")

    def test_pdf_genera_credenciales_sin_error(self):
        r = self.client.get(
            reverse("reporte_credenciales_pdf"), {"jugadores": self.j.id}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")

    def test_pdf_por_equipo_secundario_incluye_al_jugador(self):
        r = self.client.get(
            reverse("reporte_credenciales_pdf"), {"equipo": self.eq2.id}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")

    def test_suspendido_global_no_genera_credencial_ni_pdf(self):
        SuspensionJugador.objects.create(
            jugador=self.j, categoria=self.cat1, equipo=None, activo=True,
            jornadas=2, fecha_inicio=date.today(),
        )
        r = self.client.get(
            reverse("reporte_credenciales"),
            {"categoria": self.cat1.id, "equipo": self.eq1.id},
        )
        self.assertNotContains(r, "García Hernández")
        # PDF por jugador suspendido se rechaza (no hay credenciales)
        r2 = self.client.get(
            reverse("reporte_credenciales_pdf"), {"jugadores": self.j.id}
        )
        self.assertEqual(r2.status_code, 302)

    def test_pdf_por_equipo_solo_incluye_a_los_no_suspendidos(self):
        otro = Jugador.objects.create(
            nombre="Otro", apellido="Jugador", equipo=self.eq1, activo=True, posicion="DEF",
            dorsal=2, tipo_documento="CURP", curp="OTRO910101HDFRCR00",
            fecha_nacimiento=date(1999, 1, 1),
        )
        SuspensionJugador.objects.create(
            jugador=self.j, categoria=self.cat1, equipo=None, activo=True,
            jornadas=2, fecha_inicio=date.today(),
        )
        r = self.client.get(
            reverse("reporte_credenciales_pdf"), {"equipo": self.eq1.id}
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")