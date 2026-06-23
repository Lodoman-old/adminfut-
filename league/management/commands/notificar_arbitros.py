from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from league.models import Partido, DeviceToken
from league.push import send_push_notification


class Command(BaseCommand):
    help = "Envía notificaciones push a árbitros 30 min antes de su partido"

    def handle(self, *args, **options):
        ahora = timezone.now()
        ventana = ahora + timedelta(minutes=30)

        partidos = Partido.objects.filter(
            fecha_hora__gte=ahora,
            fecha_hora__lte=ventana,
            estado="PEND",
            arbitro__isnull=False,
            arbitro__usuario__isnull=False,
            recordatorio_30min_enviado=False,
        ).select_related("campo", "equipo_local", "equipo_visitante", "arbitro__usuario")

        enviadas = 0
        for p in partidos:
            tokens = list(
                DeviceToken.objects.filter(
                    usuario=p.arbitro.usuario, activo=True
                ).values_list("token", flat=True)
            )
            if not tokens:
                continue

            hora = p.fecha_hora.astimezone(timezone.get_current_timezone()).strftime("%H:%M")
            lugar = p.campo.nombre if p.campo else "Por definir"
            title = f"Partido en 30 min"
            body = f"{p.equipo_local} vs {p.equipo_visitante} - {hora} - {lugar}"

            send_push_notification(tokens, title, body, {
                "type": "recordatorio_arbitro",
                "partido_id": str(p.id),
            })
            Partido.objects.filter(pk=p.pk).update(recordatorio_30min_enviado=True)
            enviadas += 1

        self.stdout.write(self.style.SUCCESS(f"Notificaciones enviadas: {enviadas}"))
