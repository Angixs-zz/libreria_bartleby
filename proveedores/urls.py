from django.urls import path

from . import views


urlpatterns = [
    path('', views.directorio_proveedores, name='directorio_proveedores'),
    path('nuevo/', views.crear_proveedor, name='crear_proveedor'),
    path('<int:proveedor_id>/editar/', views.editar_proveedor, name='editar_proveedor'),
    path('<int:proveedor_id>/', views.detalle_proveedor, name='detalle_proveedor'),

    # Adquisiciones
    path('adquisiciones/', views.historial_adquisiciones, name='historial_adquisiciones'),
    path('adquisiciones/nueva/', views.registrar_adquisicion, name='registrar_adquisicion'),
    path('adquisiciones/<int:adquisicion_id>/inventariar/', views.inventariar_lote, name='inventariar_lote'),

    # AJAX helpers
    path('api/isbn/', views.buscar_libro_isbn, name='buscar_libro_isbn'),
    path('api/ejemplar-rapido/', views.crear_ejemplar_rapido, name='crear_ejemplar_rapido'),
]
