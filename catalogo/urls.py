from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_libros, name='lista_libros'),
    path('conocenos/', views.conocenos, name='conocenos'),
    path('libro/<int:pk>/', views.detalle_libro, name='detalle_libro'),
    path('carrito/', views.ver_carrito, name='ver_carrito'),
    path('agregar/<int:ejemplar_id>/', views.agregar_al_carrito, name='agregar_al_carrito'),
    path('quitar/<int:ejemplar_id>/', views.quitar_del_carrito, name='quitar_del_carrito'),
    path('confirmar-reserva/', views.confirmar_reserva, name='confirmar_reserva'),
    path('buscar-isbn/', views.buscar_isbn, name='buscar_isbn'),
]
