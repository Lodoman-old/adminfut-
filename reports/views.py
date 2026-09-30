from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.timezone import localtime
from reportlab.lib.pagesizes import letter, landscape
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import Table, TableStyle
from reportlab.lib.utils import simpleSplit
from django.db.models import Sum, Q, Count
from collections import Counter
import openpyxl
from io import BytesIO
import os
import math
from django.conf import settings
from league.models import Partido, Gol, Temporada, Equipo, Jugador, Jornada, Tarjeta, Arbitro, JugadorPartido, Categoria, ConfiguracionLiga, SuscripcionEmail, SuspensionJugador, JugadorEquipo
from finance.models import Ingreso, ConceptoIngreso


def draw_header(p, width, height, extra_line=""):
    """Dibuja el encabezado de la liga (logo, nombre, datos de contacto) en el PDF.
    Retorna la posici?n Y despu?s del encabezado."""
    from reportlab.lib import colors
    cfg = ConfiguracionLiga.obtener()
    y = height - 30

    # Logo
    logo_src = None
    if cfg.logo:
        local_path = os.path.join(settings.MEDIA_ROOT, cfg.logo.name)
        if os.path.exists(local_path):
            logo_src = local_path
        else:
            logo_src = _imagen_pdf(cfg.logo)
    if logo_src:
        try:
            p.drawImage(logo_src, 30, y - 25, width=50, height=50, preserveAspectRatio=True, mask='auto')
        except Exception:
            pass
        x_text = 90
    else:
        x_text = 30

    # Nombre de la liga
    p.setFont("Helvetica-Bold", 14)
    p.drawString(x_text, y - 5, cfg.nombre_liga)

    # Direcci?n y tel?fonos
    y2 = y - 22
    p.setFont("Helvetica", 8)
    datos = []
    if cfg.direccion:
        datos.append(cfg.direccion.replace("\n", ", "))
    if cfg.telefonos:
        datos.append(f"Tel: {cfg.telefonos}")
    if cfg.correo_electronico:
        datos.append(cfg.correo_electronico)
    if datos:
        p.drawString(x_text, y2, " | ".join(datos))

    # L?nea separadora
    y_sep = y2 - 8
    p.setStrokeColor(colors.HexColor("#2d5a27"))
    p.setLineWidth(1.5)
    p.line(30, y_sep, width - 30, y_sep)

    # L?nea extra (categor?a, temporada, etc.)
    if extra_line:
        lines = extra_line.split("\n")
        y_line = y_sep - 16
        for line in lines:
            p.setFont("Helvetica-Bold", 11)
            p.setFillColor(colors.HexColor("#2d5a27"))
            p.drawString(x_text, y_line, line)
            p.setFillColor(colors.black)
            y_line -= 14
        return y_line - 5
    return y_sep - 10


def draw_footer(p, width, height, font_size=7):
    """Dibuja el pie de p?gina (redes sociales)."""
    cfg = ConfiguracionLiga.obtener()
    if cfg.redes_sociales:
        p.setFont("Helvetica", font_size)
        p.setFillColor(colors.grey)
        lineas = cfg.redes_sociales.split("\n")
        y = 30
        for linea in lineas:
            linea = linea.strip()
            if linea:
                p.drawString(30, y, linea)
                y -= 10
        p.setFillColor(colors.black)


def reporte_posiciones_pdf(request):
    temp_id = request.GET.get("temporada")
    cat_id = request.GET.get("categoria")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=posiciones.pdf"

    p = canvas.Canvas(response, pagesize=landscape(letter))
    width, height = landscape(letter)

    extra = "Tabla de Posiciones"
    partes_extra = [extra]
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        partes_extra.append(f"Temporada: {temp.nombre}")
    if cat_id:
        cat = Categoria.objects.filter(id=cat_id).first()
        if cat:
            partes_extra.append(f"Categor?a: {cat.nombre}")
    extra = "\n".join(partes_extra)
    y = draw_header(p, width, height, extra)

    if temp_id:
        temp = Temporada.objects.get(pk=temp_id)

        grupos_mode = temp.tipo_rol == "GRUPOS" and temp.clasificacion_por_grupos
        if grupos_mode:
            tablas_por_grupo = temp.calcular_tablas_por_grupo()
            grupos = temp.grupos_asignados()
            ng = len(grupos)
            por_grupo = max(1, temp.num_clasificados // max(ng, 1)) if ng else 0
            y_base = y
            for grupo_letra, grupo_tabla in tablas_por_grupo:
                data = [["#", "Equipo", "PJ", "PG", "PE", "PP", "GF", "GC", "DIF", "PTS"]]
                for i, t in enumerate(grupo_tabla, 1):
                    data.append([i, t["equipo"].nombre, t["pj"], t["pg"], t["pe"], t["pp"], t["gf"], t["gc"], t["gf"] - t["gc"], t["pts"]])
                p.setFont("Helvetica-Bold", 11)
                p.drawString(30, y_base, f"Grupo {grupo_letra}")
                y_base -= 15
                table = Table(data, colWidths=[30, 200, 40, 40, 40, 40, 40, 40, 40, 40])
                style_cmds = [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 10),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ]
                for i in range(1, min(por_grupo, len(grupo_tabla)) + 1):
                    style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.Color(0.831, 0.929, 0.831)))
                table.setStyle(TableStyle(style_cmds))
                th = len(data) * 20
                y_base -= th
                if y_base < 50:
                    p.showPage()
                    y_base = height - 60
                table.wrapOn(p, 30, y_base)
                table.drawOn(p, 30, y_base)
                y_base -= 20
        else:
            tabla = temp.calcular_tabla()

            data = [["#", "Equipo", "PJ", "PG", "PE", "PP", "GF", "GC", "DIF", "PTS"]]
            clasif = temp.num_clasificados
            for i, t in enumerate(tabla, 1):
                data.append([i, t["equipo"].nombre, t["pj"], t["pg"], t["pe"], t["pp"], t["gf"], t["gc"], t["gf"] - t["gc"], t["pts"]])

            table = Table(data, colWidths=[30, 200, 40, 40, 40, 40, 40, 40, 40, 40])
            style_cmds = [
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]
            for i in range(1, min(clasif, len(tabla)) + 1):
                style_cmds.append(("BACKGROUND", (0, i), (-1, i), colors.Color(0.831, 0.929, 0.831)))
            table.setStyle(TableStyle(style_cmds))
            table.wrapOn(p, 30, y - 20)
            table.drawOn(p, 30, y - 20 - len(data) * 20)

    draw_footer(p, width, height)
    p.showPage()
    p.save()
    return response


def reporte_goleo_pdf(request):
    temp_id = request.GET.get("temporada")
    cat_id = request.GET.get("categoria")
    jornada_id = request.GET.get("jornada")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=goleo.pdf"

    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter

    extra = "Tabla de Goleo"
    partes_extra = [extra]
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        partes_extra.append(f"Temporada: {temp.nombre}")
    if cat_id:
        cat = Categoria.objects.filter(id=cat_id).first()
        if cat:
            partes_extra.append(f"Categor?a: {cat.nombre}")
    if jornada_id:
        j = Jornada.objects.filter(id=jornada_id).first()
        if j:
            partes_extra.append(f"Jornada: {j.nombre}")
    extra = "\n".join(partes_extra)
    y = draw_header(p, width, height, extra)

    if temp_id:
        from django.db.models import Count
        goleadores = (
            Gol.objects.filter(partido__temporada_id=temp_id)
            .values("jugador__nombre", "jugador__apellido", "equipo__nombre")
            .annotate(total=Count("id"))
            .order_by("-total")
        )

        data = [["#", "Jugador", "Equipo", "Goles"]]
        for i, g in enumerate(goleadores, 1):
            data.append([i, f"{g['jugador__nombre']} {g['jugador__apellido']}", g["equipo__nombre"], g["total"]])

        table = Table(data, colWidths=[30, 200, 150, 60])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        table.wrapOn(p, 30, y - 20)
        table.drawOn(p, 30, y - 20 - len(data) * 20)

    draw_footer(p, width, height)
    p.showPage()
    p.save()
    return response


def reporte_ingresos_pdf(request):
    cat_id = request.GET.get("categoria")
    temp_id = request.GET.get("temporada")
    concepto_id = request.GET.get("concepto")
    fecha_desde = request.GET.get("fecha_desde")
    fecha_hasta = request.GET.get("fecha_hasta")
    tipo_filtro = request.GET.get("tipo", "")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=movimientos.pdf"

    p = canvas.Canvas(response, pagesize=landscape(letter))
    width, height = landscape(letter)

    extra = "Reporte de Movimientos"
    partes_extra = [extra]
    if temp_id:
        temp = Temporada.objects.filter(id=temp_id).first()
        if temp:
            partes_extra.append(f"Temporada: {temp.nombre}")
    if cat_id:
        cat = Categoria.objects.filter(id=cat_id).first()
        if cat:
            partes_extra.append(f"Categor?a: {cat.nombre}")
    if concepto_id:
        from finance.models import ConceptoIngreso
        conc = ConceptoIngreso.objects.filter(id=concepto_id).first()
        if conc:
            partes_extra.append(f"Concepto: {conc.nombre}")
    if tipo_filtro:
        partes_extra.append(f"Tipo: {'Ingresos' if tipo_filtro == 'INGRESO' else 'Egresos'}")
    if fecha_desde:
        partes_extra.append(f"Desde: {fecha_desde}")
    if fecha_hasta:
        partes_extra.append(f"Hasta: {fecha_hasta}")
    extra = "\n".join(partes_extra)
    y = draw_header(p, width, height, extra)

    qs = Ingreso.objects.select_related("concepto", "equipo", "registrado_por")
    if temp_id:
        qs = qs.filter(temporada_id=temp_id)
    else:
        qs = qs.exclude(temporada__finalizada=True)
    if concepto_id:
        qs = qs.filter(concepto_id=concepto_id)
    if tipo_filtro:
        qs = qs.filter(concepto__tipo=tipo_filtro)
    if fecha_desde:
        qs = qs.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha__lte=fecha_hasta)
    ingresos = qs.order_by("-fecha")

    data = [["#", "Concepto", "Tipo", "Monto", "Fecha", "Equipo", "Registrado por"]]
    for i, ing in enumerate(ingresos, 1):
        data.append([
            i, ing.concepto.nombre,
            "Ingreso" if ing.es_ingreso else "Egreso",
            f"${ing.monto}", ing.fecha,
            ing.equipo.nombre if ing.equipo else "-",
            ing.registrado_por.username if ing.registrado_por else "-",
        ])

    table = Table(data, colWidths=[25, 130, 60, 70, 70, 120, 100])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
    ]))
    table.wrapOn(p, width - 60, height)
    needed = table._height + 20
    if y - needed < 40:
        draw_footer(p, width, height)
        p.showPage()
        y = height - 30
        y = draw_header(p, width, height, extra)
    table.drawOn(p, 30, y - needed)

    draw_footer(p, width, height)
    p.showPage()
    p.save()
    return response


