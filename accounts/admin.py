from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Rol, Usuario


@admin.register(Rol)
class RolAdmin(admin.ModelAdmin):
    list_display = ["nombre"]


@admin.register(Usuario)
class UsuarioAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("Información extra", {"fields": ("rol", "telefono", "categoria_preferida")}),
    )
    list_display = UserAdmin.list_display + ("rol", "categoria_preferida")
