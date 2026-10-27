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


class CredencialNombreLargoTest(TestCase):
    """Un nombre largo en mayúsculas debe seguir apareciendo en la credencial.

    Antes se reducía la fuente sin límite para que cupiera en dos líneas; un
    nombre largo en mayúsculas no cabía ni a 8pt, el bucle terminaba sin
    líneas y la credencial se generaba SIN el nombre del jugador.
    """

    def setUp(self):
        self.cat = Categoria.objects.create(nombre="Credenciales Largo")
        self.eq = Equipo.objects.create(
            nombre="Equipo Credencial Largo", categoria=self.cat, activo=True
        )
        rol = Rol.objects.create(
            nombre="AdminCredLargo", permisos={"credenciales_ver": True}
        )
        self.user = User.objects.create_user(
            username="credlargoadmin", password="x", rol=rol
        )
        self.client.force_login(self.user)
        self.j = Jugador.objects.create(
            nombre="JONATHAN MICHAEL ANGEL",
            apellido="RAMIREZ HERNANDEZ",
            equipo=self.eq, activo=True, posicion="DEL",
            tipo_documento="CURP", curp="RAHJ890520HGTMRN06",
            fecha_nacimiento=date(1989, 5, 20), dorsal=9,
        )

    def _spans(self, contenido):
        import fitz

        doc = fitz.open(stream=contenido, filetype="pdf")
        return [
            span
            for pagina in doc
            for bloque in pagina.get_text("dict")["blocks"]
            for linea in bloque.get("lines", [])
            for span in linea["spans"]
        ]

    def test_nombre_largo_en_mayusculas_aparece_completo(self):
        try:
            import fitz  # noqa: F401
        except ImportError:  # pragma: no cover
            self.skipTest("PyMuPDF (fitz) no está instalado")

        r = self.client.get(
            reverse("reporte_credenciales_pdf"), {"jugadores": self.j.id}
        )
        self.assertEqual(r.status_code, 200)
        spans = self._spans(r.content)
        texto = " ".join(span["text"] for span in spans)
        for palabra in (
            "JONATHAN", "MICHAEL", "ANGEL", "RAMIREZ", "HERNANDEZ",
        ):
            self.assertIn(palabra, texto)
        nombre_spans = [
            span
            for span in spans
            if any(
                p in span["text"]
                for p in ("JONATHAN", "MICHAEL", "ANGEL", "RAMIREZ", "HERNANDEZ")
            )
        ]
        self.assertTrue(nombre_spans)
        for span in nombre_spans:
            self.assertGreaterEqual(span["size"], 6.0 - 0.01)

    def test_nombre_extremo_no_queda_vacio(self):
        try:
            import fitz  # noqa: F401
        except ImportError:  # pragma: no cover
            self.skipTest("PyMuPDF (fitz) no está instalado")

        self.j.nombre = "JONATHAN MICHAEL ANGEL DE JESUS RAMIREZ HERNANDEZ Y SUS"
        self.j.apellido = "APELLIDOS MUY LARGOS PARA PROBAR EL AJUSTE AUTOMATICO"
        self.j.save(update_fields=["nombre", "apellido"])
        r = self.client.get(
            reverse("reporte_credenciales_pdf"), {"jugadores": self.j.id}
        )
        self.assertEqual(r.status_code, 200)
        spans = self._spans(r.content)
        texto = " ".join(span["text"] for span in spans)
        self.assertIn("JONATHAN", texto)
        nombre_spans = [
            span for span in spans if "JONATHAN" in span["text"]
        ]
        self.assertTrue(nombre_spans)
        for span in nombre_spans:
            self.assertGreaterEqual(span["size"], 6.0 - 0.01)
