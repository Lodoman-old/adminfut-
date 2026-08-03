from django import template

register = template.Library()

MAPA_ALERTAS = {
    "error": "danger",
    "debug": "secondary",
}


@register.filter
def dict_key(d, key):
    try:
        key = str(key)
    except (ValueError, TypeError):
        return None
    return d.get(key)


@register.filter
def bootstrap_alert(tag):
    return MAPA_ALERTAS.get(tag, tag)


@register.filter
def get_item(d, key):
    """Accede a un attributo/ítem de un objeto por nombre."""
    if hasattr(d, str(key)):
        return getattr(d, key)
    try:
        return d[key]
    except (KeyError, TypeError, IndexError):
        return None


@register.filter
def dos_lineas(nombre):
    """Divide un nombre de liga en dos líneas (tupla). La segunda línea lleva
    las últimas 2 palabras, para nombres tipo 'Liga Municipal de Futbol
    Juventino Rosas' -> 'Liga Municipal de Futbol' / 'Juventino Rosas'."""
    partes = str(nombre or "").strip().split()
    if len(partes) >= 4:
        return " ".join(partes[:-2]), " ".join(partes[-2:])
    if len(partes) == 3:
        return " ".join(partes[:2]), partes[2]
    if len(partes) == 2:
        return partes[0], partes[1]
    return nombre or "AdminFut", ""
