from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from . import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.home, name="home"),
    path("accounts/", include("accounts.urls")),
    path("", include("league.urls")),
    path("finanzas/", include("finance.urls")),
    path("reportes/", include("reports.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    urlpatterns += [
        path(f"{settings.MEDIA_URL.lstrip('/')}<path:path>", serve, {"document_root": settings.MEDIA_ROOT}),
    ]
