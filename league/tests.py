from datetime import date, datetime, timedelta

from django.test import TestCase, Client
from django.utils import timezone

from .models import Campo, Categoria, Equipo, Partido, Temporada, Jugador, Jornada, JugadorEquipo, MovimientoEquipo, SuspensionJugador
from .reglas_movimientos import errores_movimiento_jugador


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


class SuspensionJugadorTest(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(
            nombre="Libre", dias_juego=["SAB"], curp_obligatoria=False
        )
        self.campo = Campo.objects.create(nombre="Campo 1", activo=True)
        self.eq1 = Equipo.objects.create(nombre="Aguilas", categoria=self.cat, activo=True)
        self.eq2 = Equipo.objects.create(nombre="Toros", categoria=self.cat, activo=True)
        self.jugador = Jugador.objects.create(
            nombre="Juan", apellido="Perez", equipo=self.eq1, posicion="DEL"
        )
        self.temporada = Temporada.objects.create(
            categoria=self.cat, nombre="Temp 1", fecha_inicio=date.today(),
            tipo_rol="TODOS", vueltas=1, iniciada=True,
        )

    def _jornada(self, numero):
        return Jornada.objects.create(temporada=self.temporada, numero=numero, nombre=f"J{numero}")

    def _partido(self, jornada, local, visit, fecha, n=1):
        return Partido.objects.create(
            temporada=self.temporada, jornada=jornada, equipo_local=local,
            equipo_visitante=visit, fecha_hora=fecha, campo=self.campo, estado="FIN",
        )

    def test_restantes_cuenta_partidos_finalizados(self):
        susp = SuspensionJugador.objects.create(
            jugador=self.jugador, categoria=self.cat, equipo=self.eq1,
            temporada=self.temporada, jornadas=2, fecha_inicio=date.today(),
        )
        self.assertEqual(susp.restantes(), 2)
        j = self._jornada(1)
        self._partido(j, self.eq1, self.eq2, timezone.now(), n=1)
        self.assertEqual(susp.restantes(), 1)
        j2 = self._jornada(2)
        self._partido(j2, self.eq2, self.eq1, timezone.now() + timedelta(days=7), n=2)
        self.assertEqual(susp.restantes(), 0)
        self.assertFalse(susp.vigente())

    def test_tabla_castigados_incluye_suspension_manual(self):
        SuspensionJugador.objects.create(
            jugador=self.jugador, categoria=self.cat, equipo=self.eq1,
            temporada=self.temporada, jornadas=2, fecha_inicio=date.today(),
        )
        client = Client()
        r = client.get(f"/tabla-castigados/?temporada={self.temporada.id}")
        self.assertEqual(r.status_code, 200)
        # La página usa el patrón sin permiso (ruta pública de tabla)
        self.assertContains(r, "Juan Perez")

    def test_clean_equipo_bloquea_cambio_de_equipo_suspendido(self):
        from .forms import JugadorForm
        SuspensionJugador.objects.create(
            jugador=self.jugador, categoria=self.cat, equipo=self.eq1,
            temporada=self.temporada, jornadas=1, fecha_inicio=date.today(),
        )
        form = JugadorForm(
            data={
                "nombre": "Juan", "apellido": "Perez", "posicion": "DEL",
                "equipo": self.eq2.id, "tipo_documento": "CURP",
            },
            instance=self.jugador,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("suspensión activa", str(form.errors.get("equipo", "")))

    def test_levantar_suspension_desactiva(self):
        susp = SuspensionJugador.objects.create(
            jugador=self.jugador, categoria=self.cat, equipo=self.eq1,
            temporada=self.temporada, jornadas=3, fecha_inicio=date.today(),
        )
        susp.activo = False
        susp.save(update_fields=["activo"])
        self.assertEqual(susp.restantes(), 0)


class MovimientosEquipoTest(TestCase):
    def setUp(self):
        self.c1 = Categoria.objects.create(nombre="Primera", nivel=1)
        self.c2 = Categoria.objects.create(nombre="Intermedia", nivel=2)
        self.c3 = Categoria.objects.create(nombre="Segunda", nivel=3)
        self.eq1 = Equipo.objects.create(nombre="T1", categoria=self.c1, activo=True)
        self.eq2 = Equipo.objects.create(nombre="T2", categoria=self.c2, activo=True)
        self.j = Jugador.objects.create(nombre="Juan", apellido="Perez", equipo=self.eq1, fecha_nacimiento=date(1990, 1, 1))

    def _temporada(self, **kw):
        kw.setdefault("fecha_inicio", date(2026, 6, 1))
        kw.setdefault("tipo_rol", "TODOS")
        kw.setdefault("aplicar_movimientos", True)
        return Temporada.objects.create(categoria=self.c1, nombre="Temp 2026", **kw)

    def test_descenso_restringe_categoria_superior(self):
        mov = MovimientoEquipo.objects.create(
            temporada=self._temporada(), equipo=self.eq1,
            tipo="DESCENSO", origen_categoria=self.c1, destino_categoria=self.c2,
        )
        errs_sup = errores_movimiento_jugador(self.j, self.eq2, self.c1)
        self.assertTrue(any("descendió" in e for e in errs_sup))
        self.assertEqual(errores_movimiento_jugador(self.j, self.eq2, self.c2), [])
        self.assertEqual(errores_movimiento_jugador(self.j, self.eq2, self.c3), [])
        self.assertTrue(mov.cupo_50() == 0)

    def test_desaparicion_restringe_por_encima_y_dos_niveles_abajo(self):
        MovimientoEquipo.objects.create(
            temporada=self._temporada(), equipo=self.eq1,
            tipo="DESAPARECE", origen_categoria=self.c1,
        )
        self.assertTrue(any("desapareció" in e for e in errores_movimiento_jugador(self.j, None, self.c3)))
        self.assertEqual(errores_movimiento_jugador(self.j, None, self.c1), [])
        self.assertEqual(errores_movimiento_jugador(self.j, None, self.c2), [])

    def test_ascenso_50_por_ciento_fifo(self):
        c_sup = Categoria.objects.create(nombre="Maxima", nivel=0)
        eq_sup = Equipo.objects.create(nombre="T1S", categoria=c_sup, activo=True)
        otros = [
            Jugador.objects.create(nombre=f"P{i}", apellido="X", equipo=self.eq1, fecha_nacimiento=date(1990, 1, 1))
            for i in range(3)
        ]
        mov = MovimientoEquipo.objects.create(
            temporada=self._temporada(), equipo=self.eq1,
            tipo="ASCENSO", origen_categoria=self.c1, destino_categoria=c_sup,
            jugadores_plantilla=4,
        )
        # Cambiarse a OTRO equipo en categoria superior ok (cupo libre, categoría válida)
        j2 = otros[0]
        eq_destino = eq_sup
        self.assertEqual(errores_movimiento_jugador(j2, eq_destino, c_sup), [])
        # FIFO: registramos 2 (50% de 4) en el equipo de la categoría superior
        for o in otros[:2]:
            JugadorEquipo.objects.create(jugador=o, equipo=eq_sup, activo=True, es_principal=True)
        self.assertEqual(mov.transferidos(), 2)
        self.assertEqual(mov.cupo_50(), 2)
        errs = errores_movimiento_jugador(otros[2], eq_sup, c_sup)
        self.assertTrue(any("cupo del 50%" in e for e in errs))
        # Categoría incorrecta bloqueada aunque haya cupo
        errs_cat = errores_movimiento_jugador(self.j, self.eq2, self.c2)
        self.assertTrue(any("solo puede" in e for e in errs_cat))

    def test_se_queda_no_restringe(self):
        MovimientoEquipo.objects.create(
            temporada=self._temporada(), equipo=self.eq1,
            tipo="SE_QUEDA", origen_categoria=self.c1,
        )
        self.assertEqual(errores_movimiento_jugador(self.j, self.eq2, self.c3), [])
        self.assertEqual(errores_movimiento_jugador(self.j, self.eq2, self.c1), [])

    def test_guardar_movimientos_mueve_categoria_y_desactiva(self):
        from django.contrib.auth import get_user_model
        catA = Categoria.objects.create(nombre="Maxima", nivel=19)
        catB = Categoria.objects.create(nombre="Intermedia", nivel=20)
        catC = Categoria.objects.create(nombre="Segunda", nivel=21)
        t = Temporada.objects.create(
            categoria=catB, nombre="Temp", fecha_inicio=date(2026, 6, 1),
            tipo_rol="TODOS", num_ascensos=1, num_descensos=1, aplicar_movimientos=True,
            finalizada=True,
        )
        eqA = Equipo.objects.create(nombre="Alpha", categoria=catB, activo=True)
        eqB = Equipo.objects.create(nombre="Beta", categoria=catB, activo=True)
        Partido.objects.create(
            temporada=t, equipo_local=eqA, equipo_visitante=eqB,
            fecha_hora=timezone.make_aware(datetime(2026, 6, 5, 12, 0)),
            estado="FIN", goles_local=2, goles_visitante=1,
        )
        User = get_user_model()
        admin = User.objects.create_superuser(username="admin", password="p")
        self.client.force_login(admin)
        r = self.client.get(f"/temporadas/{t.pk}/movimientos/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Sube a Maxima")
        r_post = self.client.post(f"/temporadas/{t.pk}/movimientos/", {
            f"tipo_{eqA.pk}": "ASCENSO", f"tipo_{eqB.pk}": "DESAPARECE",
        })
        self.assertEqual(r_post.status_code, 302)
        eqA.refresh_from_db(); eqB.refresh_from_db()
        self.assertEqual(eqA.categoria_id, catA.id)  # sube a Maxima
        self.assertFalse(eqB.activo)  # desaparece
        movA = MovimientoEquipo.objects.get(equipo=eqA)
        self.assertEqual(movA.tipo, "ASCENSO")
        self.assertEqual(movA.destino_categoria_id, catA.id)
        movB = MovimientoEquipo.objects.get(equipo=eqB)
        self.assertEqual(movB.tipo, "DESAPARECE")
        self.assertEqual(movB.origen_categoria_id, catB.id)

    def test_regla_inactiva_suspende_restriccion(self):
        MovimientoEquipo.objects.create(
            temporada=self._temporada(), equipo=self.eq1,
            tipo="DESCENSO", origen_categoria=self.c1, destino_categoria=self.c2,
            regla_activa=False,
        )
        self.assertEqual(errores_movimiento_jugador(self.j, self.eq2, self.c1), [])
        mov = MovimientoEquipo.objects.get(equipo=self.eq1)
        mov.regla_activa = True
        mov.save(update_fields=["regla_activa"])
        self.assertTrue(any("descendió" in e for e in errores_movimiento_jugador(self.j, self.eq2, self.c1)))

    def test_cupo_porcentaje_configurable(self):
        mov = MovimientoEquipo.objects.create(
            temporada=self._temporada(), equipo=self.eq1,
            tipo="ASCENSO", origen_categoria=self.c1, destino_categoria=self.c2,
            jugadores_plantilla=4, cupo_porcentaje=25,
        )
        self.assertEqual(mov.cupo_50(), 1)
        mov.cupo_porcentaje = 100
        mov.save(update_fields=["cupo_porcentaje"])
        self.assertEqual(mov.cupo_50(), 4)

    def test_movimientos_guardan_vigencia_y_cupo(self):
        from django.contrib.auth import get_user_model
        catA = Categoria.objects.create(nombre="MaximaV", nivel=31)
        catB = Categoria.objects.create(nombre="IntermediaV", nivel=32)
        Categoria.objects.create(nombre="SegundaV", nivel=33)
        t = Temporada.objects.create(
            categoria=catB, nombre="Temp V", fecha_inicio=date(2026, 6, 1),
            tipo_rol="TODOS", aplicar_movimientos=True,
        )
        eqA = Equipo.objects.create(nombre="AlphaV", categoria=catB, activo=True)
        eqB = Equipo.objects.create(nombre="BetaV", categoria=catB, activo=True)
        Partido.objects.create(
            temporada=t, equipo_local=eqA, equipo_visitante=eqB,
            fecha_hora=timezone.make_aware(datetime(2026, 6, 5, 12, 0)),
            estado="FIN", goles_local=1, goles_visitante=0,
        )
        User = get_user_model()
        admin = User.objects.create_superuser(username="adminv", password="p")
        self.client.force_login(admin)
        r = self.client.post(f"/temporadas/{t.pk}/movimientos/", {
            f"tipo_{eqA.pk}": "ASCENSO",
            f"regla_activa_{eqA.pk}": "1",
            f"cupo_pct_{eqA.pk}": "25",
        })
        self.assertEqual(r.status_code, 302)
        mov = MovimientoEquipo.objects.get(temporada=t, equipo=eqA)
        self.assertTrue(mov.regla_activa)
        self.assertEqual(mov.cupo_porcentaje, 25)
        # Segunda pasada sin marcar la regla: se apaga la vigencia
        r2 = self.client.post(f"/temporadas/{t.pk}/movimientos/", {
            f"tipo_{eqA.pk}": "ASCENSO",
            f"cupo_pct_{eqA.pk}": "25",
        })
        self.assertEqual(r2.status_code, 302)
        mov.refresh_from_db()
        self.assertFalse(mov.regla_activa)


class JugadorSinEquipoTest(TestCase):
    def setUp(self):
        self.cat = Categoria.objects.create(
            nombre="Libre", dias_juego=["SAB"], curp_obligatoria=False
        )
        self.campo = Campo.objects.create(nombre="Campo 1", activo=True)
        self.eq1 = Equipo.objects.create(nombre="Aguilas", categoria=self.cat, activo=True)
        self.eq2 = Equipo.objects.create(nombre="Toros", categoria=self.cat, activo=True)
        self.temporada = Temporada.objects.create(
            categoria=self.cat, nombre="Temp 1", fecha_inicio=date.today(),
            tipo_rol="TODOS", vueltas=1, iniciada=True,
        )

    def _jornada(self, numero):
        return Jornada.objects.create(temporada=self.temporada, numero=numero, nombre=f"J{numero}")

    def _partido(self, jornada, local, visit, fecha, n=1):
        return Partido.objects.create(
            temporada=self.temporada, jornada=jornada, equipo_local=local,
            equipo_visitante=visit, fecha_hora=fecha, campo=self.campo, estado="FIN",
        )

    def test_jugador_sin_equipo_y_asignacion_posterior(self):
        j = Jugador.objects.create(nombre="Ana", apellido="Lopez", posicion="DEL")
        self.assertIsNone(j.equipo)
        self.assertFalse(j.registros_equipo.exists())
        j.equipo = self.eq1
        j.save(update_fields=["equipo"])
        self.assertTrue(j.registros_equipo.filter(equipo=self.eq1, es_principal=True).exists())

    def test_suspension_sin_equipo_cuenta_jornadas_de_la_categoria(self):
        j = Jugador.objects.create(nombre="Beto", apellido="Sanz", posicion="DEL")
        susp = SuspensionJugador.objects.create(
            jugador=j, categoria=self.cat, equipo=None,
            temporada=self.temporada, jornadas=2, fecha_inicio=date.today(),
        )
        self.assertEqual(susp.restantes(), 2)
        j1 = self._jornada(1)
        # Dos partidos FIN en la misma jornada descontan una sola jornada
        self._partido(j1, self.eq1, self.eq2, timezone.now(), n=1)
        self._partido(j1, self.eq2, self.eq1, timezone.now() + timedelta(hours=1), n=2)
        self.assertEqual(susp.consumidos(), 1)
        self.assertEqual(susp.restantes(), 1)
        j2 = self._jornada(2)
        self._partido(j2, self.eq1, self.eq2, timezone.now() + timedelta(days=7), n=3)
        self.assertEqual(susp.restantes(), 0)
