from django.urls import path
from django.contrib.auth.views import PasswordChangeDoneView
from . import views

urlpatterns = [
    path("login/", views.CustomLoginView.as_view(), name="login"),
    path("logout/", views.CustomLogoutView.as_view(), name="logout"),
    path("cambiar-password/", views.CustomPasswordChangeView.as_view(), name="password_change"),
    path("cambiar-password/hecho/", PasswordChangeDoneView.as_view(
        template_name="accounts/password_change_done.html",
    ), name="password_change_done"),
    path("usuarios/", views.UsuarioListView.as_view(), name="usuario_list"),
    path("usuarios/nuevo/", views.UsuarioCreateView.as_view(), name="usuario_create"),
    path("usuarios/<int:pk>/editar/", views.UsuarioUpdateView.as_view(), name="usuario_update"),
    path("usuarios/<int:pk>/eliminar/", views.UsuarioDeleteView.as_view(), name="usuario_delete"),
    path("roles/", views.RolListView.as_view(), name="rol_list"),
    path("roles/nuevo/", views.RolCreateView.as_view(), name="rol_create"),
    path("roles/<int:pk>/editar/", views.RolUpdateView.as_view(), name="rol_update"),
    path("roles/<int:pk>/eliminar/", views.RolDeleteView.as_view(), name="rol_delete"),
]
