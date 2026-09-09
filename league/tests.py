from datetime import date, datetime, timedelta, time

from django.test import TestCase, Client
from django.utils import timezone

from .models import Campo, Categoria, Equipo, Partido, Temporada, Jugador, Jornada, JugadorEquipo, MovimientoEquipo, SuspensionJugador, JugadorHerencia, AbandonoTemporada
from .reglas_movimientos import errores_movimiento_jugador, aplicar_movimiento_a_jugador
from .views import _hora_por_defecto_partido


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


class HoraDefectoPartidoTest(TestCase):
    def test_hora_por_defecto_cicla_horarios_de_categoria(self):
        cat = Categoria.objects.create(nombre="Sabadito", horarios=["15:00", "17:00"])
        t = Temporada(categoria=cat)
        self.assertEqual(_hora_por_defecto_partido(t, 0), time(15, 0))
        self.assertEqual(_hora_por_defecto_partido(t, 1), time(17, 0))
        self.assertEqual(_hora_por_defecto_partido(t, 2), time(15, 0))

    def test_hora_por_defecto_sin_horarios_usa_12(self):
        cat = Categoria.objects.create(nombre="SinHoras")
        t = Temporada(categoria=cat)
        self.assertEqual(_hora_por_defecto_partido(t, 0), time(12, 0))


class PartidosPorJornadaAbandonoTest(TestCase):
    def test_equivale_al_rol_con_abandono(self):
        cat = Categoria.objects.create(nombre="ConBaja")
        temp = Temporada.objects.create(
            nombre="T", categoria=cat, fecha_inicio=date(2026, 1, 1)
        )
        equipos = []
        for i in range(6):
            equipos.append(Equipo.objects.create(nombre=f"E{i}", categoria=cat))
        # 5 equipos se quedan; el equipo 6 "se da de baja" (abandono)
        AbandonoTemporada.objects.create(temporada=temp, equipo=equipos[5])
        # El rol real incluye al de baja: 6 // 2 = 3 partidos por jornada
        self.assertEqual(temp.partidos_por_jornada(), 3)

    def test_par_de_equipos_sin_abandono(self):
        cat = Categoria.objects.create(nombre="SinBaja")
        temp = Temporada.objects.create(
            nombre="T2", categoria=cat, fecha_inicio=date(2026, 1, 1)
        )
        for i in range(6):
            Equipo.objects.create(nombre=f"E{i}", categoria=cat)
        self.assertEqual(temp.partidos_por_jornada(), 3)


