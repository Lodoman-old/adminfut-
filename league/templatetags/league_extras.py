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
