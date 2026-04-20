from django.contrib import admin

from .models import Proveedor, Adquisicion, DetalleAdquisicion


class DetalleAdquisicionInline(admin.TabularInline):
    model = DetalleAdquisicion
    extra = 0


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'contacto', 'telefono', 'email', 'activo', 'fecha_registro']
    list_filter = ['activo']
    search_fields = ['nombre', 'contacto', 'email', 'telefono']


@admin.register(Adquisicion)
class AdquisicionAdmin(admin.ModelAdmin):
    list_display = ['id', 'proveedor', 'fecha', 'total', 'creado_por']
    list_filter = ['fecha', 'proveedor']
    search_fields = ['proveedor__nombre', 'observaciones']
    inlines = [DetalleAdquisicionInline]


@admin.register(DetalleAdquisicion)
class DetalleAdquisicionAdmin(admin.ModelAdmin):
    list_display = ['adquisicion', 'ejemplar', 'cantidad', 'costo_unitario', 'subtotal']
    list_select_related = ['adquisicion', 'ejemplar', 'ejemplar__libro']
    search_fields = ['adquisicion__proveedor__nombre', 'ejemplar__libro__titulo', 'ejemplar__sku']