def reporte_tarjetas_pdf(request):
    temp_id = request.GET.get("temporada")
    cat_id = request.GET.get("categoria")
    jornada_id = request.GET.get("jornada")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=tarjetas.pdf"
    p = canvas.Canvas(response, pagesize=letter)
    width, height = letter
    extra = "Tabla de Tarjetas"
    partes_extra = [extra]
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        partes_extra.append(f"Temporada: {temp.nombre}")
    if cat_id:
        cat = Categoria.objects.filter(id=cat_id).first()
        if cat:
            partes_extra.append(f"Categor?a: {cat.nombre}")
    if jornada_id:
        j = Jornada.objects.filter(id=jornada_id).first()
        if j:
            partes_extra.append(f"Jornada: {j.nombre}")
    extra = "\n".join(partes_extra)
    y = draw_header(p, width, height, extra)

    if temp_id:
        amarillas = (Tarjeta.objects.filter(partido__temporada_id=temp_id, tipo="AMARILLA")
                     .values("jugador__nombre", "jugador__apellido", "equipo__nombre")
                     .annotate(total=Count("id")).order_by("-total"))
        rojas = (Tarjeta.objects.filter(partido__temporada_id=temp_id, tipo="ROJA")
                 .values("jugador__nombre", "jugador__apellido", "equipo__nombre")
                 .annotate(total=Count("id")).order_by("-total"))
        p.setFont("Helvetica-Bold", 12)
        p.drawString(30, y - 10, "Amarillas")
        data_a = [["#", "Jugador", "Equipo", "Total"]]
        for i, t in enumerate(amarillas, 1):
            data_a.append([i, f"{t['jugador__nombre']} {t['jugador__apellido']}", t["equipo__nombre"], t["total"]])
        table_a = Table(data_a, colWidths=[30, 180, 150, 50])
        table_a.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        table_a.wrapOn(p, 30, y - 40)
        table_a.drawOn(p, 30, y - 40 - len(data_a) * 18)
        y_rojas = y - 60 - len(data_a) * 18
        p.setFont("Helvetica-Bold", 12)
        p.drawString(30, y_rojas, "Rojas")
        data_r = [["#", "Jugador", "Equipo", "Total"]]
        for i, t in enumerate(rojas, 1):
            data_r.append([i, f"{t['jugador__nombre']} {t['jugador__apellido']}", t["equipo__nombre"], t["total"]])
        table_r = Table(data_r, colWidths=[30, 180, 150, 50])
        table_r.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        table_r.wrapOn(p, 30, y_rojas - 20)
        table_r.drawOn(p, 30, y_rojas - 20 - len(data_r) * 18)
    draw_footer(p, width, height)
    p.showPage()
    p.save()
    return response


def reporte_castigados_pdf(request):
    temp_id = request.GET.get("temporada")
    cat_id = request.GET.get("categoria")
    jornada_id = request.GET.get("jornada")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=castigados.pdf"
    from reportlab.lib.pagesizes import landscape
    p = canvas.Canvas(response, pagesize=landscape(letter))
    width, height = landscape(letter)
    extra = "Jugadores Castigados"
    partes_extra = [extra]
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        partes_extra.append(f"Temporada: {temp.nombre}")
    if cat_id:
        cat = Categoria.objects.filter(id=cat_id).first()
        if cat:
            partes_extra.append(f"Categor?a: {cat.nombre}")
    if jornada_id:
        j = Jornada.objects.filter(id=jornada_id).first()
        if j:
            partes_extra.append(f"Jornada: {j.nombre}")
    extra = "\n".join(partes_extra)
    y = draw_header(p, width, height, extra)

    if temp_id:
        from league.views import _suspensiones_temporada
        from reportlab.platypus import Paragraph
        from reportlab.lib.styles import ParagraphStyle
        ps = ParagraphStyle("cell", fontSize=8, leading=10, alignment=0)
        temp = Temporada.objects.get(id=temp_id)
        susp_dict = _suspensiones_temporada(temp)
        castigados = Tarjeta.objects.filter(
            tipo="ROJA", suspension_jornadas__gt=0,
            partido__temporada_id=temp_id,
        ).select_related("jugador", "equipo", "partido__jornada").order_by("-partido__fecha_hora")
        data = [["#", "Jugador", "Equipo", "Susp.", "Expulsi?n", "Pendientes"]]
        procesados = set()
        for i, c in enumerate(castigados, 1):
            info = susp_dict.get(c.jugador_id)
            restantes = info["restantes"] if info else 0
            if restantes > 0:
                procesados.add(c.jugador_id)
                pend_list = info["pendientes"]
                if pend_list:
                    pend_text = "; ".join(
                        f"{p.equipo_local} vs {p.equipo_visitante} ({p.jornada.nombre})"
                        for p in pend_list
                    )
                else:
                    pend_text = f"Pendiente ({restantes}) - pr?xima temporada"
            else:
                pend_text = "Cumplida"
            data.append([
                i,
                Paragraph(f"{c.jugador.nombre} {c.jugador.apellido}", ps),
                Paragraph(c.equipo.nombre, ps),
                c.suspension_jornadas,
                Paragraph(f"{c.partido.equipo_local} - {c.partido.equipo_visitante} ({c.partido.jornada.nombre})", ps),
                Paragraph(pend_text, ps),
            ])
        for jug_id in list(susp_dict):
            if jug_id in procesados or not susp_dict[jug_id].get("es_manual"):
                continue
            info = susp_dict[jug_id]
            if info["restantes"] <= 0:
                continue
            env = info["_tarjeta"]
            pend_list = info["pendientes"]
            if getattr(env, "vitalicia", False):
                pend_text = "Por vida"
                susp_col = "Por vida"
            elif pend_list:
                pend_text = "; ".join(
                    f"{p.equipo_local} vs {p.equipo_visitante} ({p.jornada.nombre})"
                    for p in pend_list
                )
                susp_col = env.suspension_jornadas
            else:
                pend_text = f"Pendiente ({info['restantes']}) - pr?xima temporada"
                susp_col = env.suspension_jornadas
            data.append([
                len(data),
                Paragraph(f"{env.jugador.nombre} {env.jugador.apellido}", ps),
                Paragraph(env.equipo.nombre if env.equipo else "Expulsado de la liga", ps),
                susp_col,
                Paragraph("Suspensi?n manual", ps),
                Paragraph(pend_text, ps),
            ])
        col_widths = [25, 150, 100, 40, 200, 200]
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (3, 0), (3, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ]))
        table.wrapOn(p, width - 60, height)
        needed = table._height + 20
        if y - needed < 40:
            draw_footer(p, width, height)
            p.showPage()
            y = height - 30
            y = draw_header(p, width, height, extra)
        table.drawOn(p, 30, y - needed)
    draw_footer(p, width, height)
    p.showPage()
    p.save()
    return response


def reporte_ingresos(request):
    cat_id = request.GET.get("categoria")
    temp_id = request.GET.get("temporada")
    concepto_id = request.GET.get("concepto")
    fecha_desde = request.GET.get("fecha_desde")
    fecha_hasta = request.GET.get("fecha_hasta")
    tipo_filtro = request.GET.get("tipo", "")

    categorias = Categoria.objects.filter(activo=True)
    conceptos = ConceptoIngreso.objects.filter(activo=True)
    temporadas = Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")

    if cat_id:
        temporadas = temporadas.filter(categoria_id=cat_id)

    qs = Ingreso.objects.select_related("concepto", "equipo", "temporada", "jugador", "registrado_por")
    if temp_id:
        qs = qs.filter(temporada_id=temp_id)
    else:
        qs = qs.exclude(temporada__finalizada=True)
    if concepto_id:
        qs = qs.filter(concepto_id=concepto_id)
    if tipo_filtro:
        qs = qs.filter(concepto__tipo=tipo_filtro)
    if fecha_desde:
        qs = qs.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha__lte=fecha_hasta)

    total_ingresos = qs.filter(concepto__tipo="INGRESO").aggregate(total=Sum("monto"))["total"] or 0
    total_egresos = qs.filter(concepto__tipo="EGRESO").aggregate(total=Sum("monto"))["total"] or 0
    neto = total_ingresos - total_egresos
    ingresos = qs.order_by("-fecha")

    temp_sel = Temporada.objects.filter(id=temp_id).first() if temp_id else None
    concepto_sel = ConceptoIngreso.objects.filter(id=concepto_id).first() if concepto_id else None

    return render(request, "reports/reporte_ingresos.html", {
        "ingresos": ingresos,
        "total_ingresos": total_ingresos,
        "total_egresos": total_egresos,
        "neto": neto,
        "categorias": categorias,
        "cat_id": int(cat_id) if cat_id else None,
        "temporadas": temporadas,
        "temp_id": int(temp_id) if temp_id else None,
        "temp_sel": temp_sel,
        "conceptos": conceptos,
        "concepto_id": int(concepto_id) if concepto_id else None,
        "concepto_sel": concepto_sel,
        "fecha_desde": fecha_desde or "",
        "fecha_hasta": fecha_hasta or "",
        "tipo_filtro": tipo_filtro,
    })


def reporte_pagos_temporada(request):
    temp_id = request.GET.get("temporada")
    ctx = {"temporadas": Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")}

    if temp_id:
        from datetime import timedelta
        temp = Temporada.objects.get(id=temp_id)
        ctx["temp"] = temp
        equipos = Equipo.objects.filter(categoria=temp.categoria, activo=True)
        conceptos_pago = ConceptoIngreso.objects.filter(
            Q(nombre__icontains="inscripci") | Q(nombre__icontains="credencial")
        )
        fecha_min = temp.fecha_inicio - timedelta(days=365)
        fecha_max = temp.fecha_fin if temp.fecha_fin else temp.fecha_inicio + timedelta(days=365)

        data = []
        for eq in equipos:
            pagos = {}
            for conc in conceptos_pago:
                total = (
                    Ingreso.objects.filter(
                        equipo=eq,
                        concepto=conc,
                        fecha__gte=fecha_min,
                        fecha__lte=fecha_max,
                    ).aggregate(total=Sum("monto"))["total"]
                    or 0
                )
                pagos[conc.nombre] = total
            # "Completo" = tiene Inscripci?n pagada (lo ?nico necesario para iniciar)
            inscripcion_pagada = any(
                "inscripci" in c.nombre.lower() and pagos.get(c.nombre, 0) > 0
                for c in conceptos_pago
            )
            data.append({"equipo": eq, "pagos": pagos, "completo": inscripcion_pagada})

        ctx["data"] = data
        ctx["conceptos"] = conceptos_pago

    return render(request, "reports/reporte_pagos.html", ctx)


def reporte_jornadas(request):
    temp_id = request.GET.get("temporada")
    ctx = {"temporadas": Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")}
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        ctx["temp"] = temp
        jornadas = Jornada.objects.filter(temporada=temp).order_by("numero")
        data = []
        for j in jornadas:
            partidos = Partido.objects.filter(jornada=j).select_related(
                "equipo_local", "equipo_visitante", "campo"
            )
            data.append({"jornada": j, "partidos": partidos})
        ctx["data"] = data
    return render(request, "reports/reporte_jornadas.html", ctx)


def reporte_jornadas_completo(request):
    temp_id = request.GET.get("temporada")
    ctx = {"temporadas": Temporada.objects.all().select_related("categoria").order_by("finalizada", "-iniciada", "nombre")}
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        ctx["temp"] = temp
        partidos = Partido.objects.filter(jornada__temporada=temp).select_related(
            "jornada", "equipo_local", "equipo_visitante", "campo"
        ).order_by("jornada__numero", "fecha_hora")
        ctx["partidos"] = partidos
    return render(request, "reports/reporte_jornadas_completo.html", ctx)


# ??? Excel (xlsx) exports ???????????????????????????????????????????????????


def _xlsx_response(filename):
    """Retorna (workbook, response). El caller debe llamar wb.save(response)."""
    wb = openpyxl.Workbook()
    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}.xlsx"'
    return wb, response


def _add_filtros(ws, filtros):
    """Agrega filas de filtros al inicio de la hoja y retorna la fila inicial."""
    from openpyxl.styles import Font, PatternFill
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=10)
    cfg = ConfiguracionLiga.obtener()
    cell = ws.cell(row=1, column=1, value=cfg.nombre_liga)
    cell.font = Font(bold=True, size=14)
    row = 2
    for label, value in filtros:
        if value:
            ws.cell(row=row, column=1, value=f"{label}: {value}").font = Font(italic=True)
            row += 1
    ws.cell(row=row, column=1, value="").font = Font(bold=True)
    return row + 1  # fila para inicio de datos


