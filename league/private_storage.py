import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateStorage(FileSystemStorage):
    """Almacenamiento fuera de MEDIA_ROOT (no accesible por /media/)."""

    def __init__(self):
        location = os.environ.get("PRIVATE_MEDIA_ROOT") or os.path.join(
            settings.BASE_DIR, "private_media"
        )
        super().__init__(location=location)
