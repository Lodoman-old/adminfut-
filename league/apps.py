import os

from django.apps import AppConfig


class LeagueConfig(AppConfig):
    name = 'league'

    def ready(self):
        try:
            from .models import ConfiguracionLiga
            config = ConfiguracionLiga.objects.filter(pk=1).values(
                'cloudinary_cloud_name', 'cloudinary_api_key', 'cloudinary_api_secret'
            ).first()
            if config and config['cloudinary_cloud_name'] and config['cloudinary_api_key'] and config['cloudinary_api_secret']:
                import cloudinary
                cloudinary.config(
                    cloud_name=config['cloudinary_cloud_name'],
                    api_key=config['cloudinary_api_key'],
                    api_secret=config['cloudinary_api_secret'],
                    secure=True,
                )
                os.environ['CLOUDINARY_URL'] = f"cloudinary://{config['cloudinary_api_key']}:{config['cloudinary_api_secret']}@{config['cloudinary_cloud_name']}"
                from django.core.files.storage import default_storage
                from django.utils.functional import empty
                default_storage._wrapped = empty
        except Exception:
            pass
