from django import forms
from .models import Ingreso, ConceptoIngreso
from league.models import Categoria, Temporada


class ConceptoIngresoForm(forms.ModelForm):
    no_eliminar = forms.BooleanField(
        required=False, disabled=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch", "disabled": True}),
        label="Protegido (no eliminar)",
    )

    class Meta:
        model = ConceptoIngreso
        fields = ["tipo", "nombre", "descripcion", "monto_defecto", "requiere_jugador", "requiere_equipo", "requiere_categoria", "excluir_pagados", "activo", "no_eliminar"]
        widgets = {
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "nombre": forms.TextInput(attrs={"class": "form-control"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "monto_defecto": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "requiere_jugador": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "requiere_equipo": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "requiere_categoria": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "excluir_pagados": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "categoria": forms.Select(attrs={"class": "form-select"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = kwargs.get("instance")
        if inst and inst.pk and inst.no_eliminar:
            for field_name in self.fields:
                if field_name != "monto_defecto":
                    self.fields[field_name].disabled = True


class IngresoForm(forms.ModelForm):
    class Meta:
        model = Ingreso
        fields = ["concepto", "cantidad", "monto", "fecha", "equipo", "jugador", "descripcion", "pagado_a"]
        widgets = {
            "concepto": forms.Select(attrs={"class": "form-select"}),
            "cantidad": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "monto": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "equipo": forms.Select(attrs={"class": "form-select"}),
            "jugador": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "pagado_a": forms.TextInput(attrs={"class": "form-control", "placeholder": "Proveedor o persona"}),
        }


class IngresoPOSForm(forms.ModelForm):
    billete = forms.DecimalField(
        max_digits=10, decimal_places=2, required=False, initial=0,
        widget=forms.NumberInput(attrs={
            "step": "0.01", "class": "form-control form-control-lg", "id": "id_billete",
            "placeholder": "0.00"
        }),
        label="Recibí"
    )
    pos_categoria = forms.ModelChoiceField(
        queryset=Categoria.objects.filter(activo=True), required=False, label="Categoría",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_pos_categoria"})
    )
    pos_temporada = forms.ModelChoiceField(
        queryset=Temporada.objects.none(), required=False, label="Temporada",
        widget=forms.Select(attrs={"class": "form-select", "id": "id_pos_temporada"})
    )

    class Meta:
        model = Ingreso
        fields = ["concepto", "cantidad", "monto", "fecha", "equipo", "jugador", "descripcion", "pagado_a", "temporada"]
        widgets = {
            "cantidad": forms.NumberInput(attrs={"min": "1", "class": "form-control form-control-lg", "id": "id_cantidad", "value": "1"}),
            "fecha": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "monto": forms.NumberInput(attrs={"step": "0.01", "class": "form-control form-control-lg", "id": "id_monto_pos", "autofocus": True}),
            "concepto": forms.Select(attrs={"class": "form-select", "id": "id_concepto_pos"}),
            "temporada": forms.Select(attrs={"class": "form-select"}),
            "equipo": forms.Select(attrs={"class": "form-select"}),
            "jugador": forms.Select(attrs={"class": "form-select"}),
            "descripcion": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "pagado_a": forms.TextInput(attrs={"class": "form-control", "id": "id_pagado_a", "placeholder": "Proveedor o persona"}),
        }

    def clean(self):
        cleaned = super().clean()
        concepto = cleaned.get("concepto")
        equipo = cleaned.get("equipo")
        if concepto and concepto.requiere_equipo and not equipo:
            self.add_error("equipo", "Este concepto requiere seleccionar un equipo.")
        if concepto and concepto.requiere_jugador and not cleaned.get("jugador"):
            self.add_error("jugador", "Este concepto requiere seleccionar un jugador.")
        if concepto and concepto.requiere_categoria and not cleaned.get("temporada"):
            self.add_error("temporada", "Este concepto requiere seleccionar categoría y temporada.")
        return cleaned
