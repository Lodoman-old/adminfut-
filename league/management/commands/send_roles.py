from django.core.management.base import BaseCommand
from league.models import Temporada, Jornada, Partido, SuscripcionEmail, ConfiguracionLiga
from league.views import _obtener_jornada_actual, _enviar_correo_suscriptores


class Command(BaseCommand):
    help = "Envía el rol de juegos por correo a todos los suscriptores activos"

    def add_arguments(self, parser):
        parser.add_argument("--temporada", type=int, help="ID de la temporada")
        parser.add_argument("--jornada", type=int, help="ID de la jornada específica")
        parser.add_argument("--todas", action="store_true", help="Enviar todas las temporadas activas")

    def handle(self, *args, **options):
        config = ConfiguracionLiga.obtener()
        if not config.email_smtp_host:
            self.stderr.write("SMTP no configurado. Configúralo en /configuracion/")
            return

        temporadas = []
        if options["temporada"]:
            temporadas = [Temporada.objects.get(pk=options["temporada"])]
        elif options["todas"]:
            temporadas = Temporada.objects.filter(iniciada=True, finalizada=False)
        else:
            self.stderr.write("Especifica --temporada o --todas")
            return

        for temporada in temporadas:
            partidos_qs = Partido.objects.filter(temporada=temporada, estado="PEND").select_related(
                "equipo_local", "equipo_visitante", "campo", "jornada"
            ).order_by("jornada__numero", "fecha_hora")

            if options["jornada"]:
                partidos_qs = partidos_qs.filter(jornada_id=options["jornada"])
            elif config.enviar_solo_jornada_actual:
                jornada = _obtener_jornada_actual(temporada)
                if jornada:
                    partidos_qs = partidos_qs.filter(jornada=jornada)

            partidos = list(partidos_qs)
            if not partidos:
                self.stdout.write(f"Sin partidos pendientes para '{temporada}'")
                continue

            suscriptores = SuscripcionEmail.objects.filter(activo=True, recibir_roles=True)
            count = 0
            for sus in suscriptores:
                cats = sus.categorias.all()
                if cats and not cats.filter(id=temporada.categoria_id).exists():
                    continue
                ctx = {"temporada": temporada, "partidos": partidos}
                count += _enviar_correo_suscriptores(
                    [sus], config, f"Rol de juegos - {temporada.nombre}",
                    "emails/roles_semana.html", ctx
                )

            self.stdout.write(self.style.SUCCESS(f"'{temporada}': {count} correos enviados"))