def _get_filtros_comunes(request):
    """Retorna (cat_id, temp_id, categoria_obj, temporada_obj, filtros_list)."""
    cat_id = request.GET.get("categoria")
    temp_id = request.GET.get("temporada")
    categoria = None
    temporada = None
    filtros = []
    if cat_id:
        categoria = Categoria.objects.filter(id=cat_id).first()
        if categoria:
            filtros.append(("Categor?a", categoria.nombre))
    if temp_id:
        temporada = Temporada.objects.filter(id=temp_id).first()
        if temporada:
            filtros.append(("Temporada", temporada.nombre))
    return cat_id, temp_id, categoria, temporada, filtros


def reporte_posiciones_xlsx(request):
    cat_id, temp_id, categoria, temporada, filtros = _get_filtros_comunes(request)
    wb, response = _xlsx_response("posiciones")
    ws = wb.active
    ws.title = "Posiciones"

    start = _add_filtros(ws, filtros)

    headers = ["#", "Equipo", "PJ", "PG", "PE", "PP", "GF", "GC", "DIF", "PTS"]
    ws.append(headers)
    # Aplicar estilo al header
    from openpyxl.styles import Font, PatternFill
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=start, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="333333", end_color="333333", fill_type="solid")

    if temp_id:
        temp = Temporada.objects.get(pk=temp_id)
        from openpyxl.styles import PatternFill
        green_fill = PatternFill(start_color="D4EDDA", end_color="D4EDDA", fill_type="solid")

        grupos_mode = temp.tipo_rol == "GRUPOS" and temp.clasificacion_por_grupos
        if grupos_mode:
            tablas_por_grupo = temp.calcular_tablas_por_grupo()
            grupos = temp.grupos_asignados()
            ng = len(grupos)
            por_grupo = max(1, temp.num_clasificados // max(ng, 1)) if ng else 0
            for grupo_letra, grupo_tabla in tablas_por_grupo:
                ws.append([f"Grupo {grupo_letra}"])
                start += 1
                ws.append(headers)
                start += 1
                for i, t in enumerate(grupo_tabla, 1):
                    ws.append([i, t["equipo"].nombre, t["pj"], t["pg"], t["pe"], t["pp"], t["gf"], t["gc"], t["gf"] - t["gc"], t["pts"]])
                    if i <= por_grupo:
                        for col in range(1, 11):
                            ws.cell(row=start + i, column=col).fill = green_fill
                start += len(grupo_tabla) + 1
        else:
            tabla = temp.calcular_tabla()
            for i, t in enumerate(tabla, 1):
                ws.append([i, t["equipo"].nombre, t["pj"], t["pg"], t["pe"], t["pp"], t["gf"], t["gc"], t["gf"] - t["gc"], t["pts"]])
                if i <= temp.num_clasificados:
                    for col in range(1, 11):
                        ws.cell(row=start + i, column=col).fill = green_fill
    else:
        ws.append(["Selecciona una temporada para ver posiciones."])
    wb.save(response)
    return response


def reporte_goleo_xlsx(request):
    cat_id, temp_id, categoria, temporada, filtros = _get_filtros_comunes(request)
    jornada_id = request.GET.get("jornada")
    if jornada_id:
        from league.models import Jornada
        j = Jornada.objects.filter(id=jornada_id).first()
        if j:
            filtros.append(("Jornada", j.nombre))

    wb, response = _xlsx_response("goleo")
    ws = wb.active
    ws.title = "Goleo"

    start = _add_filtros(ws, filtros)
    headers = ["#", "Jugador", "Equipo", "Goles"]
    ws.append(headers)

    if temp_id:
        qs = Gol.objects.filter(partido__temporada_id=temp_id)
        if jornada_id:
            qs = qs.filter(partido__jornada_id=jornada_id)
        goleadores = qs.values("jugador__nombre", "jugador__apellido", "equipo__nombre").annotate(
            total=Count("id")
        ).order_by("-total")
        for i, g in enumerate(goleadores, 1):
            ws.append([i, f"{g['jugador__nombre']} {g['jugador__apellido']}", g["equipo__nombre"], g["total"]])
    else:
        ws.append(["Selecciona una temporada para ver la tabla de goleo."])
    wb.save(response)
    return response


def reporte_tarjetas_xlsx(request):
    cat_id, temp_id, categoria, temporada, filtros = _get_filtros_comunes(request)
    jornada_id = request.GET.get("jornada")
    if jornada_id:
        from league.models import Jornada
        j = Jornada.objects.filter(id=jornada_id).first()
        if j:
            filtros.append(("Jornada", j.nombre))

    wb, response = _xlsx_response("tarjetas")
    ws = wb.active
    ws.title = "Tarjetas"

    start = _add_filtros(ws, filtros)
    ws.append(["#", "Jugador", "Equipo", "Tipo", "Total"])
    amarillas_qs = Tarjeta.objects.filter(partido__temporada_id=temp_id, tipo="AMARILLA")
    rojas_qs = Tarjeta.objects.filter(partido__temporada_id=temp_id, tipo="ROJA")
    if jornada_id:
        amarillas_qs = amarillas_qs.filter(partido__jornada_id=jornada_id)
        rojas_qs = rojas_qs.filter(partido__jornada_id=jornada_id)

    if temp_id:
        amarillas = amarillas_qs.values("jugador__nombre", "jugador__apellido", "equipo__nombre").annotate(
            total=Count("id")
        ).order_by("-total")
        rojas = rojas_qs.values("jugador__nombre", "jugador__apellido", "equipo__nombre").annotate(
            total=Count("id")
        ).order_by("-total")
        for i, t in enumerate(amarillas, 1):
            ws.append([i, f"{t['jugador__nombre']} {t['jugador__apellido']}", t["equipo__nombre"], "Amarilla", t["total"]])
        for i, t in enumerate(rojas, 1):
            ws.append([i, f"{t['jugador__nombre']} {t['jugador__apellido']}", t["equipo__nombre"], "Roja", t["total"]])
    else:
        ws.append(["Selecciona una temporada para ver las tarjetas."])
    wb.save(response)
    return response


def reporte_castigados_xlsx(request):
    cat_id, temp_id, categoria, temporada, filtros = _get_filtros_comunes(request)
    jornada_id = request.GET.get("jornada")
    if jornada_id:
        from league.models import Jornada
        j = Jornada.objects.filter(id=jornada_id).first()
        if j:
            filtros.append(("Jornada", j.nombre))

    wb, response = _xlsx_response("castigados")
    ws = wb.active
    ws.title = "Castigados"

    start = _add_filtros(ws, filtros)

    if temp_id:
        from django.db.models import Q
        temp = Temporada.objects.get(id=temp_id)
        qs = Tarjeta.objects.filter(
            tipo="ROJA", suspension_jornadas__gt=0,
            partido__temporada_id=temp_id,
        )
        if jornada_id:
            qs = qs.filter(partido__jornada_id=jornada_id)
        castigados = qs.select_related("jugador", "equipo", "partido__jornada").order_by("-partido__fecha_hora")
        ws.append(["#", "Jugador", "Equipo", "Suspensi?n (J)", "Expulsi?n", "Pendientes"])
        for i, c in enumerate(castigados, 1):
            prox = Partido.objects.filter(
                temporada=temp,
                jornada__numero__gte=c.partido.jornada.numero,
                fecha_hora__gt=c.partido.fecha_hora,
            ).filter(
                Q(equipo_local=c.equipo) | Q(equipo_visitante=c.equipo)
            ).exclude(id=c.partido.id).order_by("jornada__numero", "fecha_hora", "id")[:c.suspension_jornadas]
            pend_list = [p for p in prox if p.estado != 'FIN']
            if pend_list:
                pend_str = "; ".join(
                    f"{p.equipo_local} vs {p.equipo_visitante} ({p.jornada.nombre})"
                    for p in pend_list
                )
            else:
                pend_str = "Cumplida"
            ws.append([
                i,
                f"{c.jugador.nombre} {c.jugador.apellido}",
                c.equipo.nombre,
                c.suspension_jornadas,
                f"{c.partido.equipo_local} vs {c.partido.equipo_visitante} ({c.partido.jornada.nombre})",
                pend_str,
            ])
        from league.models import SuspensionJugador
        manuales = SuspensionJugador.objects.filter(
            categoria=temp.categoria, activo=True
        ).select_related("jugador", "equipo")
        num_fila = 1
        for m in manuales:
            rst = m.restantes()
            if rst <= 0:
                continue
            if m.vitalicia:
                pend_str = "Por vida"
                susp_col = "Por vida"
            else:
                prox = Partido.objects.filter(
                    temporada=temp, estado__in=("PRO", "PROG"),
                )
                if m.equipo_id:
                    prox = prox.filter(
                        Q(equipo_local=m.equipo) | Q(equipo_visitante=m.equipo)
                    )
                prox = prox.order_by("jornada__numero", "fecha_hora", "id")[:rst]
                pend_list = list(prox)
                if pend_list:
                    pend_str = "; ".join(
                        f"{p.equipo_local} vs {p.equipo_visitante} ({p.jornada.nombre})"
                        for p in pend_list
                    )
                else:
                    pend_str = f"Pendiente ({rst}) - pr?xima temporada"
                susp_col = m.jornadas
            num_fila = ws.max_row or 2
            ws.append([
                num_fila - 1,
                f"{m.jugador.nombre} {m.jugador.apellido}",
                m.equipo.nombre if m.equipo else "Expulsado de la liga",
                susp_col,
                "Suspensi?n manual",
                pend_str,
            ])
    else:
        ws.append(["Selecciona una temporada para ver castigados."])
    wb.save(response)
    return response


def reporte_ingresos_xlsx(request):
    cat_id, temp_id, categoria, temporada, filtros = _get_filtros_comunes(request)

    concepto_id = request.GET.get("concepto")
    fecha_desde = request.GET.get("fecha_desde")
    fecha_hasta = request.GET.get("fecha_hasta")
    tipo_filtro = request.GET.get("tipo", "")
    concepto_sel = None
    if concepto_id:
        from finance.models import ConceptoIngreso
        concepto_sel = ConceptoIngreso.objects.filter(id=concepto_id).first()
        if concepto_sel:
            filtros.append(("Concepto", concepto_sel.nombre))
    if tipo_filtro:
        filtros.append(("Tipo", "Ingresos" if tipo_filtro == "INGRESO" else "Egresos"))
    if fecha_desde:
        filtros.append(("Fecha desde", fecha_desde))
    if fecha_hasta:
        filtros.append(("Fecha hasta", fecha_hasta))

    wb, response = _xlsx_response("movimientos")
    ws = wb.active
    ws.title = "Movimientos"

    start = _add_filtros(ws, filtros)

    qs = Ingreso.objects.select_related("concepto", "equipo", "temporada", "registrado_por")
    if temp_id:
        qs = qs.filter(temporada_id=temp_id)
    else:
        qs = qs.exclude(temporada__finalizada=True)
    if concepto_id:
        qs = qs.filter(concepto_id=concepto_id)
    if tipo_filtro:
        qs = qs.filter(concepto__tipo=tipo_filtro)
    if fecha_desde:
        qs = qs.filter(fecha__gte=fecha_desde)
    if fecha_hasta:
        qs = qs.filter(fecha__lte=fecha_hasta)

    total_ingresos = qs.filter(concepto__tipo="INGRESO").aggregate(total=Sum("monto"))["total"] or 0
    total_egresos = qs.filter(concepto__tipo="EGRESO").aggregate(total=Sum("monto"))["total"] or 0
    ws.append(["#", "Fecha", "Tipo", "Concepto", "Monto", "Equipo", "Pagado a", "Temporada", "Registrado por"])
    for i, ing in enumerate(qs.order_by("-fecha"), 1):
        ws.append([
            i, ing.fecha.strftime("%d/%m/%Y") if ing.fecha else "",
            "Ingreso" if ing.es_ingreso else "Egreso",
            ing.concepto.nombre, f"${ing.monto}",
            ing.equipo.nombre if ing.equipo else "-",
            ing.pagado_a or "-",
            ing.temporada.nombre if ing.temporada else "-",
            ing.registrado_por.username if ing.registrado_por else "-",
        ])
    ws.append([])
    ws.append(["", "", "TOTAL INGRESOS", "", f"${total_ingresos}"])
    ws.append(["", "", "TOTAL EGRESOS", "", f"${total_egresos}"])
    ws.append(["", "", "NETO", "", f"${total_ingresos - total_egresos}"])

    wb.save(response)
    return response


# ??? Pagos por Temporada ?????????????????????????????????????????????????????


def reporte_pagos_pdf(request):
    temp_id = request.GET.get("temporada")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=pagos_temporada.pdf"
    p = canvas.Canvas(response, pagesize=landscape(letter))
    width, height = landscape(letter)

    extra = "Reporte de Pagos por Temporada"
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        extra = f"Reporte de Pagos\nTemporada: {temp.nombre}\nCategor?a: {temp.categoria.nombre}"
    y = draw_header(p, width, height, extra)

    if temp_id:
        from datetime import timedelta
        from finance.models import ConceptoIngreso, Ingreso
        from django.db.models import Sum, Q

        temp = Temporada.objects.get(id=temp_id)
        equipos = Equipo.objects.filter(categoria=temp.categoria, activo=True)
        conceptos_pago = ConceptoIngreso.objects.filter(
            Q(nombre__icontains="inscripci") | Q(nombre__icontains="credencial")
        )
        fecha_min = temp.fecha_inicio - timedelta(days=365)
        fecha_max = temp.fecha_fin if temp.fecha_fin else temp.fecha_inicio + timedelta(days=365)

        data = []
        for eq in equipos:
            pagos = {}
            for conc in conceptos_pago:
                total = Ingreso.objects.filter(equipo=eq, concepto=conc, fecha__gte=fecha_min, fecha__lte=fecha_max).aggregate(total=Sum("monto"))["total"] or 0
                pagos[conc.nombre] = total
            inscripcion_pagada = any("inscripci" in c.nombre.lower() and pagos.get(c.nombre, 0) > 0 for c in conceptos_pago)
            data.append({"equipo": eq, "pagos": pagos, "completo": inscripcion_pagada})

        data = sorted(data, key=lambda x: x["equipo"].nombre)

        headers = ["#", "Equipo"] + [c.nombre for c in conceptos_pago] + ["Estado"]
        col_widths = [30, 200] + [100] * conceptos_pago.count() + [80]
        hdr = [headers]
        rows = []
        for i, item in enumerate(data, 1):
            row = [i, item["equipo"].nombre]
            for c in conceptos_pago:
                m = item["pagos"].get(c.nombre, 0)
                row.append(f"${m:.2f}" if m > 0 else "Pendiente")
            row.append("Completo" if item["completo"] else "Incompleto")
            rows.append(row)

        all_rows = hdr + rows
        table = Table(all_rows, colWidths=col_widths)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ]))
        table.wrapOn(p, 30, y - 20)
        table.drawOn(p, 30, y - 20 - len(all_rows) * 18)

    draw_footer(p, width, height)
    p.showPage()
    p.save()
    return response


