from django.urls import path
from . import views

urlpatterns = [
    path('agregar/', views.agregar_libro, name='agregar_libro'),
    path('buscar-libro/', views.buscar_libro_ajax, name='buscar_libro_ajax'),
    path('gestion/', views.gestion_inventario, name='gestion_inventario'),
    path('ejemplar/<int:ejemplar_id>/', views.detalle_ejemplar, name='detalle_ejemplar'),
    path('eliminar/<int:ejemplar_id>/', views.eliminar_ejemplar, name='eliminar_ejemplar'),
    path('pos/', views.punto_de_venta, name='pos'),
    path('api/pos/buscar/', views.api_buscar_codigo, name='api_buscar_codigo'),
    path('api/pos/cobrar/', views.api_procesar_venta, name='api_procesar_venta'),
]