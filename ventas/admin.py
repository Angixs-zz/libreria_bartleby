from django.contrib import admin
from .models import Venta, DetalleVenta

class DetalleVentaInline(admin.TabularInline):
    model = DetalleVenta
    extra = 1 # Muestra una fila vacía por defecto
    readonly_fields = ['subtotal']

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ['id', 'cajero', 'fecha_venta', 'total', 'metodo_pago']
    list_filter = ['metodo_pago', 'fecha_venta']
    readonly_fields = ['fecha_venta', 'total']
    inlines = [DetalleVentaInline]