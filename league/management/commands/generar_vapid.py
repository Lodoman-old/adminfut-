from django.core.management.base import BaseCommand
from league.push import _vapid_keys


class Command(BaseCommand):
    help = "Genera (si faltan) las claves VAPID para Web Push y muestra la clave pública."

    def handle(self, *args, **options):
        private_key, public_key = _vapid_keys()
        self.stdout.write(self.style.SUCCESS("Claves VAPID listas."))
        self.stdout.write("applicationServerKey (pública): {}".format(public_key))
        self.stdout.write("clave privada (oculta): {}...".format(private_key[:16]))
