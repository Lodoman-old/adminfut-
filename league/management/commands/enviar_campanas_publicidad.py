"""Envía las campañas de publicidad que ya cumplieron su fecha."""
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from league.campanas import enviar_campana, proxima_fecha
from league.models import CampanaPublicidad


class Command(BaseCommand):
    help = "Envía las campañas de publicidad programadas que ya tocan."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Muestra qué campañas se enviarían, sin enviar nada.",
        )

    def handle(self, *args, **options):
        ahora = timezone.now()
        campanas = (
            CampanaPublicidad.objects
            .filter(activa=True, proximo_envio__lte=ahora)
            .select_related("anuncio")
            .order_by("proximo_envio")
        )
        if not campanas.exists():
            self.stdout.write("Sin campañas pendientes.")
            return

        for campana in campanas:
            etiqueta = f"Campaña {campana.id} ({campana.anuncio.titulo})"
            if not campana.anuncio.activo or not campana.anuncio.vigente():
                self.stdout.write(f"{etiqueta}: omitida (anuncio inactivo o vencido)")
                continue
            if options["dry_run"]:
                self.stdout.write(f"{etiqueta}: se enviaría ahora ({campana.cada_dias} días)")
                continue
            if not cache.add(f"campana_lock:{campana.id}", 1, 600):
                self.stdout.write(f"{etiqueta}: omitida (otra ejecución en curso)")
                continue
            try:
                resultado = enviar_campana(campana)
                if resultado and not resultado.get("omitida"):
                    campana.ultimo_envio = ahora
                    campana.proximo_envio = proxima_fecha(campana, ahora)
                    campana.save(update_fields=[
                        "ultimo_envio", "proximo_envio", "actualizada",
                    ])
                    self.stdout.write(
                        "{}: {} ok, {} fallos; próximo {}".format(
                            etiqueta,
                            resultado.get("success", 0),
                            resultado.get("failure", 0),
                            timezone.localtime(campana.proximo_envio).strftime("%d/%m/%Y %H:%M"),
                        )
                    )
                else:
                    motivo = resultado.get("omitida") if resultado else "sin resultado"
                    self.stdout.write(f"{etiqueta}: omitida ({motivo})")
            finally:
                cache.delete(f"campana_lock:{campana.id}")