def reporte_pagos_xlsx(request):
    temp_id = request.GET.get("temporada")
    filtros = []
    temp = None
    if temp_id:
        temp = Temporada.objects.filter(id=temp_id).first()
        if temp:
            filtros.append(("Temporada", temp.nombre))
            filtros.append(("Categor?a", temp.categoria.nombre))

    wb, response = _xlsx_response("pagos_temporada")
    ws = wb.active
    ws.title = "Pagos"

    start = _add_filtros(ws, filtros)

    if temp_id:
        from datetime import timedelta
        from finance.models import ConceptoIngreso, Ingreso
        from django.db.models import Sum, Q

        temp = Temporada.objects.get(id=temp_id)
        equipos = Equipo.objects.filter(categoria=temp.categoria, activo=True)
        conceptos_pago = ConceptoIngreso.objects.filter(
            Q(nombre__icontains="inscripci") | Q(nombre__icontains="credencial")
        )
        fecha_min = temp.fecha_inicio - timedelta(days=365)
        fecha_max = temp.fecha_fin if temp.fecha_fin else temp.fecha_inicio + timedelta(days=365)

        headers = ["#", "Equipo"] + [c.nombre for c in conceptos_pago] + ["Estado"]
        ws.append(headers)
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=start, column=col)
            cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
            cell.fill = openpyxl.styles.PatternFill(start_color="333333", end_color="333333", fill_type="solid")

        data = []
        for eq in equipos:
            pagos = {}
            for conc in conceptos_pago:
                total = Ingreso.objects.filter(equipo=eq, concepto=conc, fecha__gte=fecha_min, fecha__lte=fecha_max).aggregate(total=Sum("monto"))["total"] or 0
                pagos[conc.nombre] = total
            inscripcion_pagada = any("inscripci" in c.nombre.lower() and pagos.get(c.nombre, 0) > 0 for c in conceptos_pago)
            data.append({"equipo": eq, "pagos": pagos, "completo": inscripcion_pagada})

        data = sorted(data, key=lambda x: x["equipo"].nombre)
        for i, item in enumerate(data, 1):
            row = [i, item["equipo"].nombre]
            for c in conceptos_pago:
                m = item["pagos"].get(c.nombre, 0)
                row.append(m)
            row.append("Completo" if item["completo"] else "Incompleto")
            ws.append(row)

    wb.save(response)
    return response


# ??? Juegos por Jornada ??????????????????????????????????????????????????????


def reporte_jornadas_pdf(request):
    temp_id = request.GET.get("temporada")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=juegos_jornada.pdf"
    p = canvas.Canvas(response, pagesize=landscape(letter))
    width, height = landscape(letter)

    extra = "Juegos por Jornada"
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        extra = f"Juegos por Jornada\nTemporada: {temp.nombre}\nCategor?a: {temp.categoria.nombre}"
    y = draw_header(p, width, height, extra)

    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        jornadas = Jornada.objects.filter(temporada=temp).order_by("numero")

        page_y = y - 20
        for j in jornadas:
            partidos = Partido.objects.filter(jornada=j).select_related(
                "equipo_local", "equipo_visitante", "campo", "arbitro"
            ).order_by("fecha_hora")
            if not partidos:
                continue

            # Check if we need a new page
            needed = 30 + (len(partidos) + 2) * 18
            if page_y - needed < 50:
                p.showPage()
                y2 = height - 30
                p.setFont("Helvetica-Bold", 10)
                p.drawString(30, y2 - 10, f"{extra.replace(chr(10), ' - ')} (cont.)")
                page_y = y2 - 30

            p.setFont("Helvetica-Bold", 10)
            p.setFillColor(colors.HexColor("#2d5a27"))
            p.drawString(30, page_y, f"Jornada {j.numero}")
            p.setFillColor(colors.black)
            page_y -= 16

            hdr = ["Local", "Goles", "", "Goles", "Visitante", "Campo", "Fecha/Hora", "?rbitro"]
            data = [hdr]
            for partido in partidos:
                data.append([
                    partido.equipo_local.nombre,
                    str(partido.goles_local) if partido.goles_local is not None else "-",
                    "vs",
                    str(partido.goles_visitante) if partido.goles_visitante is not None else "-",
                    partido.equipo_visitante.nombre,
                    partido.campo.nombre if partido.campo else "-",
                    localtime(partido.fecha_hora).strftime("%d/%m/%Y %H:%M") if partido.fecha_hora else "Pendiente",
                    partido.arbitro.nombre_completo() if partido.arbitro else "---",
                ])
            table = Table(data, colWidths=[150, 40, 30, 40, 150, 100, 100, 100])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ]))
            table.wrapOn(p, 30, page_y - 10)
            table.drawOn(p, 30, page_y - 10 - len(data) * 18)
            page_y = page_y - 10 - len(data) * 18 - 20

    draw_footer(p, width, height)
    p.showPage()
    p.save()
    return response


def reporte_jornadas_xlsx(request):
    temp_id = request.GET.get("temporada")
    filtros = []
    temp = None
    if temp_id:
        temp = Temporada.objects.filter(id=temp_id).first()
        if temp:
            filtros.append(("Temporada", temp.nombre))
            filtros.append(("Categor?a", temp.categoria.nombre))

    wb, response = _xlsx_response("juegos_jornada")
    ws = wb.active
    ws.title = "Juegos por Jornada"

    start = _add_filtros(ws, filtros)

    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        jornadas = Jornada.objects.filter(temporada=temp).order_by("numero")
        headers = ["Jornada", "Local", "Goles Local", "vs", "Goles Visit", "Visitante", "Campo", "Fecha", "Hora", "?rbitro"]
        ws.append(headers)
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=start, column=col)
            cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
            cell.fill = openpyxl.styles.PatternFill(start_color="333333", end_color="333333", fill_type="solid")

        for j in jornadas:
            partidos = Partido.objects.filter(jornada=j).select_related(
                "equipo_local", "equipo_visitante", "campo", "arbitro"
            ).order_by("fecha_hora")
            for p in partidos:
                ws.append([
                    j.numero,
                    p.equipo_local.nombre,
                    p.goles_local if p.goles_local is not None else "-",
                    "vs",
                    p.goles_visitante if p.goles_visitante is not None else "-",
                    p.equipo_visitante.nombre,
                    p.campo.nombre if p.campo else "-",
                    localtime(p.fecha_hora).strftime("%d/%m/%Y") if p.fecha_hora else "Pendiente",
                    localtime(p.fecha_hora).strftime("%H:%M") if p.fecha_hora else "",
                    p.arbitro.nombre_completo() if p.arbitro else "---",
                ])

    wb.save(response)
    return response


# ??? Todos los Juegos ????????????????????????????????????????????????????????


