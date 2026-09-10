from django.shortcuts import render
from django.db.models import Sum, Count
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from league.models import Partido, Gol, Categoria, Temporada, Equipo, Tarjeta, SuspensionJugador
from league.storage import url_para_nombre
from django.db.models import Q
from finance.models import Ingreso


class _EnvelopeManual:
    """Adapta una SuspensionJugador a la forma que espera home.html."""
    es_manual = True

    def __init__(self, record, restantes):
        self.jugador = record.jugador
        self.equipo = record.equipo
        self.suspension_jornadas = record.jornadas
        self.vitalicia = record.vitalicia
        self.motivo = record.motivo
        self.fecha_creacion = record.creado
        self.partido = None
        self.pendientes = []
        self.restantes = restantes


def health(request):
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False
    return JsonResponse({"status": "ok" if db_ok else "degraded", "db": db_ok}, status=200 if db_ok else 503)


def home(request):
    categorias = Categoria.objects.filter(activo=True)

    cat_id = request.GET.get("categoria")
    if cat_id:
        categoria_sel = Categoria.objects.filter(id=cat_id).first()
    else:
        default_cat = None
        if request.user.is_authenticated and request.user.categoria_preferida:
            default_cat = request.user.categoria_preferida
        elif not request.user.is_authenticated:
            # Invitado: su categoría principal (la primera que escogió al registrarse)
            pref_id = request.COOKIES.get("cat_preferida")
            if pref_id:
                default_cat = Categoria.objects.filter(id=pref_id, activo=True).first()
        if default_cat is None:
            default_cat = Categoria.objects.filter(es_principal=True).first()
        categoria_sel = default_cat or categorias.first()

    if categoria_sel:
        temp_activa = Temporada.objects.filter(
            categoria=categoria_sel, activa=True
        ).first()
    else:
        temp_activa = None

    # Próximos partidos: solo de la jornada activa (la primera con partidos pendientes)
    from league.models import Jornada
    equipo_descansa = None
    proximos_amistosos = Partido.objects.filter(
        es_amistoso=True, estado="PEND"
    ).select_related(
        "equipo_local", "equipo_visitante", "campo"
    ).order_by("fecha_hora")[:5]

    if temp_activa:
        jornada_activa = (
            Jornada.objects.filter(temporada=temp_activa, partidos__estado="PEND")
            .distinct()
            .order_by("numero")
            .first()
        )
        if jornada_activa:
            proximos_liga = Partido.objects.filter(
                temporada=temp_activa, jornada=jornada_activa, estado="PEND"
            ).select_related(
                "equipo_local", "equipo_visitante", "campo", "jornada"
            ).order_by("fecha_hora")
            ids_juegan = set(
                proximos_liga.values_list("equipo_local_id", flat=True)
            ) | set(
                proximos_liga.values_list("equipo_visitante_id", flat=True)
            )
            todos_ids = set(
                Equipo.objects.filter(categoria=categoria_sel, activo=True)
                .values_list("id", flat=True)
            )
            descansan_ids = todos_ids - ids_juegan
            equipo_descansa = Equipo.objects.filter(id__in=descansan_ids) if descansan_ids else None
        else:
            proximos_liga = []
            equipo_descansa = None
        proximos = sorted(
            list(proximos_liga) + list(proximos_amistosos),
            key=lambda p: p.fecha_hora or timezone.datetime.min
        )
    else:
        proximos = list(proximos_amistosos)

    # Resultados recientes de la categoría
    res_filter = Partido.objects.filter(estado="FIN")
    if categoria_sel:
        res_filter = res_filter.filter(temporada__categoria=categoria_sel)

    resultados = res_filter.select_related(
        "equipo_local", "equipo_visitante"
    ).order_by("-fecha_hora")[:5]

    # Stats por categoría seleccionada
    stats = {}
    if categoria_sel:
        temp_id = temp_activa.id if temp_activa else None
        stats[categoria_sel] = {
            "equipos": Equipo.objects.filter(categoria=categoria_sel, activo=True).count(),
            "partidos_fin": Partido.objects.filter(
                temporada__categoria=categoria_sel, estado="FIN"
            ).count(),
            "partidos_pend": Partido.objects.filter(
                temporada__categoria=categoria_sel, estado="PEND"
            ).count(),
            "jugadores": Equipo.objects.filter(
                categoria=categoria_sel, activo=True
            ).aggregate(total=Count("jugadores"))["total"] or 0,
            "categoria": categoria_sel,
            "temporada_activa": temp_activa,
            "temp_id": temp_id,
        }

    # Top goleadores con datos para cards (separados por liguilla)
    def _con_urls(lista):
        out = []
        for d in lista:
            d = dict(d)
            d["equipo__logo_url"] = url_para_nombre(d.get("equipo__logo"))
            d["jugador__foto_url"] = url_para_nombre(d.get("jugador__foto"))
            out.append(d)
        return out

    def _build_top_goleadores(es_liguilla):
        qs = Gol.objects.filter(partido__es_liguilla=es_liguilla)
        if categoria_sel:
            qs = qs.filter(partido__temporada__categoria=categoria_sel)
        return list(
            qs
            .values(
                "jugador__id", "jugador__nombre", "jugador__apellido",
                "jugador__foto", "jugador__dorsal",
                "equipo__nombre", "equipo__logo",
            )
            .annotate(total=Count("id"))
            .order_by("-total")[:5]
        )

    top_goleadores = _con_urls(_build_top_goleadores(False))   # temporada regular
    top_goleadores_finales = _con_urls(_build_top_goleadores(True))  # liguilla / finales

    # Top tarjetas amarillas
    amar_filter = Tarjeta.objects.filter(tipo="AMARILLA")
    rojas_filter = Tarjeta.objects.filter(tipo="ROJA")
    if categoria_sel:
        amar_filter = amar_filter.filter(partido__temporada__categoria=categoria_sel)
        rojas_filter = rojas_filter.filter(partido__temporada__categoria=categoria_sel)

    top_amarillas = _con_urls(
        amar_filter
        .values(
            "jugador__id", "jugador__nombre", "jugador__apellido",
            "jugador__foto", "jugador__dorsal",
            "equipo__nombre", "equipo__logo",
        )
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    top_rojas = _con_urls(
        rojas_filter
        .values(
            "jugador__id", "jugador__nombre", "jugador__apellido",
            "jugador__foto", "jugador__dorsal",
            "equipo__nombre", "equipo__logo",
        )
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )

    # Castigados — jugadores con roja y suspension_jornadas > 0
    cast_filter = Tarjeta.objects.filter(tipo="ROJA", suspension_jornadas__gt=0)
    if categoria_sel:
        cast_filter = cast_filter.filter(partido__temporada__categoria=categoria_sel)
    castigados = (
        cast_filter
        .select_related("jugador", "equipo", "partido__jornada")
        .order_by("-partido__fecha_hora")
    )
    castigados = list(castigados)

    # Suspensiones manuales activas de la categoría
    manual_qs = SuspensionJugador.objects.filter(activo=True).select_related("jugador", "equipo")
    if categoria_sel:
        manual_qs = manual_qs.filter(categoria=categoria_sel)
    for m in manual_qs:
        if m.jugador_id in {getattr(c, "jugador_id", None) for c in castigados}:
            continue
        if m.restantes() <= 0:
            continue
        rst = m.restantes()
        castigados.append(_EnvelopeManual(m, rst))

    _sort_base = timezone.now()
    castigados.sort(
        key=lambda c: (getattr(getattr(c, "partido", None), "fecha_hora", None)
                       or getattr(c, "fecha_creacion", None) or _sort_base),
        reverse=True,
    )
    castigados = castigados[:5]  # top 5 en el dashboard; el resto en "Ver todos"

    finanzas_visible = (
        request.user.is_authenticated
        and request.user.rol
        and request.user.rol.permisos.get("ver_finanzas", False)
    )

    ingresos_data = None
    if finanzas_visible:
        hoy = timezone.now()
        mes_act = hoy.month
        anio_act = hoy.year
        qs_mes = Ingreso.objects.filter(fecha__month=mes_act, fecha__year=anio_act)
        total_ingresos = qs_mes.filter(concepto__tipo="INGRESO").aggregate(total=Sum("monto"))["total"] or 0
        total_egresos = qs_mes.filter(concepto__tipo="EGRESO").aggregate(total=Sum("monto"))["total"] or 0
        ingresos_data = {
            "total_mes": total_ingresos - total_egresos,
            "total_ingresos": total_ingresos,
            "total_egresos": total_egresos,
            "por_concepto": (
                qs_mes.values("concepto__nombre", "concepto__tipo")
                .annotate(total=Sum("monto"))
                .order_by("-total")[:10]
            ),
        }

    return render(request, "home.html", {
        "proximos": proximos,
        "resultados": resultados,
        "stats": stats,
        "top_goleadores": top_goleadores,
        "top_goleadores_finales": top_goleadores_finales,
        "top_amarillas": top_amarillas,
        "top_rojas": top_rojas,
        "castigados": castigados,
        "categorias": categorias,
        "categoria_sel": categoria_sel,
        "finanzas_visible": finanzas_visible,
        "ingresos_data": ingresos_data,
        "equipo_descansa": equipo_descansa,
    })

def change_server(request):
    return render(request, "change_server.html")
