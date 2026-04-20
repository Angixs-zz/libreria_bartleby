from django.contrib import admin
from .models import Reserva

@admin.register(Reserva)
class ReservaAdmin(admin.ModelAdmin):
    # Cambiamos 'cliente' por 'usuario' que es el nombre real en tu modelo actual
    list_display = ['id', 'usuario', 'estado', 'fecha_reserva', 'fecha_vencimiento', 'total']
    
    # Filtros laterales para que no te vuelvas loco buscando
    list_filter = ['estado', 'fecha_reserva', 'fecha_vencimiento']
    
    # Esto evita que alguien (o tú mismo por error) edite la fecha de creación
    readonly_fields = ['fecha_reserva']
    
    # Para que puedas ver qué libros hay en el ticket dentro del detalle
    filter_horizontal = ['libros']