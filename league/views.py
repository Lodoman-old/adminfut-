import datetime
from datetime import date
import json
import logging
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

logger = logging.getLogger(__name__)

from django.urls import reverse_lazy, reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, HttpResponse, Http404
from django.core.exceptions import PermissionDenied
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db.models import Sum, Q, Count, Min, Max, OuterRef, Subquery, F, Case, When, Value, IntegerField, DateTimeField
from django import forms
from .models import Categoria, Equipo, Jugador, JugadorEquipo, Campo, Temporada, Partido, Gol, Jornada, PeriodoAltas, Tarjeta, SuspensionJugador, Arbitro, ConfiguracionLiga, SuscripcionEmail, CampoIndisponibilidad, JugadorPartido, Grupo
from .forms import CategoriaForm, TemporadaForm, EquipoForm, JugadorForm, CampoForm, ArbitroForm, PeriodoAltasForm, PartidoForm
from finance.models import ConceptoIngreso, Ingreso


class CategoriaListView(ListView):
    model = Categoria
    template_name = "league/categoria_list.html"
    context_object_name = "categorias"


class CategoriaCreateView(CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "league/categoria_form.html"
    success_url = reverse_lazy("categoria_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categorias"] = Categoria.objects.exclude(pk=self.object.pk if self.object else None)
        ctx["compatibles_ids"] = []
        from .models import Campo
        ctx["campos_disponibles"] = Campo.objects.filter(activo=True).order_by("nombre")
        ctx["campos_permitidos_ids"] = []
        return ctx


class CategoriaUpdateView(UpdateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = "league/categoria_form.html"
    success_url = reverse_lazy("categoria_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categorias"] = Categoria.objects.exclude(pk=self.object.pk)
        ctx["compatibles_ids"] = list(self.object.categorias_compatibles.values_list("pk", flat=True))
        from .models import Campo
        ctx["campos_disponibles"] = Campo.objects.filter(activo=True).order_by("nombre")
        ctx["campos_permitidos_ids"] = list(self.object.campos_permitidos.values_list("pk", flat=True))
        return ctx


class CategoriaDeleteView(DeleteView):
    model = Categoria
    template_name = "league/categoria_confirm_delete.html"
    success_url = reverse_lazy("categoria_list")


class EquipoListView(ListView):
    model = Equipo
    template_name = "league/equipo_list.html"
    context_object_name = "equipos"

    def get_queryset(self):
        qs = Equipo.objects.all()
        cat = self.request.GET.get("categoria")
        if cat:
            qs = qs.filter(categoria_id=cat)
        q = self.request.GET.get("q", "").strip()
        if len(q) >= 3:
            qs = qs.filter(nombre__icontains=q)
        return qs.select_related("categoria")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categorias"] = Categoria.objects.filter(activo=True)
        return ctx


class EquipoCreateView(CreateView):
    model = Equipo
    form_class = EquipoForm
    template_name = "league/equipo_form.html"
    success_url = reverse_lazy("equipo_list")


class EquipoUpdateView(UpdateView):
    model = Equipo
    form_class = EquipoForm
    template_name = "league/equipo_form.html"
    success_url = reverse_lazy("equipo_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        equipo = self.object
        from .models import HorarioFijoEquipo, Temporada
        from finance.models import Ingreso, ConceptoIngreso
        temporadas = Temporada.objects.filter(categoria=equipo.categoria).order_by("-iniciada", "nombre")
        concepto_hf = ConceptoIngreso.objects.filter(nombre__icontains="horario fijo").first()
        data = []
        for t in temporadas:
            pagado = False
            if concepto_hf:
                pagado = Ingreso.objects.filter(
                    Q(equipo=equipo, concepto=concepto_hf) | Q(equipo=equipo, temporada=t, concepto=concepto_hf),
                    fecha__gte=t.fecha_inicio - __import__("datetime").timedelta(days=365),
                    fecha__lte=t.fecha_fin if t.fecha_fin else t.fecha_inicio + __import__("datetime").timedelta(days=365),
                ).exists()
            horario_fijo = HorarioFijoEquipo.objects.filter(temporada=t, equipo=equipo).first()
            data.append({
                "temporada": t,
                "pagado": pagado,
                "horario": horario_fijo.horario if horario_fijo else "",
                "hf_pk": horario_fijo.pk if horario_fijo else None,
            })
        ctx["temporadas_hf"] = data
        ctx["categoria_horarios"] = equipo.categoria.horarios or []
        # Contar disponibilidad por horario en cada temporada (solo equipos SIN campo_rancheria consumen campo normal)
        from .models import HorarioFijoEquipo, Campo
        ctx["disponibilidad_horarios"] = {}
        for t in temporadas:
            ocupados = {}
            for hf in HorarioFijoEquipo.objects.filter(temporada=t).select_related("equipo"):
                if not hf.equipo.campo_rancheria_id:
                    ocupados[hf.horario] = ocupados.get(hf.horario, 0) + 1
            limite = Campo.objects.filter(activo=True, es_rancheria=False).count()
            ctx["disponibilidad_horarios"][str(t.id)] = {
                "ocupados": ocupados,
                "limite": limite,
            }
        return ctx

    def _actualizar_partidos_horario_fijo(self, equipo, temporada_id, horario):
        from .models import Partido, HorarioFijoEquipo, Campo
        if not horario:
            return 0, []
        hh, mm = horario.split(":")
        from datetime import time as t_time, timezone as dt_timezone
        from django.utils import timezone
        hora_obj = t_time(int(hh), int(mm))
        partidos = Partido.objects.filter(
            Q(equipo_local=equipo) | Q(equipo_visitante=equipo),
            temporada_id=temporada_id,
            estado__in=["PEND", "SUSP"],
        )
        actualizados = 0
        conflictos = []
        for p in partidos:
            local_dt = p.fecha_hora.astimezone(timezone.get_current_timezone())
            nueva_hora = local_dt.replace(hour=hora_obj.hour, minute=hora_obj.minute, second=0, microsecond=0)
            nueva_hora_utc = nueva_hora.astimezone(dt_timezone.utc)
            if p.fecha_hora != nueva_hora_utc:
                # Checar si hay conflicto de campo en ese horario
                mismo_campo = Partido.objects.filter(
                    campo=p.campo, fecha_hora=nueva_hora_utc, estado__in=["PEND", "SUSP"]
                ).exclude(pk=p.pk).exists()
                nuevo_campo = p.campo
                if mismo_campo:
                    # Buscar campo alternativo
                    ocupados = Partido.objects.filter(
                        fecha_hora=nueva_hora_utc, estado__in=["PEND", "SUSP"]
                    ).values_list("campo_id", flat=True)
                    disponibles = Campo.objects.filter(activo=True).exclude(pk__in=ocupados)
                    # Preferir campo_rancheria del equipo local si aplica
                    if p.equipo_local == equipo and equipo.campo_rancheria:
                        if equipo.campo_rancheria_id not in ocupados:
                            nuevo_campo = equipo.campo_rancheria
                        else:
                            nuevo_campo = disponibles.exclude(pk=equipo.campo_rancheria_id).first()
                    else:
                        nuevo_campo = disponibles.first()
                    if not nuevo_campo:
                        conflictos.append(p)
                        continue
                Partido.objects.filter(pk=p.pk).update(fecha_hora=nueva_hora_utc, campo=nuevo_campo)
                actualizados += 1
        return actualizados, conflictos

    def form_valid(self, form):
        r = super().form_valid(form)
        equipo = self.object
        from .models import HorarioFijoEquipo, Campo, Temporada
        for key, val in self.request.POST.items():
            if key.startswith("hf_"):
                partes = key.split("_")
                temp_id = int(partes[1])
                horario = val.strip()
                if horario:
                    # Validar capacidad del horario
                    if not equipo.campo_rancheria_id:
                        limite = Campo.objects.filter(activo=True, es_rancheria=False).count()
                        ocupados = HorarioFijoEquipo.objects.filter(
                            temporada_id=temp_id, horario=horario
                        ).exclude(equipo=equipo).exclude(equipo__campo_rancheria__isnull=False).count()
                        if ocupados >= limite:
                            from django.contrib import messages
                            messages.error(
                                self.request,
                                f"El horario {horario} ya está al límite ({ocupados}/{limite} campos disponibles). "
                                f"Elige otro horario para {equipo.nombre}."
                            )
                            continue
                    HorarioFijoEquipo.objects.update_or_create(
                        temporada_id=temp_id, equipo=equipo,
                        defaults={"horario": horario}
                    )
                    actualizados, conflictos = self._actualizar_partidos_horario_fijo(equipo, temp_id, horario)
                    if actualizados:
                        from django.contrib import messages
                        messages.info(self.request, f"Se actualizaron {actualizados} partido(s) al horario {horario}.")
                    if conflictos:
                        from django.contrib import messages
                        lista = ", ".join(
                            f"#{c.jornada.numero}" if c.jornada else str(c.pk)
                            for c in conflictos
                        )
                        messages.warning(
                            self.request,
                            f"No se pudo cambiar {len(conflictos)} partido(s) ({lista}) por falta de campo disponible en el horario {horario}."
                        )
                else:
                    HorarioFijoEquipo.objects.filter(
                        temporada_id=temp_id, equipo=equipo
                    ).delete()
        return r


class EquipoDeleteView(DeleteView):
    model = Equipo
    template_name = "league/equipo_confirm_delete.html"
    success_url = reverse_lazy("equipo_list")


@login_required
def horarios_fijos_report(request):
    from .models import HorarioFijoEquipo, Temporada, Categoria
    from finance.models import Ingreso, ConceptoIngreso
    cat_id = request.GET.get("categoria")
    temp_id = request.GET.get("temporada")
    qs = HorarioFijoEquipo.objects.select_related("temporada", "temporada__categoria", "equipo")
    if cat_id:
        qs = qs.filter(temporada__categoria_id=cat_id)
    if temp_id:
        qs = qs.filter(temporada_id=temp_id)
    qs = qs.order_by("temporada__categoria__nombre", "temporada__nombre", "equipo__nombre")
    concepto_hf = ConceptoIngreso.objects.filter(nombre__icontains="horario fijo").first()
    rows = []
    for hf in qs:
        pagado = False
        if concepto_hf:
            t = hf.temporada
            pagado = Ingreso.objects.filter(
                equipo=hf.equipo, concepto=concepto_hf,
                fecha__gte=t.fecha_inicio - datetime.timedelta(days=365),
                fecha__lte=t.fecha_fin if t.fecha_fin else t.fecha_inicio + datetime.timedelta(days=365),
            ).exists()
        rows.append({
            "categoria": hf.temporada.categoria,
            "temporada": hf.temporada,
            "equipo": hf.equipo,
            "horario": hf.horario,
            "pagado": pagado,
        })
    categorias = Categoria.objects.filter(activo=True)
    temporadas = Temporada.objects.all().select_related("categoria").order_by("nombre")
    return render(request, "league/horarios_fijos_report.html", {
        "rows": rows,
        "categorias": categorias,
        "temporadas": temporadas,
        "cat_id": cat_id,
        "temp_id": temp_id,
    })


class JugadorListView(ListView):
    model = Jugador
    template_name = "league/jugador_list.html"
    context_object_name = "jugadores"

    def get_queryset(self):
        qs = Jugador.objects.all()
        cat_id = self.request.GET.get("categoria")
        eq = self.request.GET.get("equipo")
        if cat_id:
            qs = qs.filter(
                Q(equipo__categoria_id=cat_id) | Q(registros_equipo__equipo__categoria_id=cat_id)
            ).distinct()
        if eq:
            qs = qs.filter(
                Q(equipo_id=eq) | Q(registros_equipo__equipo_id=eq)
            ).distinct()
        return qs.select_related("equipo", "equipo__categoria").prefetch_related("registros_equipo__equipo")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        cat_id = self.request.GET.get("categoria")
        q_equipos = Equipo.objects.filter(activo=True)
        if cat_id:
            q_equipos = q_equipos.filter(categoria_id=cat_id)
        ctx["equipos"] = q_equipos
        ctx["categorias"] = Categoria.objects.filter(activo=True)
        # Categorías con edición de jugadores permitida:
        # - sin temporada activa iniciada (sin torneo abierto) -> permitido
        # - o con temporada activa iniciada y período de altas activo -> permitido
        activas_iniciadas = list(Temporada.objects.filter(activa=True, iniciada=True))
        categorias_editables = set(Categoria.objects.filter(activo=True).values_list("id", flat=True))
        for cat_id in list(categorias_editables):
            temps_cat = [t for t in activas_iniciadas if t.categoria_id == cat_id]
            if temps_cat and not any(t.periodo_altas_activo() for t in temps_cat):
                categorias_editables.discard(cat_id)
        ctx["categorias_editables"] = categorias_editables
        # Categorías con temporada iniciada (NO se puede eliminar)
        cats_iniciadas = set()
        for t in Temporada.objects.filter(iniciada=True, finalizada=False):
            cats_iniciadas.add(t.categoria_id)
        ctx["categorias_temporada_iniciada"] = cats_iniciadas
        # Recuperar datos del modal de edad y limpiar sesión
        ctx["mostrar_modal_edad"] = self.request.session.pop("mostrar_modal_edad", None)
        return ctx


def validar_jugador(request, equipo, form):
    """Valida límite de jugadores por equipo y que no pertenezca a otro equipo en la misma categoría temporada."""
    instance = form.instance

    # Admin/superuser siempre puede editar
    if request.user.is_superuser:
        return True

    # Verificar si el jugador está suspendido por multa
    if instance and instance.pk and instance.suspendido_pago:
        messages.error(
            request,
            f"El jugador '{instance.nombre} {instance.apellido}' está suspendido por adeudo de multa. "
            f"Debe liquidar la multa en el módulo de Ingresos (POS) para poder ser registrado."
        )
        return False

    # Si es el mismo jugador en el mismo equipo (edición), permitir siempre
    es_mismo_equipo = instance.pk and instance.equipo_id == equipo.id
    if not es_mismo_equipo:
        temp_activa = Temporada.objects.filter(
            categoria=equipo.categoria, activa=True, iniciada=True
        ).first()
        if temp_activa and not temp_activa.periodo_altas_activo():
            messages.error(
                request,
                f"No hay un período de altas activo para la temporada "
                f"'{temp_activa.nombre}'. No se pueden registrar/modificar jugadores."
            )
            return False

    # Verificar límite máximo de jugadores activos
    max_jug = equipo.categoria.max_jugadores
    activos_actuales = Jugador.objects.filter(equipo=equipo, activo=True).count()
    if es_mismo_equipo and instance.activo:
        activos_actuales -= 1
    if form.cleaned_data.get("activo", True) and activos_actuales >= max_jug:
        messages.error(
            request,
            f"El equipo '{equipo.nombre}' ya tiene {activos_actuales} jugadores activos "
            f"(máximo {max_jug}). No se puede registrar más jugadores."
        )
        return False

    # Verificar que el jugador no esté registrado en otro equipo con temporada activa sin finalizar
    curp = form.cleaned_data.get("curp", "").strip().upper()
    nombre = form.cleaned_data.get("nombre", "").strip()
    apellido = form.cleaned_data.get("apellido", "").strip()
    if not es_mismo_equipo:
        otros = Jugador.objects.none()
        if curp:
            otros = Jugador.objects.filter(curp__iexact=curp, activo=True
            ).exclude(pk=instance.pk).exclude(equipo=equipo)
        elif nombre and apellido:
            otros = Jugador.objects.filter(
                nombre__iexact=nombre, apellido__iexact=apellido, activo=True
            ).exclude(pk=instance.pk).exclude(equipo=equipo)
        for otro in otros:
            # Buscar temporada activa no finalizada del otro jugador
            temp_origen = Temporada.objects.filter(
                categoria=otro.equipo.categoria, activa=True, iniciada=True, finalizada=False
            ).first()
            if temp_origen:
                messages.error(
                    request,
                    f"El jugador '{nombre} {apellido}' ya está registrado en "
                    f"'{otro.equipo.nombre}' y su temporada '{temp_origen.nombre}' "
                    f"aún no ha finalizado. No puede cambiarse de equipo hasta que la temporada termine."
                )
                return False
            # Si la temporada del otro jugador ya finalizó, verificar compatibilidad
            cat_origen = otro.equipo.categoria
            cat_destino = equipo.categoria
            if cat_origen == cat_destino:
                messages.error(
                    request,
                    f"El jugador '{nombre} {apellido}' ya está registrado en el equipo "
                    f"'{otro.equipo.nombre}' de la misma categoría. "
                    f"No puede pertenecer a dos equipos de la misma categoría."
                )
                return False
            if cat_origen not in cat_destino.categorias_compatibles.all():
                messages.error(
                    request,
                    f"El jugador '{nombre} {apellido}' ya está registrado en "
                    f"'{otro.equipo.nombre}' ({cat_origen.nombre}). "
                    f"La categoría '{cat_destino.nombre}' no tiene compatibilidad configurada con "
                    f"'{cat_origen.nombre}'. Marca la compatibilidad en la configuración de la categoría."
                )
                return False

    return True


class JugadorGeneroContextMixin:
    """Expone al template el género (para sexo H/M en autocalculo CURP) de cada equipo activo."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["equipos_genero_json"] = json.dumps({
            e.id: (e.categoria.genero or "")
            for e in Equipo.objects.filter(activo=True).select_related("categoria")
        })
        return ctx


class JugadorCreateView(JugadorGeneroContextMixin, CreateView):
    model = Jugador
    form_class = JugadorForm
    template_name = "league/jugador_form.html"
    success_url = reverse_lazy("jugador_list")

    def form_valid(self, form):
        equipo = form.cleaned_data.get("equipo")
        if equipo and not validar_jugador(self.request, equipo, form):
            return self.form_invalid(form)
        return super().form_valid(form)


class JugadorUpdateView(JugadorGeneroContextMixin, UpdateView):
    model = Jugador
    form_class = JugadorForm
    template_name = "league/jugador_form.html"
    success_url = reverse_lazy("jugador_list")

    def form_valid(self, form):
        equipo = form.cleaned_data.get("equipo")
        if equipo and not validar_jugador(self.request, equipo, form):
            return self.form_invalid(form)
        response = super().form_valid(form)

        # Procesar violaciones de edad por cambio de fecha_nacimiento
        violations = getattr(form, "_age_violations", [])
        if violations:
            jugador = self.object
            concepto_multa = ConceptoIngreso.objects.filter(
                nombre="Multa por incumplimiento de edad"
            ).first()
            multas_creadas = 0
            partidos_afectados = 0

            for v in violations:
                cat = v["categoria"]
                eq = v["equipo"]
                temp_activa = Temporada.objects.filter(
                    categoria=cat, iniciada=True, finalizada=False
                ).first()
                if temp_activa and concepto_multa:
                    # Crear multa
                    Ingreso.objects.create(
                        concepto=concepto_multa,
                        monto=concepto_multa.monto_defecto,
                        fecha=date.today(),
                        equipo=eq,
                        temporada=temp_activa,
                        jugador=jugador,
                        descripcion=(
                            f"Multa por cambio de fecha de nacimiento de {jugador}. "
                            f"Edad del jugador: {jugador.edad()} años. "
                            f"Categoría: {cat.nombre} ({v['motivo']})"
                        ),
                        registrado_por=self.request.user,
                    )
                    multas_creadas += 1

                    # Convertir partidos a default
                    participaciones = JugadorPartido.objects.filter(
                        jugador=jugador, equipo=eq,
                        partido__temporada=temp_activa,
                        partido__estado__in=("PEND", "JUG"),
                    ).select_related("partido")
                    for jp in participaciones:
                        partido = jp.partido
                        if partido.equipo_local == eq:
                            partido.default_visitante = False
                            partido.goles_local = 0
                            partido.goles_visitante = 1
                        else:
                            partido.default_visitante = True
                            partido.goles_local = 1
                            partido.goles_visitante = 0
                        partido.estado = "FIN"
                        partido.motivo_default = (
                            f"Walkover - {jugador} incumple rango de edad en {cat.nombre} "
                            f"tras cambio de fecha de nacimiento."
                        )
                        partido.save()
                        partidos_afectados += 1

            if multas_creadas:
                jugador.suspendido_pago = True
                jugador.save(update_fields=["suspendido_pago"])

            detalle = f"Se crearon {multas_creadas} multas y se marcaron {partidos_afectados} partidos como default."
            messages.warning(self.request, detalle)

            # Pasar datos del modal al template via session (se limpia al mostrar)
            self.request.session["mostrar_modal_edad"] = {
                "multas": multas_creadas,
                "partidos": partidos_afectados,
                "suspendido": True,
                "violaciones": [
                    {
                        "categoria": v["categoria"].nombre,
                        "equipo": v["equipo"].nombre,
                        "motivo": v["motivo"],
                        "edad_jugador": v["edad_jugador"],
                    }
                    for v in violations
                ],
            }

        return response


class JugadorDeleteView(DeleteView):
    model = Jugador
    template_name = "league/jugador_confirm_delete.html"
    success_url = reverse_lazy("jugador_list")

    def delete(self, request, *args, **kwargs):
        jugador = self.get_object()
        cats_ids = {jugador.equipo.categoria_id}
        cats_ids.update(
            jugador.registros_equipo.filter(activo=True)
            .values_list("equipo__categoria_id", flat=True)
        )
        if Temporada.objects.filter(
            categoria_id__in=cats_ids, iniciada=True, finalizada=False
        ).exists():
            messages.error(
                request,
                "No se puede eliminar al jugador porque tiene una temporada en curso "
                "en alguna de sus categorías. Espera a que finalice."
            )
            return redirect("jugador_list")
        return super().delete(request, *args, **kwargs)


class CampoListView(ListView):
    model = Campo
    template_name = "league/campo_list.html"
    context_object_name = "campos"


class CampoCreateView(CreateView):
    model = Campo
    form_class = CampoForm
    template_name = "league/campo_form.html"
    success_url = reverse_lazy("campo_list")

    def form_valid(self, form):
        form.instance.precio_hora = 0
        return super().form_valid(form)


class CampoUpdateView(UpdateView):
    model = Campo
    form_class = CampoForm
    template_name = "league/campo_form.html"
    success_url = reverse_lazy("campo_list")


class CampoDeleteView(DeleteView):
    model = Campo
    template_name = "league/campo_confirm_delete.html"
    success_url = reverse_lazy("campo_list")


class TemporadaListView(ListView):
    model = Temporada
    template_name = "league/temporada_list.html"
    context_object_name = "temporadas"

    def get_queryset(self):
        return Temporada.objects.all().select_related("categoria")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["categorias"] = Categoria.objects.filter(activo=True)
        return ctx


class TemporadaCreateView(CreateView):
    model = Temporada
    form_class = TemporadaForm
    template_name = "league/temporada_form.html"
    success_url = reverse_lazy("temporada_list")


class TemporadaUpdateView(UpdateView):
    model = Temporada
    form_class = TemporadaForm
    template_name = "league/temporada_form.html"
    success_url = reverse_lazy("temporada_list")


def finalizar_temporada(request, pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    if request.method == "POST":
        hoy = datetime.date.today()
        motivo = request.POST.get("motivo", "").strip()
        if temporada.fecha_fin and hoy < temporada.fecha_fin:
            if not motivo:
                messages.error(request, "Debes indicar el motivo de la finalización anticipada.")
                return redirect("temporada_list")
        temporada.activa = False
        temporada.iniciada = False
        temporada.finalizada = True
        temporada.fecha_finalizacion = hoy
        temporada.motivo_finalizacion = motivo
        temporada.save()
        messages.success(request, f"Temporada '{temporada.nombre}' finalizada correctamente.")
        return redirect("temporada_list")
    # GET: mostrar página de confirmación (modal contents rendered directly)
    es_anticipado = temporada.fecha_fin and datetime.date.today() < temporada.fecha_fin
    return render(request, "league/temporada_finalizar.html", {
        "temporada": temporada,
        "es_anticipado": es_anticipado,
    })


@admin.site.admin_view
def admin_push_logs(request):
    from .push import get_push_logs
    from .models import DeviceToken
    logs = get_push_logs(limit=200)
    tokens = DeviceToken.objects.filter(activo=True).select_related("usuario").prefetch_related("categorias").order_by("-creado")[:100]
    return render(request, "admin/push_logs.html", {"logs": logs, "tokens": tokens})


@login_required
def suspender_jornada(request, jornada_id):
    if not request.user.tiene_permiso("jornada_suspender"):
        messages.error(request, "No tienes permiso para suspender jornadas.")
        return redirect("jornada_list")
    jornada = get_object_or_404(Jornada, id=jornada_id)
    if jornada.estado == "SUSPENDIDA":
        messages.error(request, "La jornada ya está suspendida.")
        return redirect("jornada_list")

    motivo = request.POST.get("motivo", "").strip()
    semanas_str = request.POST.get("semanas", "").strip()
    if not motivo:
        messages.error(request, "Debes escribir un motivo de suspensión.")
        return redirect("jornada_list")
    try:
        semanas = int(semanas_str)
        if semanas < 1:
            raise ValueError
    except (ValueError, TypeError):
        messages.error(request, "Debes indicar un número válido de semanas (1-4).")
        return redirect("jornada_list")

    delta = datetime.timedelta(weeks=semanas)

    # Mark jornada as suspended
    jornada.estado = "SUSPENDIDA"
    jornada.motivo_suspension = motivo
    jornada.semanas_suspension = semanas
    jornada.save(update_fields=["estado", "motivo_suspension", "semanas_suspension"])

    # Shift ALL future (non-finalized) matches in jornadas >= this numero by `delta`
    qs = Partido.objects.filter(
        temporada=jornada.temporada,
        jornada__numero__gte=jornada.numero,
    ).exclude(estado="FIN")
    for p in qs.iterator():
        p.fecha_hora += delta
        p.estado = "PEND"
        p.save(update_fields=["fecha_hora", "estado"])

    # Update season end date
    jornada.temporada.actualizar_fecha_fin()

    # Avisar a invitados (push + correo) de la suspensión
    try:
        _notificar_suspension_jornada(request, jornada, motivo, semanas)
    except Exception as e:
        logger.warning("Error notificando suspensión de jornada: %s", e)

    messages.success(
        request,
        f"Jornada {jornada.numero} suspendida ({semanas} semana{'s' if semanas > 1 else ''}). "
        f"Calendario recorrido a partir de la jornada {jornada.numero}."
    )
    return redirect("jornada_list")


@login_required
def reactivar_jornada(request, jornada_id):
    if not request.user.tiene_permiso("jornada_suspender"):
        messages.error(request, "No tienes permiso para reactivar jornadas.")
        return redirect("jornada_list")
    jornada = get_object_or_404(Jornada, id=jornada_id)
    if jornada.estado != "SUSPENDIDA":
        messages.error(request, "La jornada no está suspendida.")
        return redirect("jornada_list")

    # Reactivate: set SUSP matches back to PEND (only this jornada)
    jornada.partidos.filter(estado="SUSP").update(estado="PEND")
    jornada.estado = "ACTIVA"
    jornada.motivo_suspension = ""
    jornada.semanas_suspension = None
    jornada.save(update_fields=["estado", "motivo_suspension", "semanas_suspension"])

    messages.success(request, f"Jornada {jornada.numero} reactivada.")
    return redirect("jornada_list")


def reabrir_temporada(request, pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    if not request.user.is_superuser:
        messages.error(request, "Solo el administrador puede reabrir una temporada.")
        return redirect("temporada_list")
    if request.method == "POST":
        temporada.finalizada = False
        temporada.fecha_finalizacion = None
        temporada.save(update_fields=["finalizada", "fecha_finalizacion"])
        messages.success(request, f"Temporada '{temporada.nombre}' reabierta correctamente.")
        return redirect("temporada_list")
    return render(request, "league/temporada_finalizar.html", {
        "temporada": temporada,
        "es_anticipado": False,
        "reabrir": True,
    })


from django import forms as djforms


class ConfiguracionLigaForm(djforms.ModelForm):
    class Meta:
        model = ConfiguracionLiga
        fields = "__all__"
        exclude = ("webpush_vapid_private_key", "webpush_vapid_public_key")
        widgets = {
            "nombre_liga": djforms.TextInput(attrs={"class": "form-control"}),
            "segunda_linea": djforms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Juventino Rosas"}),
            "logo": djforms.FileInput(attrs={"class": "form-control"}),
            "direccion": djforms.TextInput(attrs={"class": "form-control"}),
            "telefonos": djforms.TextInput(attrs={"class": "form-control"}),
            "email_provider": djforms.Select(attrs={"class": "form-select"}),
            "email_smtp_host": djforms.TextInput(attrs={"class": "form-control"}),
            "email_smtp_port": djforms.NumberInput(attrs={"class": "form-control"}),
            "email_smtp_user": djforms.TextInput(attrs={"class": "form-control"}),
            "email_smtp_password": djforms.PasswordInput(attrs={"class": "form-control"}, render_value=True),
            "email_from": djforms.EmailInput(attrs={"class": "form-control"}),
            "email_use_tls": djforms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "email_sendgrid_host": djforms.TextInput(attrs={"class": "form-control"}),
            "email_sendgrid_port": djforms.NumberInput(attrs={"class": "form-control"}),
            "email_sendgrid_user": djforms.TextInput(attrs={"class": "form-control"}),
            "email_sendgrid_password": djforms.PasswordInput(attrs={"class": "form-control"}, render_value=True),
            "email_sendgrid_use_tls": djforms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "enviar_solo_jornada_actual": djforms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
            "ticket_ancho_mm": djforms.NumberInput(attrs={"class": "form-control", "min": 40, "max": 100, "step": 1}),
            "ticket_encabezado": djforms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "ticket_pie": djforms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "correo_electronico": djforms.EmailInput(attrs={"class": "form-control"}),
            "redes_sociales": djforms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "facebook_page_id": djforms.TextInput(attrs={"class": "form-control"}),
            "facebook_access_token": djforms.PasswordInput(attrs={"class": "form-control"}, render_value=True),
            "reglamento": djforms.FileInput(attrs={"class": "form-control"}),
            "database_url": djforms.TextInput(attrs={"class": "form-control", "placeholder": "postgresql://user:pass@host/db?sslmode=require"}),
            "cloudinary_cloud_name": djforms.TextInput(attrs={"class": "form-control"}),
            "cloudinary_api_key": djforms.TextInput(attrs={"class": "form-control"}),
            "cloudinary_api_secret": djforms.PasswordInput(attrs={"class": "form-control"}, render_value=True),
            "firebase_service_account_json": djforms.Textarea(attrs={"class": "form-control", "rows": 8, "placeholder": '{"type": "service_account", "project_id": "...", ...}'}),
        }


def configuracion_liga(request):
    config = ConfiguracionLiga.obtener()
    if request.method == "POST":
        form = ConfiguracionLigaForm(request.POST, request.FILES, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Configuración guardada correctamente.")
            return redirect("configuracion_liga")
    else:
        form = ConfiguracionLigaForm(instance=config)
    return render(request, "league/configuracion_form.html", {"form": form, "config": config})


@login_required
def generar_vapid_keys(request):
    """Genera (o regenera) las claves VAPID para Web Push y muestra la clave pública."""
    if not request.user.tiene_permiso("gestion_configuracion"):
        raise PermissionDenied
    config = ConfiguracionLiga.obtener()
    from .push import _generar_claves_vapid
    private_b64, public_b64 = _generar_claves_vapid()
    config.webpush_vapid_private_key = private_b64
    config.webpush_vapid_public_key = public_b64
    config.save(update_fields=["webpush_vapid_private_key", "webpush_vapid_public_key"])
    messages.success(request, "Claves VAPID generadas correctamente. Los dispositivos PWA deberán volver a suscribirse.")
    return redirect("configuracion_liga")


def descarga_reglamento(request):
    config = ConfiguracionLiga.obtener()
    if not config.reglamento:
        raise Http404("No hay reglamento disponible.")
    try:
        f = config.reglamento.open("rb")
        from django.http import FileResponse
        return FileResponse(f, content_type="application/pdf",
                            as_attachment=True, filename="Reglamento.pdf")
    except Exception:
        import cloudinary
        url = cloudinary.utils.cloudinary_url(config.reglamento.name, resource_type="raw", secure=True, sign_url=True)[0]
        from django.http import HttpResponseRedirect
        return HttpResponseRedirect(url)


def descarga_apk(request):
    from pathlib import Path
    from django.conf import settings as dj_settings
    from django.http import FileResponse
    path = Path(dj_settings.BASE_DIR) / "static" / "apk" / "AdminFut.apk"
    if not path.exists():
        raise Http404("La aplicación no está disponible.")
    return FileResponse(open(path, "rb"), content_type="application/vnd.android.package-archive",
                        as_attachment=True, filename="AdminFut.apk")


def service_worker(request):
    """Servicio worker de la PWA (Web Push). Se sirve en /sw.js para alcance raíz."""
    from pathlib import Path
    from django.conf import settings as dj_settings
    path = Path(dj_settings.BASE_DIR) / "static" / "sw.js"
    if not path.exists():
        raise Http404("Service worker no disponible")
    content = path.read_text(encoding="utf-8")
    return HttpResponse(content, content_type="application/javascript; charset=utf-8")


def manifest_webmanifest(request):
    """Manifest de la PWA."""
    config = ConfiguracionLiga.obtener()
    nombre_corto = (config.segunda_linea or config.nombre_liga)[:12]
    manifest = {
        "name": config.nombre_liga,
        "short_name": nombre_corto,
        "description": f"Resultados, tablas y notificaciones de {config.nombre_liga}",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#1a3a15",
        "theme_color": "#1a3a15",
        "icons": [
            {"src": "/pwa-icon/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/pwa-icon/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        ],
    }
    return JsonResponse(manifest, content_type="application/manifest+json")


ICONOS_PWA = {
    "icon-192.png": "static/icons/icon-192.png",
    "icon-512.png": "static/icons/icon-512.png",
    "apple-touch-icon.png": "static/icons/apple-touch-icon.png",
    "badge-96.png": "static/icons/badge-96.png",
}


def pwa_icon(request, nombre):
    """Iconos de la PWA servidos con URL estable (sin hash de collectstatic)."""
    from pathlib import Path
    from django.conf import settings as dj_settings
    rel = ICONOS_PWA.get(nombre)
    if not rel:
        raise Http404("Icono no disponible")
    path = Path(dj_settings.BASE_DIR) / rel
    if not path.exists():
        raise Http404("Icono no disponible")
    return HttpResponse(path.read_bytes(), content_type="image/png")


@login_required
def test_database_connection(request):
    if not request.user.is_superuser:
        from django.http import JsonResponse
        return JsonResponse({"ok": False, "error": "Solo superusuarios"}, status=403)
    from django.http import JsonResponse
    config = ConfiguracionLiga.obtener()
    db_url = request.POST.get("database_url", "") or config.database_url
    if not db_url:
        return JsonResponse({"ok": False, "error": "No hay DATABASE_URL configurada."})
    try:
        import dj_database_url
        import psycopg2
        parsed = dj_database_url.parse(db_url)
        conn = psycopg2.connect(parsed["NAME"], user=parsed["USER"], password=parsed["PASSWORD"],
                                host=parsed["HOST"], port=parsed["PORT"],
                                sslmode=parsed.get("OPTIONS", {}).get("sslmode", "require"))
        cur = conn.cursor()
        cur.execute("SELECT version()")
        version = cur.fetchone()[0]
        cur.close()
        conn.close()
        return JsonResponse({"ok": True, "version": version})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})


@login_required
def test_email_connection(request):
    """Envía un correo de prueba con la configuración SMTP que está en pantalla (y guardada en la BD)."""
    if not request.user.is_superuser:
        return JsonResponse({"ok": False, "error": "Solo superusuarios"}, status=403)
    provider = request.POST.get("email_provider", "google")
    target = (request.POST.get("correo_prueba") or "").strip()
    if not target:
        return JsonResponse({"ok": False, "error": "Escribe un correo para recibir la prueba."})
    if provider == "sendgrid":
        smtp = {
            "host": request.POST.get("email_sendgrid_host", "smtp.sendgrid.net") or "smtp.sendgrid.net",
            "port": int(request.POST.get("email_sendgrid_port") or 587),
            "user": request.POST.get("email_sendgrid_user", "apikey") or "apikey",
            "password": request.POST.get("email_sendgrid_password", ""),
            "use_tls": request.POST.get("email_sendgrid_use_tls") == "on",
            "from_email": request.POST.get("email_from", ""),
        }
    else:
        smtp = {
            "host": request.POST.get("email_smtp_host", ""),
            "port": int(request.POST.get("email_smtp_port") or 587),
            "user": request.POST.get("email_smtp_user", ""),
            "password": request.POST.get("email_smtp_password", ""),
            "use_tls": request.POST.get("email_use_tls") == "on",
            "from_email": request.POST.get("email_from", ""),
        }
    if not smtp["host"] or not smtp["password"]:
        return JsonResponse({"ok": False, "error": "Faltan datos SMTP del proveedor activo (servidor y contraseña)."})
    subject = "Prueba de correo - AdminFut"
    html = f"""\
<div style="font-family:Arial,sans-serif;max-width:600px;margin:auto;border:1px solid #2d6b2e;border-radius:8px;overflow:hidden">
  <div style="background:#2d6b2e;color:#fff;padding:14px 20px">
    <h2 style="margin:0">LIGA DE FUTBOL JUVENINO ROSAS</h2>
  </div>
  <div style="padding:20px;color:#333">
    <p>Hola, este es un <b>correo de prueba</b> enviado desde la configuración de AdminFut.</p>
    <p>Proveedor: <b>{provider}</b> · Servidor: <b>{smtp['host']}:{smtp['port']}</b></p>
    <p>Si ves este mensaje, la configuración de correo funciona correctamente.</p>
  </div>
</div>"""
    text = "Correo de prueba de AdminFut. La configuracion de correo funciona correctamente."
    try:
        if provider == "sendgrid":
            _enviar_sendgrid_api(smtp, subject, html, text, [target])
        else:
            _enviar_smtp(smtp, subject, html, text, [target])
        return JsonResponse({"ok": True, "message": f"Correo enviado a {target}"})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)})


@login_required
def test_facebook_post(request):
    """Publica un post de prueba REAL en Facebook con la config que está en pantalla."""
    if not request.user.is_superuser:
        return JsonResponse({"ok": False, "error": "Solo superusuarios"}, status=403)
    page_id = (request.POST.get("facebook_page_id") or "").strip()
    sys_token = (request.POST.get("facebook_access_token") or "").strip()
    if not page_id or not sys_token:
        return JsonResponse({"ok": False, "error": "Ingresa el ID de página y el Access Token."})
    from .social import publicar_post_prueba
    ok, msg = publicar_post_prueba(page_id, sys_token, request)
    if ok:
        return JsonResponse({"ok": True, "message": msg})
    return JsonResponse({"ok": False, "error": msg})


def suscripcion_email(request):
    user = request.user if request.user.is_authenticated else None

    class SuscripcionForm(djforms.Form):
        email = djforms.EmailField(
            label="Tu correo electrónico",
            widget=djforms.EmailInput(attrs={"class": "form-control"})
        )
        categorias = djforms.ModelMultipleChoiceField(
            queryset=Categoria.objects.filter(activo=True),
            widget=djforms.CheckboxSelectMultiple,
            required=False,
            label="Categorías de interés"
        )
        recibir_roles = djforms.BooleanField(
            required=False, label="Recibir rol de juegos semanal",
            widget=djforms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"})
        )
        recibir_estadisticas = djforms.BooleanField(
            required=False, label="Recibir estadísticas",
            widget=djforms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"})
        )
        activo = djforms.BooleanField(
            required=False, label="Suscripción activa", initial=True,
            widget=djforms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"})
        )

    if request.method == "POST":
        form = SuscripcionForm(request.POST)
        if form.is_valid():
            if user and user.is_authenticated:
                susc, _ = SuscripcionEmail.objects.get_or_create(usuario=user)
            else:
                susc, _ = SuscripcionEmail.objects.get_or_create(email=form.cleaned_data["email"])
            susc.email = form.cleaned_data["email"]
            susc.recibir_roles = form.cleaned_data["recibir_roles"]
            susc.recibir_estadisticas = form.cleaned_data["recibir_estadisticas"]
            susc.activo = form.cleaned_data["activo"]
            susc.save()
            susc.categorias.set(form.cleaned_data["categorias"])
            messages.success(request, "Suscripción guardada. Gracias por mantenerte informado.")
            return redirect("suscripcion_email")
    else:
        form = SuscripcionForm()
    return render(request, "league/suscripcion_form.html", {"form": form, "categorias": Categoria.objects.filter(activo=True)})


def _obtener_jornada_actual(temporada):
    """Retorna la jornada actual o próxima pendiente de una temporada."""
    from django.utils import timezone
    ahora = timezone.localtime()
    return Jornada.objects.filter(
        temporada=temporada,
        partido__estado="PEND",
    ).annotate(
        min_fecha=Min("partido__fecha_hora"),
    ).order_by("numero").first()


def _enviar_correo_suscriptores(suscriptores, config, subject, template, ctx_extra, request=None):
    """Envía un correo a una lista de suscriptores. Retorna el conteo."""
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags

    smtp = config.get_active_smtp_config()
    if not smtp["host"]:
        return 0

    site_url = "https://adminfut.onrender.com"
    if request:
        site_url = f"{request.scheme}://{request.get_host()}"

    use_sendgrid_api = config.email_provider == "sendgrid"
    count = 0

    for sus in suscriptores:
        ctx = {**ctx_extra, "suscriptor_email": sus.email, "unsubscribe_token": getattr(sus, "token", ""), "config": config, "site_url": site_url}
        html = render_to_string(template, ctx)
        text = strip_tags(html)

        try:
            if use_sendgrid_api:
                _enviar_sendgrid_api(smtp, subject, html, text, [sus.email])
            else:
                _enviar_smtp(smtp, subject, html, text, [sus.email])
            count += 1
        except Exception as e:
            if request:
                messages.warning(request, f"Error al enviar a {sus.email}: {e}")
    return count


def _destinatarios_roles_email(temporada):
    """Suscriptores + invitados con correo que siguen la categoría de la temporada."""
    from .models import DeviceToken
    destinatarios = []
    for sus in SuscripcionEmail.objects.filter(activo=True, recibir_roles=True).prefetch_related("categorias"):
        cats = list(sus.categorias.all())
        if cats and temporada.categoria_id not in {c.id for c in cats}:
            continue
        destinatarios.append(sus)
    for g in DeviceToken.objects.filter(
        activo=True, es_invitado=True
    ).exclude(email="").prefetch_related("categorias"):
        cats = list(g.categorias.all())
        if cats and temporada.categoria_id not in {c.id for c in cats}:
            continue
        destinatarios.append(g)
    return destinatarios


def _enviar_suspension_email(titulo, ctx, categoria=None, request=None):
    """Envía correo de suspensión a invitados con correo que siguen la categoría."""
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags
    from .models import DeviceToken
    config = ConfiguracionLiga.obtener()
    smtp = config.get_active_smtp_config()
    if not smtp["host"]:
        return 0
    qs = DeviceToken.objects.filter(activo=True, es_invitado=True).exclude(email="")
    if categoria:
        qs = qs.filter(Q(categorias=categoria) | Q(categorias__isnull=True))
    site_url = f"{request.scheme}://{request.get_host()}" if request else "https://adminfut.onrender.com"
    count = 0
    vistos = set()
    for g in qs.distinct():
        email = g.email.strip().lower()
        if not email or email in vistos:
            continue
        vistos.add(email)
        c = {**ctx, "suscriptor_email": email, "unsubscribe_token": "", "config": config, "site_url": site_url}
        html = render_to_string("emails/suspension.html", c)
        text = strip_tags(html)
        try:
            _enviar_smtp(smtp, titulo, html, text, [email])
            count += 1
        except Exception:
            pass
    return count


def _notificar_suspension_jornada(request, jornada, motivo, semanas):
    """Push + correo a invitados cuando se suspende una jornada."""
    temporada = jornada.temporada
    categoria = temporada.categoria
    afectados = list(
        Partido.objects.filter(
            temporada=temporada, jornada__numero__gte=jornada.numero
        ).exclude(estado="FIN").select_related("equipo_local", "equipo_visitante")[:6]
    )
    titulo = f"Jornada {jornada.numero} suspendida"
    if categoria:
        titulo += f" - {categoria.nombre}"
    cuerpo = f"Se suspende la jornada {jornada.numero}"
    if categoria:
        cuerpo += f" de {categoria.nombre}"
    cuerpo += f" por: {motivo}. Se recorren {semanas} semana(s)."
    from .push import notify_suspension
    notify_suspension(
        titulo, cuerpo, categoria=categoria,
        partido_id=afectados[0].id if afectados else None,
        data_tipo="jornada_suspendida",
    )
    ctx = {
        "temporada": temporada, "jornada": jornada,
        "motivo": motivo, "semanas": semanas, "partidos": afectados,
    }
    _enviar_suspension_email(titulo, ctx, categoria, request)


def _notificar_partido_pendiente(request, partido, motivo="Partido pendiente"):
    """Push + correo a invitados cuando un partido queda pendiente/reagendado."""
    try:
        categoria = partido.jornada.temporada.categoria
    except AttributeError:
        categoria = None
    local = partido.equipo_local.nombre if partido.equipo_local else "Local"
    visit = partido.equipo_visitante.nombre if partido.equipo_visitante else "Visitante"
    titulo = "Partido pendiente"
    if categoria:
        titulo += f" - {categoria.nombre}"
    cuerpo = f"{local} vs {visit} quedó pendiente."
    fh = partido.fecha_hora
    if fh:
        cuerpo += f" Nueva fecha: {fh}"
    if motivo and motivo != "Partido pendiente":
        cuerpo += f" Motivo: {motivo}"
    from .push import notify_suspension
    notify_suspension(
        titulo, cuerpo, categoria=categoria,
        partido_id=partido.id, data_tipo="partido_pendiente",
    )
    ctx = {"partido": partido, "motivo": motivo, "categoria": categoria}
    _enviar_suspension_email(titulo, ctx, categoria, request)


def _enviar_smtp(smtp, subject, html, text, to_emails):
    from django.core.mail import EmailMultiAlternatives, get_connection
    use_ssl = smtp["port"] == 465
    conn = get_connection(
        host=smtp["host"],
        port=smtp["port"],
        username=smtp["user"],
        password=smtp["password"],
        use_tls=smtp["use_tls"] and not use_ssl,
        use_ssl=use_ssl,
        timeout=15,
    )
    msg = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=smtp["from_email"] or smtp["user"],
        to=to_emails,
        connection=conn,
    )
    msg.attach_alternative(html, "text/html")
    msg.send(fail_silently=False)


def _enviar_sendgrid_api(smtp, subject, html, text, to_emails):
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, Content, To
    message = Mail(
        from_email=Email(smtp["from_email"] or smtp["user"]),
        to_emails=[To(email) for email in to_emails],
        subject=subject,
        html_content=Content("text/html", html),
    )
    sg = SendGridAPIClient(smtp["password"])
    sg.send(message)


def _tabla_hasta_jornada(temporada, jornada_numero):
    """Tabla de posiciones considerando solo partidos hasta (inclusive) la jornada indicada."""
    return temporada.calcular_tabla(jornada_numero=jornada_numero)


def _goleadores_hasta_jornada(temporada, jornada_numero):
    """Goleadores hasta la jornada indicada."""
    from django.db.models import Count
    return list(
        Gol.objects.filter(partido__temporada=temporada, partido__jornada__numero__lte=jornada_numero)
        .values("jugador__nombre", "jugador__apellido", "equipo__nombre")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )


class _SuspensionManualEnvelope:
    """Envuelve una SuspensionJugador para integrarla con lo que esperan las
    vistas/templates que consume la lista de castigados (misma interfaz que una
    Tarjeta para los atributos que se usan)."""

    es_manual = True

    def __init__(self, record, restantes, pendientes):
        self.jugador = record.jugador
        self.equipo = record.equipo
        self.categoria = record.categoria
        self.suspension_jornadas = record.jornadas
        self.motivo = record.motivo
        self.fecha_creacion = record.creado
        self.partido = None
        self.expulsion_partido = None
        self.jornada_expulsion = None
        self.restantes = restantes
        self.pendientes = pendientes
        self._manual = record


def _suspensiones_temporada(temporada, jug_ids=None):
    """Retorna dict {jugador_id: info} con suspensiones activas.

    Pendientes se calcula como los próximos N partidos del mismo equipo
    después de la expulsión (ordenados por fecha_hora).
    Una suspensión está activa si al menos uno de esos partidos aún no ha
    finalizado (estado != 'FIN'), o si no hubo suficientes partidos para
    cumplirla (se arrastra a la siguiente temporada).

    Incluye también las suspensiones manuales (SuspensionJugador) activas
    de la categoría, que arrastran automáticamente entre temporadas.
    """
    qs = Tarjeta.objects.filter(
        tipo="ROJA", suspension_jornadas__gt=0,
        partido__temporada=temporada,
    )
    if jug_ids is not None:
        qs = qs.filter(jugador_id__in=jug_ids)
    qs = qs.select_related("jugador", "equipo", "partido__jornada").order_by("-partido__fecha_hora")
    result = {}
    for r in qs:
        prox = Partido.objects.filter(
            temporada=temporada,
            jornada__numero__gte=r.partido.jornada.numero,
            fecha_hora__gt=r.partido.fecha_hora,
        ).filter(
            Q(equipo_local=r.equipo) | Q(equipo_visitante=r.equipo)
        ).exclude(id=r.partido.id).order_by("jornada__numero", "fecha_hora", "id")[:r.suspension_jornadas]
        prox_list = list(prox)
        pendientes = [p for p in prox_list if p.estado != 'FIN']
        curr_rest = len(pendientes)
        # Si no hubo suficientes partidos para cumplir la suspension
        # y los que hubo ya finalizaron, el saldo se arrastra
        if curr_rest == 0 and len(prox_list) < r.suspension_jornadas:
            curr_rest = r.suspension_jornadas - len(prox_list)
        prev = result.get(r.jugador_id)
        prev_rest = len(prev["pendientes"]) if prev else 0
        if curr_rest > prev_rest:
            result[r.jugador_id] = {
                "pendientes": pendientes,
                "todos": prox_list,
                "expulsion_partido": r.partido,
                "expulsion_equipo": r.equipo,
                "suspension_jornadas": r.suspension_jornadas,
                "restantes": curr_rest,
                "_tarjeta": r,
            }

    # Suspensiones manuales de la categoría (arrastran entre temporadas)
    manual_qs = SuspensionJugador.objects.filter(
        categoria_id=temporada.categoria_id, activo=True,
    )
    if jug_ids is not None:
        manual_qs = manual_qs.filter(jugador_id__in=jug_ids)
    manual_qs = manual_qs.select_related("jugador", "equipo")
    for m in manual_qs:
        if m.jugador_id in result:
            continue
        restantes = m.restantes()
        if restantes <= 0:
            continue
        prox = Partido.objects.filter(
            temporada=temporada,
            estado__in=("PRO", "PROG"),
        ).filter(
            Q(equipo_local=m.equipo) | Q(equipo_visitante=m.equipo)
        ).order_by("jornada__numero", "fecha_hora", "id")[:restantes]
        pendientes = list(prox)
        env = _SuspensionManualEnvelope(m, restantes, pendientes)
        result[m.jugador_id] = {
            "pendientes": pendientes,
            "todos": pendientes,
            "expulsion_partido": None,
            "expulsion_equipo": m.equipo,
            "suspension_jornadas": m.jornadas,
            "restantes": restantes,
            "_tarjeta": env,
            "es_manual": True,
        }
    return result


def _castigados_hasta_jornada(temporada, jornada_numero):
    """Jugadores suspendidos al corte de la jornada indicada (pendientes por cumplir).

    Solo considera tarjetas rojas de esta temporada con jornada <= jornada_numero.
    También arrastra suspensiones activas de la temporada anterior.
    """
    qs = Tarjeta.objects.filter(
        tipo="ROJA", suspension_jornadas__gt=0,
        partido__temporada=temporada,
        partido__jornada__numero__lte=jornada_numero,
    ).select_related("jugador", "equipo", "partido__jornada")

    susp = _suspensiones_temporada(temporada)
    # Filtrar solo las que corresponden a tarjetas hasta jornada_numero
    ids_ok = set(qs.values_list("jugador_id", flat=True))
    ids_ok.update(
        SuspensionJugador.objects.filter(
            categoria_id=temporada.categoria_id, activo=True
        ).values_list("jugador_id", flat=True)
    )
    susp = {k: v for k, v in susp.items() if k in ids_ok}

    # Arrastrar suspensiones activas de la temporada anterior
    temp_anterior = Temporada.objects.filter(
        categoria=temporada.categoria,
        fecha_inicio__lt=temporada.fecha_inicio,
    ).order_by("-fecha_inicio").first()
    if temp_anterior:
        prev = _suspensiones_temporada(temp_anterior)
        for jug_id, info in prev.items():
            if jug_id in susp:
                continue
            if info["restantes"] > 0:
                # Buscar los próximos N partidos del jugador en la nueva temporada
                jug = info["_tarjeta"].jugador
                prox = Partido.objects.filter(
                    temporada=temporada,
                    estado__in=("PRO", "PROG"),
                ).filter(
                    Q(equipo_local=jug.equipo) | Q(equipo_visitante=jug.equipo)
                ).order_by("fecha_hora", "id")[:info["restantes"]]
                pendientes = list(prox)
                if pendientes:
                    r = info["_tarjeta"]
                    susp[jug_id] = {
                        "pendientes": pendientes,
                        "todos": pendientes,
                        "expulsion_partido": info["expulsion_partido"],
                        "expulsion_equipo": info["expulsion_equipo"],
                        "suspension_jornadas": info["suspension_jornadas"],
                        "restantes": len(pendientes),
                        "_tarjeta": r,
                    }

    castigados = []
    for jug_id, info in susp.items():
        if info["restantes"] > 0:
            r = info["_tarjeta"]
            r.pendientes = info["pendientes"]
            r.restantes = info["restantes"]
            r.expulsion_partido = info["expulsion_partido"]
            r.jornada_expulsion = (
                info["expulsion_partido"].jornada.numero
                if info["expulsion_partido"] else None
            )
            castigados.append(r)
    return castigados


def enviar_roles_semana(request, temporada_id):
    if not request.user.is_authenticated or not (request.user.rol and request.user.rol.permisos.get("gestion_partidos", False)):
        messages.error(request, "No tienes permiso para enviar correos.")
        return redirect("home")

    temporada = get_object_or_404(Temporada, pk=temporada_id)
    config = ConfiguracionLiga.obtener()
    if not config.email_smtp_host:
        messages.error(request, "Configura primero el servidor SMTP en Configuración de Liga.")
        return redirect("configuracion_liga")

    jornada_id = request.GET.get("jornada")
    partidos_qs = Partido.objects.filter(temporada=temporada, estado__in=["PEND", "SUSP"]).select_related(
        "equipo_local", "equipo_visitante", "campo", "jornada"
    ).order_by("jornada__numero", "fecha_hora")

    if jornada_id:
        partidos_qs = partidos_qs.filter(jornada_id=jornada_id)
    elif config.enviar_solo_jornada_actual:
        jornada = _obtener_jornada_actual(temporada)
        if jornada:
            partidos_qs = partidos_qs.filter(jornada=jornada)

    partidos = list(partidos_qs)
    if not partidos:
        messages.warning(request, "No hay partidos pendientes para enviar.")
        return redirect("temporada_list")

    descansan_por_jornada = {}
    for j in Jornada.objects.filter(pk__in={p.jornada_id for p in partidos}):
        descansan_por_jornada[j.numero] = [eq.nombre for eq in temporada.equipos_descansan(j)]

    suscriptores = _destinatarios_roles_email(temporada)
    count = 0
    for sus in suscriptores:
        ctx = {
            "temporada": temporada,
            "partidos": partidos,
            "descansan_por_jornada": descansan_por_jornada,
        }
        count += _enviar_correo_suscriptores(
            [sus], config, f"Rol de juegos - {temporada.nombre}",
            "emails/roles_semana.html", ctx, request
        )
    messages.success(request, f"Correos enviados a {count} suscriptores.")
    return redirect("temporada_list")


def enviar_rol_jornada(request, jornada_id):
    if not request.user.is_authenticated or not (request.user.rol and request.user.rol.permisos.get("gestion_partidos", False)):
        messages.error(request, "No tienes permiso para enviar correos.")
        return redirect("home")

    jornada = get_object_or_404(Jornada.objects.select_related("temporada"), pk=jornada_id)
    temporada = jornada.temporada
    config = ConfiguracionLiga.obtener()
    if not config.email_smtp_host:
        messages.error(request, "Configura primero el servidor SMTP en Configuración de Liga.")
        return redirect("configuracion_liga")

    partidos = Partido.objects.filter(jornada=jornada).select_related(
        "equipo_local", "equipo_visitante", "campo", "jornada"
    ).order_by("fecha_hora")

    if not partidos:
        messages.warning(request, "Esta jornada no tiene partidos.")
        return redirect("jornada_list")

    grupos_mode = temporada.tipo_rol == "GRUPOS" and temporada.clasificacion_por_grupos
    if grupos_mode:
        tablas_por_grupo = temporada.calcular_tablas_por_grupo(jornada_numero=jornada.numero)
        grupos = temporada.grupos_asignados()
        ng = len(grupos)
        por_grupo = max(1, temporada.num_clasificados // max(ng, 1)) if ng else 0
        tabla = []
    else:
        tabla = _tabla_hasta_jornada(temporada, jornada.numero)
        tablas_por_grupo = None
        por_grupo = 0

    goleadores = _goleadores_hasta_jornada(temporada, jornada.numero)
    castigados = _castigados_hasta_jornada(temporada, jornada.numero)

    suscriptores = _destinatarios_roles_email(temporada)
    count = 0
    for sus in suscriptores:
        fechas = [p.fecha_hora for p in partidos if p.fecha_hora]
        jornada_fecha = min(fechas).date() if fechas else None
        ctx = {
            "temporada": temporada,
            "jornada": jornada,
            "jornada_fecha": jornada_fecha,
            "partidos": list(partidos),
            "descansan": temporada.equipos_descansan(jornada),
            "tabla": tabla,
            "tablas_por_grupo": tablas_por_grupo,
            "por_grupo": por_grupo,
            "goleadores": goleadores,
            "castigados": castigados,
        }
        count += _enviar_correo_suscriptores(
            [sus], config, f"Resumen Jornada {jornada.numero} - {temporada.nombre}",
            "emails/jornada_completa.html", ctx, request
        )
    messages.success(request, f"Correos enviados a {count} suscriptores.")
    return redirect("jornada_list")


def enviar_estadisticas(request, temporada_id):
    if not request.user.is_authenticated or not (request.user.rol and request.user.rol.permisos.get("gestion_partidos", False)):
        messages.error(request, "No tienes permiso para enviar correos.")
        return redirect("home")

    temporada = get_object_or_404(Temporada, pk=temporada_id)
    config = ConfiguracionLiga.obtener()
    if not config.email_smtp_host:
        messages.error(request, "Configura primero el servidor SMTP en Configuración de Liga.")
        return redirect("configuracion_liga")

    grupos_mode = temporada.tipo_rol == "GRUPOS" and temporada.clasificacion_por_grupos
    if grupos_mode:
        tablas_por_grupo = temporada.calcular_tablas_por_grupo(limit=5)
        grupos = temporada.grupos_asignados()
        ng = len(grupos)
        por_grupo = max(1, temporada.num_clasificados // max(ng, 1)) if ng else 0
        tabla = []
    else:
        tabla = temporada.calcular_tabla(limit=5)
        tablas_por_grupo = None
        por_grupo = 0

    goleadores = (
        Gol.objects.filter(partido__temporada=temporada)
        .values("jugador__nombre", "jugador__apellido", "equipo__nombre")
        .annotate(total=Count("id"))
        .order_by("-total")[:10]
    )

    castigados = Tarjeta.objects.filter(
        partido__temporada=temporada, jugador__activo=True
    ).values("jugador__nombre", "jugador__apellido", "equipo__nombre").annotate(
        rojas=Count("id", filter=Q(tipo="ROJA")),
        amarillas=Count("id", filter=Q(tipo="AMARILLA")),
    ).order_by("-rojas", "-amarillas")[:10]

    suscriptores = SuscripcionEmail.objects.filter(activo=True, recibir_estadisticas=True)
    count = 0
    for sus in suscriptores:
        cats = sus.categorias.all()
        if cats and not cats.filter(id=temporada.categoria_id).exists():
            continue
        ctx = {
            "temporada": temporada,
            "goleadores": goleadores,
            "tabla": tabla,
            "tablas_por_grupo": tablas_por_grupo,
            "por_grupo": por_grupo,
            "castigados": castigados,
        }
        count += _enviar_correo_suscriptores(
            [sus], config, f"Estadísticas - {temporada.nombre}",
            "emails/estadisticas.html", ctx, request
        )
    messages.success(request, f"Estadísticas enviadas a {count} suscriptores.")
    return redirect("temporada_list")


def _parse_proxima_jornada(raw):
    """Convierte la jornada indicada a int >= 1 (default 1)."""
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = 1
    return n if n >= 1 else 1


def iniciar_temporada(request, pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    if temporada.iniciada:
        messages.warning(request, "La temporada ya fue iniciada.")
        return redirect("temporada_list")

    puede, msg = temporada.puede_iniciar()
    if not puede:
        messages.error(request, f"No se puede iniciar: {msg}")
        return redirect("temporada_list")

    # Si es por grupos, auto-asignar si no los tiene y redirigir a ajuste manual
    if temporada.tipo_rol == "GRUPOS":
        if not temporada.grupos_asignados():
            temporada.auto_asignar_grupos()
        grupos = temporada.grupos_asignados()
        cantidades = {k: len(v) for k, v in grupos.items()}
        messages.info(request, f"Grupos asignados: {cantidades}. Ajusta los equipos si es necesario antes de confirmar.")
        return redirect("asignar_grupos", pk=temporada.pk)

    if request.method == "POST":
        ya_iniciada = request.POST.get("ya_iniciada")
        if ya_iniciada == "si":
            # El usuario capturará los partidos reales de las jornadas jugadas
            return redirect("iniciar_temporada_pasadas", pk=temporada.pk)
        jornada = _parse_proxima_jornada(request.POST.get("proxima_jornada"))
        try:
            temporada.generar_rol(jornada_inicial=jornada)
        except Exception as e:
            messages.error(request, f"Error al generar el rol: {e}")
            return redirect("temporada_list")
        temporada.iniciada = True
        temporada.save()
        if jornada > 1:
            messages.success(
                request,
                f"Temporada '{temporada.nombre}' iniciada. Jornadas 1 a {jornada - 1} generadas con "
                f"fechas pasadas (captura sus cédulas y finalízalas); desde la jornada {jornada} programadas."
            )
        else:
            messages.success(request, f"Temporada '{temporada.nombre}' iniciada con rol de juegos generado.")
        return redirect("temporada_list")

    # Si la fecha de inicio es pasada, preguntar si ya estaba iniciada y desde qué jornada
    if temporada.fecha_inicio < date.today():
        ctx = {
            "temporada": temporada,
            "url_generar": reverse("iniciar_temporada", args=[pk]),
        }
        return render(request, "league/iniciar_temporada.html", ctx)

    try:
        temporada.generar_rol()
    except Exception as e:
        messages.error(request, f"Error al generar el rol: {e}")
        return redirect("temporada_list")

    temporada.iniciada = True
    temporada.save()
    messages.success(request, f"Temporada '{temporada.nombre}' iniciada con rol de juegos generado.")
    return redirect("temporada_list")


def generar_liguilla_view(request, pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    if not temporada.iniciada:
        messages.warning(request, "La temporada debe estar iniciada para generar la liguilla.")
        return redirect("temporada_list")
    if temporada.tipo_competencia != "LIGUILLA":
        messages.warning(request, "Esta temporada no es de tipo Liguilla.")
        return redirect("temporada_list")
    estado = temporada.estado_liguilla()
    if estado == "completada":
        messages.warning(request, "La liguilla ya está completa. No hay más rondas que generar.")
        return redirect("temporada_list")
    if estado == "en_curso":
        messages.warning(request, "Aún hay partidos pendientes en la ronda actual. Finalízalos antes de avanzar.")
        return redirect("temporada_list")
    if estado == "no_iniciada" and not temporada.puede_iniciar_liguilla:
        messages.warning(request, "Debes finalizar todos los partidos de la temporada regular antes de iniciar la liguilla.")
        return redirect("temporada_list")
    try:
        temporada.generar_siguiente_ronda()
        messages.success(request, f"Ronda generada correctamente para '{temporada.nombre}'.")
    except Exception as e:
        messages.error(request, f"Error: {e}")
    return redirect("temporada_list")


def asignar_grupos(request, pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    if temporada.iniciada:
        messages.warning(request, "La temporada ya fue iniciada.")
        return redirect("temporada_list")

    equipos = temporada.equipos_habilitados()
    grupos = temporada.grupos_asignados()

    if request.method == "POST":
        nuevos = {}
        for eq in equipos:
            grupo_val = request.POST.get(f"grupo_{eq.id}")
            orden_val = request.POST.get(f"orden_{eq.id}", 0)
            if grupo_val:
                nuevos[eq.id] = {"grupo": grupo_val, "orden": int(orden_val or 0)}
        if not nuevos:
            messages.error(request, "No se recibieron asignaciones.")
        else:
            Grupo.objects.filter(temporada=temporada).delete()
            for eq_id, data in nuevos.items():
                Grupo.objects.create(
                    temporada=temporada,
                    equipo_id=eq_id,
                    grupo=data["grupo"],
                    orden=data["orden"],
                )
            messages.success(request, "Grupos actualizados.")
            return redirect("confirmar_grupos", pk=temporada.pk)
        return redirect("asignar_grupos", pk=temporada.pk)

    # Convertir dict a lista plana para template
    asignaciones = []
    for eq in equipos:
        encontrado = None
        for g, eqs in grupos.items():
            if eq in eqs:
                encontrado = {"equipo": eq, "grupo": g, "orden": next(
                    (gr.orden for gr in Grupo.objects.filter(temporada=temporada, equipo=eq)), 0
                )}
                break
        if not encontrado:
            encontrado = {"equipo": eq, "grupo": "", "orden": 0}
        asignaciones.append(encontrado)

    ctx = {"temporada": temporada, "asignaciones": asignaciones, "grupos": sorted(grupos.keys())}
    return render(request, "league/asignar_grupos.html", ctx)


def confirmar_grupos(request, pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    if temporada.iniciada:
        messages.warning(request, "La temporada ya fue iniciada.")
        return redirect("temporada_list")

    grupos = temporada.grupos_asignados()
    if not grupos or all(len(v) < 2 for v in grupos.values()):
        messages.error(request, "Cada grupo debe tener al menos 2 equipos.")
        return redirect("asignar_grupos", pk=temporada.pk)

    if request.method == "POST":
        ya_iniciada = request.POST.get("ya_iniciada")
        if ya_iniciada == "si":
            return redirect("iniciar_temporada_pasadas", pk=temporada.pk)
        jornada = _parse_proxima_jornada(request.POST.get("proxima_jornada"))
        try:
            temporada.generar_rol(jornada_inicial=jornada)
        except Exception as e:
            messages.error(request, f"Error al generar el rol: {e}")
            return redirect("temporada_list")
        temporada.iniciada = True
        temporada.save()
        if jornada > 1:
            messages.success(
                request,
                f"Temporada '{temporada.nombre}' iniciada con rol por grupos. Jornadas 1 a {jornada - 1} "
                f"con fechas pasadas (captura sus cédulas); desde la jornada {jornada} programadas."
            )
        else:
            messages.success(request, f"Temporada '{temporada.nombre}' iniciada con rol por grupos generado.")
        return redirect("temporada_list")

    # Si la fecha de inicio es pasada, preguntar si ya estaba iniciada y desde qué jornada
    if temporada.fecha_inicio < date.today():
        ctx = {
            "temporada": temporada,
            "url_generar": reverse("confirmar_grupos", args=[pk]),
        }
        return render(request, "league/iniciar_temporada.html", ctx)

    try:
        temporada.generar_rol()
    except Exception as e:
        messages.error(request, f"Error al generar el rol: {e}")
        return redirect("temporada_list")

    temporada.iniciada = True
    temporada.save()
    messages.success(request, f"Temporada '{temporada.nombre}' iniciada con rol por grupos generado.")
    return redirect("temporada_list")


def iniciar_temporada_jornadas_pasadas(request, pk):
    """Wizard para temporadas ya iniciadas: captura los partidos reales de las
    jornadas ya jugadas (local, visitante, campo, hora, fecha, marcador opcional con
    finalización) y luego genera el rol de las jornadas restantes."""
    temporada = get_object_or_404(Temporada, pk=pk)
    if temporada.iniciada:
        messages.warning(request, "La temporada ya fue iniciada.")
        return redirect("temporada_list")

    puede, msg = temporada.puede_iniciar()
    if not puede:
        messages.error(request, f"No se puede iniciar: {msg}")
        return redirect("temporada_list")

    # Número de jornadas ya jugadas capturadas en esta sesión de wizard
    jornadas_guardadas = set(
        Partido.objects.filter(temporada=temporada).values_list("jornada__numero", flat=True)
    )
    proxima_jornada = (max(jornadas_guardadas) + 1) if jornadas_guardadas else 1

    equipos = temporada.equipos_habilitados()
    campos = list(Campo.objects.filter(activo=True).order_by("nombre"))
    partidos_x_jornada = temporada.partidos_por_jornada()

    # Total de jornadas ya jugadas capturadas por el usuario (persistido en sesión)
    n_jornadas = request.session.get(
        f"temp_pasadas_{temporada.pk}", 0
    )
    if request.method == "POST":
        accion = request.POST.get("accion")

        if accion == "set_jornadas":
            try:
                n_jornadas = int(request.POST.get("n_jornadas", "0"))
            except ValueError:
                n_jornadas = 0
            if n_jornadas < 1:
                messages.error(request, "Indica al menos 1 jornada ya jugada.")
            else:
                request.session[f"temp_pasadas_{temporada.pk}"] = n_jornadas
                messages.success(request, f"Jornadas pasadas registradas: {n_jornadas}.")
            return redirect("iniciar_temporada_pasadas", pk=pk)

        if accion == "guardar":
            # index por jornada dentro de la colección de filas
            jnums = request.POST.getlist("jornada_num")
            env_local = request.POST.getlist("local")
            env_visit = request.POST.getlist("visitante")
            env_campo = request.POST.getlist("campo")
            env_fecha = request.POST.getlist("fecha")
            env_hora = request.POST.getlist("hora")
            env_gl = request.POST.getlist("gl")
            env_gv = request.POST.getlist("gv")
            env_finalizar = request.POST.getlist("finalizar")

            errores = []
            creados = 0
            for i in range(len(env_local)):
                if not env_local[i] or not env_visit[i]:
                    continue
                jn = int(jnums[i]) if jnums[i] else proxima_jornada
                # Validar que no exceda el máximo de partidos de la jornada
                ya_en_jornada = Partido.objects.filter(
                    temporada=temporada, jornada__numero=jn
                ).count()
                if ya_en_jornada >= partidos_x_jornada:
                    errores.append(
                        f"Jornada {jn} ya tiene sus {partidos_x_jornada} partido(s); no se pueden agregar más."
                    )
                    continue
                local = Equipo.objects.filter(pk=int(env_local[i])).first() if env_local[i] else None
                visit = Equipo.objects.filter(pk=int(env_visit[i])).first() if env_visit[i] else None
                if local == visit:
                    errores.append("Equipo local y visitante no pueden ser el mismo.")
                    continue

                # Validar que la pareja ya no esté registrada en esta temporada
                ya_existe = Partido.objects.filter(
                    temporada=temporada,
                    equipo_local__in=[local, visit],
                    equipo_visitante__in=[visit, local],
                ).exists()
                if ya_existe:
                    errores.append(f"{local} vs {visit} ya jugaron entre sí (jornada {jn}).")
                    continue

                # Fecha/hora
                try:
                    fecha = datetime.datetime.strptime(env_fecha[i], "%Y-%m-%d").date()
                    hora = datetime.datetime.strptime(env_hora[i], "%H:%M").time()
                except (ValueError, IndexError):
                    errores.append(f"Fecha/hora inválida en la fila {i + 1}.")
                    continue
                fecha_hora_dt = datetime.datetime.combine(fecha, hora)
                fecha_hora = timezone.make_aware(fecha_hora_dt)

                # Campo con validación de choque (todas las temporadas)
                campo_id = int(env_campo[i]) if env_campo[i] else None
                campo = get_object_or_404(Campo, pk=campo_id) if campo_id else None
                if campo:
                    choque = Partido.objects.filter(
                        fecha_hora=fecha_hora, campo=campo,
                        temporada__in=Temporada.objects.filter(finalizada=False),
                    ).exclude(estado="FIN")
                    if choque.exists():
                        errores.append(f"El campo {campo} ya está ocupado el {fecha} a las {hora}.")
                        continue

                gl = int(env_gl[i]) if (env_gl[i] and env_gl[i].strip()) else None
                gv = int(env_gv[i]) if (env_gv[i] and env_gv[i].strip()) else None
                finalizar = (env_finalizar[i].strip() == "1") if env_finalizar[i] else False

                # Crear/obtener la jornada
                jornada, _ = Jornada.objects.get_or_create(
                    temporada=temporada, numero=jn,
                    defaults={"nombre": f"Jornada {jn}", "estado": "ACTIVA"},
                )
                estado = "FIN" if finalizar else "PEND"
                gl_ = gl if (finalizar and gl is not None) else 0
                gv_ = gv if (finalizar and gv is not None) else 0
                Partido.objects.create(
                    temporada=temporada, jornada=jornada,
                    equipo_local=local, equipo_visitante=visit,
                    campo=campo, fecha_hora=fecha_hora,
                    goles_local=gl_, goles_visitante=gv_,
                    estado=estado,
                )
                creados += 1

            if errores:
                for e in errores:
                    messages.error(request, e)
            if creados:
                messages.success(request, f"{creados} partido(s) registrado(s).")

            # Actualizar valores para el re-render
            jornadas_guardadas = set(
                Partido.objects.filter(temporada=temporada).values_list("jornada__numero", flat=True)
            )
            proxima_jornada = (max(jornadas_guardadas) + 1) if jornadas_guardadas else 1
            ctx = {
                "temporada": temporada,
                "equipos": equipos,
                "campos": campos,
                "jornadas_pasadas": sorted(jornadas_guardadas),
                "proxima_jornada": proxima_jornada,
                "n_jornadas": n_jornadas,
                "partidos_x_jornada": partidos_x_jornada,
                "partidos_guardados": Partido.objects.filter(temporada=temporada)
                .select_related("equipo_local", "equipo_visitante", "campo", "jornada")
                .order_by("jornada__numero"),
            }
            return render(request, "league/iniciar_temporada_jornadas.html", ctx)

        elif accion == "generar":
            if not jornadas_guardadas:
                messages.warning(request, "Registra al menos un partido de las jornadas jugadas antes de generar el rol.")
                return redirect("iniciar_temporada", pk=pk)
            if n_jornadas < 1:
                messages.error(request, "Indica cuántas jornadas ya se jugaron antes de generar el rol.")
                return redirect("iniciar_temporada", pk=pk)
            # Validar que cada jornada pasada esté completa con exactamente los partidos esperados
            incompletas = []
            for jn in range(1, n_jornadas + 1):
                cnt = Partido.objects.filter(temporada=temporada, jornada__numero=jn).count()
                if cnt != partidos_x_jornada:
                    incompletas.append(f"Jornada {jn}: {cnt}/{partidos_x_jornada}")
            if incompletas:
                messages.error(
                    request,
                    "Algunas jornadas pasadas están incompletas o con partidos de más "
                    f"(esperado {partidos_x_jornada} por jornada). Corrige antes de generar: "
                    + "; ".join(incompletas),
                )
                return redirect("iniciar_temporada_pasadas", pk=pk)
            try:
                temporada.generar_rol_respaldando_pasadas(jornada_inicial=proxima_jornada)
            except Exception as e:
                messages.error(request, f"Error al generar el rol: {e}")
                return redirect("temporada_list")
            temporada.iniciada = True
            temporada.save()
            messages.success(
                request,
                f"Temporada '{temporada.nombre}' iniciada. Jornadas {proxima_jornada} en adelante "
                f"generadas respetando los partidos ya registrados (sin huecos ni choques)."
            )
            return redirect("temporada_list")

    ctx = {
        "temporada": temporada,
        "equipos": equipos,
        "campos": campos,
        "jornadas_pasadas": sorted(jornadas_guardadas),
        "proxima_jornada": proxima_jornada,
        "n_jornadas": n_jornadas,
        "partidos_x_jornada": partidos_x_jornada,
        "partidos_guardados": Partido.objects.filter(temporada=temporada)
        .select_related("equipo_local", "equipo_visitante", "campo", "jornada")
        .order_by("jornada__numero"),
    }
    return render(request, "league/iniciar_temporada_jornadas.html", ctx)


class JornadaListView(ListView):
    model = Jornada
    template_name = "league/jornada_list.html"
    context_object_name = "jornadas"

    def get_queryset(self):
        qs = Jornada.objects.all()
        temp = self.request.GET.get("temporada")
        if temp:
            qs = qs.filter(temporada_id=temp)
        else:
            qs = qs.filter(temporada__finalizada=False)
        return qs.select_related("temporada").annotate(
            min_fecha=Min("partidos__fecha_hora"),
            max_fecha=Max("partidos__fecha_hora"),
            total_partidos=Count("partidos", distinct=True),
            pendientes=Count(
                "partidos",
                filter=Q(partidos__estado__in=["PEND", "SUSP"]),
                distinct=True,
            ),
            tiene_pendientes=Case(
                When(pendientes__gt=0, then=Value(1)),
                default=Value(0, output_field=IntegerField()),
                output_field=IntegerField(),
            ),
        ).order_by("-tiene_pendientes", "temporada", "min_fecha")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["temporadas"] = Temporada.objects.filter(activa=True)
        ctx["es_amistoso"] = self.request.GET.get("tipo") == "amistoso"
        return ctx


class ArbitroListView(ListView):
    model = Arbitro
    template_name = "league/arbitro_list.html"
    context_object_name = "arbitros"


class ArbitroCreateView(CreateView):
    model = Arbitro
    form_class = ArbitroForm
    template_name = "league/arbitro_form.html"
    success_url = reverse_lazy("arbitro_list")

    def form_valid(self, form):
        resp = super().form_valid(form)
        if form.cleaned_data.get("crear_usuario"):
            from accounts.models import Rol, Usuario
            arbitro = self.object
            username = _generar_username_arbitro(arbitro.nombre)
            rol_arbitro, _ = Rol.objects.get_or_create(nombre="Árbitro")
            user_created = Usuario.objects.create_user(
                username=username,
                password="123",
                first_name=arbitro.nombre,
                rol=rol_arbitro,
            )
            arbitro.usuario = user_created
            arbitro.save(update_fields=["usuario"])
            from django.contrib import messages
            messages.info(
                self.request,
                f"Usuario creado: {user_created.get_full_name() or user_created.username} "
                f"con contraseña predeterminada: 123.",
            )
        return resp


def _generar_username_arbitro(nombre):
    base = nombre.replace(" ", "")
    from accounts.models import Usuario
    if not Usuario.objects.filter(username=base).exists():
        return base
    i = 1
    while Usuario.objects.filter(username=f"{base}{i}").exists():
        i += 1
    return f"{base}{i}"


class ArbitroUpdateView(UpdateView):
    model = Arbitro
    form_class = ArbitroForm
    template_name = "league/arbitro_form.html"
    success_url = reverse_lazy("arbitro_list")

    def form_valid(self, form):
        resp = super().form_valid(form)
        from accounts.models import Rol, Usuario
        arbitro = self.object
        user = Usuario.objects.filter(
            username__in=[arbitro.nombre.replace(" ", ""), f"arbitro_{arbitro.id}"]
        ).first()
        if form.cleaned_data.get("crear_usuario"):
            if not user:
                username = _generar_username_arbitro(arbitro.nombre)
                rol_arbitro, _ = Rol.objects.get_or_create(nombre="Árbitro")
                user = Usuario.objects.create_user(
                    username=username,
                    password="123",
                    first_name=arbitro.nombre,
                    rol=rol_arbitro,
                )
                arbitro.usuario = user
                arbitro.save(update_fields=["usuario"])
                from django.contrib import messages
                messages.info(
                    self.request,
                    f"Usuario creado: {user.get_full_name() or user.username} "
                    f"con contraseña predeterminada: 123.",
                )
            elif user.username.startswith("arbitro_"):
                user.username = _generar_username_arbitro(arbitro.nombre)
                user.first_name = arbitro.nombre
                user.save(update_fields=["username", "first_name"])
                arbitro.usuario = user
                arbitro.save(update_fields=["usuario"])
        else:
            if user:
                user.is_active = False
                user.save(update_fields=["is_active"])
        return resp


class ArbitroDeleteView(DeleteView):
    model = Arbitro
    template_name = "league/arbitro_confirm_delete.html"
    success_url = reverse_lazy("arbitro_list")


class PeriodoAltasListView(ListView):
    model = PeriodoAltas
    template_name = "league/periodoaltas_list.html"
    context_object_name = "periodos"

    def get_queryset(self):
        qs = PeriodoAltas.objects.all()
        temp = self.request.GET.get("temporada")
        if temp:
            qs = qs.filter(temporada_id=temp)
        return qs.select_related("temporada")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["temporadas"] = Temporada.objects.filter(activa=True)
        return ctx


class PeriodoAltasCreateView(CreateView):
    model = PeriodoAltas
    form_class = PeriodoAltasForm
    template_name = "league/periodoaltas_form.html"
    success_url = reverse_lazy("periodoaltas_list")


class PeriodoAltasUpdateView(UpdateView):
    model = PeriodoAltas
    form_class = PeriodoAltasForm
    template_name = "league/periodoaltas_form.html"
    success_url = reverse_lazy("periodoaltas_list")


class PeriodoAltasDeleteView(DeleteView):
    model = PeriodoAltas
    template_name = "league/periodoaltas_confirm_delete.html"
    success_url = reverse_lazy("periodoaltas_list")


def gestionar_altas_bajas(request, pk):
    from django import forms as djforms
    from django.db.models import Count, Q

    periodo = get_object_or_404(PeriodoAltas, pk=pk)
    temp = periodo.temporada
    cat = temp.categoria
    max_jug = cat.max_jugadores
    equipos = Equipo.objects.filter(categoria=cat, activo=True).order_by("nombre")

    if request.method == "POST":
        action = request.POST.get("accion")

        if action == "baja":
            jugador_id = request.POST.get("jugador_id")
            equipo_id = request.POST.get("equipo_id")
            jug = get_object_or_404(Jugador, pk=jugador_id)
            eq = get_object_or_404(Equipo, pk=equipo_id)
            # Desactivar registro en JugadorEquipo
            JugadorEquipo.objects.filter(jugador=jug, equipo=eq).update(activo=False)
            # Si era su equipo principal, desvincular
            if jug.equipo_id == eq.id:
                jug.equipo = None
                jug.save(update_fields=["equipo"])
            messages.success(request, f"{jug} dado de baja de {eq}.")
            return redirect("gestionar_altas_bajas", pk=pk)

        elif action == "alta_existente":
            jugador_id = request.POST.get("jugador_id")
            equipo_id = request.POST.get("equipo_id")
            es_principal = request.POST.get("es_principal") == "1"
            jug = get_object_or_404(Jugador, pk=jugador_id)
            eq = get_object_or_404(Equipo, pk=equipo_id)
            # Si el jugador ya tiene equipo, validar que no haya jugado en la temporada activa
            if jug.equipo:
                from .models import JugadorPartido
                temp_activa = Temporada.objects.filter(
                    categoria=jug.equipo.categoria, iniciada=True, finalizada=False
                ).first()
                if temp_activa and JugadorPartido.objects.filter(
                    jugador=jug, equipo=jug.equipo, partido__temporada=temp_activa
                ).exists():
                    messages.error(
                        request,
                        f"{jug} ya tiene participaciones registradas con {jug.equipo} en la "
                        f"temporada actual de {jug.equipo.categoria.nombre} y no puede cambiarse de equipo."
                    )
                    return redirect("gestionar_altas_bajas", pk=pk)
            # Validar edad
            if jug.edad() is not None:
                c = eq.categoria
                if c.edad_minima is not None and jug.edad() < c.edad_minima:
                    messages.error(request, f"{jug} tiene {jug.edad()} años. {c.nombre} requiere mínimo {c.edad_minima}.")
                    return redirect("gestionar_altas_bajas", pk=pk)
                if c.edad_maxima is not None and jug.edad() > c.edad_maxima:
                    messages.error(request, f"{jug} tiene {jug.edad()} años. {c.nombre} permite máximo {c.edad_maxima}.")
                    return redirect("gestionar_altas_bajas", pk=pk)
            # Verificar cupo
            total_actual = (
                Jugador.objects.filter(equipo=eq).count()
                + JugadorEquipo.objects.filter(equipo=eq, activo=True, es_principal=False).count()
            )
            if total_actual >= max_jug:
                messages.error(request, f"{eq} ya alcanzó el límite de {max_jug} jugadores.")
                return redirect("gestionar_altas_bajas", pk=pk)
            # Crear o reactivar registro
            reg, created = JugadorEquipo.objects.get_or_create(
                jugador=jug, equipo=eq,
                defaults={"es_principal": es_principal, "activo": True}
            )
            if not created:
                reg.activo = True
                reg.es_principal = es_principal
                reg.save()
            # Si es principal, actualizar el FK en Jugador
            if es_principal:
                # Limpiar cualquier registro previo como principal en la misma categoría
                JugadorEquipo.objects.filter(
                    jugador=jug, equipo__categoria=eq.categoria,
                    es_principal=True,
                ).exclude(equipo=eq).delete()
                jug.equipo = eq
                jug.save(update_fields=["equipo"])
            messages.success(request, f"{jug} dado de alta en {eq}.")
            return redirect("gestionar_altas_bajas", pk=pk)

    # Datos para mostrar
    equipos_data = []
    for eq in equipos:
        primarios = Jugador.objects.filter(equipo=eq, activo=True)
        secundarios = JugadorEquipo.objects.filter(
            equipo=eq, activo=True, es_principal=False
        ).select_related("jugador")
        total = primarios.count() + secundarios.count()
        equipos_data.append({
            "equipo": eq,
            "primarios": primarios,
            "secundarios": secundarios,
            "total": total,
            "max": max_jug,
            "cupo_disponible": max_jug - total,
        })

    # Jugadores disponibles para alta: solo de categorías compatibles con la actual
    compat_ids = list(cat.categorias_compatibles.values_list("id", flat=True))
    compat_ids.append(cat.id)
    # Categorías que tienen a cat como compatible (dirección inversa)
    reverse_ids = list(Categoria.objects.filter(categorias_compatibles=cat).values_list("id", flat=True))
    all_ids = set(compat_ids + reverse_ids)
    # Excluir los que ya están en algún equipo de esta categoría
    ids_en_categoria = set()
    for eq in equipos:
        ids_en_categoria.update(Jugador.objects.filter(equipo=eq).values_list("id", flat=True))
        ids_en_categoria.update(
            JugadorEquipo.objects.filter(equipo=eq, activo=True)
            .values_list("jugador_id", flat=True)
        )
    jugadores_disponibles = Jugador.objects.filter(activo=True, suspendido_pago=False).exclude(
        id__in=ids_en_categoria
    ).filter(
        Q(equipo__isnull=True) | Q(equipo__categoria_id__in=all_ids)
    )

    return render(request, "league/gestionar_altas_bajas.html", {
        "periodo": periodo,
        "temporada": temp,
        "categoria": cat,
        "equipos_data": equipos_data,
        "jugadores_disponibles": jugadores_disponibles,
        "max_jug": max_jug,
    })


class PartidoListView(ListView):
    model = Partido
    template_name = "league/partido_list.html"
    context_object_name = "partidos"

    def get_queryset(self):
        qs = Partido.objects.all()
        tipo = self.request.GET.get("tipo", "liga")
        if tipo == "amistoso":
            qs = qs.filter(es_amistoso=True)
        else:
            qs = qs.filter(es_amistoso=False)
        arbitro = getattr(self.request.user, "perfil_arbitro", None)
        if arbitro:
            ahora_local = timezone.localtime(timezone.now())
            inicio_dia = ahora_local.replace(hour=0, minute=0, second=0, microsecond=0)
            fin_dia = inicio_dia + datetime.timedelta(days=1)
            qs = qs.filter(
                arbitro=arbitro,
                fecha_hora__gte=inicio_dia,
                fecha_hora__lt=fin_dia,
            )
        if tipo != "amistoso":
            temp = self.request.GET.get("temporada")
            if temp:
                qs = qs.filter(temporada_id=temp)
            elif not arbitro:
                qs = qs.filter(temporada__finalizada=False)
            jorn = self.request.GET.get("jornada")
            if jorn:
                qs = qs.filter(jornada_id=jorn)
        return qs.select_related("equipo_local", "equipo_visitante", "campo", "arbitro", "temporada", "jornada").annotate(
            estado_orden=Case(
                When(estado__in=["PEND", "SUSP"], then=Value(0)),
                When(estado="JUG", then=Value(1)),
                When(estado="FIN", then=Value(2)),
                default=Value(3),
                output_field=IntegerField(),
            ),
            pend_asc=Case(
                When(estado__in=["PEND", "SUSP"], then=F("fecha_hora")),
                default=Value(datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc), output_field=DateTimeField()),
                output_field=DateTimeField(),
            ),
            fin_desc=Case(
                When(estado="FIN", then=F("fecha_hora")),
                default=Value(datetime.datetime(1900, 1, 1, tzinfo=datetime.timezone.utc), output_field=DateTimeField()),
                output_field=DateTimeField(),
            ),
        ).order_by("estado_orden", "pend_asc", "-fin_desc")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["tipo"] = self.request.GET.get("tipo", "liga")
        ctx["temporadas"] = Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")
        temp_id = self.request.GET.get("temporada")
        if temp_id:
            ctx["jornadas"] = Jornada.objects.filter(temporada_id=temp_id).order_by("numero")
        else:
            ctx["jornadas"] = Jornada.objects.filter(temporada__finalizada=False).order_by("numero")
        jorn = self.request.GET.get("jornada")
        if jorn and self.request.GET.get("tipo", "liga") != "amistoso":
            j_obj = Jornada.objects.filter(pk=jorn).select_related("temporada").first()
            if j_obj:
                ctx["descansan"] = j_obj.temporada.equipos_descansan(j_obj)
        return ctx


def _ida_no_fin(partido):
    """True si el partido es vuelta de liguilla y su ida aun no esta FIN."""
    if partido.liguilla_leg != 2 or not partido.es_liguilla:
        return False
    return Partido.objects.filter(
        jornada=partido.jornada, es_liguilla=True,
        liguilla_leg__isnull=True,
        equipo_local=partido.equipo_visitante,
        equipo_visitante=partido.equipo_local,
    ).exclude(estado="FIN").exists()


class PartidoCreateView(CreateView):
    model = Partido
    form_class = PartidoForm
    template_name = "league/partido_form.html"
    success_url = reverse_lazy("partido_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["temporadas"] = Temporada.objects.filter(activa=True)
        return ctx


class PartidoUpdateView(UpdateView):
    model = Partido
    form_class = PartidoForm
    template_name = "league/partido_form.html"
    success_url = reverse_lazy("partido_list")

    def dispatch(self, request, *args, **kwargs):
        partido = self.get_object()
        if _ida_no_fin(partido):
            messages.error(request, "Debes finalizar el partido de ida antes de editar la vuelta.")
            return redirect("partido_list")
        if partido.estado == "FIN" and not request.user.tiene_permiso("partido_aperturar"):
            messages.error(request, "No tienes permiso para editar partidos finalizados.")
            return redirect("partido_list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["temporadas"] = Temporada.objects.filter(activa=True)
        ctx["es_amistoso"] = self.object.es_amistoso
        return ctx


class PartidoDeleteView(DeleteView):
    model = Partido
    template_name = "league/partido_confirm_delete.html"
    success_url = reverse_lazy("partido_list")

    def dispatch(self, request, *args, **kwargs):
        partido = self.get_object()
        if partido.estado == "FIN" and not request.user.tiene_permiso("partido_aperturar"):
            messages.error(request, "No tienes permiso para eliminar partidos finalizados.")
            return redirect("partido_list")
        return super().dispatch(request, *args, **kwargs)


def tabla_posiciones(request):
    cat_id = request.GET.get("categoria")
    temp_id = request.GET.get("temporada")
    categorias = Categoria.objects.filter(activo=True)
    qs_temp = Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")
    if cat_id:
        qs_temp = qs_temp.filter(categoria_id=cat_id)
    else:
        default_cat = Categoria.objects.filter(es_principal=True).first()
        if default_cat:
            qs_temp = qs_temp.filter(categoria=default_cat)
    temporadas = qs_temp

    if not temp_id:
        activas = [t for t in temporadas if not t.finalizada]
        if activas:
            temp_id = activas[0].id

    tabla = []
    tablas_por_grupo = []
    por_grupo = 0
    if temp_id:
        temp = Temporada.objects.get(pk=temp_id)
        if temp.tipo_rol == "GRUPOS" and temp.clasificacion_por_grupos:
            tablas_por_grupo = temp.calcular_tablas_por_grupo()
            grupos = temp.grupos_asignados()
            ng = len(grupos)
            por_grupo = max(1, temp.num_clasificados // max(ng, 1)) if ng else 0
        else:
            tabla = temp.calcular_tabla()

    return render(request, "league/tabla_posiciones.html", {
        "tabla": tabla,
        "tablas_por_grupo": tablas_por_grupo,
        "por_grupo": por_grupo,
        "categorias": categorias,
        "cat_id": int(cat_id) if cat_id else None,
        "temporadas": temporadas,
        "temp_id": int(temp_id) if temp_id else None,
        "temporada": temp if temp_id else None,
    })


def tabla_goleo(request):
    cat_id = request.GET.get("categoria")
    temp_id = request.GET.get("temporada")
    jornada_id = request.GET.get("jornada")
    categorias = Categoria.objects.filter(activo=True)
    qs_temp = Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")
    if cat_id:
        qs_temp = qs_temp.filter(categoria_id=cat_id)
    else:
        default_cat = Categoria.objects.filter(es_principal=True).first()
        if default_cat:
            qs_temp = qs_temp.filter(categoria=default_cat)
    temporadas = qs_temp

    if not temp_id:
        activas = [t for t in temporadas if not t.finalizada]
        if activas:
            temp_id = activas[0].id

    jornadas = []
    if temp_id:
        jornadas = Jornada.objects.filter(temporada_id=temp_id).order_by("numero")

    goleadores = []

    if temp_id:
        qs = Gol.objects.filter(partido__temporada_id=temp_id)
        if jornada_id:
            qs = qs.filter(partido__jornada_id=jornada_id)
        goleadores = (
            qs
            .values(
                "jugador__id", "jugador__nombre", "jugador__apellido",
                "jugador__foto", "jugador__dorsal",
                "equipo__id", "equipo__nombre", "equipo__logo",
            )
            .annotate(total_goles=Count("id"))
            .order_by("-total_goles")
        )

    return render(request, "league/tabla_goleo.html", {
        "goleadores": goleadores,
        "categorias": categorias,
        "cat_id": int(cat_id) if cat_id else None,
        "temporadas": temporadas,
        "temp_id": int(temp_id) if temp_id else None,
        "jornadas": jornadas,
        "jornada_id": int(jornada_id) if jornada_id else None,
    })


def cedula_arbitral(request, partido_id):
    es_invitado = not request.user.is_authenticated
    partido = get_object_or_404(Partido, pk=partido_id)

    if es_invitado:
        # Los invitados solo ven cédulas de partidos finalizados. Si el partido
        # se reabre para ajuste (deja de estar FIN), la cédula se oculta.
        if partido.estado != "FIN":
            return render(request, "league/cedula_invitado_no_disponible.html", {"partido": partido}, status=404)
    elif _ida_no_fin(partido):
        messages.error(request, "Debes finalizar el partido de ida antes de capturar la vuelta.")
        return redirect("partido_list")

    jugadores_local = list(Jugador.objects.filter(equipo=partido.equipo_local, activo=True).select_related("equipo"))
    jugadores_visit = list(Jugador.objects.filter(equipo=partido.equipo_visitante, activo=True).select_related("equipo"))
    goles = Gol.objects.filter(partido=partido).select_related("jugador", "equipo")
    tarjetas = Tarjeta.objects.filter(partido=partido).select_related("jugador", "equipo")
    arbitros_list = Arbitro.objects.filter(activo=True).order_by("apellido", "nombre")

    if request.method == "POST" and not es_invitado:
        from .cedula_service import procesar_cedula
        result = procesar_cedula(partido, request.POST, request.user)
        if not result["ok"]:
            for e in result["errors"]:
                messages.error(request, e)
            return redirect("cedula_arbitral", partido_id=partido.id)
        for w in result["warnings"]:
            messages.warning(request, w)
        if result["finalizado"]:
            messages.success(request, "Cédula arbitral guardada y partido finalizado.")
            return redirect("partido_list")
        messages.success(request, "Cédula arbitral guardada correctamente.")
        return redirect("cedula_arbitral", partido_id=partido.id)

    from collections import Counter
    goles_count = Counter(str(g.jugador_id) for g in goles)
    tarjetas_dict = {}
    for t in tarjetas:
        sid = str(t.jugador_id)
        if sid not in tarjetas_dict:
            tarjetas_dict[sid] = {"amarillas": 0, "roja": False, "suspension": 0}
        if t.tipo == "AMARILLA":
            tarjetas_dict[sid]["amarillas"] += 1
        elif t.tipo == "ROJA":
            tarjetas_dict[sid]["roja"] = True
            tarjetas_dict[sid]["suspension"] = t.suspension_jornadas

    participaciones = {p.jugador_id: p for p in JugadorPartido.objects.filter(partido=partido)}

    for j in jugadores_local + jugadores_visit:
        sid = str(j.id)
        data = tarjetas_dict.get(sid, {"amarillas": 0, "roja": False, "suspension": 0})
        j.cantidad_goles = goles_count.get(sid, 0)
        j.cantidad_amarillas = data["amarillas"]
        j.tiene_roja = data["roja"]
        j.suspension_jornadas = data["suspension"]
        p = participaciones.get(j.id)
        j.es_titular = p.titular if p else None

    # Verificar suspensiones de partidos anteriores (basado en próximos N partidos del equipo)
    for j in jugadores_local + jugadores_visit:
        j.esta_suspendido = False
        j.jornadas_pendientes = 0
    if partido.jornada and partido.temporada:
        todos_jugadores = jugadores_local + jugadores_visit
        jug_ids = [j.id for j in todos_jugadores]

        def _esta_suspendido(jugador_id, partido_actual):
            """Verifica si un jugador está suspendido para el partido actual."""
            rojas = Tarjeta.objects.filter(
                jugador_id=jugador_id,
                tipo="ROJA", suspension_jornadas__gt=0,
                partido__temporada=partido_actual.temporada,
                partido__fecha_hora__lt=partido_actual.fecha_hora,
            )
            for r in rojas:
                prox = Partido.objects.filter(
                    temporada=partido_actual.temporada,
                    jornada__numero__gte=r.partido.jornada.numero,
                    fecha_hora__gt=r.partido.fecha_hora,
                ).filter(
                    Q(equipo_local=r.equipo) | Q(equipo_visitante=r.equipo)
                ).exclude(id=r.partido.id).order_by("jornada__numero", "fecha_hora", "id")[:r.suspension_jornadas]
                for p in prox:
                    if p.id == partido_actual.id:
                        return True
            return False

        for j in todos_jugadores:
            if _esta_suspendido(j.id, partido):
                j.esta_suspendido = True
                j.jornadas_pendientes = 1

        # Cruce de temporada: revisar temporada anterior
        temp_anterior = Temporada.objects.filter(
            categoria=partido.temporada.categoria,
            fecha_inicio__lt=partido.temporada.fecha_inicio,
        ).order_by("-fecha_inicio").first()
        if temp_anterior:
            for j in todos_jugadores:
                if j.esta_suspendido:
                    continue
                rojas_prev = Tarjeta.objects.filter(
                    jugador_id=j.id,
                    tipo="ROJA", suspension_jornadas__gt=0,
                    partido__temporada=temp_anterior,
                )
                for r in rojas_prev:
                    prox = Partido.objects.filter(
                        temporada=temp_anterior,
                        jornada__numero__gte=r.partido.jornada.numero,
                        fecha_hora__gt=r.partido.fecha_hora,
                    ).filter(
                        Q(equipo_local=r.equipo) | Q(equipo_visitante=r.equipo)
                    ).exclude(id=r.partido.id).order_by("jornada__numero", "fecha_hora", "id")[:r.suspension_jornadas]
                    prox_list = list(prox)
                    pend_prev = [p for p in prox_list if p.estado != 'FIN']
                    if pend_prev:
                        # Suspensión cruza a esta temporada, buscar el partido actual
                        prox_nueva = Partido.objects.filter(
                            temporada=partido.temporada,
                            estado__in=("PRO", "PROG"),
                        ).filter(
                            Q(equipo_local=j.equipo) | Q(equipo_visitante=j.equipo)
                        ).order_by("fecha_hora", "id")[:len(pend_prev)]
                        for p in prox_nueva:
                            if p.id == partido.id:
                                j.esta_suspendido = True
                                j.jornadas_pendientes = 1
                                break
                    if j.esta_suspendido:
                        break

    # Verificar elegibilidad para liguilla según % mínimo de juegos
    if partido.es_liguilla and partido.temporada.min_porcentaje_liguilla:
        min_pct = partido.temporada.min_porcentaje_liguilla
        total_reg = Partido.objects.filter(temporada=partido.temporada, es_liguilla=False).count()
        if total_reg > 0:
            todos_jugadores = jugadores_local + jugadores_visit
            for j in todos_jugadores:
                jugados = JugadorPartido.objects.filter(
                    jugador=j, partido__temporada=partido.temporada, partido__es_liguilla=False
                ).count()
                pct = (jugados / total_reg) * 100
                j.elegible_liguilla = pct >= min_pct
        else:
            for j in jugadores_local + jugadores_visit:
                j.elegible_liguilla = True
    else:
        for j in jugadores_local + jugadores_visit:
            j.elegible_liguilla = True

    return render(request, "league/cedula_arbitral.html" if not es_invitado else "league/cedula_invitado.html", {
        "partido": partido,
        "jugadores_local": jugadores_local,
        "jugadores_visit": jugadores_visit,
        "arbitros": arbitros_list,
        "es_invitado": es_invitado,
    })


def tabla_tarjetas(request):
    cat_id = request.GET.get("categoria")
    temp_id = request.GET.get("temporada")
    jornada_id = request.GET.get("jornada")
    categorias = Categoria.objects.filter(activo=True)
    qs_temp = Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")
    if cat_id:
        qs_temp = qs_temp.filter(categoria_id=cat_id)
    else:
        default_cat = Categoria.objects.filter(es_principal=True).first()
        if default_cat:
            qs_temp = qs_temp.filter(categoria=default_cat)
    temporadas = qs_temp

    if not temp_id and temporadas.exists():
        temp_id = temporadas.first().id

    jornadas = []
    if temp_id:
        jornadas = Jornada.objects.filter(temporada_id=temp_id).order_by("numero")

    amarillas = []
    rojas = []

    if temp_id:
        qs_amarillas = Tarjeta.objects.filter(partido__temporada_id=temp_id, tipo="AMARILLA")
        qs_rojas = Tarjeta.objects.filter(partido__temporada_id=temp_id, tipo="ROJA")
        if jornada_id:
            qs_amarillas = qs_amarillas.filter(partido__jornada_id=jornada_id)
            qs_rojas = qs_rojas.filter(partido__jornada_id=jornada_id)
        amarillas = (
            qs_amarillas
            .values(
                "jugador__id", "jugador__nombre", "jugador__apellido",
                "jugador__foto", "jugador__dorsal",
                "equipo__id", "equipo__nombre", "equipo__logo",
            )
            .annotate(total=Count("id"))
            .order_by("-total")
        )
        rojas = (
            qs_rojas
            .values(
                "jugador__id", "jugador__nombre", "jugador__apellido",
                "jugador__foto", "jugador__dorsal",
                "equipo__id", "equipo__nombre", "equipo__logo",
            )
            .annotate(total=Count("id"))
            .order_by("-total")
        )

    return render(request, "league/tabla_tarjetas.html", {
        "amarillas": amarillas,
        "rojas": rojas,
        "categorias": categorias,
        "cat_id": int(cat_id) if cat_id else None,
        "temporadas": temporadas,
        "temp_id": int(temp_id) if temp_id else None,
        "jornadas": jornadas,
        "jornada_id": int(jornada_id) if jornada_id else None,
    })


def tabla_castigados(request):
    cat_id = request.GET.get("categoria")
    temp_id = request.GET.get("temporada")
    jornada_id = request.GET.get("jornada")
    categorias = Categoria.objects.filter(activo=True)
    qs_temp = Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")
    if cat_id:
        qs_temp = qs_temp.filter(categoria_id=cat_id)
    else:
        default_cat = Categoria.objects.filter(es_principal=True).first()
        if default_cat:
            qs_temp = qs_temp.filter(categoria=default_cat)
    temporadas = qs_temp

    if not temp_id and temporadas.exists():
        temp_id = temporadas.first().id

    jornadas = []
    if temp_id:
        jornadas = Jornada.objects.filter(temporada_id=temp_id).order_by("numero")

    castigados = []
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)

        # Suspensiones activas de esta temporada (basado en próximos N partidos)
        susp = _suspensiones_temporada(temp)
        processed = set()

        if jornada_id:
            # Filtrar solo las que expulsaron en la jornada específica
            # (las manuales aplican desde el inicio de la temporada)
            susp = {
                k: v for k, v in susp.items()
                if v.get("es_manual")
                or (v["_tarjeta"].partido and v["_tarjeta"].partido.jornada_id == int(jornada_id))
            }

        for jug_id, info in susp.items():
            if info["restantes"] > 0:
                r = info["_tarjeta"]
                r.pendientes = info["pendientes"]
                r.restantes = info["restantes"]
                r.expulsion_partido = info["expulsion_partido"]
                castigados.append(r)
                processed.add(jug_id)

        # Arrastrar suspensiones activas de la temporada anterior
        temp_anterior = Temporada.objects.filter(
            categoria=temp.categoria,
            fecha_inicio__lt=temp.fecha_inicio,
        ).order_by("-fecha_inicio").first()
        if temp_anterior and not jornada_id:
            prev = _suspensiones_temporada(temp_anterior)
            for jug_id, info in prev.items():
                if jug_id in processed or info["restantes"] == 0:
                    continue
                jug = info["_tarjeta"].jugador
                prox = Partido.objects.filter(
                    temporada=temp,
                    estado__in=("PRO", "PROG"),
                ).filter(
                    Q(equipo_local=jug.equipo) | Q(equipo_visitante=jug.equipo)
                ).order_by("fecha_hora", "id")[:info["restantes"]]
                pendientes = list(prox)
                if pendientes:
                    r = info["_tarjeta"]
                    r.pendientes = pendientes
                    r.restantes = len(pendientes)
                    r.expulsion_partido = info["expulsion_partido"]
                    castigados.append(r)

    return render(request, "league/tabla_castigados.html", {
        "castigados": castigados,
        "categorias": categorias,
        "cat_id": int(cat_id) if cat_id else None,
        "temporadas": temporadas,
        "temp_id": int(temp_id) if temp_id else None,
        "jornadas": jornadas,
        "jornada_id": int(jornada_id) if jornada_id else None,
    })


def temporada_suspensiones(request, temporada_pk):
    """Suspensiones manuales del administrador: buscar/crear jugador, suspender, listar, levantar."""
    temporada = get_object_or_404(Temporada, pk=temporada_pk)
    categoria = temporada.categoria
    equipos_categoria = Equipo.objects.filter(categoria=categoria, activo=True).order_by("nombre")
    resultados = []
    q = request.GET.get("q", "").strip()
    error = None

    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "suspender":
                jugador_id = request.POST.get("jugador_id")
                equipo_id = request.POST.get("equipo_id")
                jornadas = int(request.POST.get("jornadas") or 0)
                motivo = request.POST.get("motivo", "").strip()
                jugador = Jugador.objects.filter(id=jugador_id).first()
                if not jugador:
                    error = "Jugador no encontrado."
                elif not equipo_id or not Equipo.objects.filter(id=equipo_id, categoria=categoria).exists():
                    error = "Selecciona un equipo válido de la categoría."
                elif jornadas <= 0:
                    error = "El número de jornadas debe ser mayor a cero."
                else:
                    SuspensionJugador.objects.create(
                        jugador=jugador,
                        categoria=categoria,
                        equipo_id=equipo_id,
                        temporada=temporada,
                        jornadas=jornadas,
                        motivo=motivo,
                        fecha_inicio=datetime.date.today(),
                    )
                    messages.success(request, f"Suspensión registrada para {jugador}.")
            elif accion == "crear_suspender":
                nombre = request.POST.get("nombre", "").strip()
                apellido = request.POST.get("apellido", "").strip()
                equipo_id = request.POST.get("equipo_id")
                posicion = request.POST.get("posicion", "DEL")
                dorsal_raw = request.POST.get("dorsal", "").strip()
                jornadas = int(request.POST.get("jornadas") or 0)
                motivo = request.POST.get("motivo", "").strip()
                if not nombre or not apellido:
                    error = "Nombre y apellido son obligatorios."
                elif not equipo_id or not Equipo.objects.filter(id=equipo_id, categoria=categoria).exists():
                    error = "Selecciona un equipo válido de la categoría."
                elif jornadas <= 0:
                    error = "El número de jornadas debe ser mayor a cero."
                else:
                    j = Jugador.objects.create(
                        nombre=nombre,
                        apellido=apellido,
                        equipo_id=equipo_id,
                        posicion=posicion,
                        dorsal=int(dorsal_raw) if dorsal_raw.isdigit() else None,
                    )
                    SuspensionJugador.objects.create(
                        jugador=j,
                        categoria=categoria,
                        equipo_id=equipo_id,
                        temporada=temporada,
                        jornadas=jornadas,
                        motivo=motivo,
                        fecha_inicio=datetime.date.today(),
                    )
                    messages.success(request, f"Jugador {j} creado y suspendido.")
        except Exception as e:
            error = str(e)
        if not error:
            return redirect("temporada_suspensiones", temporada_pk=temporada.id)

    if q:
        tokens = [t for t in q.split() if t]
        resultados = Jugador.objects.filter(activo=True).select_related("equipo__categoria", "equipo")
        if len(tokens) >= 2:
            resultados = resultados.filter(
                Q(nombre__icontains=tokens[0]) & Q(apellido__icontains=" ".join(tokens[1:]))
            )
        else:
            resultados = resultados.filter(
                Q(nombre__icontains=tokens[0]) | Q(apellido__icontains=tokens[0])
            )
        resultados = resultados.order_by("apellido", "nombre")[:30]

    suspensiones = (
        SuspensionJugador.objects.filter(categoria=categoria)
        .select_related("jugador", "equipo", "temporada")
        .order_by("-activo", "-creado")[:100]
    )
    lista_suspensiones = []
    for s in suspensiones:
        rest = s.restantes()
        lista_suspensiones.append({
            "id": s.id,
            "jugador": s.jugador,
            "equipo": s.equipo,
            "temporada": s.temporada,
            "jornadas": s.jornadas,
            "restantes": rest,
            "motivo": s.motivo,
            "activo": s.activo,
            "vetado": s.vigente() and s.activo,
            "fecha_inicio": s.fecha_inicio,
        })

    return render(request, "league/temporada_suspensiones.html", {
        "temporada": temporada,
        "categoria": categoria,
        "equipos": equipos_categoria,
        "q": q,
        "resultados": resultados,
        "suspensiones": lista_suspensiones,
        "error": error,
    })


def levantar_suspension(request, pk):
    s = get_object_or_404(SuspensionJugador, pk=pk)
    temporada_pk = s.temporada_id
    s.activo = False
    s.save(update_fields=["activo"])
    messages.success(request, f"Suspensión de {s.jugador} levantada.")
    if temporada_pk:
        return redirect("temporada_suspensiones", temporada_pk=temporada_pk)
    return redirect("tabla_castigados")


from django.http import JsonResponse
def api_equipos_categoria(request):
    """API: retorna categorías compatibles con equipos para un equipo dado."""
    equipo_id = request.GET.get("equipo_id")
    if not equipo_id:
        return JsonResponse({"error": "equipo_id requerido"}, status=400)
    try:
        eq = Equipo.objects.get(id=equipo_id)
    except Equipo.DoesNotExist:
        return JsonResponse({"error": "Equipo no encontrado"}, status=404)
    cat = eq.categoria
    from .forms import _get_allowed_secondary_categories
    jugador = None
    jugador_id = request.GET.get("jugador_id")
    if jugador_id:
        try:
            jugador = Jugador.objects.get(id=jugador_id)
        except Jugador.DoesNotExist:
            pass
    allowed = _get_allowed_secondary_categories(eq)

    # Build compatibility maps for frontend validation
    all_cats = list(Categoria.objects.prefetch_related("categorias_compatibles").all())
    forward_map = {}
    reverse_map = {}
    for c in all_cats:
        fwd = list(c.categorias_compatibles.values_list("id", flat=True))
        forward_map[str(c.id)] = fwd
        for compat_id in fwd:
            reverse_map.setdefault(str(compat_id), []).append(c.id)
    # Ensure every category appears
    for c in all_cats:
        if str(c.id) not in reverse_map:
            reverse_map[str(c.id)] = []
    # Also include the main category
    if str(cat.id) not in forward_map:
        forward_map[str(cat.id)] = list(cat.categorias_compatibles.values_list("id", flat=True))
    if str(cat.id) not in reverse_map:
        reverse_map[str(cat.id)] = []

    compatibles = []
    for acat in allowed:
        equipos = list(Equipo.objects.filter(categoria=acat, activo=True).values("id", "nombre"))
        compatibles.append({
            "id": acat.id,
            "nombre": acat.nombre,
            "equipos": equipos,
        })

    registros = {}
    if jugador:
        for r in jugador.registros_equipo.filter(es_principal=False).select_related("equipo"):
            registros[str(r.equipo.categoria_id)] = r.equipo_id

    # Categorías con temporada en curso (no se puede cambiar equipo)
    from .models import Temporada as Tmp
    temps_activas = set(
        Tmp.objects.filter(iniciada=True, finalizada=False)
        .values_list("categoria_id", flat=True)
    )
    # Periodos de altas activos por categoría
    periodos = {}
    for tid in temps_activas:
        t = Tmp.objects.filter(categoria_id=tid, iniciada=True, finalizada=False).first()
        if t:
            periodos[str(tid)] = t.periodos_altas.filter(activo=True).exists()
        else:
            periodos[str(tid)] = False

    # Jugador ha jugado partidos por categoría (para saber si puede cambiar)
    ha_jugado = {}
    if jugador:
        from .models import JugadorPartido
        for tid in temps_activas:
            equipos_en_cat = Equipo.objects.filter(categoria_id=tid)
            ha_jugado[str(tid)] = JugadorPartido.objects.filter(
                jugador=jugador, equipo__in=equipos_en_cat
            ).exists()
    else:
        for tid in temps_activas:
            ha_jugado[str(tid)] = False

    return JsonResponse({
        "categoria_actual": cat.id,
        "categoria_nombre": cat.nombre,
        "compatibles": compatibles,
        "registros": registros,
        "forward_map": forward_map,
        "reverse_map": reverse_map,
        "temporadas_activas": list(temps_activas),
        "periodos_abiertos": periodos,
        "ha_jugado": ha_jugado,
    })


def reagendar_partido(request, pk):
    partido = get_object_or_404(Partido, pk=pk)
    if partido.estado not in ["PEND", "SUSP"]:
        messages.warning(request, "Solo se pueden reagendar partidos Pendientes o Suspendidos.")
        return redirect("partido_list")

    from django.utils.timezone import is_aware, make_aware, localtime

    class ReagendarForm(forms.Form):
        campo = forms.ModelChoiceField(queryset=Campo.objects.filter(activo=True), label="Campo")
        fecha = forms.DateField(
            label="Fecha",
            widget=forms.DateInput(attrs={"type": "date", "class": "form-control"})
        )
        hora = forms.TimeField(
            label="Hora",
            widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "HH:MM"}),
            input_formats=["%H:%M", "%H:%M:%S"],
        )

    if request.method == "POST":
        form = ReagendarForm(request.POST)
        if form.is_valid():
            partido.campo = form.cleaned_data["campo"]
            fecha = form.cleaned_data["fecha"]
            hora = form.cleaned_data["hora"]
            dt = datetime.datetime.combine(fecha, hora)
            partido.fecha_hora = make_aware(dt) if not is_aware(dt) else dt
            partido.estado = "PEND"
            partido.save()
            if partido.temporada_id:
                partido.temporada.actualizar_fecha_fin()
            # Avisar a invitados (push + correo) de que el partido quedó pendiente
            try:
                _notificar_partido_pendiente(request, partido)
            except Exception as e:
                logger.warning("Error notificando partido pendiente: %s", e)
            messages.success(request, f"Partido reagendado correctamente.")
            return redirect("partido_list")
    else:
        fh = partido.fecha_hora
        if fh:
            local = localtime(fh) if is_aware(fh) else fh
            initial_fecha = local.date()
            initial_hora = local.time()
        else:
            initial_fecha = None
            initial_hora = None
        form = ReagendarForm(initial={
            "campo": partido.campo,
            "fecha": initial_fecha,
            "hora": initial_hora,
        })

    return render(request, "league/partido_reagendar.html", {
        "form": form,
        "partido": partido,
    })


def reporte_semanal(request):
    hoy = datetime.date.today()
    lunes = hoy - datetime.timedelta(days=hoy.weekday())
    domingo = lunes + datetime.timedelta(days=6)
    inicio = request.GET.get("inicio") or lunes.isoformat()
    fin = request.GET.get("fin") or domingo.isoformat()
    try:
        fecha_inicio = datetime.date.fromisoformat(inicio)
        fecha_fin = datetime.date.fromisoformat(fin)
    except ValueError:
        fecha_inicio = lunes
        fecha_fin = domingo

    cat_id = request.GET.get("categoria")
    temp_id = request.GET.get("temporada")
    categorias = Categoria.objects.filter(activo=True)
    temporadas = Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")

    data = []
    if temp_id:
        temp = get_object_or_404(Temporada, id=temp_id)
        cat = temp.categoria
        partidos = Partido.objects.filter(
            temporada=temp,
            fecha_hora__date__gte=fecha_inicio,
            fecha_hora__date__lte=fecha_fin,
        ).select_related("jornada", "equipo_local", "equipo_visitante", "campo"
        ).order_by("fecha_hora")
        if partidos.exists():
            data.append({"categoria": cat, "partidos": partidos})
    elif cat_id:
        cat = get_object_or_404(Categoria, id=cat_id)
        partidos = Partido.objects.filter(
            equipo_local__categoria=cat,
            temporada__finalizada=False,
            fecha_hora__date__gte=fecha_inicio,
            fecha_hora__date__lte=fecha_fin,
        ).select_related("jornada", "equipo_local", "equipo_visitante", "campo"
        ).order_by("fecha_hora")
        if partidos.exists():
            data.append({"categoria": cat, "partidos": partidos})
    else:
        from django.db.models import Prefetch
        cats = Categoria.objects.filter(activo=True).prefetch_related(
            Prefetch("equipos", queryset=Equipo.objects.filter(activo=True), to_attr="equipos_activos")
        )
        for cat in cats:
            partidos = Partido.objects.filter(
                equipo_local__categoria=cat,
                temporada__finalizada=False,
                fecha_hora__date__gte=fecha_inicio,
                fecha_hora__date__lte=fecha_fin,
            ).select_related("jornada", "equipo_local", "equipo_visitante", "campo"
            ).order_by("fecha_hora")
            if partidos.exists():
                data.append({"categoria": cat, "partidos": partidos})

    return render(request, "league/reporte_semanal.html", {
        "data": data,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "categorias": categorias,
        "temporadas": temporadas,
        "cat_id": int(cat_id) if cat_id else None,
        "temp_id": int(temp_id) if temp_id else None,
    })


def reiniciar_temporada(request, pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    if not temporada.iniciada:
        messages.warning(request, "La temporada no está iniciada.")
    else:
        Partido.objects.filter(temporada=temporada).delete()
        Jornada.objects.filter(temporada=temporada).delete()
        temporada.iniciada = False
        temporada.save()
        messages.success(request, f"Temporada '{temporada.nombre}' reiniciada. Puedes volver a iniciarla.")
    return redirect("temporada_list")


def guardar_observaciones(request, pk):
    partido = get_object_or_404(Partido, pk=pk)
    if request.method == "POST":
        if partido.estado == "FIN" and not request.user.tiene_permiso("partido_aperturar"):
            messages.error(request, "No tienes permiso para modificar un partido finalizado.")
            return redirect("partido_list")
        partido.observaciones = request.POST.get("observaciones", "")
        partido.save()
        messages.success(request, "Observaciones guardadas.")
    return redirect("partido_list")


def temporada_equipos(request, pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    equipos = temporada.equipos_habilitados()
    pagados = temporada.equipos_pagados()
    info_equipos = []
    for eq in equipos:
        info_equipos.append({
            "equipo": eq,
            "pagado": eq in pagados,
            "en_mora": temporada.equipo_en_mora(eq),
            "abandono": temporada.equipo_abandono(eq),
        })
    context = {
        "temporada": temporada,
        "info_equipos": info_equipos,
    }
    return render(request, "league/temporada_equipos.html", context)


def marcar_abandono(request, pk, equipo_pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    equipo = get_object_or_404(Equipo, pk=equipo_pk)
    from league.models import AbandonoTemporada
    AbandonoTemporada.objects.get_or_create(temporada=temporada, equipo=equipo)
    messages.success(request, f"{equipo.nombre} marcado como abandonó la temporada.")
    return redirect("temporada_equipos", pk=pk)


def desmarcar_abandono(request, pk, equipo_pk):
    temporada = get_object_or_404(Temporada, pk=pk)
    equipo = get_object_or_404(Equipo, pk=equipo_pk)
    from league.models import AbandonoTemporada
    AbandonoTemporada.objects.filter(temporada=temporada, equipo=equipo).delete()
    messages.success(request, f"{equipo.nombre} reincorporado a la temporada.")
    return redirect("temporada_equipos", pk=pk)


def gestionar_indisponibilidad(request):
    from django import forms as djforms

    class IndispoForm(djforms.Form):
        campo = djforms.ModelChoiceField(
            queryset=Campo.objects.filter(activo=True), label="Campo",
            widget=djforms.Select(attrs={"class": "form-select"})
        )
        fecha_desde = djforms.DateField(
            label="Desde", widget=djforms.DateInput(attrs={"type": "date", "class": "form-control"})
        )
        fecha_hasta = djforms.DateField(
            label="Hasta", widget=djforms.DateInput(attrs={"type": "date", "class": "form-control"})
        )
        motivo = djforms.CharField(
            required=False, label="Motivo",
            widget=djforms.Textarea(attrs={"class": "form-control", "rows": 2})
        )

    campos = Campo.objects.filter(activo=True)
    afectados = None
    indisp = None

    if request.method == "POST":
        if "eliminar_indisponibilidad" in request.POST:
            indisp_id = request.POST.get("indisp_id")
            indisp = get_object_or_404(CampoIndisponibilidad, pk=indisp_id)
            indisp.delete()
            messages.success(request, "Indisponibilidad eliminada.")
            return redirect("gestionar_indisponibilidad")
        elif "guardar_indisponibilidad" in request.POST:
            form = IndispoForm(request.POST)
            if form.is_valid():
                indisp = CampoIndisponibilidad.objects.create(
                    campo=form.cleaned_data["campo"],
                    fecha_desde=form.cleaned_data["fecha_desde"],
                    fecha_hasta=form.cleaned_data["fecha_hasta"],
                    motivo=form.cleaned_data.get("motivo", ""),
                )
                messages.success(request, f"Indisponibilidad creada para {indisp.campo.nombre}.")
                return redirect(f"{reverse('gestionar_indisponibilidad')}?indisp={indisp.pk}")
        elif "reasignar" in request.POST:
            indisp_id = request.POST.get("indisp_id")
            indisp = get_object_or_404(CampoIndisponibilidad, pk=indisp_id)
            partidos_afectados = Partido.objects.filter(
                campo=indisp.campo,
                fecha_hora__date__gte=indisp.fecha_desde,
                fecha_hora__date__lte=indisp.fecha_hasta,
            )
            cambios = 0
            for p in partidos_afectados:
                nuevo_campo_id = request.POST.get(f"nuevo_campo_{p.pk}")
                nueva_fecha = request.POST.get(f"nueva_fecha_{p.pk}")
                nueva_hora = request.POST.get(f"nueva_hora_{p.pk}")
                if nuevo_campo_id:
                    p.campo_id = int(nuevo_campo_id)
                if nueva_fecha and nueva_hora:
                    import datetime
                    dt = datetime.datetime.strptime(f"{nueva_fecha} {nueva_hora}", "%Y-%m-%d %H:%M")
                    from django.utils.timezone import make_aware
                    p.fecha_hora = make_aware(dt)
                p.save()
                cambios += 1
            messages.success(request, f"{cambios} partidos reasignados correctamente.")
            return redirect("partido_list")

        indisp_id = request.POST.get("indisp_id")
    else:
        form = IndispoForm()
        indisp_id = request.GET.get("indisp")

    if indisp_id:
        indisp = get_object_or_404(CampoIndisponibilidad, pk=indisp_id)
        afectados = Partido.objects.filter(
            campo=indisp.campo,
            fecha_hora__date__gte=indisp.fecha_desde,
            fecha_hora__date__lte=indisp.fecha_hasta,
        ).select_related("equipo_local", "equipo_visitante", "jornada")

    return render(request, "league/gestionar_indisponibilidad.html", {
        "form": form,
        "campos": campos,
        "afectados": afectados,
        "indisp": indisp,
        "indisponibilidades": CampoIndisponibilidad.objects.select_related("campo").all()[:20],
    })


def publicar_rol_facebook(request, temporada_id):
    from django.utils import timezone
    temporada = get_object_or_404(Temporada, pk=temporada_id)
    ahora = timezone.localtime()
    ahora_str = ahora.strftime("%d/%m/%Y %H:%M")
    jornadas_qs = Jornada.objects.filter(temporada=temporada).order_by("numero")

    jornadas_data = []
    for j in jornadas_qs:
        partidos_qs = Partido.objects.filter(jornada=j).select_related(
            "equipo_local", "equipo_visitante", "campo"
        ).order_by("fecha_hora")
        if not partidos_qs:
            continue
        partidos_data = []
        for p in partidos_qs:
            d = {
                "local": p.equipo_local.nombre,
                "visitante": p.equipo_visitante.nombre,
                "campo": p.campo.nombre if p.campo else "",
                "fecha": timezone.localtime(p.fecha_hora).strftime("%d/%m %H:%M") if p.fecha_hora else "Pendiente",
                "is_fin": p.estado == "FIN",
                "susp": p.estado == "SUSP",
            }
            if p.estado == "FIN":
                gl, gv = p.goles_local, p.goles_visitante
                d["marcador"] = f"{gl}\u2013{gv}"
                d["local_win"] = gl > gv
                d["vis_win"] = gv > gl
            else:
                d["marcador"] = "vs"
                d["local_win"] = False
                d["vis_win"] = False
            partidos_data.append(d)
        jornadas_data.append({
            "nombre": j.nombre,
            "partidos": partidos_data,
            "descansan": [eq.nombre for eq in temporada.equipos_descansan(j)],
        })

    from .social_image import generar_imagen_rol
    from .social import publicar_imagen_en_facebook
    imagen = generar_imagen_rol(temporada.nombre, jornadas_data, ahora_str)
    caption = f"\U0001f4cb Rol de Juegos - {temporada.nombre}\n#FutbolLiga"
    publicar_imagen_en_facebook(imagen, caption, request)
    return redirect(request.META.get("HTTP_REFERER", "home"))


def publicar_posiciones_facebook(request, temporada_id):
    from django.utils import timezone
    temporada = get_object_or_404(Temporada, pk=temporada_id)
    ahora = timezone.localtime()
    ahora_str = ahora.strftime("%d/%m/%Y %H:%M")

    grupos_mode = temporada.tipo_rol == "GRUPOS" and temporada.clasificacion_por_grupos
    if grupos_mode:
        tablas_por_grupo = temporada.calcular_tablas_por_grupo()
        grupos = temporada.grupos_asignados()
        ng = len(grupos)
        por_grupo = max(1, temporada.num_clasificados // max(ng, 1)) if ng else 0
        tabla = []
    else:
        tabla = temporada.calcular_tabla()
        tablas_por_grupo = None
        por_grupo = 0

    from .social_image import generar_imagen_posiciones
    from .social import publicar_imagen_en_facebook
    imagen = generar_imagen_posiciones(
        temporada.nombre, tabla, ahora_str, temporada.num_clasificados,
        tablas_por_grupo=tablas_por_grupo, por_grupo=por_grupo,
    )
    caption = f"\U0001f3c6 Tabla de Posiciones - {temporada.nombre}\n#FutbolLiga"
    publicar_imagen_en_facebook(imagen, caption, request)
    return redirect(request.META.get("HTTP_REFERER", "home"))


def publicar_jornada_facebook(request, jornada_id):
    from django.utils import timezone
    jornada = get_object_or_404(Jornada.objects.select_related("temporada"), pk=jornada_id)
    temporada = jornada.temporada
    ahora = timezone.localtime()
    ahora_str = ahora.strftime("%d/%m/%Y %H:%M")

    partidos_data = []
    partidos_qs = Partido.objects.filter(jornada=jornada).select_related(
        "equipo_local", "equipo_visitante", "campo"
    ).order_by("fecha_hora")
    for p in partidos_qs:
        d = {
            "local": p.equipo_local.nombre,
            "visitante": p.equipo_visitante.nombre,
            "campo": p.campo.nombre if p.campo else "",
            "fecha": timezone.localtime(p.fecha_hora).strftime("%d/%m %H:%M") if p.fecha_hora else "",
            "is_fin": p.estado == "FIN",
            "susp": p.estado == "SUSP",
        }
        if p.estado == "FIN":
            gl, gv = p.goles_local, p.goles_visitante
            d["marcador"] = f"{gl}\u2013{gv}"
            d["local_win"] = gl > gv
            d["vis_win"] = gv > gl
        else:
            d["marcador"] = "vs"
            d["local_win"] = False
            d["vis_win"] = False
        partidos_data.append(d)

    grupos_mode = temporada.tipo_rol == "GRUPOS" and temporada.clasificacion_por_grupos
    if grupos_mode:
        tablas_por_grupo = temporada.calcular_tablas_por_grupo(jornada_numero=jornada.numero)
        grupos = temporada.grupos_asignados()
        ng = len(grupos)
        por_grupo = max(1, temporada.num_clasificados // max(ng, 1)) if ng else 0
        tabla = []
    else:
        tabla = _tabla_hasta_jornada(temporada, jornada.numero)
        tablas_por_grupo = None
        por_grupo = 0

    castigados_data = []
    for c in _castigados_hasta_jornada(temporada, jornada.numero):
        castigados_data.append({
            "jugador": f"{c.jugador.nombre} {c.jugador.apellido}",
            "equipo": c.equipo.nombre,
            "jornada_expulsion": c.jornada_expulsion,
            "restantes": c.restantes,
        })

    from .social_image import generar_imagen_rol, generar_imagen_posiciones, generar_imagen_castigados
    from .social import publicar_varias_imagenes_en_facebook

    imagenes = []

    # Imagen 1: Partidos
    img_partidos = generar_imagen_rol(
        temporada.nombre,
        [{
            "nombre": f"Jornada {jornada.numero}",
            "partidos": partidos_data,
            "descansan": [eq.nombre for eq in temporada.equipos_descansan(jornada)],
        }],
        ahora_str,
    )
    imagenes.append((img_partidos, ""))

    # Imagen 2: Tabla de posiciones (solo si hay equipos)
    tiene_tabla = bool(tabla) or bool(tablas_por_grupo)
    if tiene_tabla:
        img_tabla = generar_imagen_posiciones(
            temporada.nombre, tabla, ahora_str, temporada.num_clasificados,
            tablas_por_grupo=tablas_por_grupo, por_grupo=por_grupo,
        )
        imagenes.append((img_tabla, ""))

    # Imagen 3: Castigados (solo si hay)
    if castigados_data:
        img_castigados = generar_imagen_castigados(
            temporada.nombre, jornada.numero, castigados_data, ahora_str,
        )
        imagenes.append((img_castigados, ""))

    caption = (
        f"\u26bd Jornada {jornada.numero} - {temporada.nombre}\n"
        f"\n#FutbolLiga #Jornada{jornada.numero}"
    )
    if len(imagenes) == 1:
        from .social import publicar_imagen_en_facebook
        publicar_imagen_en_facebook(imagenes[0][0], caption, request)
    else:
        publicar_varias_imagenes_en_facebook(
            [(img, "") for img, _ in imagenes],
            request,
            mensaje=caption,
        )
    return redirect(request.META.get("HTTP_REFERER", "home"))


def publicar_campeon_view(request, pk):
    """Anuncia al campeon de la liguilla: genera imagen, publica en Facebook y envia correos."""
    if not request.user.is_authenticated or not (request.user.rol and request.user.rol.permisos.get("gestion_partidos", False)):
        messages.error(request, "No tienes permiso para publicar el campeon.")
        return redirect("home")
    temporada = get_object_or_404(Temporada, pk=pk)
    estado = temporada.estado_liguilla()
    if estado != "completada":
        messages.error(request, "La liguilla aun no esta completa. No hay campeon que anunciar.")
        return redirect("temporada_list")
    campeon = temporada.obtener_campeon()
    if not campeon:
        messages.error(request, "No se pudo determinar el campeon.")
        return redirect("temporada_list")

    ahora = datetime.datetime.now()
    ahora_str = ahora.strftime("%d/%m/%Y %H:%M")
    logo_path = None
    if campeon.logo:
        try:
            logo_path = campeon.logo.path
        except NotImplementedError:
            import requests as _req
            try:
                r = _req.get(campeon.logo.url, timeout=10)
                if r.status_code == 200:
                    import tempfile
                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                    tmp.write(r.content)
                    tmp.close()
                    logo_path = tmp.name
            except Exception:
                pass

    from .social_image import generar_imagen_campeon
    from .social import publicar_imagen_en_facebook
    categoria_nombre = temporada.categoria.nombre
    imagen = generar_imagen_campeon(temporada.nombre, campeon.nombre, logo_path, ahora_str, categoria_nombre)
    caption = (
        f"\U0001f3c6 \U0001f451 CAMPEON \U0001f451 \U0001f3c6\n\n"
        f"{campeon.nombre.upper()} se corona campeon de {temporada.nombre} ({categoria_nombre})!\n\n"
        f"#FutbolLiga #Campeon"
    )
    publicar_imagen_en_facebook(imagen, caption, request)

    config = ConfiguracionLiga.obtener()
    if config.email_smtp_host:
        from .models import SuscripcionEmail
        suscriptores = SuscripcionEmail.objects.filter(activo=True, recibir_roles=True)
        count = 0
        for sus in suscriptores:
            cats = sus.categorias.all()
            if cats and not cats.filter(id=temporada.categoria_id).exists():
                continue
            ctx = {
                "temporada": temporada,
                "campeon": campeon,
                "categoria": temporada.categoria,
                "ahora_str": ahora_str,
            }
            count += _enviar_correo_suscriptores(
                [sus], config, f"\U0001f3c6 \U0001f451 Campeon - {temporada.nombre}",
                "emails/campeon.html", ctx, request
            )
        messages.success(request, f"Campeon anunciado a {count} suscriptores.")
    else:
        messages.success(request, "Campeon publicado en Facebook (correo no configurado).")

    return redirect("temporada_list")


# ============ MODO OFFLINE (APP ANDROID) ============

@login_required
def modo_offline(request):
    from django.utils import timezone as tz
    from datetime import timedelta
    import secrets
    from league.models import OfflineToken

    if not request.user.es_arbitro:
        messages.error(request, "El modo offline solo está disponible para árbitros.")
        return redirect("index")

    if request.method == "POST" and request.POST.get("revocar") == "1":
        OfflineToken.objects.filter(usuario=request.user, activo=True).update(activo=False)
        messages.success(request, "Modo offline desactivado. Genera un nuevo token cuando lo necesites.")
        return redirect("modo_offline")

    token = (OfflineToken.objects.filter(usuario=request.user, activo=True)
             .order_by("-creado").first())
    if token is None or token.expira <= tz.now():
        if token is not None:
            token.activo = False
            token.save()
        token = OfflineToken.objects.create(
            usuario=request.user,
            token=secrets.token_urlsafe(32),
            expira=tz.now() + timedelta(days=180),
        )
    return render(request, "league/modo_offline.html", {"token": token})


def _get_offline_user(request):
    from league.models import OfflineToken
    from django.utils import timezone as tz
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    t = OfflineToken.objects.filter(token=auth[7:].strip(), activo=True, expira__gt=tz.now()).first()
    return t.usuario if t else None


@csrf_exempt
def api_offline_datos(request):
    from django.http import JsonResponse
    user = _get_offline_user(request)
    if user is None:
        return JsonResponse({"ok": False, "error": "Token inválido o expirado."}, status=401)
    if not user.es_arbitro:
        return JsonResponse({"ok": False, "error": "El modo offline solo es para árbitros."}, status=403)

    partidos = Partido.objects.filter(estado__in=["PEND", "JUG"], arbitro__usuario=user).select_related(
        "equipo_local", "equipo_visitante", "campo", "temporada", "arbitro"
    )

    arbitros = list(Arbitro.objects.filter(activo=True).values("id", "nombre", "apellido"))

    def jugadores_dto(equipo):
        return [
            {"id": j.id, "nombre": j.nombre, "apellido": j.apellido, "dorsal": j.dorsal}
            for j in Jugador.objects.filter(equipo=equipo, activo=True).order_by("apellido", "nombre")
        ]

    matches = []
    for p in partidos.order_by("fecha_hora"):
        matches.append({
            "id": p.id,
            "fecha_hora": p.fecha_hora.isoformat(),
            "campo": p.campo.nombre if p.campo else "",
            "estado": p.estado,
            "es_amistoso": p.es_amistoso,
            "es_liguilla": p.es_liguilla,
            "goles_default": p.temporada.goles_default if p.temporada_id else 1,
            "min_jugadores": p.temporada.min_jugadores if p.temporada_id else 7,
            "cambios_permitidos": p.temporada.cambios_permitidos if p.temporada_id else 3,
            "max_titulares": (p.temporada.max_titulares or 11) if p.temporada_id else 11,
            "arbitro_id": p.arbitro_id,
            "equipo_local": {"id": p.equipo_local_id, "nombre": p.equipo_local.nombre,
                             "jugadores": jugadores_dto(p.equipo_local)},
            "equipo_visitante": {"id": p.equipo_visitante_id, "nombre": p.equipo_visitante.nombre,
                                 "jugadores": jugadores_dto(p.equipo_visitante)},
        })
    return JsonResponse({"ok": True, "matches": matches, "arbitros": arbitros})


@csrf_exempt
def api_offline_cedula(request):
    import json as jsonlib
    from django.http import JsonResponse
    from django.http import QueryDict
    from .cedula_service import procesar_cedula
    user = _get_offline_user(request)
    if user is None:
        return JsonResponse({"ok": False, "error": "Token inválido o expirado."}, status=401)
    if not user.es_arbitro:
        return JsonResponse({"ok": False, "error": "El modo offline solo es para árbitros."}, status=403)
    try:
        payload = jsonlib.loads(request.body or "{}")
    except Exception:
        return JsonResponse({"ok": False, "error": "JSON inválido."}, status=400)

    partido_id = payload.get("partido_id")
    partido = Partido.objects.filter(pk=partido_id).first()
    if partido is None:
        return JsonResponse({"ok": False, "error": "Partido no encontrado."}, status=404)

    data = QueryDict("", mutable=True)
    data["arbitro"] = str(payload.get("arbitro", "") or "")
    data["finalizar"] = "1" if payload.get("finalizar") else "0"
    if payload.get("default_local"):
        data["defaultLocalCheck"] = "on"
    if payload.get("default_visitante"):
        data["defaultVisitCheck"] = "on"
    if payload.get("motivo_default_local"):
        data["motivo_default_local"] = str(payload["motivo_default_local"])
    if payload.get("motivo_default_visitante"):
        data["motivo_default_visitante"] = str(payload["motivo_default_visitante"])

    for jid, jdata in (payload.get("jugadores") or {}).items():
        data[f"equipo_{jid}"] = str(jdata.get("equipo", ""))
        participacion = jdata.get("participacion", "")
        if participacion in ("titular", "cambio"):
            data[f"participacion_{jid}"] = participacion
        goles = int(jdata.get("goles") or 0)
        if goles > 0:
            data[f"gol_{jid}"] = str(goles)
        amarillas = int(jdata.get("amarillas") or 0)
        if amarillas >= 1:
            data[f"tarjeta_{jid}_AMARILLA"] = "AMARILLA"
        if amarillas >= 2:
            data[f"tarjeta_{jid}_AMARILLA_2"] = "AMARILLA"
        if jdata.get("roja"):
            data[f"tarjeta_{jid}_ROJA"] = "ROJA"
        suspension = int(jdata.get("suspension") or 0)
        if suspension > 0:
            data[f"suspension_{jid}"] = str(suspension)

    result = procesar_cedula(partido, data, user)
    resp = {"ok": result["ok"], "finalizado": result.get("finalizado", False)}
    if result["errors"]:
        resp["errors"] = result["errors"]
    if result["warnings"]:
        resp["warnings"] = result["warnings"]
    return JsonResponse(resp)
