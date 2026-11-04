import os

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateStorage(FileSystemStorage):
    """Almacenamiento fuera de MEDIA_ROOT (no accesible por /media/)."""

    def __init__(self):
        super().__init__(location=os.path.join(settings.BASE_DIR, "private_media"))
