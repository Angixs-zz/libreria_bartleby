from django.urls import path

from . import views


urlpatterns = [
    path('', views.dashboard_reportes, name='dashboard_reportes'),
    path('exportar/pdf/', views.exportar_reporte_pdf, name='exportar_reporte_pdf'),
    path('alertas/', views.centro_alertas, name='centro_alertas'),
]