def reporte_jornadas_completo_pdf(request):
    temp_id = request.GET.get("temporada")
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=todos_juegos.pdf"
    p = canvas.Canvas(response, pagesize=landscape(letter))
    width, height = landscape(letter)

    extra = "Todos los Juegos"
    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        extra = f"Todos los Juegos\nTemporada: {temp.nombre}\nCategor?a: {temp.categoria.nombre}"
    y = draw_header(p, width, height, extra)

    if temp_id:
        temp = Temporada.objects.get(id=temp_id)
        partidos = Partido.objects.filter(jornada__temporada=temp).select_related(
            "jornada", "equipo_local", "equipo_visitante", "campo", "arbitro"
        ).order_by("jornada__numero", "fecha_hora")

        hdr = ["#", "Jor.", "Local", "Goles", "", "Goles", "Visitante", "Campo", "Fecha/Hora", "?rbitro"]
        data = [hdr]
        for i, partido in enumerate(partidos, 1):
            data.append([
                i, partido.jornada.numero,
                partido.equipo_local.nombre,
                str(partido.goles_local) if partido.goles_local is not None else "-", "vs",
                str(partido.goles_visitante) if partido.goles_visitante is not None else "-",
                partido.equipo_visitante.nombre,
                partido.campo.nombre if partido.campo else "-",
                localtime(partido.fecha_hora).strftime("%d/%m/%Y %H:%M") if partido.fecha_hora else "Pendiente",
                partido.arbitro.nombre_completo() if partido.arbitro else "---",
            ])

        hdr = data[0]
        tres_rows = data[1:]
        cols = [30, 30, 120, 35, 25, 35, 120, 80, 90, 80]
        style = TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ])
        row_h = 18
        per_page = max(1, int((y - 70) // row_h))
        rows_chunk = max(1, per_page - 1)
        idx = 0
        first = True
        while idx < len(tres_rows):
            if not first:
                p.showPage()
                page_y2 = height - 30
                p.setFont("Helvetica-Bold", 10)
                p.drawString(30, page_y2 - 10, f"{extra.replace(chr(10), ' - ')} (cont.)")
                page_y = page_y2 - 30
            else:
                page_y = y - 20
            end = min(idx + rows_chunk, len(tres_rows))
            page_data = [hdr] + tres_rows[idx:end]
            table = Table(page_data, colWidths=cols)
            table.setStyle(style)
            table.wrapOn(p, 30, page_y - 10)
            table.drawOn(p, 30, page_y - 10 - len(page_data) * row_h)
            draw_footer(p, width, height)
            idx = end
            first = False

    p.showPage()
    p.save()
    return response


def reporte_jornadas_completo_xlsx(request):
    temp_id = request.GET.get("temporada")
    filtros = []
    if temp_id:
        temp = Temporada.objects.filter(id=temp_id).first()
        if temp:
            filtros.append(("Temporada", temp.nombre))
            filtros.append(("Categor?a", temp.categoria.nombre))

    wb, response = _xlsx_response("todos_juegos")
    ws = wb.active
    ws.title = "Todos los Juegos"

    start = _add_filtros(ws, filtros)
    headers = ["#", "Jornada", "Local", "Goles Local", "vs", "Goles Visit", "Visitante", "Campo", "Fecha", "Hora", "?rbitro"]
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=start, column=col)
        cell.font = openpyxl.styles.Font(bold=True, color="FFFFFF")
        cell.fill = openpyxl.styles.PatternFill(start_color="333333", end_color="333333", fill_type="solid")

    if temp_id:
        partidos = Partido.objects.filter(jornada__temporada_id=temp_id).select_related(
            "jornada", "equipo_local", "equipo_visitante", "campo", "arbitro"
        ).order_by("jornada__numero", "fecha_hora")
        for i, p in enumerate(partidos, 1):
            ws.append([
                i, p.jornada.numero, p.equipo_local.nombre,
                p.goles_local if p.goles_local is not None else "-", "vs",
                p.goles_visitante if p.goles_visitante is not None else "-",
                p.equipo_visitante.nombre, p.campo.nombre if p.campo else "-",
                localtime(p.fecha_hora).strftime("%d/%m/%Y") if p.fecha_hora else "Pendiente",
                localtime(p.fecha_hora).strftime("%H:%M") if p.fecha_hora else "",
                p.arbitro.nombre_completo() if p.arbitro else "---",
            ])

    wb.save(response)
    return response


# ??? C?dula Arbitral ?????????????????????????????????????????????????????????


def reporte_cedula_arbitral_xlsx(request, partido_id):
    partido = get_object_or_404(
        Partido.objects.select_related("equipo_local", "equipo_visitante", "campo", "arbitro"),
        pk=partido_id,
    )
    # Incluir jugadores con el equipo como principal O secundario
    from django.db.models import Q
    from league.models import JugadorEquipo

    local_jugador_ids = JugadorEquipo.objects.filter(
        equipo=partido.equipo_local, activo=True
    ).values_list("jugador_id", flat=True)
    jugadores_local = list(Jugador.objects.filter(
        Q(pk__in=local_jugador_ids) | Q(equipo=partido.equipo_local), activo=True
    ).order_by("nombre", "apellido").distinct())

    visit_jugador_ids = JugadorEquipo.objects.filter(
        equipo=partido.equipo_visitante, activo=True
    ).values_list("jugador_id", flat=True)
    jugadores_visit = list(Jugador.objects.filter(
        Q(pk__in=visit_jugador_ids) | Q(equipo=partido.equipo_visitante), activo=True
    ).order_by("nombre", "apellido").distinct())
    goles = Gol.objects.filter(partido=partido)
    tarjetas = Tarjeta.objects.filter(partido=partido)
    participaciones = {p.jugador_id: p for p in JugadorPartido.objects.filter(partido=partido)}

    goles_count = Counter(g.jugador_id for g in goles)
    tarjetas_dict = {}
    for t in tarjetas:
        sid = t.jugador_id
        if sid not in tarjetas_dict:
            tarjetas_dict[sid] = {"amarillas": 0, "roja": False}
        if t.tipo == "AMARILLA":
            tarjetas_dict[sid]["amarillas"] += 1
        elif t.tipo == "ROJA":
            tarjetas_dict[sid]["roja"] = True

    wb, response = _xlsx_response(f"cedula_arbitral_{partido_id}")
    ws = wb.active
    ws.title = "C?dula"

    # Filtros
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
    ws.cell(row=1, column=1, value=f"{partido.equipo_local} vs {partido.equipo_visitante}").font = openpyxl.styles.Font(bold=True, size=14)
    ws.cell(row=2, column=1, value=f"Fecha: {localtime(partido.fecha_hora).strftime('%d/%m/%Y %H:%M') if partido.fecha_hora else 'Pendiente'}").font = openpyxl.styles.Font(italic=True)
    ws.cell(row=3, column=1, value=f"Campo: {partido.campo.nombre if partido.campo else '-'}").font = openpyxl.styles.Font(italic=True)
    ws.cell(row=4, column=1, value=f"?rbitro: {partido.arbitro.nombre_completo() if partido.arbitro else '---'}").font = openpyxl.styles.Font(italic=True)
    ws.append([])
    start = 6

    headers = ["#", "Jugador", "Titular", "Cambio", "Goles", "Amarilla", "Roja"]
    ws.append(headers)

    def add_jugadores(jugadores, equipo_nombre, etiqueta):
        ws.append([f"--- {etiqueta}: {equipo_nombre} ---"])
        for j in jugadores:
            part = participaciones.get(j.id)
            card = tarjetas_dict.get(j.id, {"amarillas": 0, "roja": False})
            g = goles_count.get(j.id, 0)
            ws.append([
                j.dorsal or "-",
                f"{j.nombre} {j.apellido}",
                "S?" if part and part.titular else "",
                "S?" if part and not part.titular else "",
                g if g > 0 else "",
                "S?" if card["amarillas"] >= 1 else "",
                "S?" if card["roja"] else "",
            ])

    def _logo_src(equipo):
        if not equipo.logo:
            return None
        local = os.path.join(settings.MEDIA_ROOT, equipo.logo.name)
        if os.path.exists(local):
            return local
        try:
            url = equipo.logo.url
        except Exception:
            return None
        if not url:
            return None
        import urllib.request
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AdminFut)"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = r.read()
            if not data:
                return None
            return BytesIO(data)
        except Exception:
            return None

    from openpyxl.drawing.image import Image as XLImage

    def _anexar_logo(equipo, fila):
        src = _logo_src(equipo)
        if not src:
            return
        try:
            img = XLImage(src)
            img.width, img.height = 36, 36
            ws.add_image(img, f"B{fila}")
        except Exception:
            pass

    fila_local = 7
    add_jugadores(jugadores_local, str(partido.equipo_local), "LOCAL")
    _anexar_logo(partido.equipo_local, fila_local)
    fila_visit = fila_local + len(jugadores_local) + 1
    add_jugadores(jugadores_visit, str(partido.equipo_visitante), "VISITANTE")
    _anexar_logo(partido.equipo_visitante, fila_visit)

    wb.save(response)
    return response


