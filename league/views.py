import datetime
from datetime import date
import json
import logging
import re
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

logger = logging.getLogger(__name__)

from django.urls import reverse_lazy, reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.http import FileResponse, HttpResponse, Http404, JsonResponse
from django.core.exceptions import PermissionDenied
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from django.db import models
from django.utils import timezone
from django.db.models import Sum, Q, Count, Min, Max, OuterRef, Subquery, F, Case, When, Value, IntegerField, DateTimeField
from django import forms
from .models import Categoria, Equipo, Jugador, JugadorEquipo, Campo, Temporada, Partido, Gol, Jornada, PeriodoAltas, Tarjeta, SuspensionJugador, MovimientoEquipo, Arbitro, ConfiguracionLiga, SuscripcionEmail, CampoIndisponibilidad, JugadorPartido, Grupo, JugadorHerencia, Anuncio, AnuncioClick, AnuncioImpresion, AnuncioDia, PronosticoQuiniela, Descarga
from .forms import CategoriaForm, TemporadaForm, EquipoForm, JugadorForm, CampoForm, ArbitroForm, PeriodoAltasForm, PartidoForm, AnuncioForm
from finance.models import ConceptoIngreso, Ingreso
from .storage import url_para_nombre


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


class AnuncioListView(ListView):
    model = Anuncio
    template_name = "league/anuncio_list.html"
    context_object_name = "anuncios"

    def get_queryset(self):
        return Anuncio.objects.select_related().order_by("-activo", "orden", "-creado")


class AnuncioCreateView(CreateView):
    model = Anuncio
    form_class = AnuncioForm
    template_name = "league/anuncio_form.html"
    success_url = reverse_lazy("anuncio_list")


class AnuncioUpdateView(UpdateView):
    model = Anuncio
    form_class = AnuncioForm
    template_name = "league/anuncio_form.html"
    success_url = reverse_lazy("anuncio_list")


class AnuncioDeleteView(DeleteView):
    model = Anuncio
    template_name = "league/anuncio_confirm_delete.html"
    success_url = reverse_lazy("anuncio_list")


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


def _puede_cambiar_equipo_secundario(jugador, registro_actual, temporada=None, categoria=None):
    """¿Se puede mover al jugador a otro equipo de una categoría donde ya
    tiene secundario? Devuelve (permitido, motivo_bloqueo).

    Mismo criterio que JugadorForm: si la categoría tiene temporada en curso
    hace falta un período de altas abierto y que el jugador no tenga
    participaciones ya registradas en esa categoría (si ya jugó, el equipo
    queda congelado para toda la temporada). Sin temporada en curso no hay
    bloqueo, igual que en el formulario.
    """
    cat = categoria or registro_actual.equipo.categoria
    if temporada is None:
        temporada = Temporada.objects.filter(
            categoria_id=cat.pk, iniciada=True, finalizada=False
        ).order_by("id").first()
    if temporada is None:
        return True, ""

    if not temporada.periodos_altas.filter(activo=True).exists():
        return False, (
            "No hay un período de altas activo en {}. No se puede cambiar de equipo.".format(
                cat.nombre)
        )

    from .models import JugadorPartido
    ya_jugo = JugadorPartido.objects.filter(
        jugador=jugador, partido__temporada=temporada, equipo__categoria_id=cat.pk
    ).exists()
    if ya_jugo:
        return False, (
            "No se puede cambiar de equipo en {} porque el jugador ya tiene "
            "participaciones registradas en la categoría.".format(cat.nombre)
        )
    return True, ""


def _jugadores_con_secundario_posible(jugadores):
    """Pks de los jugadores que tienen AL MENOS UN equipo secundario válido.

    El botón "agregar equipo secundario" solo se muestra cuando el jugador
    cumple los requisitos, así que esta función aplica exactamente las mismas
    reglas que JugadorForm y que jugador_agregar_equipo_secundario:

      - debe tener equipo principal;
      - la categoría destino debe ser compatible con TODAS las categorías
        donde ya juega (misma fuente: _allowed_secondary_category_ids);
      - debe ser un alta nueva (no una categoría donde ya está registrado);
      - la edad debe caer en el rango de la categoría, si tiene fecha de
        nacimiento y la categoría define mínimo/máximo;
      - si la categoría tiene temporada en curso, debe haber período de
        altas abierto;
      - no debe tener suspensión activa (bloquea los altas nuevas);
      - la categoría destino debe tener al menos un equipo activo y pasar
        las reglas de movimiento (ascenso/descenso).

    Se resuelve con un número acotado de consultas (sin una por fila).
    """
    jugadores = list(jugadores)
    if not jugadores:
        return set()

    from .forms import _allowed_secondary_category_ids, _compatibilidad_maps
    from .reglas_movimientos import errores_movimiento_jugador

    forward_map, reverse_map = _compatibilidad_maps()
    cats = Categoria.objects.filter(activo=True).in_bulk()

    # Equipos activos agrupados por categoría.
    equipos_por_cat = {}
    for eq in Equipo.objects.filter(activo=True).select_related("categoria"):
        equipos_por_cat.setdefault(eq.categoria_id, []).append(eq)

    # Temporadas en curso por categoría (el formulario usa .first()).
    temp_por_cat = {}
    for t in Temporada.objects.filter(iniciada=True, finalizada=False).order_by("id"):
        temp_por_cat.setdefault(t.categoria_id, t)
    cats_con_altas = set()
    for categoria_id, t in temp_por_cat.items():
        if t.periodos_altas.filter(activo=True).exists():
            cats_con_altas.add(categoria_id)

    pks = [j.pk for j in jugadores]

    # Categorías donde el jugador ya tiene equipo secundario.
    cats_registradas = {}
    registros_por_jugador = {}
    for row in JugadorEquipo.objects.filter(
        jugador_id__in=pks, es_principal=False
    ).values("id", "jugador_id", "equipo_id", "equipo__categoria_id"):
        cats_registradas.setdefault(row["jugador_id"], []).append(row["equipo__categoria_id"])
        registros_por_jugador.setdefault(row["jugador_id"], []).append(row)

    # Una suspensión activa impide dar de alta en cualquier equipo nuevo.
    suspendidos = set(
        SuspensionJugador.objects.filter(jugador_id__in=pks, activo=True)
        .values_list("jugador_id", flat=True)
    )

    def edad_valida(cat, edad):
        if edad is None:
            return True
        if cat.edad_minima is not None and edad < cat.edad_minima:
            return False
        if cat.edad_maxima is not None and edad > cat.edad_maxima:
            return False
        return True

    def tiene_destino(jugador):
        principal_cat_id = jugador.equipo.categoria_id
        registradas = cats_registradas.get(jugador.pk, [])
        permitidas = _allowed_secondary_category_ids(
            jugador.equipo, jugador,
            forward_map=forward_map, reverse_map=reverse_map,
            categorias_registradas=registradas,
        )
        edad = jugador.edad()

        # 1) ALTA en una categoría nueva.
        for cid in permitidas:
            if cid == principal_cat_id or cid in registradas:
                continue
            cat = cats.get(cid)
            if cat is None or not edad_valida(cat, edad):
                continue
            if cid in temp_por_cat and cid not in cats_con_altas:
                continue
            for eq in equipos_por_cat.get(cid, []):
                try:
                    if errores_movimiento_jugador(jugador, eq, cat):
                        continue
                except Exception:
                    continue
                return True

        # 2) CAMBIO de equipo dentro de una categoría donde ya es secundario
        #    (requiere período de altas abierto y sin participaciones previas).
        for reg in registros_por_jugador.get(jugador.pk, []):
            cid = reg["equipo__categoria_id"]
            if cid == principal_cat_id or cid not in permitidas:
                continue
            cat = cats.get(cid)
            if cat is None or not edad_valida(cat, edad):
                continue
            otros = [eq for eq in equipos_por_cat.get(cid, [])
                     if eq.pk != reg["equipo_id"]]
            if not otros:
                continue
            stub = JugadorEquipo(id=reg["id"], equipo_id=reg["equipo_id"])
            try:
                permitido, _ = _puede_cambiar_equipo_secundario(
                    jugador, stub, temporada=temp_por_cat.get(cid), categoria=cat
                )
            except Exception:
                continue
            if permitido:
                return True

        return False

    resultado = set()
    for jugador in jugadores:
        if not jugador.equipo_id:
            continue
        if jugador.pk in suspendidos:
            continue
        if tiene_destino(jugador):
            resultado.add(jugador.pk)
    return resultado


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
        # Pks de jugadores con al menos un equipo secundario válido disponible:
        # el botón "agregar equipo secundario" solo se muestra para esos.
        ctx["puede_secundario"] = _jugadores_con_secundario_posible(ctx["jugadores"])
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


def subir_foto_jugador(request, pk):
    """Sube la foto de un jugador SIN foto (durante temporada en curso).

    Solo actualiza el campo `foto`. Si el jugador ya tiene foto, solo se puede
    reemplazar siendo superusuario o con un período de altas activo.
    """
    jugador = get_object_or_404(Jugador, pk=pk)
    if request.method != "POST":
        return redirect("jugador_list")

    if jugador.foto:
        puede_reemplazar = False
        if request.user.is_superuser:
            puede_reemplazar = True
        elif jugador.equipo_id:
            puede_reemplazar = Temporada.objects.filter(
                categoria=jugador.equipo.categoria,
                iniciada=True,
                finalizada=False,
                periodos_altas__activo=True,
            ).exists()
        if not puede_reemplazar:
            messages.error(
                request,
                f"{jugador} ya tiene foto asignada. Solo se puede cambiar con un "
                "período de altas activo o por un administrador."
            )
            return redirect("jugador_list")

    foto = request.FILES.get("foto")
    if not foto:
        messages.error(request, "Selecciona una imagen para subir.")
        return redirect("jugador_list")

    from django.forms import ImageField
    from django.core.exceptions import ValidationError
    try:
        ImageField().clean(foto)
    except ValidationError:
        messages.error(request, "El archivo no es una imagen válida.")
        return redirect("jugador_list")

    jugador.foto = foto
    jugador.save(update_fields=["foto"])
    messages.success(request, f"Foto de {jugador} guardada.")
    return redirect("jugador_list")


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


def _anuncio_dia_bump(anuncio_id, campo):
    """Incrementa el contador diario del anuncio (campo: 'impresiones' o 'clics')."""
    try:
        hoy = timezone.localdate()
        obj, _ = AnuncioDia.objects.get_or_create(anuncio_id=anuncio_id, fecha=hoy)
        AnuncioDia.objects.filter(pk=obj.pk).update(**{campo: models.F(campo) + 1})
    except Exception:
        pass


