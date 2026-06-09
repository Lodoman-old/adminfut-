from django import template

register = template.Library()


@register.filter
def tiene_permiso(user, permiso):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not user.rol:
        return False
    return user.rol.permisos.get(permiso, False)


@register.filter
def dict_key(d, key):
    return d.get(key, False)
