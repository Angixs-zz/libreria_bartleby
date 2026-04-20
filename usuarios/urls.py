from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Login y Logout (usando las vistas por defecto de Django)
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    
    # Login con código
    path('login-codigo/', views.login_con_codigo, name='login_con_codigo'),
    path('verificar-codigo-login/', views.verificar_codigo_login, name='verificar_codigo_login'),
    
    # Registro (vista personalizada que haremos ahora)
    path('registrar/', views.registrar, name='registrar'),
    path('verificar/', views.verificar_codigo, name='verificar_codigo'), # <-- Nueva
    path('mi-perfil/', views.mi_perfil_actividad, name='mi_perfil'),
    path('personal/', views.panel_personal, name='panel_personal'),
    path('auditoria/', views.panel_auditoria, name='panel_auditoria'),
    path('personal/nuevo/', views.crear_staff, name='crear_staff'),
    path('personal/<int:user_id>/editar/', views.editar_personal, name='editar_personal'),
    path('personal/<int:user_id>/desactivar/', views.desactivar_personal, name='desactivar_personal'),
    path('personal/<int:user_id>/reactivar/', views.reactivar_personal, name='reactivar_personal'),
    path('personal/<int:user_id>/resetear-password/', views.resetear_password_personal, name='resetear_password_personal'),
    path('clientes/', views.panel_clientes, name='panel_clientes'),
    path('clientes/<int:user_id>/', views.detalle_cliente, name='detalle_cliente'),
]