def reporte_cedula_arbitral_pdf(request, partido_id):
    partido = get_object_or_404(
        Partido.objects.select_related("equipo_local", "equipo_visitante", "campo", "arbitro"),
        pk=partido_id,
    )
    # Incluir jugadores con el equipo como principal O secundario
    from django.db.models import Q
    from league.models import JugadorEquipo

    local_jugador_ids = JugadorEquipo.objects.filter(
        equipo=partido.equipo_local, activo=True
    ).values_list("jugador_id", flat=True)
    jugadores_local = list(Jugador.objects.filter(
        Q(pk__in=local_jugador_ids) | Q(equipo=partido.equipo_local), activo=True
    ).order_by("nombre", "apellido").distinct())

    visit_jugador_ids = JugadorEquipo.objects.filter(
        equipo=partido.equipo_visitante, activo=True
    ).values_list("jugador_id", flat=True)
    jugadores_visit = list(Jugador.objects.filter(
        Q(pk__in=visit_jugador_ids) | Q(equipo=partido.equipo_visitante), activo=True
    ).order_by("nombre", "apellido").distinct())
    goles = Gol.objects.filter(partido=partido)
    tarjetas = Tarjeta.objects.filter(partido=partido)
    participaciones = {p.jugador_id: p for p in JugadorPartido.objects.filter(partido=partido)}

    goles_count = Counter(g.jugador_id for g in goles)
    tarjetas_dict = {}
    for t in tarjetas:
        sid = t.jugador_id
        if sid not in tarjetas_dict:
            tarjetas_dict[sid] = {"amarillas": 0, "roja": False}
        if t.tipo == "AMARILLA":
            tarjetas_dict[sid]["amarillas"] += 1
        elif t.tipo == "ROJA":
            tarjetas_dict[sid]["roja"] = True

    # Determinar jugadores suspendidos de partidos anteriores
    todos_jugadores = jugadores_local + jugadores_visit
    suspendidos = set()
    if partido.jornada and partido.temporada:
        rojas_previas = Tarjeta.objects.filter(
            jugador_id__in=[j.id for j in todos_jugadores],
            tipo="ROJA",
            suspension_jornadas__gt=0,
            partido__temporada=partido.temporada,
            partido__jornada__numero__lt=partido.jornada.numero,
        ).select_related("partido__jornada")
        for r in rojas_previas:
            fin = r.partido.jornada.numero + r.suspension_jornadas
            if partido.jornada.numero <= fin:
                suspendidos.add(r.jugador_id)

    # Verificar elegibilidad para liguilla seg?n % m?nimo de juegos
    no_elegibles = set()
    if partido.es_liguilla and partido.temporada.min_porcentaje_liguilla:
        min_pct = partido.temporada.min_porcentaje_liguilla
        total_reg = Partido.objects.filter(temporada=partido.temporada, es_liguilla=False).count()
        if total_reg > 0:
            for j in todos_jugadores:
                jugados = JugadorPartido.objects.filter(
                    jugador=j, partido__temporada=partido.temporada, partido__es_liguilla=False
                ).count()
                pct = (jugados / total_reg) * 100
                if pct < min_pct:
                    no_elegibles.add(j.id)

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f"attachment; filename=cedula_arbitral_{partido_id}.pdf"
    p = canvas.Canvas(response, pagesize=letter)
    w, h = letter
    col_widths = [9, 180, 17, 17, 17, 14, 14, 19]
    hdr = ["#", "Jugador", "Tit", "Camb", "Gol", "A1", "A2", "Roja"]
    row_h = 15
    franja_h = 26
    top_margin = 40
    table_w = sum(col_widths)
    gap = 7
    left_x = (w - (2 * table_w + gap)) // 2
    right_x = left_x + table_w + gap

    def cabecera_pagina():
        cfg_liga = ConfiguracionLiga.obtener()
        x0 = left_x
        logo_src = None
        if cfg_liga.logo:
            local_path = os.path.join(settings.MEDIA_ROOT, cfg_liga.logo.name)
            if os.path.exists(local_path):
                logo_src = local_path
            else:
                logo_src = _imagen_pdf(cfg_liga.logo)
        if logo_src:
            try:
                p.drawImage(logo_src, x0, h - top_margin - 6 - 17, width=34, height=34, preserveAspectRatio=True, mask='auto')
            except Exception:
                logo_src = None
        x_text = x0 + (42 if logo_src else 0)
        y0 = h - top_margin - 6
        p.setFillColor(colors.black)
        p.setFont("Helvetica-Bold", 10)
        p.drawString(x_text, y0, cfg_liga.nombre_liga[:60])
        p.setFont("Helvetica-Bold", 12)
        p.drawRightString(w - x0, y0, "C?DULA ARBITRAL")
        # El "Equipo A vs Equipo B" central se elimin?: los nombres ya van en
        # la franja de cada equipo (LOCAL / VISITANTE) con su logo m?s grande.
        y2 = y0 - 24
        p.setFont("Helvetica", 8.5)
        p.drawString(x0, y2, f"Fecha: {localtime(partido.fecha_hora).strftime('%d/%m/%Y %H:%M') if partido.fecha_hora else 'Pendiente'}")
        p.drawCentredString(w / 2, y2, f"Campo: {partido.campo.nombre if partido.campo else 'Por definir'}")
        if partido.arbitro:
            p.drawRightString(w - x0, y2, f"?rbitro: {partido.arbitro.nombre_completo()}")
        else:
            p.drawRightString(w - x0, y2, "?rbitro: __________________________")
        return y2 - 15

    table_top = cabecera_pagina()

    def dibuja_franja(x_start, y, header_color, titulo, equipo):
        p.setFillColor(colors.white)
        p.setStrokeColor(colors.black)
        p.rect(x_start, y - franja_h, table_w, franja_h, fill=1, stroke=1)
        if equipo.logo:
            logo_src = None
            local_path = os.path.join(settings.MEDIA_ROOT, equipo.logo.name)
            if os.path.exists(local_path):
                logo_src = local_path
            else:
                logo_src = _imagen_pdf(equipo.logo)
            if logo_src:
                try:
                    p.drawImage(logo_src, x_start + 4, y - franja_h + 2, width=22, height=22, preserveAspectRatio=True, mask='auto')
                except Exception:
                    pass
        p.setFillColor(colors.black)
        p.setFont("Helvetica-Bold", 9)
        p.drawCentredString(x_start + (table_w + 12) / 2, y - franja_h + 6, f"{titulo} - {equipo.nombre}")

    def dibuja_cabecera_columnas(x_start, y):
        p.setFont("Helvetica-Bold", 8.5)
        x = x_start
        for i, txt in enumerate(hdr):
            p.setFillColor(colors.white)
            p.rect(x, y - row_h, col_widths[i], row_h, fill=1, stroke=1)
            p.setFillColor(colors.black)
            p.drawCentredString(x + col_widths[i] / 2, y - row_h + 3, txt)
            x += col_widths[i]

    def nombre_linea(j, sufijo=""):
        full = f"{j.nombre} {j.apellido}".upper()
        base_size = 8.5
        usable = col_widths[1] - 6
        txt = full + sufijo
        tam = base_size
        w = p.stringWidth(txt, "Helvetica", base_size)
        if w > usable:
            tam = usable * 0.97 * base_size / w
        return tam, txt

    def rh_para(j):
        return row_h

    def dibuja_fila(j, x_start, y, rh, idx):
        x = x_start
        if j is None:
            for i in range(len(col_widths)):
                p.setFillColor(colors.white)
                p.rect(x, y - rh, col_widths[i], rh, fill=1, stroke=1)
                x += col_widths[i]
            p.setFillColor(colors.black)
            return
        card = tarjetas_dict.get(j.id, {"amarillas": 0, "roja": False})
        g = goles_count.get(j.id, 0)
        part = participaciones.get(j.id)
        datos = [
            str(j.dorsal or "-"),
            f"{j.nombre} {j.apellido}",
            "[X]" if part and part.titular else "[ ]",
            "[X]" if part and not part.titular else "[ ]",
            str(g) if g > 0 else "",
            "[X]" if card["amarillas"] >= 1 else "",
            "[X]" if card["amarillas"] >= 2 else "",
            "[X]" if card["roja"] else "",
        ]
        if j.id in suspendidos:
            row_color = colors.HexColor("#ffe0e0")
            sufijo = " (S)"
            estado_color = colors.black
        elif j.id in no_elegibles:
            row_color = colors.HexColor("#fff8e0")
            sufijo = " (NE)"
            estado_color = colors.black
        else:
            row_color = colors.HexColor("#f0f0f0") if idx % 2 == 0 else colors.white
            sufijo = ""
            estado_color = colors.black
        for i, txt in enumerate(datos):
            p.setFillColor(row_color)
            p.rect(x, y - rh, col_widths[i], rh, fill=1, stroke=1)
            if i == 1:
                tam, nombre_txt = nombre_linea(j, sufijo)
                p.setFillColor(estado_color)
                p.setFont("Helvetica", tam)
                base = y - rh + 3 + (8.5 - tam) / 2
                p.drawString(x + 3, base, nombre_txt)
                if sufijo == " (S)":
                    tw = p.stringWidth(nombre_txt, "Helvetica", tam)
                    p.line(x + 3, base + 2, x + 3 + tw, base + 2)
            else:
                p.setFillColor(colors.black)
                p.setFont("Helvetica", 9)
                p.drawCentredString(x + col_widths[i] / 2, y - rh + 3.5, txt)
            p.setFillColor(colors.black)
            x += col_widths[i]

    def dibuja_cedula(y_top):
        y = y_top
        dibuja_franja(left_x, y, colors.HexColor("#2d6b2e"), "LOCAL", partido.equipo_local)
        dibuja_franja(right_x, y, colors.HexColor("#1a5276"), "VISITANTE", partido.equipo_visitante)
        y -= franja_h
        dibuja_cabecera_columnas(left_x, y)
        dibuja_cabecera_columnas(right_x, y)
        y -= row_h
        p.setFont("Helvetica", 8)
        y_min = 170
        n = max(len(jugadores_local), len(jugadores_visit))
        for idx in range(n):
            jl = jugadores_local[idx] if idx < len(jugadores_local) else None
            jv = jugadores_visit[idx] if idx < len(jugadores_visit) else None
            rh = max(rh_para(jl), rh_para(jv))
            if y - rh < y_min:
                p.showPage()
                draw_footer(p, w, h, 14)
                y = cabecera_pagina()
                dibuja_cabecera_columnas(left_x, y)
                dibuja_cabecera_columnas(right_x, y)
                y -= row_h
            dibuja_fila(jl, left_x, y, rh, idx)
            dibuja_fila(jv, right_x, y, rh, idx)
            y -= rh
        return y

    y_final = dibuja_cedula(table_top)

    footer_y = y_final - 42
    if footer_y < 165:
        footer_y = 165
    p.setFillColor(colors.black)
    p.setFont("Helvetica", 10)
    gol_local = str(partido.goles_local) if partido.estado == "FIN" else "___________________"
    gol_visit = str(partido.goles_visitante) if partido.estado == "FIN" else "___________________"
    p.drawString(left_x, footer_y, f"Goles local: {gol_local}")
    p.drawString(right_x, footer_y, f"Goles visitante: {gol_visit}")

    # Firmas en un solo rengl?n, al final de la hoja (sin nombres de capitanes)
    p.setFont("Helvetica", 9)
    firma_y = footer_y - 28
    p.drawString(left_x, firma_y, "Firma local: ____________")
    p.drawCentredString(w / 2, firma_y, "Firma del ?rbitro: ____________")
    p.drawRightString(w - left_x, firma_y, "Firma visitante: ____________")

    draw_footer(p, w, h, 14)

    p.showPage()
    p.save()
    return response


def reporte_suscriptores(request):
    """P?gina web con lista de suscriptores."""
    if not request.user.is_authenticated or not request.user.rol or not request.user.rol.permisos.get("reporte_suscriptores", False):
        return redirect("login")
    from league.models import Categoria
    cat_id = request.GET.get("categoria")
    qs = SuscripcionEmail.objects.all().order_by("-creado")
    if cat_id:
        qs = qs.filter(categorias__id=cat_id)
    ctx = {
        "suscriptores": qs,
        "categorias": Categoria.objects.filter(activo=True),
        "cat_id": int(cat_id) if cat_id else None,
        "total": qs.count(),
        "activos": qs.filter(activo=True).count(),
    }
    return render(request, "reports/reporte_suscriptores.html", ctx)


def reporte_suscriptores_pdf(request):
    if not request.user.is_authenticated or not request.user.rol or not request.user.rol.permisos.get("reporte_suscriptores", False):
        return redirect("login")
    cat_id = request.GET.get("categoria")
    qs = SuscripcionEmail.objects.all().order_by("-creado")
    if cat_id:
        qs = qs.filter(categorias__id=cat_id)
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = "attachment; filename=suscriptores.pdf"
    p = canvas.Canvas(response, pagesize=landscape(letter))
    w, h = landscape(letter)
    extra = "Reporte de Suscriptores"
    if cat_id:
        from league.models import Categoria
        cat = Categoria.objects.filter(id=cat_id).first()
        if cat:
            extra += f" - {cat.nombre}"
    draw_header(p, w, extra)
    headers = ["Email", "Usuario", "Categor?as", "Roles", "Estad?sticas", "Activo", "Creado"]
    data = [headers]
    for s in qs:
        cats = ", ".join(s.categorias.values_list("nombre", flat=True)) if s.categorias.exists() else "Todas"
        usuario = s.usuario.username if s.usuario else "-"
        data.append([
            s.email, usuario, cats,
            "S?" if s.recibir_roles else "No",
            "S?" if s.recibir_estadisticas else "No",
            "S?" if s.activo else "No",
            s.creado.strftime("%d/%m/%Y"),
        ])
    table = Table(data, colWidths=[180, 100, 120, 60, 60, 60, 80])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    tw, th = table.wrap(0, 0)
    table.drawOn(p, (w - tw) / 2, h - 120 - th)
    draw_footer(p, w, h, 14)
    p.showPage()
    p.save()
    return response


def _imagen_pdf(filefield, timeout=15):
    """Descarga una imagen (FileField) y devuelve un ImageReader para ReportLab.

    Usa la URL del storage (con fallback entre nubes de Cloudinary). Devuelve
    None si no hay imagen o falla la descarga.
    """
    try:
        url = filefield.url
    except Exception:
        return None
    if not url:
        return None
    import urllib.request

    from reportlab.lib.utils import ImageReader
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; AdminFut)"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        if not data:
            return None
        buf = BytesIO(data)
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


def _suspensos_globales():
    """Jugadores con suspensi?n en toda la liga (sin equipo): no generan credencial."""
    return set(SuspensionJugador.objects.filter(activo=True, equipo__isnull=True).values_list("jugador_id", flat=True))


def reporte_credenciales(request):
    if not request.user.is_authenticated or not request.user.rol or not request.user.rol.permisos.get("credenciales_ver", False):
        messages.error(request, "No tienes permiso para generar credenciales.")
        return redirect("home")
    categorias = Categoria.objects.all().order_by("nombre")
    cat_id = request.GET.get("categoria")
    equipo_id = request.GET.get("equipo")
    equipos = []
    equipo = None
    jugadores = []
    if cat_id:
        equipos = Equipo.objects.filter(categoria_id=cat_id, activo=True).order_by("nombre")
    if equipo_id:
        equipo = get_object_or_404(Equipo, pk=equipo_id)
        sus = _suspensos_globales()
        jugadores = (
            Jugador.objects.filter(
                registros_equipo__equipo=equipo, registros_equipo__activo=True, activo=True
            )
            .exclude(id__in=sus)
            .distinct()
            .order_by("dorsal")
        )
    return render(request, "reports/reporte_credenciales.html", {
        "categorias": categorias,
        "equipos": equipos,
        "equipo": equipo,
        "cat_id": int(cat_id) if cat_id else None,
        "equipo_id": int(equipo_id) if equipo_id else None,
        "jugadores": jugadores,
        "mostrar_logo": "1" in request.GET.getlist("logo"),
        "mostrar_numero": "1" in request.GET.getlist("numero"),
    })


