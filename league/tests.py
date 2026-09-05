from datetime import date, datetime

from django.test import TestCase, Client
from django.utils import timezone

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

    def test_generar_rol_desde_jornada_inicial_genera_todo(self):
        from unittest import mock

        t = Temporada.objects.create(
            categoria=self.cat, nombre="Temp",
            fecha_inicio=date(2026, 5, 2),  # sábado, hace meses
            tipo_rol="TODOS", vueltas=1,
        )
        # Hoy = lunes 2026-05-18: el próximo día de juego (SAB) es 2026-05-23
        with mock.patch("django.utils.timezone.now", return_value=datetime(2026, 5, 18, 12, 0)):
            t.generar_rol(jornada_inicial=4)

        jornadas = list(t.jornadas.order_by("numero"))
        self.assertEqual(len(jornadas), 5)  # TODAS las jornadas se generan
        self.assertEqual([j.numero for j in jornadas], [1, 2, 3, 4, 5])

        # 1-3 con fechas pasadas desde fecha_inicio; 4-5 desde el próximo día de juego real
        fechas = [Partido.objects.filter(jornada=j).first().fecha_hora.date() for j in jornadas]
        self.assertEqual(fechas, [
            date(2026, 5, 2),
            date(2026, 5, 9),
            date(2026, 5, 16),
            date(2026, 5, 23),
            date(2026, 5, 30),
        ])


