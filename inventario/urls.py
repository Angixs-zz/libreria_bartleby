from django.urls import path
from . import views

urlpatterns = [
    path('agregar/', views.agregar_libro, name='agregar_libro'),
    path('agregar/compra/', views.agregar_libro, name='agregar_libro_compra'),
    path('buscar-libro/', views.buscar_libro_ajax, name='buscar_libro_ajax'),
    path('buscar-isbn/', views.buscar_isbn_enriquecido, name='buscar_isbn_enriquecido'),
    path('gestion/', views.gestion_inventario, name='gestion_inventario'),
    path('ejemplar/<int:ejemplar_id>/', views.detalle_ejemplar, name='detalle_ejemplar'),
    path('eliminar/<int:ejemplar_id>/', views.eliminar_ejemplar, name='eliminar_ejemplar'),
    path('exportar/', views.exportar_inventario, name='exportar_inventario'),
    path('importar/', views.importar_inventario, name='importar_inventario'),
    path('pos/', views.punto_de_venta, name='pos'),
    path('api/pos/buscar/', views.api_buscar_codigo, name='api_buscar_codigo'),
    path('api/pos/cobrar/', views.api_procesar_venta, name='api_procesar_venta'),
]
