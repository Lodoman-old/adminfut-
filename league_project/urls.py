from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.admin.views.decorators import staff_member_required
from . import views
from league.views import admin_push_logs

urlpatterns = [
    path("admin/push-logs/", staff_member_required(admin_push_logs), name="admin_push_logs"),
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("accounts/", include("accounts.urls")),
    path("", include("league.urls")),
    path("finanzas/", include("finance.urls")),
    path("reportes/", include("reports.urls")),
]

if settings.DEBUG and settings.MEDIA_ROOT:
    urlpatterns += static('media/', document_root=settings.MEDIA_ROOT)