class CedulaInvitadoTest(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(nombre="CedulaCat")
        self.campo = Campo.objects.create(nombre="Campo 1", activo=True)
        self.local = Equipo.objects.create(nombre="Local", categoria=self.cat, activo=True)
        self.visit = Equipo.objects.create(nombre="Visitante", categoria=self.cat, activo=True)
        self.fecha = timezone.make_aware(datetime(2026, 1, 1, 12, 0))

    def _partido(self, estado):
        return Partido.objects.create(
            equipo_local=self.local, equipo_visitante=self.visit,
            campo=self.campo, fecha_hora=self.fecha, estado=estado,
            goles_local=2, goles_visitante=1,
        )

    def test_invitado_ve_solo_cedulas_finalizadas(self):
        fin = self._partido("FIN")
        pend = self._partido("PEND")
        c = Client()
        r = c.get(f"/cedula-arbitral/{fin.id}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Vista de solo lectura")
        c404 = Client(raise_request_exception=False)
        r2 = c404.get(f"/cedula-arbitral/{pend.id}/")
        self.assertEqual(r2.status_code, 404)
        from django.template.loader import render_to_string
        html = render_to_string("league/cedula_invitado_no_disponible.html", {"partido": pend})
        self.assertIn("Cédula no disponible", html)

    def test_home_invitado_usa_categoria_principal_de_cookie(self):
        otra = Categoria.objects.create(nombre="PrincipalCat", es_principal=True)
        c = Client()
        r = c.get("/")
        self.assertContains(r, f"Máximos Goleadores - {otra.nombre}")
        c.cookies["cat_preferida"] = str(self.cat.id)
        r2 = c.get("/")
        self.assertContains(r2, f"Máximos Goleadores - {self.cat.nombre}")


class PwaWebPushTest(TestCase):
    def test_endpoints_pwa_publicos(self):
        c = Client()
        r = c.get("/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/javascript; charset=utf-8")
        self.assertContains(r, "showNotification")

        r = c.get("/manifest.webmanifest")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/manifest+json")
        self.assertIn("standalone", r.json().get("display", ""))

        r = c.get("/pwa-icon/icon-192.png")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "image/png")
        r = c.get("/pwa-icon/no-existe.png")
        self.assertEqual(r.status_code, 404)

        r = c.get("/api/vapid-public-key/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("public_key"))

    def test_registro_invitado_guarda_suscripcion_webpush(self):
        import json
        from .models import DeviceToken
        c = Client()
        r = c.post(
            "/api/register-guest/",
            data=json.dumps({
                "token": "web-111",
                "plataforma": "web",
                "device_id": "dev-pwa-001",
                "nombre": "Invitado PWA",
                "telefono": "6441112233",
                "email": "",
                "categorias": [],
                "subscripcion": {
                    "endpoint": "https://push.example.com/sub/abc123",
                    "p256dh": "BGhT9lP2T-k=",
                    "auth": "SxM9gQ==",
                },
            }),
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 200)
        dt = DeviceToken.objects.get(device_id="dev-pwa-001")
        self.assertEqual(dt.plataforma, "pwa")
        self.assertEqual(dt.webpush_endpoint, "https://push.example.com/sub/abc123")
        self.assertEqual(dt.webpush_p256dh, "BGhT9lP2T-k=")
        self.assertEqual(dt.webpush_auth, "SxM9gQ==")
        self.assertTrue(dt.activo)

    def test_envio_webpush_desactiva_endpoint_410(self):
        from unittest import mock

        from pywebpush import WebPushException

        from .models import DeviceToken
        from .push import _enviar_webpush

        dt = DeviceToken.objects.create(
            token="w-410", device_id="dev-410",
            plataforma="pwa", activo=True,
            webpush_endpoint="https://push.example.com/sub/gone",
            webpush_p256dh="BGhT9lP2T-k=", webpush_auth="SxM9gQ==",
        )

        class Resp410:
            status_code = 410

        def fake_webpush(info, data, **kw):
            raise WebPushException("gone", Resp410())

        with mock.patch("pywebpush.webpush", side_effect=fake_webpush), \
                mock.patch("league.push._vapid_keys", return_value=("priv", "pub")):
            res = _enviar_webpush([dt], "T", "B", {"x": 1})

        self.assertEqual(res["success"], 0)
        self.assertEqual(res["failure"], 1)
        dt.refresh_from_db()
        self.assertFalse(dt.activo)


class CurpReglaMariaJoseTest(TestCase):
    def _form(self):
        from .forms import JugadorForm
        return JugadorForm()

    def test_inicial_nombre_curp_regla_maria_jose(self):
        f = self._form()
        self.assertEqual(f._inicial_nombre_curp("JOSE LUIS"), "L")
        self.assertEqual(f._inicial_nombre_curp("MARIA GUADALUPE"), "G")
        self.assertEqual(f._inicial_nombre_curp("MARIA DEL CARMEN"), "C")
        self.assertEqual(f._inicial_nombre_curp("JOSE MARIA"), "M")
        self.assertEqual(f._inicial_nombre_curp("JOSE"), "J")
        self.assertEqual(f._inicial_nombre_curp("LUIS"), "L")

    def test_inicial_nombre_curp_regla_abreviaturas(self):
        f = self._form()
        self.assertEqual(f._inicial_nombre_curp("J. CARMEN"), "C")
        self.assertEqual(f._inicial_nombre_curp("J. LUIS"), "L")
        self.assertEqual(f._inicial_nombre_curp("MA. GUADALUPE"), "G")
        self.assertEqual(f._inicial_nombre_curp("M. JOSE"), "J")
        self.assertEqual(f._inicial_nombre_curp("Jose Carmen"), "C")

    def test_validacion_acepta_regla_maria_jose(self):
        f = self._form()
        # José Luis García Hernández, 1990-01-01 → posición 4 = L (Luis)
        errs = f._validar_curp_contra_datos(
            "GAHL900101HDFRCR00", "José Luis", "García Hernández", date(1990, 1, 1)
        )
        self.assertEqual(errs, [])

    def test_validacion_rechaza_inicial_del_primer_nombre(self):
        f = self._form()
        # Con la inicial del primer nombre (J de José) debe marcar error explicando la regla
        errs = f._validar_curp_contra_datos(
            "GAHJ900101HDFRCR00", "José Luis", "García Hernández", date(1990, 1, 1)
        )
        self.assertTrue(any("María/José" in e for e in errs))
