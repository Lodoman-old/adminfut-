def configuracion_global(request):
    from pathlib import Path

    from django.conf import settings

    from league.models import ConfiguracionLiga

    apk = Path(settings.BASE_DIR) / "static" / "apk" / "AdminFut.apk"
    try:
        return {"config": ConfiguracionLiga.obtener(), "apk_disponible": apk.exists()}
    except Exception:
        return {"config": None, "apk_disponible": apk.exists()}