def detalle_anuncio(request, anuncio_id):
    """Página pública: muestra el anuncio en grande y registra el clic."""
    anuncio = get_object_or_404(Anuncio, pk=anuncio_id, activo=True)
    # Registrar el clic (banner -> detalle), salvo IPs excluidas de métricas
    ip = (request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR') or '').split(',')[0].strip()
    if not ConfiguracionLiga.es_ip_excluida(ip):
        anuncio.clics = (anuncio.clics or 0) + 1
        anuncio.save(update_fields=["clics"])
        _anuncio_dia_bump(anuncio_id, "clics")
        try:
            AnuncioClick.objects.create(
                anuncio=anuncio,
                ip=ip or None,
                sesion=(request.session.session_key or '')[:64],
            )
        except Exception:
            pass
    return render(request, "publicidad/detalle.html", {"anuncio": anuncio})


def impresion_anuncio(request, anuncio_id):
    """Registra una impresión del banner (se llama desde el cliente, solo
    navegadores reales con JS; los bots no cuentan)."""
    from django.http import JsonResponse
    if request.method != "GET":
        return JsonResponse({"ok": False}, status=405)
    ip = (request.META.get('HTTP_X_FORWARDED_FOR') or request.META.get('REMOTE_ADDR') or '').split(',')[0].strip()
    if ConfiguracionLiga.es_ip_excluida(ip):
        return JsonResponse({"ok": True, "excluida": True})
    try:
        nup = Anuncio.objects.filter(pk=anuncio_id, activo=True).update(
            impresiones=models.F("impresiones") + 1
        )
        if nup == 1:
            _anuncio_dia_bump(anuncio_id, "impresiones")
            # Impresión única (1 por anuncio + día + visitante) para reportar alcance
            clave = (request.session.session_key or ip or "anon")[:64]
            try:
                AnuncioImpresion.objects.get_or_create(
                    anuncio_id=anuncio_id, fecha=timezone.localdate(), clave=clave,
                )
            except Exception:
                pass
        return JsonResponse({"ok": nup == 1})
    except Exception:
        return JsonResponse({"ok": False})


def _mes_rango(mes_param, hoy):
    """Devuelve (year, month, desde, hasta) a partir de 'YYYY-MM' (o mes actual)."""
    try:
        y, m = [int(x) for x in mes_param.split("-")]
        if not (1 <= m <= 12):
            raise ValueError
    except Exception:
        y, m = hoy.year, hoy.month
    desde = datetime.date(y, m, 1)
    hasta = datetime.date(y + 1, 1, 1) if m == 12 else datetime.date(y, m + 1, 1)
    return y, m, desde, hasta


@admin.site.admin_view
def reporte_anuncio(request, anuncio_id):
    """Reporte imprimible de un anuncio para un mes (para enviar al anunciante)."""
    from .models import Visita, DeviceToken, SuscripcionEmail
    anuncio = get_object_or_404(Anuncio, pk=anuncio_id)
    hoy = timezone.localdate()
    y, m, desde, hasta = _mes_rango(request.GET.get("mes", ""), hoy)

    dias = list(AnuncioDia.objects.filter(anuncio=anuncio, fecha__gte=desde, fecha__lt=hasta).order_by("fecha"))
    imp_mes = sum(d.impresiones for d in dias)
    clics_mes = sum(d.clics for d in dias)
    unicas_mes = AnuncioImpresion.objects.filter(anuncio=anuncio, fecha__gte=desde, fecha__lt=hasta).count()
    ctr_mes = (clics_mes / imp_mes * 100) if imp_mes else 0
    ctr_unicas = (clics_mes / unicas_mes * 100) if unicas_mes else 0
    dias_max = max([d.impresiones for d in dias] + [1])

    acum_imp = anuncio.impresiones
    acum_clics = anuncio.clics
    acum_unicas = AnuncioImpresion.objects.filter(anuncio=anuncio).count()
    acum_ctr = (acum_clics / acum_imp * 100) if acum_imp else 0

    MESES = ["", "enero", "febrero", "marzo", "abril", "mayo", "junio",
             "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    prev = desde - datetime.timedelta(days=1)
    prox = hasta

    # Audiencia del sitio (contexto para el anunciante)
    hace_30 = timezone.localtime() - datetime.timedelta(days=30)
    visitas_mes = Visita.objects.filter(inicio=True, fecha__gte=hace_30).count()
    paginas_mes = Visita.objects.filter(fecha__gte=hace_30).count()
    dispositivos = DeviceToken.objects.filter(activo=True).count()
    suscriptores = SuscripcionEmail.objects.filter(activo=True).count()

    return render(request, "publicidad/reporte.html", {
        "anuncio": anuncio,
        "mes_nombre": MESES[m], "anio": y, "mes_param": "%04d-%02d" % (y, m),
        "prev_mes": "%04d-%02d" % (prev.year, prev.month),
        "prox_mes": "%04d-%02d" % (prox.year, prox.month),
        "dias": dias, "dias_max": dias_max,
        "imp_mes": imp_mes, "clics_mes": clics_mes, "unicas_mes": unicas_mes,
        "ctr_mes": ctr_mes, "ctr_unicas": ctr_unicas,
        "acum_imp": acum_imp, "acum_clics": acum_clics, "acum_unicas": acum_unicas, "acum_ctr": acum_ctr,
        "visitas_mes": visitas_mes, "paginas_mes": paginas_mes,
        "dispositivos": dispositivos, "suscriptores": suscriptores,
        "hoy": hoy, "config": ConfiguracionLiga.obtener(),
    })


@admin.site.admin_view
def admin_push_logs(request):
    from .push import get_push_logs
    from .models import DeviceToken, Visita, Descarga, AnuncioImpresion, SuscripcionEmail
    from datetime import timedelta
    from django.db.models import Count, Case, When, F, Value, CharField
    from django.db.models.functions import TruncDate, Cast
    from django.utils import timezone

    logs = get_push_logs(limit=200)
    show_inactive = request.GET.get("show_inactive") in ("1", "on", "true")
    if show_inactive:
        tokens = DeviceToken.objects.select_related("usuario").prefetch_related("categorias").order_by("-creado")[:200]
    else:
        tokens = DeviceToken.objects.filter(activo=True).select_related("usuario").prefetch_related("categorias").order_by("-creado")[:100]
    dispositivos_activos = DeviceToken.objects.filter(activo=True).count()
    suscriptores_email = SuscripcionEmail.objects.filter(activo=True).count()

    ahora = timezone.localtime()
    inicio_hoy = timezone.make_aware(timezone.datetime(ahora.year, ahora.month, ahora.day))
    hace_7dias = ahora - timedelta(days=7)
    hace_30dias = ahora - timedelta(days=30)

    def clave_expr():
        return Case(
            When(sesion__gt='', then=F('sesion')),
            default=Case(When(ip__isnull=False, then=Cast('ip', output_field=CharField())), default=Value('')),
            output_field=CharField(),
        )

    def unicos(qs):
        return qs.annotate(k=clave_expr()).values('k').distinct().count()

    visitas_total = Visita.objects.filter(inicio=True).count()
    visitas_hoy = Visita.objects.filter(inicio=True, fecha__gte=inicio_hoy).count()
    visitas_semana = Visita.objects.filter(inicio=True, fecha__gte=hace_7dias).count()
    visitas_mes = Visita.objects.filter(inicio=True, fecha__gte=hace_30dias).count()
    paginas_mes = Visita.objects.filter(fecha__gte=hace_30dias).count()
    unicos_hoy = unicos(Visita.objects.filter(fecha__gte=inicio_hoy))
    unicos_mes = unicos(Visita.objects.filter(fecha__gte=hace_30dias))

    top_paginas = list(
        Visita.objects.filter(fecha__gte=hace_30dias)
        .values("path")
        .annotate(c=Count("id"))
        .order_by("-c")[:12]
    )
    _tot_pag = (paginas_mes or 1)
    for p in top_paginas:
        p["pct"] = p["c"] / _tot_pag * 100

    import re as _re
    _movil_re = _re.compile(r'Android|iPhone|iPad|iPod|Mobile|Windows Phone|BlackBerry|Opera Mini|IEMobile', _re.I)
    moviles_mes = sum(1 for ua in Visita.objects.filter(fecha__gte=hace_30dias).values_list("user_agent", flat=True).iterator() if _movil_re.search(ua or ""))
    web_mes = max(paginas_mes - moviles_mes, 0)
    _tot = (moviles_mes + web_mes) or 1
    moviles_pct = round(moviles_mes / _tot * 100)
    web_pct = 100 - moviles_pct

    anuncios = list(Anuncio.objects.all().order_by("-activo", "orden", "-creado"))
    hace_30dias_date = timezone.localdate() - timedelta(days=30)
    for a in anuncios:
        a.ctr = (a.clics / a.impresiones * 100) if a.impresiones else 0
        a.clics_mes = AnuncioClick.objects.filter(anuncio=a, fecha__gte=hace_30dias).count()
        a.unicas_total = AnuncioImpresion.objects.filter(anuncio=a).count()
        a.unicas_mes = AnuncioImpresion.objects.filter(anuncio=a, fecha__gte=hace_30dias_date).count()

    desde_serie = inicio_hoy - timedelta(days=13)
    por_dia = {}
    for r in Visita.objects.filter(inicio=True, fecha__gte=desde_serie).annotate(d=TruncDate("fecha")).values("d").annotate(c=Count("id")):
        por_dia[r["d"]] = r["c"]
    serie_diaria = []
    for i in range(14):
        d = (desde_serie + timedelta(days=i)).date()
        serie_diaria.append({"fecha": d.strftime("%d/%m"), "c": por_dia.get(d, 0)})
    serie_max = max([s["c"] for s in serie_diaria] or [1])

    # --- Descargas de archivos (APK / reglamento) ---
    def _dcount(tipo, desde=None):
        qs = Descarga.objects.filter(tipo=tipo)
        if desde is not None:
            qs = qs.filter(fecha__gte=desde)
        return qs.count()

    descargas_apk = {
        "total": _dcount("APK"),
        "hoy": _dcount("APK", inicio_hoy),
        "semana": _dcount("APK", hace_7dias),
        "mes": _dcount("APK", hace_30dias),
    }
    descargas_reglamento = {
        "total": _dcount("REGLAMENTO"),
        "hoy": _dcount("REGLAMENTO", inicio_hoy),
        "semana": _dcount("REGLAMENTO", hace_7dias),
        "mes": _dcount("REGLAMENTO", hace_30dias),
    }
    descargas_total = Descarga.objects.count()
    descargas_mes_qs = Descarga.objects.filter(fecha__gte=hace_30dias)
    descargas_mes = descargas_mes_qs.count()
    descargas_movil_mes = sum(1 for ua in descargas_mes_qs.values_list("user_agent", flat=True).iterator() if _movil_re.search(ua or ""))
    descargas_web_mes = max(descargas_mes - descargas_movil_mes, 0)
    descargas_total_mov_web = (descargas_movil_mes + descargas_web_mes) or 1
    descargas_movil_pct = round(descargas_movil_mes / descargas_total_mov_web * 100)
    descargas_web_pct = 100 - descargas_movil_pct

    desc_por_dia = {}
    for r in Descarga.objects.filter(fecha__gte=desde_serie).annotate(d=TruncDate("fecha")).values("d").annotate(c=Count("id")):
        desc_por_dia[r["d"]] = r["c"]
    descargas_serie = []
    for i in range(14):
        d = (desde_serie + timedelta(days=i)).date()
        descargas_serie.append({"fecha": d.strftime("%d/%m"), "c": desc_por_dia.get(d, 0)})
    descargas_serie_max = max([s["c"] for s in descargas_serie] or [1])

    descargas_recientes = Descarga.objects.select_related("usuario").order_by("-fecha")[:40]

    # Visitantes únicos por día (últimos 14 días) y promedio diario
    dau_por_dia = {}
    for r in (Visita.objects.filter(fecha__gte=desde_serie)
              .annotate(d=TruncDate("fecha"), k=clave_expr())
              .values("d", "k").distinct()):
        dau_por_dia[r["d"]] = dau_por_dia.get(r["d"], 0) + 1
    dau_serie = []
    for i in range(14):
        d = (desde_serie + timedelta(days=i)).date()
        dau_serie.append({"fecha": d.strftime("%d/%m"), "c": dau_por_dia.get(d, 0)})
    dau_max = max([s["c"] for s in dau_serie] or [1])
    dau_promedio = round(sum(s["c"] for s in dau_serie) / 14)

    # Origen del tráfico (referer) últimos 30 días
    from urllib.parse import urlparse
    ref_conteo = {}
    for ref in Visita.objects.filter(fecha__gte=hace_30dias).values_list("referer", flat=True).iterator():
        ref = (ref or "").strip()
        if not ref:
            fuente = "Directo (sin referencia)"
        else:
            try:
                host = (urlparse(ref if "://" in ref else "http://" + ref).hostname or ref).lower()
            except Exception:
                host = ref.lower()
            if host.startswith("www."):
                host = host[4:]
            if "facebook" in host or host.endswith("fb.com"):
                fuente = "Facebook"
            elif "whatsapp" in host or host == "wa.me":
                fuente = "WhatsApp"
            elif "google" in host:
                fuente = "Google"
            elif "instagram" in host:
                fuente = "Instagram"
            elif "twitter" in host or host == "x.com" or host == "t.co":
                fuente = "X / Twitter"
            else:
                fuente = host
        ref_conteo[fuente] = ref_conteo.get(fuente, 0) + 1
    _tot_ref = sum(ref_conteo.values()) or 1
    top_origenes = [{"fuente": f, "c": c, "pct": c / _tot_ref * 100}
                    for f, c in sorted(ref_conteo.items(), key=lambda kv: -kv[1])[:10]]

    # Mapa de calor: visitas por día de la semana y hora (últimos 30 días, hora local)
    heat = [[0] * 24 for _ in range(7)]
    for f in Visita.objects.filter(fecha__gte=hace_30dias).values_list("fecha", flat=True).iterator():
        loc = timezone.localtime(f)
        heat[loc.weekday()][loc.hour] += 1
    heat_max = max([max(r) for r in heat] + [1])
    dias_semana = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    heat_rows = []
    for i, nombre in enumerate(dias_semana):
        fila = [{"h": h, "c": heat[i][h], "a": round(heat[i][h] / heat_max, 2)} for h in range(24)]
        heat_rows.append({"dia": nombre, "horas": fila, "total": sum(heat[i])})
    horas_tot = [sum(heat[i][h] for i in range(7)) for h in range(24)]
    heat_total = sum(horas_tot)
    if heat_total:
        mejor_dia = dias_semana[max(range(7), key=lambda i: sum(heat[i]))]
        mejor_hora = max(range(24), key=lambda h: horas_tot[h])
    else:
        mejor_dia = "-"
        mejor_hora = 0

    recientes = Visita.objects.select_related("usuario").order_by("-fecha")[:60]

    return render(request, "admin/push_logs.html", {
        "logs": logs,
        "tokens": tokens,
        "visitas_unicas": visitas_total,
        "visitas_hoy": visitas_hoy,
        "visitas_semana": visitas_semana,
        "visitas_mes": visitas_mes,
        "paginas_mes": paginas_mes,
        "unicos_hoy": unicos_hoy,
        "unicos_mes": unicos_mes,
        "top_paginas": top_paginas,
        "moviles_mes": moviles_mes,
        "web_mes": web_mes,
        "moviles_pct": moviles_pct,
        "web_pct": web_pct,
        "anuncios": anuncios,
        "serie_diaria": serie_diaria,
        "serie_max": serie_max,
        "recientes": recientes,
        "descargas_apk": descargas_apk,
        "descargas_reglamento": descargas_reglamento,
        "descargas_total": descargas_total,
        "descargas_mes": descargas_mes,
        "descargas_movil_mes": descargas_movil_mes,
        "descargas_web_mes": descargas_web_mes,
        "descargas_movil_pct": descargas_movil_pct,
        "descargas_web_pct": descargas_web_pct,
        "descargas_serie": descargas_serie,
        "descargas_serie_max": descargas_serie_max,
        "descargas_recientes": descargas_recientes,
        "dau_serie": dau_serie,
        "dau_max": dau_max,
        "dau_promedio": dau_promedio,
        "top_origenes": top_origenes,
        "dispositivos_activos": dispositivos_activos,
        "suscriptores_email": suscriptores_email,
        "heat_rows": heat_rows,
        "heat_horas": list(range(24)),
        "heat_total": heat_total,
        "mejor_dia": mejor_dia,
        "mejor_hora": mejor_hora,
    })


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

    # Capturar el día original programado ANTES de recorrer el calendario.
    # (el corrimiento +N semanas reprograma los partidos; sin esto perderíamos
    #  qué día era para el aviso del dashboard.)
    primer_pend = (
        Partido.objects.filter(jornada=jornada, temporada=jornada.temporada)
        .exclude(estado="FIN")
        .order_by("fecha_hora")
        .first()
    )
    if primer_pend and primer_pend.fecha_hora:
        jornada.fecha_original = timezone.localdate(primer_pend.fecha_hora)

    # Mark jornada as suspended
    jornada.estado = "SUSPENDIDA"
    jornada.motivo_suspension = motivo
    jornada.semanas_suspension = semanas
    jornada.save(update_fields=["estado", "motivo_suspension", "semanas_suspension", "fecha_original"])

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
    jornada.fecha_original = None
    jornada.save(update_fields=["estado", "motivo_suspension", "semanas_suspension", "fecha_original"])

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
    rotacion_banners_segundos = djforms.IntegerField(
        min_value=5, max_value=3600, initial=30,
        widget=djforms.NumberInput(attrs={"class": "form-control", "min": 5, "max": 3600}),
        help_text="Cuántos segundos se muestra cada anuncio en el inicio antes de rotar. Mínimo 5.",
    )

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
            "ips_excluidas": djforms.Textarea(attrs={"class": "form-control", "rows": 4,
                                                     "placeholder": "Una IP por línea. Ej: 190.12.34.56 o 190.12.34.*"}),
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
            "mostrar_quiniela": djforms.CheckboxInput(attrs={"class": "form-check-input", "role": "switch"}),
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


_BOTS_DESCARGA = re.compile(
    r'(bot|spider|crawl|slurp|bingpreview|facebookexternalhit|whatsapp|'
    r'curl|wget|python-requests|python-urllib|go-http-client|ahrefs|mj12|'
    r'semrush|google-inspectiontool|pingdom|uptime|monitor)', re.I)


def _registrar_descarga(request, tipo):
    """Guarda una descarga para las métricas de /push-logs/ (ignora personal y bots)."""
    try:
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_staff", False):
            return
        ua = request.META.get("HTTP_USER_AGENT", "") or ""
        if _BOTS_DESCARGA.search(ua):
            return
        ip = (request.META.get("HTTP_X_FORWARDED_FOR") or request.META.get("REMOTE_ADDR") or "").split(",")[0].strip()
        if ConfiguracionLiga.es_ip_excluida(ip):
            return
        sesion = ""
        if getattr(request, "session", None):
            sesion = request.session.get("_session_key") or ""
        gu = user if (user is not None and user.is_authenticated and not user.is_staff) else None
        Descarga.objects.create(
            tipo=tipo,
            ip=ip or None,
            user_agent=ua[:255],
            referer=request.META.get("HTTP_REFERER", "")[:255],
            sesion=sesion[:64],
            usuario=gu,
        )
    except Exception:
        pass


def descarga_reglamento(request):
    config = ConfiguracionLiga.obtener()
    if not config.reglamento:
        raise Http404("No hay reglamento disponible.")
    _registrar_descarga(request, "REGLAMENTO")
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
    _registrar_descarga(request, "APK")
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


def _enviar_correo_suscriptores(suscriptores, config, subject, template, ctx_extra, request=None, adjuntos=None):
    """Envía un correo a una lista de suscriptores. Retorna el conteo.

    `adjuntos` es una lista opcional de dicts con las llaves
    {cid, filename, content(bytes), mimetype} para incrustar imágenes inline
    (src="cid:...") dentro del HTML.
    """
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
                _enviar_sendgrid_api(smtp, subject, html, text, [sus.email], adjuntos)
            else:
                _enviar_smtp(smtp, subject, html, text, [sus.email], adjuntos)
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


def _enviar_smtp(smtp, subject, html, text, to_emails, adjuntos=None):
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
    if adjuntos:
        from email.mime.image import MIMEImage
        for a in adjuntos:
            img = MIMEImage(a["content"], _subtype=(a.get("mimetype") or "image/png").split("/")[-1])
            img.add_header("Content-ID", f"<{a['cid']}>")
            img.add_header("Content-Disposition", "inline", filename=a.get("filename", "imagen.png"))
            msg.attach(img)
    msg.send(fail_silently=False)


def _enviar_sendgrid_api(smtp, subject, html, text, to_emails, adjuntos=None):
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, Content, To, Attachment, Disposition, ContentId, FileContent, FileName, FileType
    message = Mail(
        from_email=Email(smtp["from_email"] or smtp["user"]),
        to_emails=[To(email) for email in to_emails],
        subject=subject,
        html_content=Content("text/html", html),
    )
    if adjuntos:
        import base64
        for a in adjuntos:
            b64 = base64.b64encode(a["content"]).decode()
            att = Attachment(
                FileContent(b64),
                FileName(a.get("filename", "imagen.png")),
                FileType(a.get("mimetype") or "image/png"),
                Disposition("inline"),
                ContentId(a["cid"]),
            )
            message.add_attachment(att)
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
        self.vitalicia = record.vitalicia
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
        if m.vitalicia:
            # Suspensión de por vida: no hay partidos pendientes ni cuenta que cumplir
            env = _SuspensionManualEnvelope(m, restantes, [])
            result[m.jugador_id] = {
                "pendientes": [],
                "todos": [],
                "expulsion_partido": None,
                "expulsion_equipo": m.equipo,
                "suspension_jornadas": m.jornadas,
                "restantes": restantes,
                "_tarjeta": env,
                "es_manual": True,
            }
            continue
        prox = Partido.objects.filter(
            temporada=temporada,
            estado__in=("PRO", "PROG"),
        )
        if m.equipo_id:
            prox = prox.filter(
                Q(equipo_local=m.equipo) | Q(equipo_visitante=m.equipo)
            )
        prox = prox.order_by("jornada__numero", "fecha_hora", "id")[:restantes]
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

    ignore_players = request.POST.get("ignore_players") == "on"
    puede, msg = temporada.puede_iniciar(ignore_players=ignore_players)
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

    # Si es POST, procesar el formulario
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

    # GET: siempre mostrar formulario (para que se vea el checkbox ignore_players)
    ctx = {
        "temporada": temporada,
        "url_generar": reverse("iniciar_temporada", args=[pk]),
        "fecha_pasada": temporada.fecha_inicio < date.today(),
    }
    return render(request, "league/iniciar_temporada.html", ctx)


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


def _hora_por_defecto_partido(temporada, indice_en_jornada):
    """Hora por defecto para partidos ya jugados sin hora definida.

    Sigue cíclicamente los horarios configurados de la categoría (ej. 15:00,
    17:00): el 1er partido de la jornada usa el 1º horario, el 2º el siguiente,
    etc. Si la categoría no tiene horarios, usa las 12:00 (como el generador
    de rol)."""
    hs = temporada.categoria.horarios or ["12:00"]
    hh, mm = hs[indice_en_jornada % len(hs)].split(":")
    return datetime.time(int(hh), int(mm))


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

                # Fecha obligatoria; hora opcional (usa las de la categoría por defecto)
                try:
                    fecha = datetime.datetime.strptime(env_fecha[i], "%Y-%m-%d").date()
                except (ValueError, IndexError):
                    errores.append(f"Fecha inválida en la fila {i + 1}.")
                    continue
                if env_hora[i] and env_hora[i].strip():
                    try:
                        hora = datetime.datetime.strptime(env_hora[i], "%H:%M").time()
                    except ValueError:
                        errores.append(f"Hora inválida en la fila {i + 1}.")
                        continue
                else:
                    # Sin hora: usa las horas configuradas de la categoría
                    hora = _hora_por_defecto_partido(temporada, ya_en_jornada)
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
                finalizar = (
                    len(env_finalizar) > i and env_finalizar[i] and env_finalizar[i].strip() == "1"
                )

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
            ok_p, errores_p = temporada.validar_continuacion_rol()
            if not ok_p:
                messages.error(
                    request,
                    "No se puede completar el rol con las jornadas capturadas: "
                    + "; ".join(errores_p),
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
            # Reglas de ascenso/descenso/desaparición
            from .reglas_movimientos import errores_movimiento_jugador
            mov_errs = errores_movimiento_jugador(jug, eq, eq.categoria)
            if mov_errs:
                for msg in mov_errs:
                    messages.error(request, msg)
                return redirect("gestionar_altas_bajas", pk=pk)
            # Suspensión activa: no cambiar de equipo principal hasta cumplirla
            if es_principal and jug.equipo_id and jug.equipo_id != eq.id:
                susp_activa = SuspensionJugador.objects.filter(jugador=jug, activo=True).first()
                if susp_activa:
                    nomin = susp_activa.equipo.nombre if susp_activa.equipo else susp_activa.categoria.nombre
                    messages.error(
                        request,
                        f"{jug} tiene una suspensión activa ({nomin}, restan "
                        f"{susp_activa.restantes()} jornada(s)). No puede darse de alta en otro equipo "
                        f"hasta cumplir la suspensión."
                    )
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
        goleadores = list(
            qs
            .values(
                "jugador__id", "jugador__nombre", "jugador__apellido",
                "jugador__foto", "jugador__dorsal",
                "equipo__id", "equipo__nombre", "equipo__logo",
            )
            .annotate(total_goles=Count("id"))
            .order_by("-total_goles")
        )
        for g in goleadores:
            g["equipo__logo_url"] = url_para_nombre(g.get("equipo__logo"))
            g["jugador__foto_url"] = url_para_nombre(g.get("jugador__foto"))

    # GOLES POR EQUIPO — solo temporada regular (excluye liguilla/finales).
    # Se suma el MARCADOR real del partido (goles_local/goles_visitante) en vez de
    # contar filas Gol con autor, para no perder los resultados sin goleador detallado.
    equipos = []
    if temp_id:
        partidos_fin = Partido.objects.filter(
            temporada_id=temp_id, estado="FIN", es_liguilla=False
        )

        por_local = (
            partidos_fin
            .values("equipo_local_id", "equipo_local__nombre", "equipo_local__logo")
            .annotate(total_goles=Sum("goles_local"))
        )
        por_visita = (
            partidos_fin
            .values("equipo_visitante_id", "equipo_visitante__nombre", "equipo_visitante__logo")
            .annotate(total_goles=Sum("goles_visitante"))
        )

        # Combinar local + visitante por equipo
        acc = {}
        for fila in list(por_local) + list(por_visita):
            eid = fila.get("equipo_local_id") or fila.get("equipo_visitante_id")
            nombre = fila.get("equipo_local__nombre") or fila.get("equipo_visitante__nombre")
            logo = fila.get("equipo_local__logo") or fila.get("equipo_visitante__logo")
            if not eid:
                continue
            key = eid
            if key not in acc:
                acc[key] = {
                    "equipo__id": eid,
                    "equipo__nombre": nombre,
                    "equipo__logo": logo,
                    "total_goles": 0,
                }
            acc[key]["total_goles"] += fila.get("total_goles") or 0

        equipos = sorted(
            acc.values(),
            key=lambda d: (-d["total_goles"], (d.get("equipo__nombre") or "").lower()),
        )
        for eq in equipos:
            eq["equipo__logo_url"] = url_para_nombre(eq.get("equipo__logo"))

    return render(request, "league/tabla_goleo.html", {
        "goleadores": goleadores,
        "equipos": equipos,
        "total_equipos": len(equipos),
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

    # Obtener jugadores con el equipo como principal O secundario
    from django.db.models import Q
    from .models import JugadorEquipo

    # Jugadores del equipo local (principal o secundario)
    local_jugador_ids = JugadorEquipo.objects.filter(
        equipo=partido.equipo_local, activo=True
    ).values_list("jugador_id", flat=True)
    jugadores_local = list(Jugador.objects.filter(
        Q(pk__in=local_jugador_ids) | Q(equipo=partido.equipo_local), activo=True
    ).select_related("equipo").distinct())

    # Jugadores del equipo visitante (principal o secundario)
    visit_jugador_ids = JugadorEquipo.objects.filter(
        equipo=partido.equipo_visitante, activo=True
    ).values_list("jugador_id", flat=True)
    jugadores_visit = list(Jugador.objects.filter(
        Q(pk__in=visit_jugador_ids) | Q(equipo=partido.equipo_visitante), activo=True
    ).select_related("equipo").distinct())
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
        amarillas = list(
            qs_amarillas
            .values(
                "jugador__id", "jugador__nombre", "jugador__apellido",
                "jugador__foto", "jugador__dorsal",
                "equipo__id", "equipo__nombre", "equipo__logo",
            )
            .annotate(total=Count("id"))
            .order_by("-total")
        )
        rojas = list(
            qs_rojas
            .values(
                "jugador__id", "jugador__nombre", "jugador__apellido",
                "jugador__foto", "jugador__dorsal",
                "equipo__id", "equipo__nombre", "equipo__logo",
            )
            .annotate(total=Count("id"))
            .order_by("-total")
        )
        for t in amarillas + rojas:
            t["equipo__logo_url"] = url_para_nombre(t.get("equipo__logo"))
            t["jugador__foto_url"] = url_para_nombre(t.get("jugador__foto"))

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
    filtro_cat = int(cat_id) if cat_id else None
    qs_temp = Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")
    if filtro_cat:
        qs_temp = qs_temp.filter(categoria_id=filtro_cat)
    else:
        # Misma lógica que el dashboard: categoría preferida del usuario,
        # luego la principal de la liga, para que se vean los mismos castigados
        default_cat = None
        if request.user.is_authenticated and request.user.categoria_preferida:
            default_cat = request.user.categoria_preferida
        if default_cat is None:
            default_cat = Categoria.objects.filter(es_principal=True).first()
        if default_cat:
            filtro_cat = default_cat.id
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

    if not temp_id:
        # Sin temporada (o categoría sin temporada creada): mostrar igual las
        # suspensiones manuales/heredadas vigentes, como hace el dashboard
        manual_qs = SuspensionJugador.objects.filter(activo=True).select_related("jugador", "equipo", "categoria")
        if filtro_cat:
            manual_qs = manual_qs.filter(categoria_id=filtro_cat)
        vistos = {
            getattr(c, "jugador_id", getattr(getattr(c, "jugador", None), "id", None))
            for c in castigados
        }
        for m in manual_qs:
            if m.jugador_id in vistos or m.restantes() <= 0:
                continue
            env = _SuspensionManualEnvelope(m, m.restantes(), [])
            castigados.append(env)

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
                equipo_id = request.POST.get("equipo_id") or None
                jornadas = int(request.POST.get("jornadas") or 0)
                motivo = request.POST.get("motivo", "").strip()
                jugador = Jugador.objects.filter(id=jugador_id).first()
                if not jugador:
                    error = "Jugador no encontrado."
                elif equipo_id and not Equipo.objects.filter(id=equipo_id, categoria=categoria).exists():
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
                equipo_id = request.POST.get("equipo_id") or None
                posicion = request.POST.get("posicion", "DEL")
                dorsal_raw = request.POST.get("dorsal", "").strip()
                jornadas = int(request.POST.get("jornadas") or 0)
                motivo = request.POST.get("motivo", "").strip()
                if not nombre or not apellido:
                    error = "Nombre y apellido son obligatorios."
                elif equipo_id and not Equipo.objects.filter(id=equipo_id, categoria=categoria).exists():
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
            "equipo_display": (s.equipo.nombre if s.equipo else f"Toda la categoría"),
            "temporada": s.temporada,
            "jornadas": s.jornadas,
            "vitalicia": s.vitalicia,
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


def _normalizar_texto(valor):
    """Minúsculas y sin acentos para búsquedas insensibles (Pérez == Perez)."""
    import unicodedata
    return "".join(
        ch for ch in unicodedata.normalize("NFD", valor or "")
        if unicodedata.category(ch) != "Mn"
    ).lower()


def _coincide_nombre(jugador, nombre, apellido):
    """True si nombre y apellido coinciden ignorando tildes/mayúsculas."""
    return (
        _normalizar_texto(jugador.nombre) == _normalizar_texto(nombre)
        and _normalizar_texto(jugador.apellido) == _normalizar_texto(apellido)
    )


def alta_jugadores_heredados(request):
    """Pantalla inicial (solo administrador) para registrar jugadores heredados:
    castigados de antes del sistema, o jugadores de equipos que ascendieron,
    descendieron o se dieron de baja.

    Antes de dar de alta, busca en el universo de jugadores si ya existe
    alguien con el mismo CURP (o nombre+apellido+fecha): si ya está registrado
    y tiene un equipo, se bloquea y se indica dónde está. Se guarda la
    categoría del evento para aplicar las reglas y los castigos.
    """
    from datetime import date as dt_date
    from .reglas_movimientos import aplicar_movimiento_a_jugador, errores_movimiento_jugador

    categorias = Categoria.objects.filter(activo=True).order_by("nombre")
    error = None
    resultados = []
    q = request.GET.get("q", "").strip()

    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            if accion == "buscar":
                q = request.POST.get("q", "").strip()
            elif accion == "crear":
                nombre = request.POST.get("nombre", "").strip()
                apellido = request.POST.get("apellido", "").strip()
                curp = request.POST.get("curp", "").strip() or None
                fecha_raw = request.POST.get("fecha_nacimiento", "").strip()
                fecha_nac = None
                if fecha_raw:
                    try:
                        fecha_nac = datetime.datetime.strptime(fecha_raw, "%Y-%m-%d").date()
                    except ValueError:
                        error = "Fecha de nacimiento inválida."
                tipo = request.POST.get("tipo", "CASTIGADO")
                categoria_id = request.POST.get("categoria_id")
                jornadas_raw = request.POST.get("jornadas", "0").strip()
                motivo = request.POST.get("motivo", "").strip()
                if error:
                    pass
                elif not nombre or not apellido:
                    error = "Nombre y apellido son obligatorios."
                elif not categoria_id or not Categoria.objects.filter(id=categoria_id).exists():
                    error = "Selecciona una categoría."
                else:
                    categoria = Categoria.objects.get(id=categoria_id)
                    jornadas = int(jornadas_raw) if jornadas_raw.isdigit() else 0
                    forzar = request.POST.get("forzar") == "1"
                    # Buscar si el jugador ya existe en el universo (CURP o nombre+apellido)
                    already = None
                    if curp:
                        already = Jugador.objects.filter(curp=curp).first()
                    if not already and nombre and apellido:
                        candidatos = [j for j in Jugador.objects.all() if _coincide_nombre(j, nombre, apellido)]
                        if fecha_nac:
                            already = next(
                                (j for j in candidatos if j.fecha_nacimiento == fecha_nac),
                                None,
                            )
                        if not already:
                            already = (
                                next((j for j in candidatos if j.equipo_id), None)
                                or (candidatos[0] if candidatos else None)
                            )
                    if already and not forzar:
                        bloqueado = bool(already.equipo_id)
                        eq_disp = already.equipo.nombre if already.equipo else "sin equipo"
                        datos = {
                            "nombre": already.nombre,
                            "apellido": already.apellido,
                            "curp": already.curp,
                            "fecha_nacimiento": already.fecha_nacimiento,
                            "equipo_id": already.equipo_id,
                        }
                        duplicado = {"jugador": already, "equipo": eq_disp, "bloqueado": bloqueado, "datos": datos}
                        if bloqueado:
                            messages.error(
                                request,
                                f"Ya existe un jugador ({already}) y está registrado con el equipo "
                                f"{already.equipo.nombre} ({already.equipo.categoria.nombre}). "
                                f"Para heredar este jugador usa el botón 'Ya existe' (no ocupará cupo).",
                            )
                        else:
                            messages.warning(
                                request,
                                f"Ya existe el jugador {already} (sin equipo): "
                                f"usa el botón 'Ya existe' para heredarlo.",
                            )
                        raise EarlyReturn(render(request, "league/jugadores_heredados.html", {
                            "categorias": categorias, "q": q, "resultados": [],
                            "duplicado": duplicado, "form_heredar": datos, "seleccionado": {
                                "tipo": tipo, "categoria_id": categoria_id, "jornadas": jornadas_raw, "motivo": motivo,
                            },
                            "heredados": JugadorHerencia.objects.select_related("jugador", "categoria").order_by("-creado")[:50],
                            "error": error,
                        }))
                    # No existe (o se forzó): crear jugador sin equipo
                    if forzar and curp and Jugador.objects.filter(curp=curp).exists():
                        curp = None  # no reutilizar un CURP ya asignado en el universo
                    jugador = Jugador.objects.create(
                        nombre=nombre, apellido=apellido, curp=curp,
                        fecha_nacimiento=fecha_nac, posicion=request.POST.get("posicion", "DEL"),
                    )
                    aplicar_movimiento_a_jugador(jugador, tipo, categoria, jornadas, motivo)
                    if tipo == "VITALICIO":
                        messages.success(request, f"{jugador} creado y expulsado de por vida en {categoria.nombre}.")
                    elif tipo == "CASTIGADO" and jornadas > 0:
                        messages.success(request, f"{jugador} creado y suspendido en {categoria.nombre} ({jornadas} jornada(s)).")
                    else:
                        messages.success(request, f"{jugador} registrado como herencia ({categoria.nombre}).")
                    return redirect("alta_jugadores_heredados")
            elif accion == "eliminar":
                he_id = request.POST.get("herencia_id")
                he = JugadorHerencia.objects.filter(id=he_id).first()
                if not he:
                    error = "Registro de herencia no encontrado."
                else:
                    nombre = str(he.jugador)
                    tipo_nombre = he.get_tipo_display()
                    if he.tipo in ("CASTIGADO", "VITALICIO"):
                        # Al eliminar un castigo heredado se levanta su suspensión
                        SuspensionJugador.objects.filter(jugador=he.jugador, activo=True).update(activo=False)
                        he.delete()
                        messages.success(
                            request,
                            f"Herencia de {nombre} ('{tipo_nombre}') eliminada y su suspensión levantada. "
                            f"Puedes volver a heredarlo para ajustarlo.",
                        )
                    else:
                        he.delete()
                        messages.success(request, f"Herencia de {nombre} ('{tipo_nombre}') eliminada.")
                    return redirect("alta_jugadores_heredados")
            elif accion == "heredar":
                jugador_id = request.POST.get("jugador_id")
                tipo = request.POST.get("tipo", "CASTIGADO")
                categoria_id = request.POST.get("categoria_id")
                jornadas_raw = request.POST.get("jornadas", "0").strip()
                motivo = request.POST.get("motivo", "").strip()
                jugador = Jugador.objects.filter(id=jugador_id).first()
                if not jugador:
                    error = "Jugador no encontrado."
                elif not categoria_id or not Categoria.objects.filter(id=categoria_id).exists():
                    error = "Selecciona una categoría."
                else:
                    categoria = Categoria.objects.get(id=categoria_id)
                    jornadas = int(jornadas_raw) if jornadas_raw.isdigit() else 0
                    if not error:
                        previo = JugadorHerencia.objects.filter(jugador=jugador).exists()
                        if previo:
                            # Corregir/ajustar: se borra el historial previo y se re-registra de cero
                            if tipo in ("CASTIGADO", "VITALICIO") and (tipo == "VITALICIO" or jornadas > 0):
                                activa = SuspensionJugador.objects.filter(jugador=jugador, activo=True).first()
                                cat_prev = f" (categoría anterior: {activa.categoria.nombre})" if activa else ""
                                mensaje_evento = f"Se reemplazó la herencia/suspensión anterior de {jugador}{cat_prev} por la nueva."
                            else:
                                mensaje_evento = f"Se reemplazó la herencia anterior de {jugador} por la nueva."
                            from .reglas_movimientos import reemplazar_herederos
                            reemplazar_herederos(jugador)
                            messages.warning(request, mensaje_evento)
                        aplicar_movimiento_a_jugador(jugador, tipo, categoria, jornadas, motivo)
                        messages.success(request, f"{jugador} registrado como herencia en {categoria.nombre}.")
                        return redirect("alta_jugadores_heredados")
        except EarlyReturn as e:
            return e.response
        except Exception as e:
            error = str(e)

    if q:
        tokens = [_normalizar_texto(t) for t in q.split() if t]
        resultados = []
        for j in Jugador.objects.select_related("equipo__categoria", "equipo").order_by("apellido", "nombre"):
            texto = _normalizar_texto(f"{j.nombre} {j.apellido}")
            if all(tok in texto for tok in tokens):
                resultados.append(j)
        resultados = resultados[:30]

    heredados = (
        JugadorHerencia.objects.select_related("jugador", "categoria")
        .order_by("-creado")[:50]
    )
    return render(request, "league/jugadores_heredados.html", {
        "categorias": categorias,
        "q": q,
        "resultados": resultados,
        "heredados": heredados,
        "error": error,
    })


class EarlyReturn(Exception):
    def __init__(self, response):
        self.response = response


def temporada_movimientos(request, temporada_pk):
    """Cierre de temporada: registrar ascensos/descensos/desapariciones de equipos.

    Al guardar, el sistema mueve la categoría del Equipo (FK) y deja las
    restricciones de los jugadores activas para la siguiente temporada.
    """
    temporada = get_object_or_404(Temporada, pk=temporada_pk)
    cat = temporada.categoria
    cat_sup = cat.categoria_superior()
    cat_inf = cat.categoria_inferior()
    opciones = {"ASCENSO": cat_sup, "DESCENSO": cat_inf}

    if request.method == "POST":
        errores = []
        n_guardados = 0
        filas_post = [
            (int(k[len("tipo_"):]), v)
            for k, v in request.POST.items()
            if k.startswith("tipo_") and k[len("tipo_"):].isdigit()
            and v in ("ASCENSO", "DESCENSO", "DESAPARECE", "SE_QUEDA")
        ]
        for equipo_id, tipo in filas_post:
            equipo = Equipo.objects.filter(id=equipo_id).first()
            if not equipo:
                continue
            destino = opciones.get(tipo)
            if tipo in ("ASCENSO", "DESCENSO") and destino is None:
                errores.append(f"{equipo.nombre}: no existe la categoría {'superior' if tipo == 'ASCENSO' else 'inferior'} para registrarlo.")
                continue
            regla_activa = request.POST.get(f"regla_activa_{equipo_id}") == "1"
            cupo_raw = request.POST.get(f"cupo_pct_{equipo_id}", "").strip()
            cupo_pct = 50
            if cupo_raw.isdigit():
                cupo_pct = min(int(cupo_raw), 100)
            MovimientoEquipo.objects.update_or_create(
                temporada=temporada,
                equipo=equipo,
                defaults={
                    "tipo": tipo,
                    "origen_categoria": cat,
                    "destino_categoria": destino,
                    "jugadores_plantilla": JugadorEquipo.objects.filter(
                        equipo=equipo, activo=True
                    ).count(),
                    "regla_activa": regla_activa,
                    "cupo_porcentaje": cupo_pct,
                },
            )
            if tipo in ("ASCENSO", "DESCENSO"):
                if equipo.categoria_id != destino.id:
                    equipo.categoria = destino
                    equipo.save(update_fields=["categoria"])
                if not equipo.activo:
                    equipo.activo = True
                    equipo.save(update_fields=["activo"])
            elif tipo == "DESAPARECE":
                if equipo.activo:
                    equipo.activo = False
                    equipo.save(update_fields=["activo"])
            else:  # SE_QUEDA
                if not equipo.activo:
                    equipo.activo = True
                    equipo.save(update_fields=["activo"])
            n_guardados += 1
        # Actualizar vigencia/cupo de movimientos ya registrados (aunque el equipo ya haya cambiado de categoría)
        for mov in temporada.movimientos_equipos.all():
            if f"tipo_{mov.equipo_id}" in request.POST:
                continue
            regla = request.POST.get(f"regla_activa_{mov.equipo_id}") == "1"
            cupo_raw = request.POST.get(f"cupo_pct_{mov.equipo_id}", "").strip()
            cupo_pct = mov.cupo_porcentaje
            if cupo_raw.isdigit():
                cupo_pct = min(int(cupo_raw), 100)
            if regla != mov.regla_activa or cupo_pct != mov.cupo_porcentaje:
                mov.regla_activa = regla
                mov.cupo_porcentaje = cupo_pct
                mov.save(update_fields=["regla_activa", "cupo_porcentaje"])
        if errores:
            for e in errores:
                messages.error(request, e)
        else:
            messages.success(
                request,
                f"Movimientos guardados ({n_guardados} equipo{'s' if n_guardados != 1 else ''}). "
                "Las restricciones de ascenso/descenso ya aplican a los jugadores "
                "con la vigencia y cupo configurados.",
            )
        return redirect("temporada_movimientos", temporada_pk=temporada.id)

    # Sugerencias automáticas según la tabla final
    sugerir = temporada.tipo_rol == "TODOS" and not temporada.clasificacion_por_grupos
    asc_candidates = []
    desc_candidates = []
    if sugerir and (cat_sup or cat_inf):
        orden = [r["equipo"] for r in temporada.calcular_tabla()]
        num_asc = temporada.num_ascensos or 0
        num_desc = temporada.num_descensos or 0
        if num_desc and cat_inf and len(orden) >= 1:
            desc_candidates = [e.id for e in orden[-num_desc:]]
        if num_asc and cat_sup and orden:
            campeon = temporada.obtener_campeon()
            if campeon:
                candidatos = [campeon.id]
                if orden[0].id != campeon.id:
                    candidatos.append(orden[0].id)
                elif len(orden) > 1:
                    candidatos.append(orden[1].id)
                asc_candidates = candidatos[:num_asc]
            else:
                asc_candidates = [e.id for e in orden[:num_asc]]

    movimientos = {
        m.equipo_id: m for m in temporada.movimientos_equipos.all()
    }

    # Detalle para gestionar vigencia, cupo y jugadores de cada movimiento
    detalle_movimiento = {}
    for m in movimientos.values():
        plantilla = list(
            JugadorEquipo.objects.filter(equipo=m.equipo, activo=True)
            .select_related("jugador").order_by("jugador__apellido", "jugador__nombre")
        )
        detalle_movimiento[m.equipo_id] = {
            "mov": m,
            "regla_activa": m.regla_activa,
            "cupo_porcentaje": m.cupo_porcentaje,
            "cupo": m.cupo_50(),
            "transferidos": m.transferidos(),
            "plantilla": plantilla,
        }

    tabla = temporada.calcular_tabla() if temporada.tipo_rol == "TODOS" else []
    datos_tabla = {r["equipo"].id: r for r in tabla}
    filas = []
    equipos_cat = Equipo.objects.filter(categoria=cat).order_by("nombre")
    for eq in equipos_cat:
        t = datos_tabla.get(eq.id)
        mov = movimientos.get(eq.id)
        if mov:
            tipo_actual = mov.tipo
        elif eq.id in asc_candidates:
            tipo_actual = "ASCENSO"
        elif eq.id in desc_candidates:
            tipo_actual = "DESCENSO"
        else:
            tipo_actual = "SE_QUEDA"
        filas.append({
            "equipo": eq,
            "pos": t.get("pos") if t else None,
            "pj": t.get("pj") if t else None,
            "pts": t.get("pts") if t else None,
            "tipo_actual": tipo_actual,
        })

    return render(request, "league/temporada_movimientos.html", {
        "temporada": temporada,
        "categoria": cat,
        "cat_superior": cat_sup,
        "cat_inferior": cat_inf,
        "filas": filas,
        "sugerir": sugerir,
        "detalle_movimiento": detalle_movimiento,
    })


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
    allowed = _get_allowed_secondary_categories(eq, jugador)

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
            "edad_minima": acat.edad_minima,
            "edad_maxima": acat.edad_maxima,
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


def _categorias_secundarias_payload(jugador):
    """Equipos secundarios activos del jugador, para refrescar la fila del listado."""
    return [
        {
            "categoria_id": r.equipo.categoria_id,
            "categoria_nombre": r.equipo.categoria.nombre,
            "equipo_id": r.equipo_id,
            "equipo_nombre": r.equipo.nombre,
        }
        for r in jugador.registros_equipo.filter(
            es_principal=False, activo=True
        ).select_related("equipo__categoria").order_by("equipo__categoria__nombre")
    ]


@require_POST
def jugador_agregar_equipo_secundario(request, pk):
    """Registra un EQUIPO SECUNDARIO (categoría compatible) para un jugador.

    No modifica ningún dato del jugador: solo crea o reactiva el registro
    JugadorEquipo con es_principal=False. Reutiliza las mismas reglas de
    negocio ya aplicadas por JugadorForm (compatibilidad de categorías,
    suspensiones, movimientos de ascenso/descenso, edad y períodos de altas),
    de modo que el listado y la pantalla de jugador se comportan igual.
    """
    # --- Permiso: se responde JSON (no redirect) para que el modal lo muestre ---
    user = request.user
    if not (user.is_superuser or user.is_staff or user.tiene_permiso("jugador_editar")):
        return JsonResponse(
            {"ok": False, "error": "No tienes permiso para agregar equipos secundarios."},
            status=403,
        )

    def fallo(mensaje, status=400, extra=None):
        data = {"ok": False, "error": mensaje}
        if extra:
            data.update(extra)
        return JsonResponse(data, status=status)

    jugador = get_object_or_404(Jugador, pk=pk)

    equipo_id = (request.POST.get("equipo_id") or "").strip()
    if not equipo_id.isdigit():
        return fallo("No se recibió un equipo válido.")
    equipo = (Equipo.objects.filter(pk=int(equipo_id), activo=True)
              .select_related("categoria").first())
    if not equipo:
        return fallo("El equipo no existe o está inactivo.", status=404)

    if not jugador.equipo_id:
        return fallo("El jugador no tiene equipo principal, así que no puede tener uno secundario.")

    principal = jugador.equipo
    cat_destino = equipo.categoria

    # ¿Está ya registrado como secundario en ESTA categoría?
    # Si sí, la operación es un CAMBIO de equipo dentro de la categoría.
    registro_actual = jugador.registros_equipo.filter(
        es_principal=False, equipo__categoria_id=cat_destino.pk, activo=True
    ).select_related("equipo__categoria").first()
    es_cambio = registro_actual is not None

    # 1) No agregar el propio equipo principal, ni otro de la MISMA categoría
    #    que la principal. Un cambio de equipo nunca aplica a la principal.
    if equipo.pk == principal.pk:
        return fallo("Ese ya es el equipo principal del jugador.")
    if cat_destino.pk == principal.categoria_id:
        return fallo(
            "{} ya tiene al jugador en la categoría {} y no puede estar en dos equipos "
            "de la misma categoría.".format(principal.nombre, principal.categoria.nombre)
        )
    if es_cambio and registro_actual.equipo_id == equipo.pk:
        # Ya está en ese equipo: no hay nada que cambiar. Se responde ok para
        # que un doble clic no genere un error.
        return JsonResponse({
            "ok": True,
            "cambio": False,
            "sin_cambios": True,
            "mensaje": "{} ya está registrado en {} ({}).".format(
                jugador, equipo.nombre, cat_destino.nombre),
            "avisos": [],
            "equipo": {
                "id": equipo.pk,
                "nombre": equipo.nombre,
                "categoria_id": cat_destino.pk,
                "categoria_nombre": cat_destino.nombre,
            },
            "categorias_secundarias": _categorias_secundarias_payload(jugador),
        })

    # 2) Compatibilidad de categoría: misma regla que aplica el formulario
    #    (compatible con TODAS las categorías donde ya participa).
    from .forms import _get_allowed_secondary_categories
    permitidas = _get_allowed_secondary_categories(principal, jugador)
    if not permitidas.filter(pk=cat_destino.pk).exists():
        return fallo(
            "{} no es una categoría compatible con {} ni con las categorías donde el "
            "jugador ya participa.".format(cat_destino.nombre, principal.categoria.nombre)
        )

    # 3) ¿Ya está registrado en ese equipo?
    ya_registrado = jugador.registros_equipo.filter(equipo=equipo, activo=True).exists()

    # 4) Suspensión activa: bloquea el alta en cualquier equipo nuevo
    susp = SuspensionJugador.objects.filter(jugador=jugador, activo=True).first()
    if susp and not ya_registrado:
        return fallo(
            "No se puede agregar el equipo porque el jugador tiene una suspensión activa "
            "en {} (restan {} jornada(s)).".format(susp.categoria.nombre, susp.restantes())
        )

    # 5) Ascenso / descenso / desaparición de categoría
    from .reglas_movimientos import errores_movimiento_jugador
    errores = list(errores_movimiento_jugador(jugador, equipo, cat_destino))
    if errores:
        return fallo(errores[0], extra={"errores": errores})

    # 6) Edad mínima / máxima de la categoría destino (criterio del formulario)
    edad = jugador.edad()
    if edad is not None:
        if cat_destino.edad_minima is not None and edad < cat_destino.edad_minima:
            return fallo(
                "{} requiere edad mínima de {} años. El jugador tiene {}.".format(
                    cat_destino.nombre, cat_destino.edad_minima, edad)
            )
        if cat_destino.edad_maxima is not None and edad > cat_destino.edad_maxima:
            return fallo(
                "{} permite edad máxima de {} años. El jugador tiene {}.".format(
                    cat_destino.nombre, cat_destino.edad_maxima, edad)
            )

    # 7) Temporada en curso:
    #    - ALTA nueva: hace falta período de altas activo.
    #    - CAMBIO de equipo: hace falta período de altas activo Y que el
    #      jugador no tenga participaciones ya registradas en la categoría.
    temp_activa = Temporada.objects.filter(
        categoria_id=cat_destino.pk, iniciada=True, finalizada=False
    ).order_by("id").first()

    if es_cambio:
        permitido, motivo = _puede_cambiar_equipo_secundario(
            jugador, registro_actual, temporada=temp_activa
        )
        if not permitido:
            return fallo(motivo)
    elif temp_activa and not ya_registrado:
        if not temp_activa.periodos_altas.filter(activo=True).exists():
            return fallo(
                "No hay un período de altas activo en {}, así que no se puede agregar "
                "un equipo en esa categoría.".format(cat_destino.nombre)
            )


    # 8) Aviso de cupo. No bloquea, igual que en la pantalla de jugador.
    avisos = []
    maximo = cat_destino.max_jugadores
    activos = equipo.registros_jugador.filter(activo=True).count()
    if maximo and activos >= maximo:
        avisos.append(
            "{} ya tiene {}/{} jugadores activos.".format(equipo.nombre, activos, maximo)
        )

    # 9) Persistencia idempotente. unique_together = (jugador, equipo) NO mira
    #    'activo', por eso update_or_create en vez de create.
    with transaction.atomic():
        if es_cambio:
            # Cambio de equipo dentro de la categoría: se retira el registro
            # anterior (igual que hace JugadorForm.save) para no dejar al
            # jugador en dos equipos de la misma categoría.
            JugadorEquipo.objects.filter(
                jugador=jugador, es_principal=False,
                equipo__categoria_id=cat_destino.pk
            ).delete()
        JugadorEquipo.objects.update_or_create(
            jugador=jugador,
            equipo=equipo,
            defaults={"es_principal": False, "activo": True},
        )

    return JsonResponse({
        "ok": True,
        "cambio": es_cambio,
        "mensaje": (
            "{} ahora juega en {} ({}).".format(
                jugador, equipo.nombre, cat_destino.nombre)
            if es_cambio else
            "{} agregado a {} ({}).".format(
                jugador, equipo.nombre, cat_destino.nombre)
        ),
        "avisos": avisos,
        "equipo": {
            "id": equipo.pk,
            "nombre": equipo.nombre,
            "categoria_id": cat_destino.pk,
            "categoria_nombre": cat_destino.nombre,
        },
        "categorias_secundarias": _categorias_secundarias_payload(jugador),
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


def regenerar_rol_temporada(request, pk):
    """Regenera el rol desde la jornada X indicada conservando las anteriores.

    Borra las jornadas >= X y regenera el rol con el optimizer, respetando los
    partidos ya capturados a mano en las jornadas < X. Solo se permite si las
    jornadas a borrar no tienen partidos con resultados capturados (PEND).
    """
    temporada = get_object_or_404(Temporada, pk=pk)
    if request.method != "POST":
        return redirect("temporada_list")
    if not request.user.tiene_permiso("temporada_reiniciar"):
        raise PermissionDenied

    raw = request.POST.get("jornada_inicial", "").strip()
    try:
        x = int(raw)
    except (TypeError, ValueError):
        messages.error(request, "Indica a partir de qué jornada regenerar (número entero).")
        return redirect("temporada_list")

    numeros = sorted(temporada.jornadas.values_list("numero", flat=True))
    max_j = max(numeros) if numeros else 0
    if x < 2:
        messages.error(request, "La jornada inicial debe ser al menos 2 (1..N-1 se conservan).")
        return redirect("temporada_list")
    if x > max_j:
        messages.error(request, f"La jornada {x} no existe (máximo creado: {max_j}).")
        return redirect("temporada_list")

    pj = temporada.partidos_por_jornada()
    pasadas = temporada.jornadas.filter(numero__lt=x)
    incompletas = []
    for j in pasadas.order_by("numero"):
        cnt = Partido.objects.filter(temporada=temporada, jornada=j).count()
        if cnt != pj:
            incompletas.append(f"Jornada {j.numero}: {cnt}/{pj}")
    if incompletas:
        messages.error(request, "No se puede: jornadas anteriores incompletas (%d por jornada): %s"
                        % (pj, "; ".join(incompletas)))
        return redirect("temporada_list")

    ok_p, errores_p = temporada.validar_continuacion_rol()
    if not ok_p:
        messages.error(
            request,
            "No se puede completar el rol con las jornadas capturadas: "
            + "; ".join(errores_p),
        )
        return redirect("temporada_list")

    a_borrar = temporada.jornadas.filter(numero__gte=x)
    capturados = Partido.objects.filter(temporada=temporada, jornada__in=a_borrar)\
        .exclude(estado="PEND").exists()
    if capturados:
        messages.error(request, "No se puede: hay partidos con resultados capturados en las "
                        "jornadas a regenerar (>= %d). Bórralos primero o elige otra jornada." % x)
        return redirect("temporada_list")

    n_borrar = a_borrar.count()
    with transaction.atomic():
        Partido.objects.filter(temporada=temporada, jornada__in=a_borrar).delete()
        a_borrar.delete()
        temporada.generar_rol_respaldando_pasadas(jornada_inicial=x)

    nums = sorted(temporada.jornadas.values_list("numero", flat=True))
    por_j = {n: Partido.objects.filter(temporada=temporada, jornada__numero=n).count() for n in nums}
    resumen = ", ".join(f"J{n}:{c}" for n, c in por_j.items())
    messages.success(
        request,
        f"Rol regenerado desde la jornada {x}. Borradas {n_borrar} jornadas. "
        f"Jornadas finales ({len(nums)}): {resumen}."
    )
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


def _secciones_rol():
    """Secciones del rol de la próxima jornada de TODAS las categorías activas."""
    from django.utils import timezone

    ahora = timezone.localtime()
    ahora_str = ahora.strftime("%d/%m/%Y %H:%M")

    from .social_image import _cargar_logo

    def _prioridad_categoria(nombre):
        """Orden jerárquico del rol: Veteranos 50+, Veteranos 35+, Primera,
        Intermedia, Segunda y el resto por orden alfabético."""
        n = (nombre or "").lower()
        for i, clave in enumerate(
            ["veteranos 50", "veteranos 35", "primera", "intermedia", "segunda"]
        ):
            if clave in n:
                return (0, i)
        return (1, n)

    cats = sorted(Categoria.objects.filter(activo=True), key=lambda c: _prioridad_categoria(c.nombre))

    from .models import ConfiguracionLiga
    cfg_liga = ConfiguracionLiga.obtener()
    nombre_liga = (cfg_liga.nombre_liga if cfg_liga else "") or "Mi Liga"
    logo_liga = _cargar_logo(cfg_liga.logo) if cfg_liga else None

    secciones = []
    for cat in cats:
        temp_activa = Temporada.objects.filter(categoria=cat, activa=True).first()
        if not temp_activa:
            continue
        jornada = (
            Jornada.objects.filter(temporada=temp_activa, partidos__estado="PEND")
            .distinct()
            .order_by("numero")
            .first()
        )
        if not jornada:
            continue
        partidos_qs = [
            x for x in Partido.objects.filter(
                temporada=temp_activa, jornada=jornada, estado="PEND"
            ).select_related(
                "equipo_local", "equipo_visitante", "campo"
            ).order_by("fecha_hora")
        ]
        # Incluye partidos FIN resueltos por walkover (DFT) para mostrarlos en el rol.
        partidos_qs += [
            x for x in Partido.objects.filter(
                temporada=temp_activa, jornada=jornada, estado="FIN"
            ).select_related("equipo_local", "equipo_visitante", "campo")
            if x.ganador_walkover is not None
        ]
        if not partidos_qs:
            continue

        ids_juegan = {p.equipo_local_id for p in partidos_qs} | {
            p.equipo_visitante_id for p in partidos_qs
        }
        todos_ids = set(
            Equipo.objects.filter(categoria=cat, activo=True).values_list("id", flat=True)
        )
        descansan_ids = todos_ids - ids_juegan
        descansan = (
            list(Equipo.objects.filter(id__in=descansan_ids).order_by("nombre").values_list("nombre", flat=True))
            if descansan_ids else []
        )

        partidos_data = []
        for p in partidos_qs:
            d = {
                "local": p.equipo_local.nombre,
                "visitante": p.equipo_visitante.nombre,
                "campo": p.campo.nombre if p.campo else "",
                "fecha": timezone.localtime(p.fecha_hora).strftime("%d/%m/%Y %H:%M") if p.fecha_hora else "Pendiente",
                "logo_local": _cargar_logo(p.equipo_local.logo),
                "logo_visitante": _cargar_logo(p.equipo_visitante.logo),
                "marcador": "",
                "is_fin": p.estado == "FIN",
                "local_win": False,
                "vis_win": False,
                "default_win": None,
            }
            if p.estado == "FIN":
                gl, gv = p.goles_local, p.goles_visitante
                d["marcador"] = f"{gl}\u2013{gv}"
                d["local_win"] = gl > gv
                d["vis_win"] = gv > gl
            ganador_dft = p.ganador_walkover
            if ganador_dft:
                if ganador_dft == p.equipo_local:
                    d["default_win"] = "local"
                    d["local_win"] = True
                else:
                    d["default_win"] = "visitante"
                    d["vis_win"] = True
            partidos_data.append(d)
        secciones.append({
            "categoria": cat.nombre,
            "temporada": temp_activa.nombre,
            "jornada": jornada.nombre,
            "partidos": partidos_data,
            "descansan": descansan,
            "nombre_liga": nombre_liga,
            "logo_liga": logo_liga,
        })
    return secciones, ahora_str


def publicar_rol_facebook(request, temporada_id):
    # No se usa temporada_id: se publican los próximos partidos de todas las categorías.
    from .social_image import generar_imagen_rol_dashboard
    from .social import publicar_imagen_en_facebook

    secciones, ahora_str = _secciones_rol()
    if not secciones:
        messages.error(request, "No hay próximos partidos pendientes por publicar.")
        return redirect(request.META.get("HTTP_REFERER", "home"))

    imagen = generar_imagen_rol_dashboard(secciones, ahora_str)
    caption = "\U0001f4cb Próximos partidos - Todas las categorías\n#FutbolLiga"
    publicar_imagen_en_facebook(imagen, caption, request)
    return redirect(request.META.get("HTTP_REFERER", "home"))


def publicar_rol_facebook_todas(request):
    """Publica en Facebook el rol de la próxima jornada de todas las categorías (botón único)."""
    from .social_image import generar_imagen_rol_dashboard
    from .social import publicar_imagen_en_facebook

    secciones, ahora_str = _secciones_rol()
    if not secciones:
        messages.error(request, "No hay próximos partidos pendientes por publicar.")
        return redirect(request.META.get("HTTP_REFERER", "home"))

    imagen = generar_imagen_rol_dashboard(secciones, ahora_str)
    caption = "\U0001f4cb Próximos partidos - Todas las categorías\n#FutbolLiga"
    publicar_imagen_en_facebook(imagen, caption, request)
    return redirect(request.META.get("HTTP_REFERER", "home"))


def descargar_rol_facebook(request):
    """Descarga la imagen del rol de la próxima jornada de todas las categorías (sin publicar)."""
    from django.http import HttpResponse
    from .social_image import generar_imagen_rol_dashboard

    secciones, ahora_str = _secciones_rol()
    if not secciones:
        messages.error(request, "No hay próximos partidos pendientes por generar.")
        return redirect(request.META.get("HTTP_REFERER", "home"))

    buf = generar_imagen_rol_dashboard(secciones, ahora_str)
    nombre = f"rol_todas_categorias_{ahora_str.replace('/', '-').replace(':', '-').replace(' ', '_')}.png"
    response = HttpResponse(buf.getvalue(), content_type="image/png")
    response["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return response


def reporte_registro(request):
    """Reporte de registro de jugadores de un equipo (Categoría→Temporada→Equipo).

    Visible para cualquier usuario autenticado. Solo muestra los jugadores del
    equipo seleccionado con sus datos y foto (sin tablas ni castigados).
    """
    from .models import Categoria, Temporada, Equipo, JugadorEquipo

    cat_id = request.GET.get("categoria") or ""
    temp_id = request.GET.get("temporada") or ""
    eq_id = request.GET.get("equipo") or ""

    categorias = Categoria.objects.filter(activo=True).order_by("nombre")
    temporadas = Temporada.objects.none()
    equipos = Equipo.objects.none()
    jugadores = []
    equipo = None

    if cat_id:
        temporadas = Temporada.objects.filter(categoria_id=cat_id).order_by(
            "-iniciada", "-nombre"
        )
    if cat_id and temp_id:
        equipos = (
            Equipo.objects.active() if hasattr(Equipo.objects, "active") else Equipo.objects.all()
        ).filter(categoria_id=cat_id).order_by("nombre")
    if eq_id:
        equipo = Equipo.objects.filter(pk=eq_id).first()
        if equipo:
            ids = JugadorEquipo.objects.filter(
                equipo=equipo, activo=True
            ).values_list("jugador_id", flat=True)
            from django.db.models import Q
            jugadores = (
                Jugador.objects.filter(
                    Q(pk__in=ids) | Q(equipo=equipo)
                ).distinct()
                .select_related("equipo")
                .order_by("apellido", "nombre")
            )

    ctx = {
        "categorias": categorias,
        "temporadas": temporadas,
        "equipos": equipos,
        "jugadores": jugadores,
        "equipo": equipo,
        "cat_id": cat_id,
        "temp_id": temp_id,
        "eq_id": eq_id,
    }
    if request.GET.get("imprimir"):
        from django.template.loader import render_to_string
        html = render_to_string("league/reporte_registro_print.html", ctx, request=request)
        from django.template.loader import render_to_string
        html = render_to_string("league/reporte_registro_print.html", ctx, request=request)
        from django.http import HttpResponse
        resp = HttpResponse(html)
        resp["Content-Type"] = "text/html; charset=utf-8"
        return resp
    return render(request, "league/reporte_registro.html", ctx)


def enviar_rol_por_correo(request):
    """Envía por correo a los dispositivos registrados: 1 ROL general (imagen de todas las
    categorías, la misma que se publica en Facebook) + 1 correo por cada
    categoría de interés del dispositivo con tabla de posiciones, castigados y
    goleo de esa categoría. Solo staff (ver middleware).
    """
    from .models import ConfiguracionLiga, DeviceToken

    config = ConfiguracionLiga.obtener()
    smtp_host = config.get_active_smtp_config()["host"]
    if not smtp_host:
        messages.error(request, "No hay SMTP configurado.")
        return redirect(request.META.get("HTTP_REFERER", "reporte_registro"))

    secciones, ahora_str = _secciones_rol()
    if not secciones:
        messages.error(request, "No hay próximos partidos pendientes por enviar.")
        return redirect(request.META.get("HTTP_REFERER", "reporte_registro"))

    from .social_image import generar_imagen_rol_dashboard
    from django.utils.html import escape
    from django.template.loader import render_to_string
    from django.utils.html import strip_tags

    buf = generar_imagen_rol_dashboard(secciones, ahora_str)
    adjunto_rol = {
        "cid": "rol",
        "filename": "rol.png",
        "content": buf.getvalue(),
        "mimetype": "image/png",
    }

    class _DeviceEmail:
        __slots__ = ("email", "categorias", "token", "nombre")
        def __init__(self, device):
            self.nombre = device.nombre or (device.usuario.get_full_name() if device.usuario else "") or device.token[:20]
            # Email: prioriza usuario.email, luego device.email
            self.email = device.usuario.email if device.usuario_id and device.usuario.email else device.email
            self.categorias = device.categorias.all()
            # token para unsubscribe (usamos device_id o token)
            self.token = device.device_id or device.token[:32]

    devices = list(
        DeviceToken.objects.filter(activo=True)
        .select_related("usuario")
        .prefetch_related("categorias")
    )
    # Filtrar los que tienen email (usuario.email o device.email)
    destinatarios = [d for d in devices if (d.usuario_id and d.usuario.email) or d.email]
    destinatarios = [_DeviceEmail(d) for d in destinatarios]

    if not destinatarios:
        messages.warning(request, "No hay dispositivos con correo registrado.")
        return redirect(request.META.get("HTTP_REFERER", "reporte_registro"))

    total = 0
    from .models import Temporada, Gol, Tarjeta
    from django.db.models import Count

    for sus in destinatarios:
        # 1) ROL general (mismo para todos): imagen dashboard con todas las categorías.
        ctx_rol = {
            "ahora_str": ahora_str,
            "liga": config,
            "suscriptor_email": sus.email,
        }
        try:
            total += _enviar_correo_suscriptores(
                [sus], config,
                f"Próximos partidos - {ahora_str}",
                "emails/rol_general.html", ctx_rol, request,
                [adjunto_rol],
            )
        except Exception:
            pass

        # 2) Un correo por categoría de interés: tabla + castigados + goleo.
        for cat in sus.categorias:
            temp = Temporada.objects.filter(categoria=cat, activa=True).first()
            if not temp:
                continue
            goleadores = list(
                Gol.objects.filter(partido__temporada=temp)
                .values("jugador__nombre", "jugador__apellido", "equipo__nombre")
                .annotate(total_goles=Count("id"))
                .order_by("-total_goles")[:10]
            )
            tabla_html = temp.calcular_tabla()
            castigados = list(
                Tarjeta.objects.filter(partido__temporada=temp)
                .values("jugador__nombre", "jugador__apellido", "equipo__nombre")
                .annotate(
                    rojas=Count("id", filter=Q(tipo="ROJA")),
                    amarillas=Count("id", filter=Q(tipo="AMARILLA")),
                )
                .order_by("-rojas", "-amarillas")[:10]
            )
            ctx_cat = {
                "temporada": temp,
                "tabla": tabla_html,
                "goleadores": goleadores,
                "castigados": castigados,
                "liga": config,
                "suscriptor_email": sus.email,
                "categoria_nombre": cat.nombre,
            }
            try:
                total += _enviar_correo_suscriptores(
                    [sus], config,
                    f"Estadísticas {cat.nombre} - {ahora_str}",
                    "emails/estadisticas.html", ctx_cat, request,
                )
            except Exception:
                pass

    messages.success(request, f"Correos encolados/enviados: {total}.")
    return redirect(request.META.get("HTTP_REFERER", "reporte_registro"))


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
        ganador_dft = p.ganador_walkover
        if ganador_dft:
            if ganador_dft == p.equipo_local:
                d["default_win"] = "local"
                d["local_win"] = True
            else:
                d["default_win"] = "visitante"
                d["vis_win"] = True
        else:
            d["default_win"] = None
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
        max_cambios = p.temporada.limite_cambios_efectivo() if p.temporada_id else 3
        matches.append({
            "id": p.id,
            "fecha_hora": p.fecha_hora.isoformat(),
            "campo": p.campo.nombre if p.campo else "",
            "estado": p.estado,
            "es_amistoso": p.es_amistoso,
            "es_liguilla": p.es_liguilla,
            "goles_default": p.temporada.goles_default if p.temporada_id else 1,
            "min_jugadores": p.temporada.min_jugadores if p.temporada_id else 7,
            "cambios_permitidos": max_cambios if max_cambios is not None else 99,
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

def quiniela(request):
    """Página de quiniela por categoría: pronósticos de marcador por partido,
    tabs por categoría (estilo home con escuditos) + ranking público."""

    # El contenido de quiniela (pronosticar + ranking) es exclusivo de usuarios
    # registrados. Un anónimo ve una pantalla con 2 salidas: descargar la app
    # o registrarse desde la web (que lo lleva al login).
    if not request.user.is_authenticated:
        return render(request, "league/quiniela_acceso.html", {})

    from django.db.models import Q
    from django.contrib import messages
    from django.utils import timezone
    from django.utils.html import format_html

    categorias = Categoria.objects.filter(activo=True).order_by("nombre")
    cat_sel_id = request.GET.get("categoria")
    categoria = None
    if cat_sel_id:
        categoria = Categoria.objects.filter(pk=cat_sel_id, activo=True).first()
    if not categoria:
        categoria = categorias.first()

    partidos = Partido.objects.none()
    temporada = None
    jornada_actual = None
    if categoria:
        temporada = Temporada.objects.filter(categoria=categoria, activa=True).order_by("-fecha_inicio", "-fecha_fin").first()
        if temporada:
            proximo = (
                Partido.objects.filter(temporada=temporada, estado="PEND")
                .select_related("jornada")
                .order_by("fecha_hora")
                .first()
            )
            jornada_actual = proximo.jornada if proximo else None
            if jornada_actual:
                partidos = (
                    Partido.objects.filter(jornada=jornada_actual)
                    .select_related("equipo_local", "equipo_visitante", "jornada")
                    .exclude(estado="SUSP")
                    .order_by("fecha_hora")
                )

    pronosticos = {}
    if request.user.is_authenticated:
        for pr in PronosticoQuiniela.objects.filter(usuario=request.user, partido_id__in=partidos.values_list("id", flat=True)):
            pronosticos[pr.partido_id] = pr

    if request.method == "POST" and request.user.is_authenticated:
        partido_id = request.POST.get("partido_id")
        goles_local = request.POST.get("goles_local", "").strip()
        goles_visitante = request.POST.get("goles_visitante", "").strip()
        accion = request.POST.get("accion")
        partido = partidos.filter(pk=partido_id).first() if accion == "guardar" else None

        if accion == "guardar" and partido:
            if not (goles_local.isdigit() or goles_local == ""):
                messages.error(request, "Marca inválida para el gol local.")
            elif not (goles_visitante.isdigit() or goles_visitante == ""):
                messages.error(request, "Marca inválida para el gol visitante.")
            elif partido.estado != "PEND":
                messages.error(request, "Este partido ya no puede pronosticarse (iniciado o finalizado).")
            else:
                local = int(goles_local) if goles_local != "" else None
                visitante = int(goles_visitante) if goles_visitante != "" else None
                if local is None or visitante is None:
                    messages.error(request, "Debes indicar un marcador en ambos equipos.")
                else:
                    PronosticoQuiniela.objects.update_or_create(
                        usuario=request.user, partido=partido,
                        defaults={"goles_local": local, "goles_visitante": visitante},
                    )
                    messages.success(request, "Pronóstico guardado. ¡2 pts marcador exacto, 1 pt solo signo!")
        elif accion == "borrar" and partido:
            PronosticoQuiniela.objects.filter(usuario=request.user, partido=partido).delete()
            messages.success(request, "Pronóstico eliminado.")

        url_destino = reverse("quiniela")
        if categoria:
            url_destino = f"{url_destino}?categoria={categoria.pk}"
        return redirect(url_destino)

    pendientes = [p for p in partidos if p.estado == "PEND"]
    finalizados = [p for p in partidos if p.estado != "PEND"]

    context = {
        "categorias": categorias,
        "categoria": categoria,
        "temporada": temporada,
        "jornada_actual": jornada_actual,
        "pendientes": pendientes,
        "finalizados": finalizados,
        "pronosticos": pronosticos,
    }
    return render(request, "league/quiniela.html", context)


def historico_quiniela(request):
    """Histórico de la quiniela: partidos ya finalizados de la temporada, con el
    resultado real, el pronóstico del usuario (si lo hubo) y los puntos por jornada."""

    if not request.user.is_authenticated:
        return render(request, "league/quiniela_acceso.html", {})

    categorias = Categoria.objects.filter(activo=True).order_by("nombre")
    cat_sel_id = request.GET.get("categoria")
    categoria = None
    if cat_sel_id:
        categoria = Categoria.objects.filter(pk=cat_sel_id, activo=True).first()
    if not categoria:
        categoria = categorias.first()

    solo_mios = request.GET.get("solo_mios") in ("1", "on", "true")

    temporada = None
    jornadas = []
    total_puntos = 0
    total_aciertos = 0
    total_jugados = 0
    if categoria:
        temporada = Temporada.objects.filter(categoria=categoria, activa=True).order_by("-fecha_inicio", "-fecha_fin").first()
        if temporada:
            partidos = (
                Partido.objects.filter(temporada=temporada, estado="FIN")
                .select_related("equipo_local", "equipo_visitante", "jornada")
                .order_by("-jornada__numero", "fecha_hora")
            )
            pronosticos = {
                pr.partido_id: pr
                for pr in PronosticoQuiniela.objects.filter(usuario=request.user, partido__in=partidos)
            }
            grupos = {}
            for p in partidos:
                pr = pronosticos.get(p.pk)
                if solo_mios and pr is None:
                    continue
                g = grupos.get(p.jornada_id)
                if g is None:
                    g = {"jornada": p.jornada, "items": [], "puntos": 0, "aciertos": 0, "jugados": 0}
                    grupos[p.jornada_id] = g
                g["items"].append({"partido": p, "pronostico": pr})
                if pr:
                    pts = pr.puntos
                    g["puntos"] += pts
                    g["jugados"] += 1
                    total_puntos += pts
                    total_jugados += 1
                    if pts > 0:
                        g["aciertos"] += 1
                        total_aciertos += 1
            jornadas = list(grupos.values())

    context = {
        "categorias": categorias,
        "categoria": categoria,
        "temporada": temporada,
        "jornadas": jornadas,
        "solo_mios": solo_mios,
        "total_puntos": total_puntos,
        "total_aciertos": total_aciertos,
        "total_jugados": total_jugados,
    }
    return render(request, "league/quiniela_historico.html", context)


def ranking_quiniela(request):
    from django.db.models import Count, Sum
    ranking = []
    cat_sel = request.GET.get("categoria")
    categorias = Categoria.objects.filter(activo=True).order_by("nombre")
    categoria = categorias.filter(pk=cat_sel).first() if cat_sel else categorias.first()

    if categoria:
        temporada = Temporada.objects.filter(categoria=categoria, activa=True).order_by("-fecha_inicio", "-fecha_fin").first()
        if temporada:
                pronosticos = (
                    PronosticoQuiniela.objects
                    .filter(partido__temporada=temporada)
                    .select_related("usuario", "partido")
                )
                puntos_por_usuario = {}
                conteo_por_usuario = {}
                for pr in pronosticos:
                    uid = pr.usuario_id
                    puntos_por_usuario[uid] = puntos_por_usuario.get(uid, 0) + pr.puntos
                    conteo_por_usuario[uid] = conteo_por_usuario.get(uid, 0) + 1
                ids = list(puntos_por_usuario.keys())
                User = get_user_model()
                usuarios = (
                    User.objects.filter(pk__in=ids)
                    .values("id", "username", "first_name", "last_name")
                    if ids else User.objects.none()
                )
                for i, usr in enumerate(usuarios, 1):
                    nombre = (usr["first_name"] or "") + (" " + usr["last_name"] if usr["last_name"] else "")
                    ranking.append({
                        "posicion": i,
                        "usuario": usr["username"],
                        "nombre": nombre.strip() or usr["username"],
                        "puntos": puntos_por_usuario.get(usr["id"], 0),
                        "pronosticos": conteo_por_usuario.get(usr["id"], 0),
                    })

    context = {"ranking": ranking, "categorias": categorias, "categoria": categoria}
    return render(request, "league/ranking_quiniela.html", context)
