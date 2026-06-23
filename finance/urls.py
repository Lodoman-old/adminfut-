from django.urls import path
from . import views

urlpatterns = [
    path("conceptos/", views.ConceptoListView.as_view(), name="concepto_list"),
    path("conceptos/nuevo/", views.ConceptoCreateView.as_view(), name="concepto_create"),
    path("conceptos/<int:pk>/editar/", views.ConceptoUpdateView.as_view(), name="concepto_update"),
    path("conceptos/<int:pk>/eliminar/", views.ConceptoDeleteView.as_view(), name="concepto_delete"),

    path("ingresos/", views.IngresoListView.as_view(), name="ingreso_list"),
    path("ingresos/nuevo/", views.IngresoCreateView.as_view(), name="ingreso_create"),
    path("ingresos/<int:pk>/editar/", views.IngresoUpdateView.as_view(), name="ingreso_update"),
    path("ingresos/<int:pk>/eliminar/", views.IngresoDeleteView.as_view(), name="ingreso_delete"),

    path("ingresos/pos/", views.ingreso_pos, name="ingreso_pos"),
    path("ingresos/<int:pk>/ticket/", views.ingreso_ticket, name="ingreso_ticket"),

    path("caja/", views.caja_dashboard, name="caja_dashboard"),
    path("caja/aperturar/", views.caja_aperturar, name="caja_aperturar"),
    path("caja/corte/", views.caja_corte, name="caja_corte"),
    path("caja/<int:pk>/cerrar/", views.caja_cerrar, name="caja_cerrar"),
    path("caja/<int:pk>/", views.caja_detail, name="caja_detail"),
]