class LimiteCambiosTest(TestCase):
    def test_limite_cambios_efectivo(self):
        t = Temporada(cambios_permitidos=5)
        self.assertEqual(t.limite_cambios_efectivo(), 5)
        t.cambios_permitidos = 1
        self.assertEqual(t.limite_cambios_efectivo(), 1)
        t.cambios_permitidos = 0
        self.assertIsNone(t.limite_cambios_efectivo())
        t.cambios_permitidos = None
        self.assertIsNone(t.limite_cambios_efectivo())

    def test_guardar_cambios_cero_y_nulo(self):
        cat = Categoria.objects.create(nombre="LimiteCat")
        t0 = Temporada.objects.create(nombre="Sin cambios", categoria=cat, fecha_inicio=date(2026, 1, 1), cambios_permitidos=0)
        tn = Temporada.objects.create(nombre="Sin limite", categoria=cat, fecha_inicio=date(2026, 1, 1), cambios_permitidos=None)
        t5 = Temporada.objects.create(nombre="Con limite", categoria=cat, fecha_inicio=date(2026, 1, 1), cambios_permitidos=5)
        self.assertIsNone(t0.limite_cambios_efectivo())
        self.assertIsNone(tn.limite_cambios_efectivo())
        self.assertEqual(t5.limite_cambios_efectivo(), 5)


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

    def _curp18(self, base17):
        from .forms import JugadorForm
        return base17 + str(JugadorForm._calcular_digito_curp(base17))

    def test_apellido_con_particula_paterno_deriva_del_nucleo(self):
        f = self._form()
        # 'De la Torre García' → de 'TORRE' (T,O) y 'GARCÍA' (G)
        curp = self._curp18("TOGP" + "900101" + "HDF" + "RCR" + "0")
        errs = f._validar_curp_contra_datos(
            curp, "Pedro", "De la Torre García", date(1990, 1, 1)
        )
        self.assertEqual(errs, [])

    def test_apellido_con_particula_materno_deriva_del_nucleo(self):
        f = self._form()
        # 'García De la Torre' → 'GARCÍA' (G,A) y materno 'TORRE' (T)
        curp = self._curp18("GATP" + "900101" + "HDF" + "RCR" + "0")
        errs = f._validar_curp_contra_datos(
            curp, "Pedro", "García De la Torre", date(1990, 1, 1)
        )
        self.assertEqual(errs, [])

    def test_apellido_unico_con_particula(self):
        f = self._form()
        # 'De León' (apellido único) → 'LEÓN' (L,E); sin materno usa 'X'
        curp = self._curp18("LEXJ" + "900101" + "HDF" + "RCR" + "0")
        errs = f._validar_curp_contra_datos(
            curp, "Juan", "De León", date(1990, 1, 1)
        )
        self.assertEqual(errs, [])

    def test_curp_real_de_la_cruz_acepta(self):
        f = self._form()
        # Caso real RENAPO: 'DE LA CRUZ FLORINDA' + 'FELIPE' → 'CUFF...'
        curp = self._curp18("CUFF" + "760301" + "HDF" + "RCR" + "0")
        errs = f._validar_curp_contra_datos(
            curp, "Felipe", "De la Cruz Florinda", date(1976, 3, 1)
        )
        self.assertEqual(errs, [])

    def test_apellido_con_particula_mal_capturado_si_marca_error(self):
        f = self._form()
        # Con la letra de la partícula ('D' en vez de 'T') debe reportar el error
        curp = self._curp18("DEGP" + "900101" + "HDF" + "RCR" + "0")
        errs = f._validar_curp_contra_datos(
            curp, "Pedro", "De la Torre García", date(1990, 1, 1)
        )
        self.assertTrue(any("apellido paterno" in e for e in errs))

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

    def test_tabla_castigados_heredero_global_sin_temporada(self):
        # Heredado global (equipo None) en una categoría sin temporadas:
        # debe verse igual aunque no haya temporada creada
        cat2 = Categoria.objects.create(nombre="Libre B", curp_obligatoria=False)
        SuspensionJugador.objects.create(
            jugador=self.jugador, categoria=cat2, equipo=None,
            jornadas=2, fecha_inicio=date.today(),
        )
        r = Client().get(f"/tabla-castigados/?categoria={cat2.id}")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Juan Perez")
        self.assertContains(r, "Expulsado de la liga")

    def test_tabla_castigados_usa_categoria_preferida_del_usuario(self):
        from django.contrib.auth import get_user_model
        cat_principal = Categoria.objects.create(
            nombre="Principal", activo=True, es_principal=True, curp_obligatoria=False
        )
        cat_pref = Categoria.objects.create(
            nombre="Preferida", activo=True, curp_obligatoria=False
        )
        Temporada.objects.create(
            categoria=cat_pref, nombre="T Pref", fecha_inicio=date.today(),
            tipo_rol="TODOS", vueltas=1,
        )
        SuspensionJugador.objects.create(
            jugador=self.jugador, categoria=cat_pref, equipo=None,
            jornadas=2, fecha_inicio=date.today(),
        )
        User = get_user_model()
        u = User.objects.create_user(
            username="prefcat", password="x", categoria_preferida=cat_pref
        )
        client = Client()
        client.force_login(u)
        r = client.get("/tabla-castigados/")
        self.assertEqual(r.status_code, 200)
        # Sin seleccionar categoría se usa la preferida del usuario, no la principal
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


