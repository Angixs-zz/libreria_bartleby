from django.contrib import admin
from .models import Categoria, Libro, Ejemplar

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

# Esto permite ver los ejemplares directamente dentro de la página del Libro
class EjemplarInline(admin.TabularInline):
    model = Ejemplar
    extra = 1

@admin.register(Libro)
class LibroAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'autor', 'categoria', 'isbn')
    search_fields = ('titulo', 'autor', 'isbn')
    list_filter = ('categoria',)
    inlines = [EjemplarInline] # Agregamos los ejemplares aquí

@admin.register(Ejemplar)
class EjemplarAdmin(admin.ModelAdmin):
    list_display = ('sku', 'libro', 'estado_fisico', 'precio_venta', 'stock')
    search_fields = ('sku', 'libro__titulo')
    list_filter = ('estado_fisico',)
    list_editable = ('precio_venta', 'stock')
    readonly_fields = ('sku',)