def reporte_credenciales_pdf(request):
    if not request.user.is_authenticated or not request.user.rol or not request.user.rol.permisos.get("credenciales_ver", False):
        return redirect("login")

    jugadores_ids = request.GET.get("jugadores")
    equipo_id = request.GET.get("equipo")
    mostrar_logo = "1" in request.GET.getlist("logo")
    mostrar_numero = "1" in request.GET.getlist("numero")
    sus = _suspensos_globales()

    if jugadores_ids:
        ids = [int(x) for x in jugadores_ids.split(",") if x.strip().isdigit()]
        jugadores = list(Jugador.objects.filter(id__in=ids, activo=True).exclude(id__in=sus).select_related("equipo__categoria").order_by("nombre", "apellido"))
        if not jugadores:
            messages.error(request, "No se encontraron jugadores seleccionados.")
            return redirect("reporte_credenciales")
        card_items = []
        for j in jugadores:
            registros = j.registros_equipo.filter(activo=True).select_related("equipo", "equipo__categoria").order_by("-es_principal", "id")
            if registros:
                card_items.extend((j, r.equipo) for r in registros)
            else:
                card_items.append((j, j.equipo))
        teams = {eq.nombre for _, eq in card_items}
        filename = f"credenciales_{list(teams)[0]}.pdf" if len(teams) == 1 else "credenciales_seleccionadas.pdf"
    elif equipo_id:
        equipo = get_object_or_404(Equipo, pk=equipo_id)
        jugadores = list(Jugador.objects.filter(registros_equipo__equipo=equipo, registros_equipo__activo=True, activo=True).exclude(id__in=sus).distinct().select_related("equipo__categoria").order_by("nombre", "apellido"))
        if not jugadores:
            messages.error(request, "El equipo no tiene jugadores activos.")
            return redirect("reporte_credenciales")
        card_items = [(j, equipo) for j in jugadores]
        filename = f"credenciales_{equipo.nombre}.pdf"
    else:
        messages.error(request, "Selecciona un equipo o jugadores.")
        return redirect("reporte_credenciales")

    try:
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = f"attachment; filename={filename}"
        p = canvas.Canvas(response, pagesize=letter)
        w, h = letter

        card_w = 243
        card_h = 153
        gap_x = 40
        gap_y = 30
        cols = 2
        rows = 4
        total_w = cols * card_w + (cols - 1) * gap_x
        total_h = rows * card_h + (rows - 1) * gap_y
        offset_x = (w - total_w) / 2
        top_y = h - (h - total_h) / 2

        cfg = ConfiguracionLiga.obtener()
        name_font = "Helvetica-Bold"
        data_font = "Helvetica"

        def draw_soccer_bg(cx, cy, cw, ch):
            p.setStrokeColor(colors.HexColor("#d5edd5"))
            p.setLineWidth(0.3)
            p.rect(cx + 4, cy + 4, cw - 8, ch - 8, fill=0, stroke=1)
            p.line(cx + cw / 2, cy + 4, cx + cw / 2, cy + ch - 4)
            p.circle(cx + cw / 2, cy + ch / 2, 10, fill=0, stroke=1)
            for left in [True, False]:
                sign = 1 if left else -1
                border = cx if left else cx + cw
                p.rect(border - sign * 22, cy + (ch - 14) / 2, 22, 14, fill=0, stroke=1)
                p.rect(border - sign * 10, cy + (ch - 8) / 2, 10, 8, fill=0, stroke=1)

        bar_h = 26
        content_pad = 4

        for idx, (j, eq_card) in enumerate(card_items):
            pos = idx % (cols * rows)
            if pos == 0:
                if idx > 0:
                    p.showPage()

            col = pos % cols
            row = pos // cols
            x = offset_x + col * (card_w + gap_x)
            y = top_y - (row + 1) * card_h - row * gap_y
            content_y = y + content_pad
            content_h_top = y + card_h - bar_h - content_pad
            content_h = content_h_top - content_y

            cat = eq_card.categoria

            # Shadow
            p.setFillColor(colors.HexColor("#d0d0d0"))
            p.roundRect(x + 2, y - 2, card_w, card_h, 6, fill=1, stroke=0)

            # Card background (image or soccer pattern)
            p.saveState()
            clip = p.beginPath()
            clip.roundRect(x, y, card_w, card_h, 6)
            p.clipPath(clip, stroke=0, fill=0)
            fondo_buf = _imagen_pdf(cat.fondo_credencial) if cat.fondo_credencial else None
            if fondo_buf:
                p.drawImage(fondo_buf, x, y, width=card_w, height=card_h, preserveAspectRatio=False)
            else:
                draw_soccer_bg(x, y, card_w, card_h)
            p.restoreState()

            # Card border
            p.setStrokeColor(colors.HexColor("#2d6b2e"))
            p.setLineWidth(2.5)
            p.roundRect(x, y, card_w, card_h, 6, fill=0, stroke=1)

            # Green top bar with team name
            p.setFillColor(colors.HexColor("#2d6b2e"))
            bar_path = p.beginPath()
            bar_path.moveTo(x + 6, y + card_h)
            bar_path.lineTo(x + card_w - 6, y + card_h)
            bar_path.lineTo(x + card_w, y + card_h - 6)
            bar_path.lineTo(x + card_w, y + card_h - bar_h)
            bar_path.lineTo(x, y + card_h - bar_h)
            bar_path.lineTo(x, y + card_h - 6)
            bar_path.close()
            p.drawPath(bar_path, fill=1, stroke=0)

            bar_center_x = x + card_w / 2
            if cfg.logo:
                bar_center_x = x + 54 + (card_w - 54) / 2  # avoid overlap with logo
            p.setFillColor(colors.white)
            bar_text_y = y + card_h - bar_h + 8
            league_label = cfg.nombre_liga.upper()
            max_w_team = card_w - 56
            p.setFont(name_font, 12)
            if p.stringWidth(league_label, name_font, 12) <= max_w_team:
                p.drawCentredString(bar_center_x, bar_text_y, league_label)
            else:
                p.setFont(name_font, 9)
                words = league_label.split()
                line1, line2 = "", ""
                for w in words:
                    candidate = (line1 + " " + w).strip()
                    if p.stringWidth(candidate, name_font, 9) <= max_w_team:
                        line1 = candidate
                    else:
                        line2 = (line2 + " " + w).strip()
                if not line1:
                    mid = len(league_label) // 2
                    line1, line2 = league_label[:mid], league_label[mid:]
                while p.stringWidth(line1, name_font, 9) > max_w_team and len(line1) > 2:
                    line1 = line1[:-1]
                while p.stringWidth(line2, name_font, 9) > max_w_team and len(line2) > 2:
                    line2 = line2[:-1]
                p.drawCentredString(bar_center_x, bar_text_y + 4, line1)
                if line2:
                    p.drawCentredString(bar_center_x, bar_text_y - 4, line2)

            # League logo on the left side of the bar, bigger
            logo_buf = _imagen_pdf(cfg.logo) if cfg.logo else None
            if logo_buf:
                try:
                    logo_size = 44
                    logo_x = x + 2
                    logo_y = y + card_h - logo_size
                    p.drawImage(logo_buf, logo_x, logo_y, width=logo_size, height=logo_size, preserveAspectRatio=True, mask='auto')
                except Exception:
                    pass

            # Player photo circle
            photo_size = 64
            photo_x = x + 10
            photo_y = content_y + (content_h - photo_size) / 2 + 4
            cx = photo_x + photo_size / 2
            cy = photo_y + photo_size / 2
            cr = photo_size / 2

            p.setFillColor(colors.white)
            p.setStrokeColor(colors.HexColor("#2d6b2e"))
            p.setLineWidth(1.5)
            p.circle(cx, cy, cr + 1, fill=1, stroke=1)

            initials = f"{j.nombre[0]}{j.apellido[0]}" if j.nombre and j.apellido else "?"
            foto_buf = _imagen_pdf(j.foto) if j.foto else None
            if foto_buf:
                try:
                    p.saveState()
                    clip_photo = p.beginPath()
                    clip_photo.circle(cx, cy, cr)
                    p.clipPath(clip_photo, stroke=0, fill=0)
                    p.drawImage(foto_buf, photo_x, photo_y, width=photo_size, height=photo_size, preserveAspectRatio=True, mask="auto")
                    p.restoreState()
                except Exception:
                    p.setFillColor(colors.HexColor("#ddd"))
                    p.circle(cx, cy, cr, fill=1, stroke=0)
                    p.setFillColor(colors.HexColor("#888"))
                    p.setFont(data_font, 22)
                    p.drawCentredString(cx, cy - 7, initials)
            else:
                p.setFillColor(colors.HexColor("#eee"))
                p.circle(cx, cy, cr, fill=1, stroke=0)
                p.setFillColor(colors.HexColor("#999"))
                p.setFont(data_font, 22)
                p.drawCentredString(cx, cy - 7, initials)

            # Helper to draw text with outline (shadow method, compatible with all ReportLab versions)
            def outlined_text(x, y, text, font_name, font_size, outline_color=colors.HexColor("#000000"), fill_color=colors.white):
                p.setFillColor(outline_color)
                for dx, dy in [(-1.0, -1.0), (-1.0, 0), (1.0, 0), (-1.0, 1.0), (0, 1.0), (1.0, 1.0), (1.0, -1.0), (0, -1.0)]:
                    p.setFont(font_name, font_size)
                    p.drawString(x + dx, y + dy, text)
                p.setFillColor(fill_color)
                p.setFont(font_name, font_size)
                p.drawString(x, y, text)

            # Player info (right of photo)
            text_x = x + 86
            avail_w = 110

            # Name (bold, wraps to 2 lines expanding upward, centered)
            full_name = f"{j.nombre} {j.apellido}"
            name_size = 11
            name_lines = []
            while name_size >= 8:
                words = full_name.split()
                lines = []
                cur = ""
                for word in words:
                    cand = (cur + " " + word).strip()
                    if p.stringWidth(cand, name_font, name_size) <= avail_w:
                        cur = cand
                    else:
                        if cur:
                            lines.append(cur)
                        cur = word
                if cur:
                    lines.append(cur)
                if len(lines) <= 2:
                    name_lines = lines
                    break
                name_size -= 1
            name_y = content_y + content_h - 40
            line_h = name_size * 1.15
            name_cx = text_x + avail_w / 2
            for k, ln in enumerate(name_lines):
                ly = name_y + (len(name_lines) - 1 - k) * line_h
                ln_w = p.stringWidth(ln, name_font, name_size)
                outlined_text(name_cx - ln_w / 2, ly, ln, name_font, name_size)

            # Category (9pt)
            outlined_text(text_x, content_y + content_h - 56, f"Categor?a: {cat.nombre}", data_font, 9)

            # Documento (9pt)
            tipo_label = {"CURP": "CURP", "PAS": "PASAPORTE", "INM": "INM", "OTR": "DOC"}.get(j.tipo_documento, "CURP")
            curp_text = j.curp if j.curp else "S/C"
            outlined_text(text_x, content_y + content_h - 72, f"{tipo_label}: {curp_text}", data_font, 9)

            # Team name at bottom-left corner
            team_name_x = x + 4
            outlined_text(team_name_x, y + 9, eq_card.nombre, name_font, 11)

            # Team logo at top-right corner, just below the green bar
            if mostrar_logo:
                team_logo_size = 36
                tl_x = x + card_w - 4 - team_logo_size
                tl_y = y + card_h - bar_h - team_logo_size - 4
                logo_drawn = False
                eq_logo_buf = _imagen_pdf(eq_card.logo) if eq_card.logo else None
                if eq_logo_buf:
                    try:
                        p.drawImage(eq_logo_buf, tl_x, tl_y, width=team_logo_size, height=team_logo_size, preserveAspectRatio=True, mask='auto')
                        logo_drawn = True
                    except Exception:
                        pass
                if not logo_drawn:
                    # Escudo generico de relleno para saber donde va el logo del equipo
                    lcx = tl_x + team_logo_size / 2
                    lcy = tl_y + team_logo_size / 2
                    p.setFillColor(colors.HexColor("#d7d7d7"))
                    p.setStrokeColor(colors.HexColor("#9a9a9a"))
                    p.setLineWidth(0.6)
                    p.circle(lcx, lcy, team_logo_size / 2 - 1, fill=1, stroke=1)
                    r = team_logo_size * 0.32
                    pts = []
                    for i in range(10):
                        rad = r if i % 2 == 0 else r * 0.45
                        ang = -math.pi / 2 + i * math.pi / 5
                        pts.append((lcx + rad * math.cos(ang), lcy + rad * math.sin(ang)))
                    star = p.beginPath()
                    star.moveTo(*pts[0])
                    for pt in pts[1:]:
                        star.lineTo(*pt)
                    star.close()
                    p.setFillColor(colors.HexColor("#777777"))
                    p.setStrokeColor(colors.HexColor("#9a9a9a"))
                    p.drawPath(star, fill=1, stroke=1)

            # Dorsal badge (rectangular, opcional seg?n el checkbox "n?mero")
            if mostrar_numero:
                jersey_w = 28
                jersey_body_h = 20
                jersey_x = x + card_w - 12 - jersey_w
                jersey_y = y + 4
                jersey_cx = jersey_x + jersey_w / 2
                jersey_cy = jersey_y + jersey_body_h / 2

                # Badge body (rounded rectangle)
                p.setFillColor(colors.HexColor("#222222"))
                p.roundRect(jersey_x, jersey_y, jersey_w, jersey_body_h, 4, fill=1, stroke=0)

                # Thin white outline around the body
                p.setStrokeColor(colors.HexColor("#cccccc"))
                p.setLineWidth(0.5)
                p.roundRect(jersey_x, jersey_y, jersey_w, jersey_body_h, 4, fill=0, stroke=1)

                # Number centered in body
                p.setFillColor(colors.white)
                p.setFont(name_font, 9)
                dorsal_str = str(j.dorsal) if j.dorsal is not None else "-"
                p.drawCentredString(jersey_cx, jersey_cy - 3, dorsal_str)

        p.showPage()
        p.save()
        return response
    except Exception as e:
        import traceback
        traceback.print_exc()
        messages.error(request, f"Error al generar PDF: {e}")
        return redirect("reporte_credenciales")


