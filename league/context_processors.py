def configuracion_global(request):
    from league.models import ConfiguracionLiga
    try:
        return {"config": ConfiguracionLiga.obtener()}
    except Exception:
        return {"config": None}
