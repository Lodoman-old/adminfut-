from django.views.generic import ListView, CreateView, UpdateView, DeleteView, View
from django.urls import reverse_lazy, reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib import messages
from .models import ConceptoIngreso, Ingreso
from .forms import IngresoPOSForm, ConceptoIngresoForm, IngresoForm
from league.models import ConfiguracionLiga, Categoria, Temporada, Equipo


class ConceptoListView(ListView):
    model = ConceptoIngreso
    template_name = "finance/concepto_list.html"
    context_object_name = "conceptos"


class ConceptoCreateView(CreateView):
    model = ConceptoIngreso
    form_class = ConceptoIngresoForm
    template_name = "finance/concepto_form.html"
    success_url = reverse_lazy("concepto_list")


class ConceptoUpdateView(UpdateView):
    model = ConceptoIngreso
    form_class = ConceptoIngresoForm
    template_name = "finance/concepto_form.html"
    success_url = reverse_lazy("concepto_list")


class ConceptoDeleteView(DeleteView):
    model = ConceptoIngreso
    template_name = "finance/concepto_confirm_delete.html"
    success_url = reverse_lazy("concepto_list")

    def get(self, request, *args, **kwargs):
        concepto = self.get_object()
        if concepto.no_eliminar:
            messages.error(request, f"El concepto '{concepto.nombre}' está protegido y no puede eliminarse.")
            return redirect("concepto_list")
        return super().get(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        concepto = self.get_object()
        if concepto.no_eliminar:
            messages.error(request, f"El concepto '{concepto.nombre}' está protegido y no puede eliminarse.")
            return redirect("concepto_list")
        return super().delete(request, *args, **kwargs)


class IngresoListView(ListView):
    model = Ingreso
    template_name = "finance/ingreso_list.html"
    context_object_name = "ingresos"

    def get_queryset(self):
        return Ingreso.objects.all().select_related("concepto", "equipo", "registrado_por")


class IngresoCreateView(CreateView):
    model = Ingreso
    form_class = IngresoForm
    template_name = "finance/ingreso_form.html"
    success_url = reverse_lazy("ingreso_list")

    def form_valid(self, form):
        form.instance.registrado_por = self.request.user
        return super().form_valid(form)


class IngresoUpdateView(UpdateView):
    model = Ingreso
    form_class = IngresoForm
    template_name = "finance/ingreso_form.html"
    success_url = reverse_lazy("ingreso_list")


class IngresoDeleteView(DeleteView):
    model = Ingreso
    template_name = "finance/ingreso_confirm_delete.html"
    success_url = reverse_lazy("ingreso_list")


def ingreso_pos(request):
    config = ConfiguracionLiga.obtener()
    tipo_filtro = request.GET.get("tipo", "INGRESO")
    conceptos = ConceptoIngreso.objects.filter(activo=True)
    categorias = Categoria.objects.filter(activo=True)
    ultimos = Ingreso.objects.all().select_related("concepto", "equipo").order_by("-fecha_registro")[:10]
    ticket_ingreso = None
    ticket_pk = request.GET.get("ticket")

    if ticket_pk:
        try:
            ticket_ingreso = Ingreso.objects.select_related(
                "concepto", "equipo", "jugador", "registrado_por"
            ).get(pk=ticket_pk)
        except Ingreso.DoesNotExist:
            pass

    if request.method == "POST":
        form = IngresoPOSForm(request.POST)
        # Populate querysets for validation
        form.fields["pos_categoria"].queryset = categorias
        cat_id = request.POST.get("pos_categoria")
        temp_id = request.POST.get("pos_temporada")
        if cat_id:
            temps = Temporada.objects.filter(categoria_id=cat_id, activa=True)
            form.fields["pos_temporada"].queryset = temps
            if temp_id:
                t = Temporada.objects.get(pk=temp_id)
                form.fields["equipo"].queryset = Equipo.objects.filter(
                    pk__in=[eq.pk for eq in t.equipos_habilitados()]
                )
        if form.is_valid():
            ingreso = form.save(commit=False)
            ingreso.registrado_por = request.user
            # If temporada was selected via cascade, store it
            if form.cleaned_data.get("pos_temporada"):
                ingreso.temporada = form.cleaned_data["pos_temporada"]
            ingreso.save()

            # Verificar si es pago de multa de edad y levantar suspensión
            concepto_multa_nombre = "Multa por incumplimiento de edad"
            if (ingreso.concepto.nombre == concepto_multa_nombre
                    and ingreso.jugador
                    and ingreso.jugador.suspendido_pago):
                from django.db.models import Sum
                total_adeudo = ConceptoIngreso.objects.filter(
                    nombre=concepto_multa_nombre
                ).values_list("monto_defecto", flat=True).first() or 500
                pagado = Ingreso.objects.filter(
                    concepto__nombre=concepto_multa_nombre,
                    jugador=ingreso.jugador,
                ).aggregate(Sum("monto"))["monto__sum"] or 0
                if pagado >= total_adeudo:
                    ingreso.jugador.suspendido_pago = False
                    ingreso.jugador.save(update_fields=["suspendido_pago"])
                    messages.success(
                        request,
                        f"Multa liquidada. Se ha levantado la suspensión de {ingreso.jugador}."
                    )

            return redirect(f"{reverse('ingreso_pos')}?ticket={ingreso.pk}")
    else:
        form = IngresoPOSForm()
        form.fields["pos_categoria"].queryset = categorias
        form.fields["pos_temporada"].queryset = Temporada.objects.none()

    # Preload cascade data as JSON
    import json
    temps = Temporada.objects.filter(activa=True).values("id", "nombre", "categoria_id")
    cascade_data = {
        "temporadas": list(temps),
        "equipos_por_temporada": {},
    }
    for t in Temporada.objects.filter(activa=True):
        eq_ids = [eq.id for eq in t.equipos_habilitados()]
        cascade_data["equipos_por_temporada"][str(t.id)] = eq_ids
    # Excluir pagados: por concepto y temporada, IDs de equipos que ya pagaron
    ids_pagados = {}
    for c in ConceptoIngreso.objects.filter(excluir_pagados=True):
        ids_pagados[str(c.id)] = {}
        ingresos = Ingreso.objects.filter(
            concepto=c, temporada_id__isnull=False, equipo_id__isnull=False
        ).values_list("temporada_id", "equipo_id")
        for temp_id, eq_id in ingresos:
            ids_pagados[str(c.id)].setdefault(str(temp_id), []).append(eq_id)
    cascade_data["ids_pagados"] = ids_pagados
    # All equipos for display
    todos_equipos = list(Equipo.objects.filter(activo=True).values("id", "nombre"))

    return render(request, "finance/ingreso_pos.html", {
        "form": form,
        "conceptos": conceptos,
        "categorias": categorias,
        "ultimos": ultimos,
        "config": config,
        "ticket_ingreso": ticket_ingreso,
        "tipo_filtro": tipo_filtro,
        "cascade_data_json": json.dumps(cascade_data),
        "todos_equipos_json": json.dumps(todos_equipos),
    })


def ingreso_ticket(request, pk):
    ingreso = get_object_or_404(Ingreso.objects.select_related("concepto", "equipo", "registrado_por"), pk=pk)
    config = ConfiguracionLiga.obtener()
    return render(request, "finance/ingreso_ticket.html", {
        "ingreso": ingreso,
        "config": config,
    })