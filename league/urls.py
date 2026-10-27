from django.urls import path
from . import views
from . import api_views

urlpatterns = [
    path("equipo/<int:pk>/", views.equipo_ficha, name="equipo_ficha"),
]
