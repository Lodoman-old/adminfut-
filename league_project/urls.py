from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views
from league.views import (
    admin_push_logs,
    cedulas_capturas,
    cedula_captura_foto,
    cedula_captura_leer,
    cedula_captura_asignar,
    cedula_captura_eliminar,
    cedula_captura_limpiar,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", views.health, name="health"),
    path("robots.txt", views.robots_txt, name="robots_txt"),
    path("push-logs/", admin_push_logs, name="admin_push_logs"),
    path("push-logs/cedulas/", cedulas_capturas, name="cedulas_capturas"),
    path("push-logs/cedulas/limpiar/", cedula_captura_limpiar, name="cedula_captura_limpiar"),
    path("push-logs/cedulas/<int:pk>/foto/", cedula_captura_foto, name="cedula_captura_foto"),
    path("push-logs/cedulas/<int:pk>/leer/", cedula_captura_leer, name="cedula_captura_leer"),
    path("push-logs/cedulas/<int:pk>/asignar/", cedula_captura_asignar, name="cedula_captura_asignar"),
    path("push-logs/cedulas/<int:pk>/eliminar/", cedula_captura_eliminar, name="cedula_captura_eliminar"),
    path("", views.home, name="home"),
    path("change-server/", views.change_server, name="change_server"),
    path("accounts/", include("accounts.urls")),
    path("", include("league.urls")),
    path("finanzas/", include("finance.urls")),
    path("reportes/", include("reports.urls")),
]

if settings.DEBUG and settings.MEDIA_ROOT:
    urlpatterns += static('media/', document_root=settings.MEDIA_ROOT)
