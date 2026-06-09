from django.contrib import admin
from .models import ConceptoIngreso, Ingreso


@admin.register(ConceptoIngreso)
class ConceptoIngresoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "tipo", "monto_defecto", "activo", "no_eliminar"]
    readonly_fields = ["no_eliminar"]

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if obj and obj.no_eliminar:
            return [f.name for f in self.model._meta.fields if f.name != "monto_defecto"]
        return fields

    def has_delete_permission(self, request, obj=None):
        if obj and obj.no_eliminar:
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions


@admin.register(Ingreso)
class IngresoAdmin(admin.ModelAdmin):
    list_display = [
        "concepto", "monto", "fecha", "equipo", "registrado_por"
    ]
    list_filter = ["concepto", "fecha"]
