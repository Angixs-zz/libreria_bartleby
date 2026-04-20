from django.urls import path

from . import views


urlpatterns = [
    path('', views.dashboard_reportes, name='dashboard_reportes'),
    path('alertas/', views.centro_alertas, name='centro_alertas'),
]
