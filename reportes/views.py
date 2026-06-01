from datetime import timedelta, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, F, DecimalField, ExpressionWrapper, Q, Max
from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncHour
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from decorators import admin_required
from inventario.models import Libro
from proveedores.models import Adquisicion, DetalleAdquisicion, Proveedor
from reservas.models import Reserva
from django.contrib.auth.models import User
from ventas.models import Venta, DetalleVenta


PERIODOS = {
    'today': 'Hoy',
    'week': 'Esta semana',
    'month': 'Este mes',
}

ALERTA_STOCK_CRITICO = 1
ALERTA_PROVEEDOR_INACTIVO_DIAS = 90
ALERTA_CLIENTE_INACTIVO_DIAS = 60
ALERTA_CLIENTE_FRECUENTE_MOVIMIENTOS = 3


def _inicio_periodo(periodo, ahora):
    inicio_hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    if periodo == 'today':
        return inicio_hoy
    if periodo == 'week':
        return inicio_hoy - timedelta(days=ahora.weekday())
    if periodo == 'month':
        return inicio_hoy.replace(day=1)
    return inicio_hoy.replace(day=1)


def _resolver_periodo(request):
    periodo = request.GET.get('periodo', 'month')
    if periodo not in PERIODOS and periodo != 'custom':
        periodo = 'month'

    ahora = timezone.localtime()

    if periodo == 'custom':
        try:
            inicio_periodo = timezone.make_aware(datetime.strptime(request.GET.get('fecha_inicio'), '%Y-%m-%d'))
            fin_periodo = timezone.make_aware(datetime.strptime(request.GET.get('fecha_fin'), '%Y-%m-%d')).replace(hour=23, minute=59, second=59)
            periodo_label = f"{inicio_periodo.strftime('%d/%m/%Y')} al {fin_periodo.strftime('%d/%m/%Y')}"
        except (ValueError, TypeError):
            inicio_periodo = _inicio_periodo('month', ahora)
            fin_periodo = ahora
            periodo = 'month'
            periodo_label = PERIODOS['month']
    else:
        inicio_periodo = _inicio_periodo(periodo, ahora)
        fin_periodo = ahora
        periodo_label = PERIODOS[periodo]

    return periodo, periodo_label, inicio_periodo, fin_periodo, ahora


def _decimal_or_zero(value):
    return value or Decimal('0.00')


def _date_key(value):
    return value.date() if hasattr(value, 'date') else value


