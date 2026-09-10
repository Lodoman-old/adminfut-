from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from league.models import Temporada, Jornada, Partido


class Command(BaseCommand):
    help = (
        "Borra las jornadas desde --jornada-inicial en adelante y regenera el rol "
        "respetando las jornadas anteriores capturadas a mano."
    )

    def add_arguments(self, parser):
        parser.add_argument("--temporada", type=int, required=True, help="ID de la temporada")
        parser.add_argument("--jornada-inicial", type=int, required=True,
                            help="Jornada X desde donde regenerar (las < X se conservan)")
        parser.add_argument("--force", action="store_true", help="No pedir confirmación")
        parser.add_argument("--dry-run", action="store_true", help="Solo mostrar qué haría")

    def handle(self, *args, **options):
        try:
            temporada = Temporada.objects.get(pk=options["temporada"])
        except Temporada.DoesNotExist:
            raise CommandError(f"No existe temporada con id {options['temporada']}")

        x = options["jornada_inicial"]
        pj = temporada.partidos_por_jornada()

        pasadas = temporada.jornadas.filter(numero__lt=x)
        incompletas = []
        for j in pasadas.order_by("numero"):
            cnt = Partido.objects.filter(temporada=temporada, jornada=j).count()
            if cnt != pj:
                incompletas.append(f"Jornada {j.numero}: {cnt}/{pj}")

        if incompletas:
            raise CommandError(
                "Jornadas anteriores incompletas (esperado %d por jornada): %s"
                % (pj, "; ".join(incompletas)))

        ok_p, errores_p = temporada.validar_continuacion_rol()
        if not ok_p:
            raise CommandError(
                "No se puede completar el rol con las jornadas capturadas: "
                + "; ".join(errores_p))

        numeros_existentes = sorted(
            temporada.jornadas.values_list("numero", flat=True))
        a_borrar = [n for n in numeros_existentes if n >= x]

        self.stdout.write("=" * 60)
        self.stdout.write(f"Temporada: {temporada.nombre} (id={temporada.id})")
        self.stdout.write(f"Partidos por jornada esperados: {pj}")
        self.stdout.write(f"Jornadas existentes: {numeros_existentes}")
        self.stdout.write(f"Se conservan (< {x}): {[n for n in numeros_existentes if n < x]}")
        self.stdout.write(f"Se borran y regeneran (>= {x}): {a_borrar}")

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Modo dry-run: nada se modifica."))
            return

        if not a_borrar:
            self.stdout.write(self.style.WARNING("No hay jornadas >= %d que borrar." % x))
            return

        if not options["force"]:
            resp = input(f"¿Borrar {len(a_borrar)} jornadas (>= {x}) y regenerar? [s/N]: ")
            if resp.strip().lower() not in ("s", "si", "sí", "y", "yes"):
                self.stdout.write(self.style.WARNING("Cancelado."))
                return

        with transaction.atomic():
            j_qs = temporada.jornadas.filter(numero__gte=x)
            Partido.objects.filter(temporada=temporada, jornada__in=j_qs).delete()
            borradas = j_qs.delete()[0]
            temporada.generar_rol_respaldando_pasadas(jornada_inicial=x)

        pasadas_cnt = temporada.partidos.count()
        nums = sorted(temporada.jornadas.values_list("numero", flat=True))
        self.stdout.write(self.style.SUCCESS(
            f"Listo. Borradas {borradas} jornadas desde la {x}, regeneradas.")
        )
        self.stdout.write(f"Jornadas finales: {nums} (total {len(nums)})")
        self.stdout.write(f"Partidos totales: {pasadas_cnt}")
        por_j = {n: Partido.objects.filter(temporada=temporada, jornada__numero=n).count()
                 for n in nums}
        self.stdout.write(f"Partidos por jornada: {por_j}")