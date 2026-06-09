from django.core.management.base import BaseCommand
from django.db.models import Count, Q
from league.models import Temporada, Gol, Tarjeta, SuscripcionEmail, ConfiguracionLiga
from league.views import _enviar_correo_suscriptores


class Command(BaseCommand):
    help = "Envía las estadísticas por correo a todos los suscriptores activos"

    def add_arguments(self, parser):
        parser.add_argument("--temporada", type=int, help="ID de la temporada")
        parser.add_argument("--todas", action="store_true", help="Enviar todas las temporadas activas")

    def handle(self, *args, **options):
        config = ConfiguracionLiga.obtener()
        if not config.email_smtp_host:
            self.stderr.write("SMTP no configurado.")
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
            goleadores = list(
                Gol.objects.filter(partido__temporada=temporada)
                .values("jugador__nombre", "jugador__apellido", "equipo__nombre")
                .annotate(total=Count("id"))
                .order_by("-total")[:10]
            )

            grupos_mode = temporada.tipo_rol == "GRUPOS" and temporada.clasificacion_por_grupos
            if grupos_mode:
                tablas_por_grupo = temporada.calcular_tablas_por_grupo(limit=5)
                grupos = temporada.grupos_asignados()
                ng = len(grupos)
                por_grupo = max(1, temporada.num_clasificados // max(ng, 1)) if ng else 0
                tabla = []
            else:
                tabla = temporada.calcular_tabla(limit=5)
                tablas_por_grupo = None
                por_grupo = 0

            castigados = list(
                Tarjeta.objects.filter(partido__temporada=temporada)
                .values("jugador__nombre", "jugador__apellido", "equipo__nombre")
                .annotate(rojas=Count("id", filter=Q(tipo="ROJA")), amarillas=Count("id", filter=Q(tipo="AMARILLA")))
                .order_by("-rojas", "-amarillas")[:10]
            )

            suscriptores = SuscripcionEmail.objects.filter(activo=True, recibir_estadisticas=True)
            count = 0
            for sus in suscriptores:
                cats = sus.categorias.all()
                if cats and not cats.filter(id=temporada.categoria_id).exists():
                    continue
                ctx = {"temporada": temporada, "goleadores": goleadores, "tabla": tabla, "tablas_por_grupo": tablas_por_grupo, "por_grupo": por_grupo, "castigados": castigados}
                count += _enviar_correo_suscriptores(
                    [sus], config, f"Estadísticas - {temporada.nombre}",
                    "emails/estadisticas.html", ctx
                )

            self.stdout.write(self.style.SUCCESS(f"'{temporada}': {count} correos enviados"))
