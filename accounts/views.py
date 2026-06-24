from django.shortcuts import render, redirect
from django.contrib.auth import logout as auth_logout
from django.http import JsonResponse
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordChangeDoneView
from django.contrib.auth.forms import PasswordChangeForm
from django.urls import reverse_lazy, reverse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django import forms
from league.models import Categoria
from .models import Usuario, Rol, PERMISOS_MENU, get_permisos_flat


PERMISOS_FLAT = get_permisos_flat()


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"

    def get_success_url(self):
        return reverse("biometric_verify")


class CustomLogoutView(View):
    def get(self, request):
        auth_logout(request)
        return render(request, "accounts/logout.html")


class UsuarioForm(forms.ModelForm):
    password = forms.CharField(
        label="Contraseña", required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        help_text="Dejar vacío para mantener la contraseña actual (solo en edición)."
    )

    class Meta:
        model = Usuario
        fields = ["username", "first_name", "last_name", "email", "telefono", "rol", "is_active", "categoria_preferida"]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "telefono": forms.TextInput(attrs={"class": "form-control"}),
            "rol": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "categoria_preferida": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["password"].required = False
        else:
            self.fields["password"].required = True
        if self.instance and self.instance.pk and self.instance.es_admin:
            self.fields["rol"].disabled = True
            self.fields["rol"].help_text = "El administrador no puede cambiar de rol."
            self.fields["is_active"].disabled = True
            self.fields["is_active"].help_text = "El administrador no puede desactivarse."

    def save(self, commit=True):
        instance = super().save(commit=False)
        password = self.cleaned_data.get("password")
        if password:
            instance.set_password(password)
        if commit:
            instance.save()
        return instance


class UsuarioListView(LoginRequiredMixin, ListView):
    model = Usuario
    template_name = "accounts/usuario_list.html"
    context_object_name = "usuarios"


class UsuarioCreateView(LoginRequiredMixin, CreateView):
    model = Usuario
    form_class = UsuarioForm
    template_name = "accounts/usuario_form.html"
    success_url = reverse_lazy("usuario_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nuevo Usuario"
        return ctx


class UsuarioUpdateView(LoginRequiredMixin, UpdateView):
    model = Usuario
    form_class = UsuarioForm
    template_name = "accounts/usuario_form.html"
    success_url = reverse_lazy("usuario_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Usuario"
        return ctx

    def form_valid(self, form):
        if self.object.es_admin:
            messages.success(self.request, "Datos del administrador actualizados.")
        return super().form_valid(form)


class UsuarioDeleteView(LoginRequiredMixin, DeleteView):
    model = Usuario
    template_name = "accounts/usuario_confirm_delete.html"
    success_url = reverse_lazy("usuario_list")
    context_object_name = "usuario"

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.es_admin:
            messages.error(request, "El administrador no puede ser eliminado.")
            return redirect("usuario_list")
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.es_admin:
            messages.error(request, "El administrador no puede ser eliminado.")
            return redirect("usuario_list")
        return super().post(request, *args, **kwargs)


# ─── Roles ───────────────────────────────────────────────────────────────────


class RolForm(forms.ModelForm):
    class Meta:
        model = Rol
        fields = ["nombre"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Administrador"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        permisos_iniciales = self.instance.permisos if self.instance.pk else {}
        for key, label, grupo, recurso, public in PERMISOS_FLAT:
            field_name = f"perm_{key}"
            self.fields[field_name] = forms.BooleanField(
                label=label, required=False,
                initial=permisos_iniciales.get(key, False),
                widget=forms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        permisos = {}
        for key, label, grupo, recurso, public in PERMISOS_FLAT:
            permisos[key] = self.cleaned_data.get(f"perm_{key}", False)
        instance.permisos = permisos
        if commit:
            instance.save()
        return instance


class RolListView(LoginRequiredMixin, ListView):
    model = Rol
    template_name = "accounts/rol_list.html"
    context_object_name = "roles"


class RolCreateView(LoginRequiredMixin, CreateView):
    model = Rol
    form_class = RolForm
    template_name = "accounts/rol_form.html"
    success_url = reverse_lazy("rol_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Nuevo Rol"
        ctx["permisos_menu"] = PERMISOS_MENU
        return ctx


class RolUpdateView(LoginRequiredMixin, UpdateView):
    model = Rol
    form_class = RolForm
    template_name = "accounts/rol_form.html"
    success_url = reverse_lazy("rol_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["titulo"] = "Editar Rol"
        ctx["permisos_menu"] = PERMISOS_MENU
        return ctx


class RolDeleteView(LoginRequiredMixin, DeleteView):
    model = Rol
    template_name = "accounts/rol_confirm_delete.html"
    success_url = reverse_lazy("rol_list")
    context_object_name = "rol"


class CustomPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class CustomPasswordChangeView(LoginRequiredMixin, PasswordChangeView):
    form_class = CustomPasswordChangeForm
    template_name = "accounts/password_change.html"
    success_url = reverse_lazy("password_change_done")


def biometric_verify(request):
    if not request.user.is_authenticated:
        return redirect("login")

    if request.method == "POST":
        request.session["bio_verified"] = True
        return JsonResponse({"ok": True, "redirect": str(reverse("home"))})

    if request.session.get("bio_verified"):
        return redirect("home")

    return render(request, "accounts/biometric_verify.html")


def registro_invitado(request):
    categorias = Categoria.objects.filter(activo=True)
    return render(request, "accounts/registro_invitado.html", {
        "categorias": categorias,
    })