class JugadorHeredadoTest(TestCase):
    def setUp(self):
        self.c1 = Categoria.objects.create(nombre="MaximaH", nivel=0, activo=True, curp_obligatoria=False)
        self.c2 = Categoria.objects.create(nombre="IntermediaH", nivel=1, activo=True, curp_obligatoria=False)
        self.c3 = Categoria.objects.create(nombre="SegundaH", nivel=2, activo=True, curp_obligatoria=False)
        self.eq_sup = Equipo.objects.create(nombre="Kings", categoria=self.c1, activo=True)

    def test_castigado_con_jornadas_crea_suspension_global(self):
        j = Jugador.objects.create(nombre="Leo", apellido="Messi", posicion="DEL")
        he = aplicar_movimiento_a_jugador(j, "CASTIGADO", self.c2, jornadas=2, motivo="Expulsado")
        self.assertEqual(JugadorHerencia.objects.filter(jugador=j, activo=True).count(), 1)
        susp = SuspensionJugador.objects.filter(jugador=j, activo=True).first()
        self.assertIsNotNone(susp)
        self.assertEqual(susp.equipo, None)
        self.assertEqual(susp.jornadas, 2)
        self.assertEqual(he.tipo, "CASTIGADO")

    def test_castigado_sin_jornadas_no_crea_suspension(self):
        j = Jugador.objects.create(nombre="Sergio", apellido="Ramos", posicion="DEF")
        aplicar_movimiento_a_jugador(j, "CASTIGADO", self.c2, jornadas=0)
        self.assertFalse(SuspensionJugador.objects.filter(jugador=j, activo=True).exists())
        self.assertEqual(errores_movimiento_jugador(j, self.eq_sup, self.c1), [])

    def test_expulsado_por_vida_crea_suspension_permanente(self):
        j = Jugador.objects.create(nombre="Diego", apellido="Campos Cerrito", posicion="DEL")
        he = aplicar_movimiento_a_jugador(j, "VITALICIO", self.c2, motivo="Expulsado por agresión")
        self.assertEqual(he.tipo, "VITALICIO")
        susp = SuspensionJugador.objects.filter(jugador=j, activo=True).first()
        self.assertIsNotNone(susp)
        self.assertTrue(susp.vitalicia)
        self.assertEqual(susp.equipo, None)
        # Nunca se cumple: restantes siempre > 0 aunque pasen partidos
        self.assertEqual(susp.restantes(), 1)
        self.assertTrue(susp.vigente())
        # Bloquea el registro en cualquier categoría
        errs = errores_movimiento_jugador(j, self.eq_sup, self.c1)
        self.assertTrue(any("por vida" in e for e in errs))
        errs2 = errores_movimiento_jugador(j, None, self.c3)
        self.assertTrue(any("por vida" in e for e in errs2))

    def test_expulsado_por_vida_sale_de_todos_los_equipos(self):
        j = Jugador.objects.create(
            nombre="Raul", apellido="Jimeno", posicion="DEF", equipo=self.eq_sup
        )
        aplicar_movimiento_a_jugador(j, "VITALICIO", self.c1)
        j.refresh_from_db()
        self.assertIsNone(j.equipo)
        self.assertFalse(JugadorEquipo.objects.filter(jugador=j, activo=True).exists())
        self.assertEqual(SuspensionJugador.objects.filter(jugador=j, activo=True).count(), 1)

    def test_castigado_heredero_expulsa_de_todos_los_equipos(self):
        j = Jugador.objects.create(
            nombre="Gabriel", apellido="Reyes Casas", posicion="DEL", equipo=self.eq_sup
        )
        otro = Equipo.objects.create(nombre="Otro Club", categoria=self.c1, activo=True)
        JugadorEquipo.objects.create(jugador=j, equipo=otro, es_principal=False, activo=True)
        aplicar_movimiento_a_jugador(j, "CASTIGADO", self.c1, jornadas=2, motivo="Expulsado")
        j.refresh_from_db()
        self.assertIsNone(j.equipo)
        # Ningún registro activo: no aparece en rosters ni credenciales
        self.assertFalse(JugadorEquipo.objects.filter(jugador=j, activo=True).exists())
        # Corte histórico conservado
        self.assertEqual(JugadorEquipo.objects.filter(jugador=j, equipo=self.eq_sup).count(), 1)
        self.assertEqual(SuspensionJugador.objects.filter(jugador=j, activo=True).count(), 1)

    def test_herencia_ascenso_descenso_desaparece_aplican_reglas(self):
        base = Jugador.objects.create(nombre="Pelusa", apellido="Rojo", posicion="DEL")
        aplicar_movimiento_a_jugador(base, "ASCENSO", self.c3)
        # Ascendió a SegundaH (c3): solo puede jugar en c3 o la inmediata inferior
        eq_c3 = Equipo.objects.create(nombre="SegundaH Eq", categoria=self.c3, activo=True)
        self.assertEqual(errores_movimiento_jugador(base, eq_c3, self.c3), [])
        self.assertTrue(any("asciende (heredado)" in e for e in errores_movimiento_jugador(base, self.eq_sup, self.c1)))
        self.assertTrue(any("asciende (heredado)" in e for e in errores_movimiento_jugador(base, self.eq_sup, self.c2)))

        des = Jugador.objects.create(nombre="Dena", apellido="Dos", posicion="MED")
        aplicar_movimiento_a_jugador(des, "DESCENSO", self.c1)
        # Descendió a MaximaH (c1): no puede jugar por encima (no hay); sí en c1, c2, c3
        self.assertEqual(errores_movimiento_jugador(des, None, self.c1), [])
        eq_c2 = Equipo.objects.create(nombre="IntermediaH Eq", categoria=self.c2, activo=True)
        self.assertEqual(errores_movimiento_jugador(des, eq_c2, self.c2), [])
        self.assertEqual(errores_movimiento_jugador(des, None, self.c3), [])

        desa = Jugador.objects.create(nombre="Baja", apellido="Tres", posicion="POR")
        aplicar_movimiento_a_jugador(desa, "DESAPARECE", self.c1)
        self.assertEqual(errores_movimiento_jugador(desa, None, self.c1), [])
        self.assertEqual(errores_movimiento_jugador(desa, eq_c2, self.c2), [])
        self.assertTrue(any("equipo dado de baja" in e for e in errores_movimiento_jugador(desa, None, self.c3)))

    def test_herencia_desactivada_deja_de_restringir(self):
        j = Jugador.objects.create(nombre="Free", apellido="Cuatro", posicion="DEL")
        he = aplicar_movimiento_a_jugador(j, "DESAPARECE", self.c1)
        self.assertTrue(any("equipo dado de baja" in e for e in errores_movimiento_jugador(j, None, self.c3)))
        he.activo = False
        he.save(update_fields=["activo"])
        self.assertEqual(errores_movimiento_jugador(j, None, self.c3), [])

    def test_alta_duplicado_bloqueado_y_guardado_herencia(self):
        from django.contrib.auth import get_user_model
        existente = Jugador.objects.create(
            nombre="Dup", apellido="Cinco", posicion="DEL", equipo=self.eq_sup,
            fecha_nacimiento=date(1995, 5, 5),
        )
        User = get_user_model()
        admin = User.objects.create_superuser(username="adminh", password="p")
        self.client.force_login(admin)
        # Crear con mismo nombre+fecha: debe bloquear el alta (responder 200 sin crear otro)
        r = self.client.post("/jugadores-heredados/", {
            "accion": "crear",
            "nombre": "Dup", "apellido": "Cinco",
            "fecha_nacimiento": "1995-05-05",
            "tipo": "CASTIGADO", "categoria_id": self.c1.id, "jornadas": "1",
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Jugador.objects.filter(nombre="Dup").count(), 1)
        self.assertContains(r, "Ya existe")
        # Heredar al existente sin nuevo alta
        r2 = self.client.post("/jugadores-heredados/", {
            "accion": "heredar", "jugador_id": existente.id,
            "tipo": "CASTIGADO", "categoria_id": self.c1.id, "jornadas": "1", "motivo": "",
        })
        self.assertEqual(r2.status_code, 302)
        self.assertTrue(SuspensionJugador.objects.filter(jugador=existente, activo=True).exists())
        # Expulsado por castigo heredado: sale del equipo actual y deja el cupo
        existente.refresh_from_db()
        self.assertIsNone(existente.equipo)
        self.assertFalse(
            JugadorEquipo.objects.filter(jugador=existente, equipo=self.eq_sup, activo=True).exists()
        )

    def test_crear_jugador_nuevo_con_herencia(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin = User.objects.create_superuser(username="adminj", password="p")
        self.client.force_login(admin)
        r = self.client.post("/jugadores-heredados/", {
            "accion": "crear",
            "nombre": "Nuevo", "apellido": "Heredado",
            "tipo": "DESCENSO", "categoria_id": self.c2.id, "jornadas": "0", "motivo": "baja previa",
        })
        self.assertEqual(r.status_code, 302)
        j = Jugador.objects.get(nombre="Nuevo")
        self.assertIsNone(j.equipo)
        he = JugadorHerencia.objects.get(jugador=j)
        self.assertEqual(he.tipo, "DESCENSO")
        self.assertEqual(he.categoria_id, self.c2.id)

    def test_busqueda_nombre_completo_con_acentos_sin_acento(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin = User.objects.create_superuser(username="adminbus", password="p")
        self.client.force_login(admin)
        j = Jugador.objects.create(
            nombre="Juan Carlos", apellido="Pérez Ramírez", posicion="DEL",
            equipo=self.eq_sup, fecha_nacimiento=date(1990, 1, 1),
        )
        # Nombre completo en otro orden y sin tildes debe encontrarlo
        r = self.client.get("/jugadores-heredados/", {"q": "juan carlos perez ramirez"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Pérez Ramírez")
        # Buscando solo el apellido compuesto también
        r2 = self.client.get("/jugadores-heredados/", {"q": "perez ramirez"})
        self.assertContains(r2, j.apellido)

    def test_duplicado_solo_por_nombre_y_apellido_bloqueado(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin = User.objects.create_superuser(username="admindup2", password="p")
        self.client.force_login(admin)
        existente = Jugador.objects.create(nombre="Ana", apellido="López", posicion="DEL", equipo=self.eq_sup)
        # Sin CURP ni fecha: solo nombre+apellido (con tilde distinta) debe bloquear
        r = self.client.post("/jugadores-heredados/", {
            "accion": "crear",
            "nombre": "Ana", "apellido": "Lopez",
            "tipo": "CASTIGADO", "categoria_id": self.c1.id, "jornadas": "0",
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Ya existe")
        self.assertEqual(Jugador.objects.filter(nombre="Ana").count(), 1)

    def test_crear_forzado_permite_homonimo(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin = User.objects.create_superuser(username="adminfor", password="p")
        self.client.force_login(admin)
        Jugador.objects.create(nombre="Ana", apellido="López", posicion="DEL", equipo=self.eq_sup)
        r = self.client.post("/jugadores-heredados/", {
            "accion": "crear", "forzar": "1",
            "nombre": "Ana", "apellido": "Lopez",
            "tipo": "CASTIGADO", "categoria_id": self.c1.id, "jornadas": "0", "motivo": "homonimo real",
        })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(Jugador.objects.filter(nombre="Ana").count(), 2)

    def test_heredar_corrige_reemplazando_suspension_anterior(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin = User.objects.create_superuser(username="admincor", password="p")
        self.client.force_login(admin)
        j = Jugador.objects.create(nombre="Alexis", apellido="Montoya", posicion="DEL")
        # Primera herencia: castigado en c2
        self.client.post("/jugadores-heredados/", {
            "accion": "heredar", "jugador_id": j.id,
            "tipo": "CASTIGADO", "categoria_id": self.c2.id, "jornadas": "2", "motivo": "",
        })
        self.assertTrue(SuspensionJugador.objects.filter(jugador=j, activo=True).exists())
        # Corregir: heredar de nuevo con otra categoría no debe bloquear
        r = self.client.post("/jugadores-heredados/", {
            "accion": "heredar", "jugador_id": j.id,
            "tipo": "CASTIGADO", "categoria_id": self.c1.id, "jornadas": "3", "motivo": "ajustado",
        })
        self.assertEqual(r.status_code, 302)
        # Reemplazo: queda una sola herencia activa y un solo registro en total
        self.assertEqual(SuspensionJugador.objects.filter(jugador=j, activo=True).count(), 1)
        susp = SuspensionJugador.objects.get(jugador=j, activo=True)
        self.assertEqual(susp.categoria_id, self.c1.id)
        self.assertEqual(susp.jornadas, 3)
        self.assertEqual(JugadorHerencia.objects.filter(jugador=j).count(), 1)
        he_new = JugadorHerencia.objects.get(jugador=j)
        self.assertTrue(he_new.activo)
        self.assertEqual(he_new.categoria_id, self.c1.id)

    def test_eliminar_castigado_levanta_la_suspension(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin = User.objects.create_superuser(username="admindes", password="p")
        self.client.force_login(admin)
        j = Jugador.objects.create(nombre="Beto", apellido="Des", posicion="MED")
        self.client.post("/jugadores-heredados/", {
            "accion": "heredar", "jugador_id": j.id,
            "tipo": "CASTIGADO", "categoria_id": self.c2.id, "jornadas": "2", "motivo": "",
        })
        self.assertTrue(SuspensionJugador.objects.filter(jugador=j, activo=True).exists())
        he = JugadorHerencia.objects.get(jugador=j)
        r = self.client.post("/jugadores-heredados/", {
            "accion": "eliminar", "herencia_id": he.id,
        })
        self.assertEqual(r.status_code, 302)
        self.assertFalse(JugadorHerencia.objects.filter(jugador=j).exists())
        self.assertFalse(SuspensionJugador.objects.filter(jugador=j, activo=True).exists())

    def test_herencia_desaparece_saca_del_equipo_incompatible(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin = User.objects.create_superuser(username="adminmov", password="p")
        self.client.force_login(admin)
        # Orden: c1=Primera(nivel 0), c2=Intermedia(1), c3=Segunda(2)
        eq_3 = Equipo.objects.create(nombre="SegundaH Club", categoria=self.c3, activo=True)
        j = Jugador.objects.create(nombre="Dani", apellido="Oli", posicion="DEL", equipo=eq_3)
        rer = self.client.post("/jugadores-heredados/", {
            "accion": "heredar", "jugador_id": j.id,
            "tipo": "DESAPARECE", "categoria_id": self.c1.id, "jornadas": "0", "motivo": "",
        })
        self.assertEqual(rer.status_code, 302)
        j.refresh_from_db()
        self.assertIsNone(j.equipo)
        # Registro desactivado (historial conservado) y no aparece en listas
        self.assertFalse(JugadorEquipo.objects.filter(jugador=j, equipo=eq_3, activo=True).exists())
        self.assertEqual(JugadorEquipo.objects.filter(jugador=j, equipo=eq_3).count(), 1)

    def test_herencia_descenso_conserva_equipo_compatible(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        admin = User.objects.create_superuser(username="admincon", password="p")
        self.client.force_login(admin)
        eq_3 = Equipo.objects.create(nombre="SegundaH Club B", categoria=self.c3, activo=True)
        j = Jugador.objects.create(nombre="Ana", apellido="Com", posicion="DEF", equipo=eq_3)
        r = self.client.post("/jugadores-heredados/", {
            "accion": "heredar", "jugador_id": j.id,
            "tipo": "DESCENSO", "categoria_id": self.c1.id, "jornadas": "0", "motivo": "",
        })
        self.assertEqual(r.status_code, 302)
        j.refresh_from_db()
        # c3 está por debajo (nivel 2): descendido en c1(nivel 0) sí puede jugar ahí
        self.assertEqual(j.equipo_id, eq_3.id)
        self.assertTrue(JugadorEquipo.objects.filter(jugador=j, equipo=eq_3, activo=True).exists())