def _build_report_data(request):
    periodo, periodo_label, inicio_periodo, fin_periodo, ahora = _resolver_periodo(request)

    inicio_180_dias = ahora - timedelta(days=180)

    ventas_periodo = Venta.objects.filter(
        fecha_venta__gte=inicio_periodo,
        fecha_venta__lte=fin_periodo,
    )
    detalle_periodo = DetalleVenta.objects.filter(
        venta__fecha_venta__gte=inicio_periodo,
        venta__fecha_venta__lte=fin_periodo,
    )
    compras_periodo = Adquisicion.objects.filter(
        fecha__gte=inicio_periodo.date(),
        fecha__lte=fin_periodo.date(),
    )
    detalle_compras_periodo = DetalleAdquisicion.objects.filter(
        adquisicion__fecha__gte=inicio_periodo.date(),
        adquisicion__fecha__lte=fin_periodo.date(),
    )

    ganancia_expr = ExpressionWrapper(
        (F('precio_unitario') - F('ejemplar__precio_compra')) * F('cantidad'),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    ventas_totales = ventas_periodo.aggregate(
        total=Coalesce(Sum('total'), Decimal('0.00')),
        tickets=Count('id'),
    )
    ganancia_neta = detalle_periodo.aggregate(
        total=Coalesce(Sum(ganancia_expr), Decimal('0.00'))
    )['total']

    compras_totales = compras_periodo.aggregate(
        total=Coalesce(Sum('total'), Decimal('0.00')),
        lotes=Count('id'),
        pendientes=Count('id', filter=Q(estado='por_inventariar')),
    )
    compras_unidades = detalle_compras_periodo.aggregate(
        total=Coalesce(Sum('cantidad'), 0)
    )['total']
    compras_monto = _decimal_or_zero(compras_totales['total'])
    ventas_monto = _decimal_or_zero(ventas_totales['total'])
    flujo_neto = ventas_monto - compras_monto
    margen_operativo = ((ganancia_neta / ventas_monto) * Decimal('100')) if ventas_monto else Decimal('0.00')

    top_libros = list(
        detalle_periodo.values(
            'ejemplar__libro__titulo',
            'ejemplar__libro__autor',
        ).annotate(
            unidades_vendidas=Coalesce(Sum('cantidad'), 0),
            registros=Count('id'),
            ingresos=Coalesce(Sum('subtotal'), Decimal('0.00')),
        ).order_by('-unidades_vendidas', '-registros', 'ejemplar__libro__titulo')[:5]
    )

    top_proveedores = list(
        compras_periodo.values('proveedor_id', 'proveedor__nombre')
        .annotate(
            lotes=Count('id', distinct=True),
            gasto=Coalesce(Sum('total'), Decimal('0.00')),
            ultima_compra=Max('fecha'),
        )
        .order_by('-gasto', '-lotes', 'proveedor__nombre')[:5]
    )
    unidades_por_proveedor = {
        item['adquisicion__proveedor_id']: item['unidades']
        for item in detalle_compras_periodo.values('adquisicion__proveedor_id')
        .annotate(unidades=Coalesce(Sum('cantidad'), 0))
    }
    for proveedor in top_proveedores:
        proveedor['unidades'] = unidades_por_proveedor.get(proveedor['proveedor_id'], 0)

    compras_recientes = list(
        compras_periodo.select_related('proveedor')
        .annotate(unidades=Coalesce(Sum('detalles__cantidad'), 0))
        .order_by('-fecha', '-creado_en')[:8]
    )

    stock_bajo = list(
        Libro.objects.annotate(
            stock_total=Coalesce(Sum('ejemplares__stock'), 0),
            ejemplares_registrados=Count('ejemplares', distinct=True),
        ).filter(
            ejemplares_registrados__gt=0,
            stock_total__lt=1,
        ).order_by('stock_total', 'titulo')[:8]
    )

    delta_days = (fin_periodo - inicio_periodo).days

    if delta_days <= 1:
        ventas_chart_qs = (
            ventas_periodo
            .annotate(periodo_agrupado=TruncHour('fecha_venta'))
            .values('periodo_agrupado')
            .annotate(total=Coalesce(Sum('total'), Decimal('0.00')), tickets=Count('id'))
            .order_by('periodo_agrupado')
        )
        ventas_chart_map = {
            item['periodo_agrupado'].replace(minute=0, second=0, microsecond=0): item
            for item in ventas_chart_qs if item['periodo_agrupado']
        }
        compras_chart_qs = (
            compras_periodo
            .annotate(periodo_agrupado=TruncDay('fecha'))
            .values('periodo_agrupado')
            .annotate(total=Coalesce(Sum('total'), Decimal('0.00')), lotes=Count('id'))
        )
        compras_total_dia = sum((item['total'] for item in compras_chart_qs), Decimal('0.00'))
        compras_lotes_dia = sum((item['lotes'] for item in compras_chart_qs), 0)

        chart_labels = []
        chart_totals = []
        chart_tickets = []
        chart_compras = []
        chart_lotes = []

        for i in range(24):
            hora_actual = inicio_periodo.replace(hour=i, minute=0, second=0, microsecond=0)
            if hora_actual > ahora:
                break
            dato = ventas_chart_map.get(hora_actual)
            chart_labels.append(hora_actual.strftime('%H:00'))
            chart_totals.append(float(dato['total']) if dato else 0)
            chart_tickets.append(dato['tickets'] if dato else 0)
            chart_compras.append(float(compras_total_dia) if i == 12 else 0)
            chart_lotes.append(compras_lotes_dia if i == 12 else 0)
    else:
        ventas_chart_qs = (
            ventas_periodo
            .annotate(periodo_agrupado=TruncDay('fecha_venta'))
            .values('periodo_agrupado')
            .annotate(total=Coalesce(Sum('total'), Decimal('0.00')), tickets=Count('id'))
            .order_by('periodo_agrupado')
        )
        compras_chart_qs = (
            compras_periodo
            .annotate(periodo_agrupado=TruncDay('fecha'))
            .values('periodo_agrupado')
            .annotate(total=Coalesce(Sum('total'), Decimal('0.00')), lotes=Count('id'))
            .order_by('periodo_agrupado')
        )
        ventas_chart_map = {
            _date_key(item['periodo_agrupado']): item for item in ventas_chart_qs if item['periodo_agrupado']
        }
        compras_chart_map = {
            _date_key(item['periodo_agrupado']): item for item in compras_chart_qs if item['periodo_agrupado']
        }

        chart_labels = []
        chart_totals = []
        chart_tickets = []
        chart_compras = []
        chart_lotes = []

        dias_a_mostrar = min(delta_days + 1, 60)
        for offset in range(dias_a_mostrar):
            fecha_actual = (inicio_periodo + timedelta(days=offset)).date()
            if fecha_actual > ahora.date() and periodo != 'custom':
                continue
            venta_dato = ventas_chart_map.get(fecha_actual)
            compra_dato = compras_chart_map.get(fecha_actual)
            chart_labels.append(fecha_actual.strftime('%d %b'))
            chart_totals.append(float(venta_dato['total']) if venta_dato else 0)
            chart_tickets.append(venta_dato['tickets'] if venta_dato else 0)
            chart_compras.append(float(compra_dato['total']) if compra_dato else 0)
            chart_lotes.append(compra_dato['lotes'] if compra_dato else 0)

    ventas_mensuales = list(
        Venta.objects.filter(fecha_venta__gte=inicio_180_dias, fecha_venta__lte=ahora)
        .annotate(periodo=TruncMonth('fecha_venta'))
        .values('periodo')
        .annotate(total=Coalesce(Sum('total'), Decimal('0.00')), tickets=Count('id'))
        .order_by('-periodo')[:6]
    )
    compras_mensuales = list(
        Adquisicion.objects.filter(fecha__gte=inicio_180_dias.date(), fecha__lte=ahora.date())
        .annotate(periodo=TruncMonth('fecha'))
        .values('periodo')
        .annotate(total=Coalesce(Sum('total'), Decimal('0.00')), lotes=Count('id'))
        .order_by('-periodo')[:6]
    )

    meses = {}
    for item in ventas_mensuales:
        meses[item['periodo']] = {'periodo': item['periodo'], 'ventas': item['total'], 'tickets': item['tickets'], 'compras': Decimal('0.00'), 'lotes': 0}
    for item in compras_mensuales:
        meses.setdefault(item['periodo'], {'periodo': item['periodo'], 'ventas': Decimal('0.00'), 'tickets': 0, 'compras': Decimal('0.00'), 'lotes': 0})
        meses[item['periodo']]['compras'] = item['total']
        meses[item['periodo']]['lotes'] = item['lotes']
    resumen_mensual = sorted(
        meses.values(),
        key=lambda item: item['periodo'].strftime('%Y%m') if item['periodo'] else '',
        reverse=True,
    )[:6]
    for item in resumen_mensual:
        item['flujo'] = item['ventas'] - item['compras']
        item['flujo_negativo'] = item['flujo'] < 0

    libros_en_stock = (
        Libro.objects.annotate(stock_total=Coalesce(Sum('ejemplares__stock'), 0))
        .filter(stock_total__gt=0)
        .count()
    )
    apartados_activos = Reserva.objects.filter(estado='pendiente').count()

    return {
        'periodo': periodo,
        'periodos': PERIODOS,
        'periodo_label': periodo_label,
        'ventas_monto': ventas_monto,
        'ventas_tickets': ventas_totales['tickets'],
        'ganancia_neta': ganancia_neta,
        'compras_monto': compras_monto,
        'compras_lotes': compras_totales['lotes'],
        'compras_unidades': compras_unidades,
        'compras_pendientes': compras_totales['pendientes'],
        'flujo_neto': flujo_neto,
        'flujo_neto_negativo': flujo_neto < 0,
        'margen_operativo': margen_operativo.quantize(Decimal('0.01')),
        'libros_en_stock': libros_en_stock,
        'apartados_activos': apartados_activos,
        'top_libros': top_libros,
        'top_proveedores': top_proveedores,
        'compras_recientes': compras_recientes,
        'stock_bajo': stock_bajo,
        'chart_labels': chart_labels,
        'chart_totals': chart_totals,
        'chart_tickets': chart_tickets,
        'chart_compras': chart_compras,
        'chart_lotes': chart_lotes,
        'ventas_mensuales': ventas_mensuales,
        'compras_mensuales': compras_mensuales,
        'resumen_mensual': resumen_mensual,
        'filtro_desde': inicio_periodo,
        'filtro_hasta': fin_periodo,
    }


@login_required
@admin_required
@require_http_methods(["GET"])
def dashboard_reportes(request):
    return render(request, 'reportes/dashboard_reportes.html', _build_report_data(request))


def _pdf_escape(text):
    return str(text).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')


def _pdf_text_width(text, size):
    return len(str(text)) * size * Decimal('0.48')


def _pdf_wrap_text(text, max_width, size=9):
    words = str(text).split()
    if not words:
        return ['']
    lines = []
    current = ''
    for word in words:
        candidate = f'{current} {word}'.strip()
        if _pdf_text_width(candidate, size) <= Decimal(str(max_width)):
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


class _ReportPdfCanvas:
    width = 612
    height = 842
    margin = 42

    def __init__(self, data):
        self.data = data
        self.pages = []
        self.ops = []
        self.y = 0
        self.page_num = 0
        self.new_page()

    def new_page(self):
        if self.ops:
            self._footer()
            self.pages.append('\n'.join(self.ops))
        self.page_num += 1
        self.ops = []
        self.y = 760
        self._header()

    def finish(self):
        self._footer()
        self.pages.append('\n'.join(self.ops))
        return self.pages

    def ensure_space(self, height):
        if self.y - height < 72:
            self.new_page()

    def color(self, r, g, b, stroke=False):
        op = 'RG' if stroke else 'rg'
        self.ops.append(f'{r:.3f} {g:.3f} {b:.3f} {op}')

    def rect(self, x, y, w, h, fill=(1, 1, 1), stroke=None):
        self.color(*fill)
        if stroke:
            self.color(*stroke, stroke=True)
            self.ops.append(f'{x} {y} {w} {h} re B')
        else:
            self.ops.append(f'{x} {y} {w} {h} re f')

    def line(self, x1, y1, x2, y2, color=(0.78, 0.79, 0.72), width=1):
        self.color(*color, stroke=True)
        self.ops.append(f'{width} w {x1} {y1} m {x2} {y2} l S')

    def text(self, x, y, text, size=10, font='F1', color=(0.10, 0.11, 0.10)):
        self.color(*color)
        self.ops.append(f'BT /{font} {size} Tf {x} {y} Td ({_pdf_escape(text)}) Tj ET')

    def wrapped_text(self, x, y, text, width, size=9, leading=12, color=(0.45, 0.47, 0.42)):
        lines = _pdf_wrap_text(text, width, size)
        for idx, line in enumerate(lines):
            self.text(x, y - (idx * leading), line, size=size, color=color)
        return len(lines) * leading

    def _header(self):
        self.rect(0, 792, 612, 50, fill=(0.08, 0.09, 0.06))
        self.rect(42, 806, 36, 18, fill=(0.64, 0.77, 0.42))
        self.text(88, 816, 'LIBRERIA BARTLEBY', size=12, font='F2', color=(0.93, 0.94, 0.88))
        self.text(88, 802, 'Reporte operativo consolidado', size=8, color=(0.68, 0.70, 0.62))
        self.text(430, 812, self.data['periodo_label'], size=9, font='F2', color=(0.64, 0.77, 0.42))
        self.line(42, 780, 570, 780, color=(0.24, 0.30, 0.12), width=1)

    def _footer(self):
        self.line(42, 48, 570, 48, color=(0.78, 0.79, 0.72), width=.7)
        self.text(42, 32, 'Generado desde el modulo de Reportes', size=8, color=(0.45, 0.47, 0.42))
        self.text(530, 32, f'Pagina {self.page_num}', size=8, color=(0.45, 0.47, 0.42))

    def section(self, title, subtitle=None):
        self.ensure_space(46)
        self.text(42, self.y, title, size=16, font='F2', color=(0.24, 0.32, 0.10))
        self.y -= 16
        if subtitle:
            used = self.wrapped_text(42, self.y, subtitle, 520, size=8, leading=11)
            self.y -= used + 8
        else:
            self.y -= 12

    def kpi_grid(self, items):
        card_w = 124
        gap = 10
        card_h = 82
        self.ensure_space(card_h + 10)
        x = 42
        y = self.y - card_h
        for idx, item in enumerate(items):
            cx = x + idx * (card_w + gap)
            self.rect(cx, y, card_w, card_h, fill=(0.96, 0.96, 0.93), stroke=(0.78, 0.79, 0.72))
            self.text(cx + 12, y + 56, item['label'].upper(), size=7, font='F2', color=(0.45, 0.47, 0.42))
            self.text(cx + 12, y + 31, item['value'], size=15, font='F2', color=item.get('color', (0.24, 0.32, 0.10)))
            self.wrapped_text(cx + 12, y + 17, item.get('hint', ''), card_w - 24, size=7, leading=9, color=(0.45, 0.47, 0.42))
        self.y = y - 24

    def table(self, headers, rows, widths):
        row_h = 23
        header_h = 24
        self.ensure_space(header_h + row_h + 18)
        x = 42
        table_w = sum(widths)
        self.rect(x, self.y - header_h, table_w, header_h, fill=(0.92, 0.94, 0.88), stroke=(0.78, 0.79, 0.72))
        current_x = x
        for header, width in zip(headers, widths):
            self.text(current_x + 7, self.y - 16, header.upper(), size=7, font='F2', color=(0.35, 0.38, 0.30))
            current_x += width
        self.y -= header_h

        if not rows:
            self.rect(x, self.y - row_h, table_w, row_h, fill=(0.98, 0.98, 0.96), stroke=(0.78, 0.79, 0.72))
            self.text(x + 7, self.y - 15, 'Sin datos para este periodo.', size=9, color=(0.45, 0.47, 0.42))
            self.y -= row_h + 16
            return

        for index, row in enumerate(rows):
            self.ensure_space(row_h + 18)
            fill = (0.99, 0.99, 0.97) if index % 2 == 0 else (0.95, 0.96, 0.92)
            self.rect(x, self.y - row_h, table_w, row_h, fill=fill, stroke=(0.86, 0.86, 0.80))
            current_x = x
            for cell, width in zip(row, widths):
                value = str(cell)
                if len(value) > max(8, int(width / 5)):
                    value = value[:max(8, int(width / 5)) - 1] + '...'
                self.text(current_x + 7, self.y - 15, value, size=8, color=(0.10, 0.11, 0.10))
                current_x += width
            self.y -= row_h
        self.y -= 16

    def bar_chart(self, title, labels, values, height=120, color=(0.64, 0.77, 0.42)):
        self.ensure_space(height + 40)
        x = 42
        width = 520
        curr_y = self.y
        self.text(x, curr_y, title, size=10, font='F2', color=(0.24, 0.32, 0.10))
        
        chart_x = x + 35
        chart_y = curr_y - height + 15
        chart_w = width - 40
        chart_h = height - 30
        
        max_val = max(values) if values else 0
        if max_val == 0: max_val = 1
        
        ticks = 4
        for i in range(ticks + 1):
            tick_y = chart_y + (i * chart_h / ticks)
            tick_val = (i * max_val / ticks)
            self.text(x, tick_y - 3, f"${int(tick_val)}", size=6, color=(0.45, 0.47, 0.42))
            self.line(chart_x - 3, tick_y, chart_x + chart_w, tick_y, color=(0.92, 0.92, 0.90))

        self.line(chart_x, chart_y, chart_x + chart_w, chart_y, color=(0.78, 0.79, 0.72))
        self.line(chart_x, chart_y, chart_x, chart_y + chart_h, color=(0.78, 0.79, 0.72))
        
        if labels and values:
            n = len(labels)
            step_x = chart_w / n
            bar_w = step_x * 0.7
            
            for i, (lbl, val) in enumerate(zip(labels, values)):
                bx = chart_x + (i * step_x) + (step_x * 0.15)
                bh = (val / max_val) * chart_h
                self.rect(bx, chart_y, bar_w, max(bh, 1), fill=color, stroke=(0.45, 0.55, 0.30))
                
                if n <= 15 or i % max(1, int(n/8)) == 0:
                    self.text(bx, chart_y - 10, str(lbl)[:8], size=6, color=(0.45, 0.47, 0.42))
        
        self.y -= (height + 20)


def _build_pdf_document(page_streams):
    objects = []
    page_refs = []

    def add_object(content):
        objects.append(content)
        return len(objects)

    regular_font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    bold_font_id = add_object("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

    for stream in page_streams:
        content_id = add_object(f"<< /Length {len(stream.encode('latin-1', errors='replace'))} >>\nstream\n{stream}\nendstream")
        page_id = add_object(
            f"<< /Type /Page /Parent 0 0 R /MediaBox [0 0 612 842] "
            f"/Resources << /Font << /F1 {regular_font_id} 0 R /F2 {bold_font_id} 0 R >> >> "
            f"/Contents {content_id} 0 R >>"
        )
        page_refs.append(page_id)

    kids = " ".join(f"{page_id} 0 R" for page_id in page_refs)
    pages_id = add_object(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_refs)} >>")
    objects = [obj.replace("/Parent 0 0 R", f"/Parent {pages_id} 0 R") for obj in objects]
    catalog_id = add_object(f"<< /Type /Catalog /Pages {pages_id} 0 R >>")

    pdf = "%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf.encode('latin-1', errors='replace')))
        pdf += f"{index} 0 obj\n{obj}\nendobj\n"
    xref_offset = len(pdf.encode('latin-1', errors='replace'))
    pdf += f"xref\n0 {len(objects) + 1}\n"
    pdf += "0000000000 65535 f \n"
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n"
    pdf += f"trailer\n<< /Size {len(objects) + 1} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    return pdf.encode('latin-1', errors='replace')


def _build_report_pdf(data):
    canvas = _ReportPdfCanvas(data)
    canvas.text(42, 744, 'Resumen ejecutivo', size=22, font='F2', color=(0.24, 0.32, 0.10))
    periodo = (
        f"Del {data['filtro_desde'].strftime('%d/%m/%Y %H:%M')} "
        f"al {data['filtro_hasta'].strftime('%d/%m/%Y %H:%M')}"
    )
    canvas.wrapped_text(42, 724, periodo, 520, size=9)
    canvas.y = 686
    canvas.kpi_grid([
        {'label': 'Ventas', 'value': f"${data['ventas_monto']}", 'hint': f"{data['ventas_tickets']} tickets", 'color': (0.24, 0.32, 0.10)},
        {'label': 'Compras', 'value': f"${data['compras_monto']}", 'hint': f"{data['compras_lotes']} lotes", 'color': (0.85, 0.47, 0.02)},
        {'label': 'Flujo neto', 'value': f"${data['flujo_neto']}", 'hint': 'Ventas menos compras', 'color': (0.24, 0.32, 0.10) if not data['flujo_neto_negativo'] else (0.86, 0.15, 0.15)},
        {'label': 'Margen', 'value': f"{data['margen_operativo']}%", 'hint': 'Ganancia sobre ventas', 'color': (0.10, 0.53, 0.33)},
    ])

    canvas.section('Evolucion de Ventas')
    canvas.bar_chart('Ingresos por periodo', data['chart_labels'], data['chart_totals'])

    canvas.section('Indicadores de inventario', 'Lectura rapida para decidir compras, prioridad de inventario y seguimiento comercial.')
    canvas.kpi_grid([
        {'label': 'Unidades compradas', 'value': str(data['compras_unidades']), 'hint': 'Entradas del periodo', 'color': (0.85, 0.47, 0.02)},
        {'label': 'Lotes pendientes', 'value': str(data['compras_pendientes']), 'hint': 'Por inventariar', 'color': (0.86, 0.15, 0.15)},
        {'label': 'Titulos en stock', 'value': str(data['libros_en_stock']), 'hint': 'Con existencias', 'color': (0.10, 0.53, 0.33)},
        {'label': 'Apartados activos', 'value': str(data['apartados_activos']), 'hint': 'Pendientes', 'color': (0.05, 0.43, 0.99)},
    ])

    canvas.section('Top libros vendidos')
    canvas.table(
        ['Titulo', 'Autor', 'Uds', 'Ingresos'],
        [
            [item['ejemplar__libro__titulo'], item['ejemplar__libro__autor'], item['unidades_vendidas'], f"${item['ingresos']}"]
            for item in data['top_libros']
        ],
        [230, 150, 55, 95],
    )

    canvas.section('Top proveedores por gasto')
    canvas.table(
        ['Proveedor', 'Lotes', 'Uds', 'Gasto'],
        [
            [item['proveedor__nombre'], item['lotes'], item['unidades'], f"${item['gasto']}"]
            for item in data['top_proveedores']
        ],
        [260, 70, 70, 130],
    )

    canvas.section('Compras recientes')
    canvas.table(
        ['Lote', 'Proveedor', 'Estado', 'Uds', 'Total'],
        [
            [compra.codigo_lote or compra.id, compra.proveedor.nombre, compra.get_estado_display(), compra.unidades, f"${compra.total}"]
            for compra in data['compras_recientes']
        ],
        [95, 170, 110, 55, 100],
    )

    canvas.section('Ritmo mensual consolidado')
    canvas.table(
        ['Mes', 'Ventas', 'Compras', 'Flujo'],
        [
            [item['periodo'].strftime('%m/%Y'), f"${item['ventas']}", f"${item['compras']}", f"${item['flujo']}"]
            for item in data['resumen_mensual']
        ],
        [120, 135, 135, 140],
    )

    return _build_pdf_document(canvas.finish())


@login_required
@admin_required
@require_http_methods(["GET"])
def exportar_reporte_pdf(request):
    data = _build_report_data(request)
    response = HttpResponse(_build_report_pdf(data), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="reporte_bartleby.pdf"'
    return response


@login_required
@admin_required
@require_http_methods(["GET"])
def centro_alertas(request):
    ahora = timezone.localtime()
    inicio_hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_hoy = inicio_hoy + timedelta(days=1)
    fecha_corte_proveedores = ahora.date() - timedelta(days=ALERTA_PROVEEDOR_INACTIVO_DIAS)
    fecha_corte_clientes = ahora - timedelta(days=ALERTA_CLIENTE_INACTIVO_DIAS)

    reservas_por_vencer = list(
        Reserva.objects.filter(
            estado='pendiente',
            fecha_vencimiento__gte=inicio_hoy,
            fecha_vencimiento__lt=fin_hoy,
        )
        .select_related('usuario')
        .prefetch_related('libros')
        .order_by('fecha_vencimiento')
    )

    stock_critico = list(
        Libro.objects.annotate(
            stock_total=Coalesce(Sum('ejemplares__stock'), 0),
            ejemplares_registrados=Count('ejemplares', distinct=True),
            reservas_activas=Count(
                'ejemplares__reservas_activas',
                filter=Q(ejemplares__reservas_activas__estado='pendiente'),
                distinct=True,
            ),
        )
        .filter(ejemplares_registrados__gt=0, stock_total__lt=ALERTA_STOCK_CRITICO)
        .order_by('stock_total', 'titulo')[:12]
    )

    ventas_sin_cliente = list(
        Venta.objects.filter(cliente__isnull=True)
        .select_related('cajero')
        .prefetch_related('detalles__ejemplar__libro')
        .order_by('-fecha_venta')[:12]
    )

    proveedores_inactivos = list(
        Proveedor.objects.filter(activo=True)
        .annotate(
            ultima_compra=Max('adquisiciones__fecha'),
            compras_registradas=Count('adquisiciones', distinct=True),
        )
        .filter(
            Q(ultima_compra__isnull=True) | Q(ultima_compra__lt=fecha_corte_proveedores)
        )
        .order_by('ultima_compra', 'nombre')[:12]
    )

    clientes_candidatos = (
        User.objects.filter(is_staff=False)
        .select_related('perfil')
        .annotate(
            compras_total=Count('compras_realizadas', distinct=True),
            reservas_total=Count('reserva', distinct=True),
            ultima_compra=Max('compras_realizadas__fecha_venta'),
            ultima_reserva=Max('reserva__fecha_reserva'),
        )
        .order_by('username')
    )

    clientes_frecuentes_inactivos = []
    for cliente in clientes_candidatos:
        movimientos_total = cliente.compras_total + cliente.reservas_total
        if movimientos_total < ALERTA_CLIENTE_FRECUENTE_MOVIMIENTOS:
            continue

        fechas = [fecha for fecha in [cliente.ultima_compra, cliente.ultima_reserva] if fecha]
        ultima_actividad = max(fechas) if fechas else None
        if ultima_actividad and ultima_actividad >= fecha_corte_clientes:
            continue

        cliente.movimientos_total = movimientos_total
        cliente.ultima_actividad = ultima_actividad
        clientes_frecuentes_inactivos.append(cliente)

    clientes_frecuentes_inactivos = sorted(
        clientes_frecuentes_inactivos,
        key=lambda cliente: cliente.ultima_actividad or timezone.make_aware(datetime(1970, 1, 1)),
    )[:12]

    context = {
        'reservas_por_vencer': reservas_por_vencer,
        'stock_critico': stock_critico,
        'ventas_sin_cliente': ventas_sin_cliente,
        'proveedores_inactivos': proveedores_inactivos,
        'clientes_frecuentes_inactivos': clientes_frecuentes_inactivos,
        'seguimientos_alerta_total': len(proveedores_inactivos) + len(clientes_frecuentes_inactivos),
        'total_alertas': (
            len(reservas_por_vencer)
            + len(stock_critico)
            + len(ventas_sin_cliente)
            + len(proveedores_inactivos)
            + len(clientes_frecuentes_inactivos)
        ),
        'fecha_corte_proveedores': fecha_corte_proveedores,
        'fecha_corte_clientes': fecha_corte_clientes,
        'umbral_stock_critico': ALERTA_STOCK_CRITICO,
        'umbral_cliente_frecuente': ALERTA_CLIENTE_FRECUENTE_MOVIMIENTOS,
    }
    return render(request, 'reportes/centro_alertas.html', context)
