from datetime import timedelta, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum, F, DecimalField, ExpressionWrapper, Q, Max
from django.db.models.functions import Coalesce, TruncDay, TruncMonth
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from decorators import admin_required
from inventario.models import Libro
from proveedores.models import Proveedor
from reservas.models import Reserva
from django.contrib.auth.models import User
from ventas.models import Venta, DetalleVenta


PERIODOS = {
    'today': 'Hoy',
    'week': 'Esta semana',
    'month': 'Este mes',
}

ALERTA_STOCK_CRITICO = 3
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


@login_required
@admin_required
@require_http_methods(["GET"])
def dashboard_reportes(request):
    periodo = request.GET.get('periodo', 'month')
    if periodo not in PERIODOS:
        periodo = 'month'

    ahora = timezone.localtime()
    inicio_periodo = _inicio_periodo(periodo, ahora)
    inicio_7_dias = ahora.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=6)
    inicio_180_dias = ahora - timedelta(days=180)

    ventas_periodo = Venta.objects.filter(
        fecha_venta__gte=inicio_periodo,
        fecha_venta__lte=ahora,
    )
    detalle_periodo = DetalleVenta.objects.filter(
        venta__fecha_venta__gte=inicio_periodo,
        venta__fecha_venta__lte=ahora,
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

    stock_bajo = list(
        Libro.objects.annotate(
            stock_total=Coalesce(Sum('ejemplares__stock'), 0),
            ejemplares_registrados=Count('ejemplares', distinct=True),
        ).filter(
            ejemplares_registrados__gt=0,
            stock_total__lt=3,
        ).order_by('stock_total', 'titulo')[:8]
    )

    ventas_diarias_qs = (
        Venta.objects.filter(fecha_venta__gte=inicio_7_dias, fecha_venta__lte=ahora)
        .annotate(periodo=TruncDay('fecha_venta'))
        .values('periodo')
        .annotate(
            total=Coalesce(Sum('total'), Decimal('0.00')),
            tickets=Count('id'),
        )
        .order_by('periodo')
    )
    ventas_diarias_map = {
        item['periodo'].date(): item for item in ventas_diarias_qs
    }

    chart_labels = []
    chart_totals = []
    chart_tickets = []
    for offset in range(7):
        fecha = (inicio_7_dias + timedelta(days=offset)).date()
        dato = ventas_diarias_map.get(fecha)
        chart_labels.append(fecha.strftime('%d %b'))
        chart_totals.append(float(dato['total']) if dato else 0)
        chart_tickets.append(dato['tickets'] if dato else 0)

    ventas_mensuales = list(
        Venta.objects.filter(fecha_venta__gte=inicio_180_dias, fecha_venta__lte=ahora)
        .annotate(periodo=TruncMonth('fecha_venta'))
        .values('periodo')
        .annotate(
            total=Coalesce(Sum('total'), Decimal('0.00')),
            tickets=Count('id'),
        )
        .order_by('-periodo')[:6]
    )

    libros_en_stock = (
        Libro.objects.annotate(stock_total=Coalesce(Sum('ejemplares__stock'), 0))
        .filter(stock_total__gt=0)
        .count()
    )
    apartados_activos = Reserva.objects.filter(estado='pendiente').count()

    context = {
        'periodo': periodo,
        'periodos': PERIODOS,
        'periodo_label': PERIODOS[periodo],
        'ventas_monto': ventas_totales['total'],
        'ventas_tickets': ventas_totales['tickets'],
        'ganancia_neta': ganancia_neta,
        'libros_en_stock': libros_en_stock,
        'apartados_activos': apartados_activos,
        'top_libros': top_libros,
        'stock_bajo': stock_bajo,
        'chart_labels': chart_labels,
        'chart_totals': chart_totals,
        'chart_tickets': chart_tickets,
        'ventas_mensuales': ventas_mensuales,
        'filtro_desde': inicio_periodo,
        'filtro_hasta': ahora,
    }
    return render(request, 'reportes/dashboard_reportes.html', context)


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