def reporte_suscriptores_xlsx(request):
    if not request.user.is_authenticated or not request.user.rol or not request.user.rol.permisos.get("reporte_suscriptores", False):
        return redirect("login")
    cat_id = request.GET.get("categoria")
    wb, response = _xlsx_response("suscriptores")
    ws = wb.active
    ws.title = "Suscriptores"
    filtros = []
    if cat_id:
        from league.models import Categoria
        cat = Categoria.objects.filter(id=cat_id).first()
        if cat:
            filtros.append(("Categor?a", cat.nombre))
    start = _add_filtros(ws, filtros)
    qs = SuscripcionEmail.objects.all().order_by("-creado")
    if cat_id:
        qs = qs.filter(categorias__id=cat_id)
    headers = ["Email", "Usuario", "Categor?as", "Recibe Roles", "Recibe Estad?sticas", "Activo", "Creado"]
    from openpyxl.styles import Font, PatternFill
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=start, column=col, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="333333", end_color="333333", fill_type="solid")
    for i, s in enumerate(qs, start + 1):
        cats = ", ".join(s.categorias.values_list("nombre", flat=True)) if s.categorias.exists() else "Todas"
        usuario = s.usuario.username if s.usuario else "-"
        ws.cell(row=i, column=1, value=s.email)
        ws.cell(row=i, column=2, value=usuario)
        ws.cell(row=i, column=3, value=cats)
        ws.cell(row=i, column=4, value="S?" if s.recibir_roles else "No")
        ws.cell(row=i, column=5, value="S?" if s.recibir_estadisticas else "No")
        ws.cell(row=i, column=6, value="S?" if s.activo else "No")
        ws.cell(row=i, column=7, value=s.creado.strftime("%d/%m/%Y"))
    # Ajustar ancho de columnas
    for col in range(1, len(headers) + 1):
        ws.column_dimensions[chr(64 + col)].width = 20
    wb.save(response)
    return response


def reporte_registro_pdf(request):
    """Exporta a PDF el reporte de registro de jugadores de un equipo."""
    from league.models import Categoria, Temporada, Equipo, Jugador, JugadorEquipo
    from django.db.models import Q
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    import os
    from django.conf import settings

    cat_id = request.GET.get("categoria") or ""
    temp_id = request.GET.get("temporada") or ""
    eq_id = request.GET.get("equipo") or ""

    if not eq_id:
        messages.error(request, "Debes seleccionar un equipo.")
        return redirect("reporte_registro")

    equipo = Equipo.objects.filter(pk=eq_id).first()
    if not equipo:
        messages.error(request, "Equipo no encontrado.")
        return redirect("reporte_registro")

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

    # Configuración de la liga
    from league.models import ConfiguracionLiga
    config = ConfiguracionLiga.obtener()

    # Crear PDF
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = 'attachment; filename="registro_{}.pdf"'.format(equipo.nombre.replace(" ", "_"))

    p = canvas.Canvas(response, pagesize=letter)
    w, h = letter

    # Encabezado por página
    def draw_header(p):
        y = h - 18 * mm
        p.setFillColor(colors.black)
        p.setFont("Helvetica-Bold", 18)

        # Logo de la liga (más grande y visible)
        cfg = ConfiguracionLiga.obtener()
        if cfg.logo:
            try:
                local_path = os.path.join(settings.MEDIA_ROOT, cfg.logo.name)
                if os.path.exists(local_path):
                    p.drawImage(local_path, 15 * mm, h - 30 * mm, width=30 * mm, height=30 * mm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
        # Logo del equipo (más pequeño, a la derecha)
        if equipo.logo:
            try:
                local_path = os.path.join(settings.MEDIA_ROOT, equipo.logo.name)
                if os.path.exists(local_path):
                    p.drawImage(local_path, w - 50 * mm, h - 28 * mm, width=20 * mm, height=20 * mm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass
        p.setFont("Helvetica-Bold", 20)
        p.drawString(25 * mm, h - 18 * mm, cfg.nombre_liga)
        p.setFont("Helvetica", 11)
        p.drawString(25 * mm, h - 24 * mm, "Registro de jugadores - " + equipo.nombre)
        p.setFont("Helvetica", 10)
        # Obtener nombre de la temporada desde temp_id del request
        from league.models import Temporada
        temp_name = "N/A"
        if temp_id:
            temp = Temporada.objects.filter(pk=temp_id).first()
            if temp:
                temp_name = temp.nombre
        p.drawString(25 * mm, h - 30 * mm, "Categoría: " + equipo.categoria.nombre + "  |  Temporada: " + temp_name)
        # Línea separadora
        p.setStrokeColor(colors.black)
        p.setLineWidth(0.5)
        p.line(15 * mm, h - 35 * mm, w - 15 * mm, h - 35 * mm)
        return h - 45 * mm

    # Datos de jugadores
    jugadores_list = list(jugadores)
    total_jugadores = len(jugadores_list)

    # Layout: tarjetas de jugadores en grid (2 columnas x 4 filas = 8 por página)
    # Márgenes más amplios para impresión (no al ras de la hoja)
    margin_left = 18 * mm
    margin_right = 18 * mm
    margin_top = 50 * mm   # espacio para header
    margin_bottom = 18 * mm
    card_w = (w - 36 * mm) / 2  # (216mm - 36mm - 5mm gap) / 2 = 87.5mm
    card_h = 58 * mm  # más pequeña para que quepan 8 por página con margen
    gap_x = 5 * mm
    gap_y = 12 * mm  # más espacio vertical entre filas

    page_num = 1
    p.setTitle("Registro " + equipo.nombre)
    p.setAuthor(config.nombre_liga)

    # Iterar jugadores y dibujar tarjetas
    for idx, j in enumerate(jugadores_list):
        col = idx % 2
        row_in_page = (idx // 2) % 4

        if idx > 0 and idx % 8 == 0:
            p.showPage()
            page_num += 1

        # Posición de la tarjeta
        x = 20 * mm + col * (87.5 * mm + 5 * mm)
        y = draw_header(p) - 58 * mm - ((idx // 2) % 4) * (58 * mm + 12 * mm)
        x = 20 * mm + col * (87.5 * mm + 5 * mm)

        # Fondo de la tarjeta (redondeada)
        p.setFillColor(colors.white)
        p.setStrokeColor(colors.HexColor("#cccccc"))
        p.setLineWidth(0.5)
        p.roundRect(x, y, 87.5 * mm, 58 * mm, 3 * mm, fill=1, stroke=1)

        # Coordenadas internas de la tarjeta (origen en esquina superior izquierda)
        card_x = x
        card_y_top = y + 58 * mm  # esquina superior de la tarjeta (y + altura)

        # Foto del jugador (esquina superior derecha de la tarjeta)
        img_w = 30 * mm
        img_h = 35 * mm
        img_x = 87.5 * mm - 4 * mm - 30 * mm - 3 * mm
        img_y = 3 * mm
        p.setFillColor(colors.HexColor("#f0f0f0"))
        p.roundRect(x + img_x, y + 58 * mm - 3 * mm - 35 * mm, 30 * mm, 35 * mm, 2 * mm, fill=1, stroke=0)
        if j.foto:
            try:
                local_path = os.path.join(settings.MEDIA_ROOT, j.foto.name)
                if os.path.exists(local_path):
                    from reports.views import _imagen_pdf
                    img_reader = _imagen_pdf(j.foto)
                    if img_reader:
                        p.drawImage(img_reader, x + img_x, y + 58 * mm - 3 * mm - 35 * mm, 
                                    width=30 * mm, height=35 * mm, preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

        # Nombre y apellido (arriba a la izquierda, al lado de la foto)
        p.setFont("Helvetica-Bold", 11)
        p.setFillColor(colors.black)
        p.drawString(x + 3 * mm, y + 58 * mm - 10 * mm, j.nombre + " " + j.apellido)

        # Posición
        if j.posicion:
            p.setFont("Helvetica", 9)
            p.setFillColor(colors.black)
            p.drawString(x + 3 * mm, y + 58 * mm - 25 * mm, "Pos: " + j.get_posicion_display())

        # Fecha de nacimiento
        if j.fecha_nacimiento:
            p.setFont("Helvetica", 9)
            p.drawString(x + 3 * mm, y + 58 * mm - 33 * mm, "Nac: " + j.fecha_nacimiento.strftime("%d/%m/%Y"))

        # Edad
        edad = j.edad()
        if edad is not None:
            p.setFont("Helvetica", 9)
            p.drawString(x + 3 * mm, y + 58 * mm - 41 * mm, "Edad: " + str(edad) + " años")

        # Documento (incluye CURP si existe)
        if j.curp or j.tipo_documento:
            p.setFont("Helvetica", 7)
            p.setFillColor(colors.grey)
            doc_parts = []
            if j.tipo_documento:
                doc_parts.append(j.get_tipo_documento_display())
            if j.curp:
                doc_parts.append(j.curp)
            doc_text = " | ".join(doc_parts) if doc_parts else "—"
            p.drawString(x + 3 * mm, y + 58 * mm - 50 * mm, "Doc: " + doc_text)

    # Footer en última página
    p.setFont("Helvetica", 8)
    p.setFillColor(colors.grey)
    p.drawString(20 * mm, 10 * mm, "Generado por " + config.nombre_liga)
    p.drawRightString(w - 20 * mm, 10 * mm, "Total jugadores: " + str(total_jugadores))

    p.save()
    return response