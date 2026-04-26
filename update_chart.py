import os

views_path = r'c:\Users\migue\libreria_bartleby\reportes\views.py'
with open(views_path, 'r', encoding='utf-8') as f:
    views_content = f.read()

# 1. Update imports
views_content = views_content.replace(
    'from django.db.models.functions import Coalesce, TruncDay, TruncMonth',
    'from django.db.models.functions import Coalesce, TruncDay, TruncMonth, TruncHour'
)

# 2. Update chart logic
old_chart_logic = """    ventas_diarias_qs = (
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
        chart_tickets.append(dato['tickets'] if dato else 0)"""

new_chart_logic = """    delta_days = (fin_periodo - inicio_periodo).days

    if delta_days <= 1:
        # Agrupar por hora
        ventas_chart_qs = (
            Venta.objects.filter(fecha_venta__gte=inicio_periodo, fecha_venta__lte=fin_periodo)
            .annotate(periodo_agrupado=TruncHour('fecha_venta'))
            .values('periodo_agrupado')
            .annotate(
                total=Coalesce(Sum('total'), Decimal('0.00')),
                tickets=Count('id'),
            )
            .order_by('periodo_agrupado')
        )
        
        ventas_chart_map = {
            item['periodo_agrupado'].replace(minute=0, second=0, microsecond=0): item for item in ventas_chart_qs if item['periodo_agrupado']
        }

        chart_labels = []
        chart_totals = []
        chart_tickets = []
        
        # Generar las 24 horas del dia
        for i in range(24):
            hora_actual = inicio_periodo.replace(hour=i, minute=0, second=0, microsecond=0)
            if hora_actual > ahora:
                break
            dato = ventas_chart_map.get(hora_actual)
            chart_labels.append(hora_actual.strftime('%H:00'))
            chart_totals.append(float(dato['total']) if dato else 0)
            chart_tickets.append(dato['tickets'] if dato else 0)

    else:
        # Agrupar por dia
        ventas_chart_qs = (
            Venta.objects.filter(fecha_venta__gte=inicio_periodo, fecha_venta__lte=fin_periodo)
            .annotate(periodo_agrupado=TruncDay('fecha_venta'))
            .values('periodo_agrupado')
            .annotate(
                total=Coalesce(Sum('total'), Decimal('0.00')),
                tickets=Count('id'),
            )
            .order_by('periodo_agrupado')
        )
        
        ventas_chart_map = {
            item['periodo_agrupado'].date(): item for item in ventas_chart_qs if item['periodo_agrupado']
        }

        chart_labels = []
        chart_totals = []
        chart_tickets = []
        
        dias_a_mostrar = min(delta_days + 1, 60) # Limitar a 60 dias maximo para que no explote la grafica
        for offset in range(dias_a_mostrar):
            fecha_actual = (inicio_periodo + timedelta(days=offset)).date()
            if fecha_actual > ahora.date() and periodo != 'custom':
                continue
            dato = ventas_chart_map.get(fecha_actual)
            chart_labels.append(fecha_actual.strftime('%d %b'))
            chart_totals.append(float(dato['total']) if dato else 0)
            chart_tickets.append(dato['tickets'] if dato else 0)"""

views_content = views_content.replace(old_chart_logic, new_chart_logic)

with open(views_path, 'w', encoding='utf-8') as f:
    f.write(views_content)

print("Views updated.")
