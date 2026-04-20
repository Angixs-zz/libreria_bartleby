from django.urls import path
from . import views

urlpatterns = [
    # Cliente
    path('mis-reservas/', views.mis_reservas, name='mis_reservas'),
    path('ticket/<int:reserva_id>/', views.detalle_ticket, name='detalle_ticket'),
    path('cancelar/<int:reserva_id>/', views.cancelar_reserva, name='cancelar_reserva'),
    
    # Admin/Gestor
    path('gestor/', views.gestor_reservas, name='gestor_reservas'),
    path('gestor/entregar/<int:reserva_id>/', views.marcar_entregada, name='marcar_entregada'),
    path('gestor/liberar/<int:reserva_id>/', views.liberar_reserva, name='liberar_reserva'),
]
