# config/urls.py
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from usuarios import views as usuarios_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'aviso-privacidad/',
        usuarios_views.documento_legal,
        {'slug': 'aviso-privacidad'},
        name='aviso_privacidad'
    ),
    path(
        'terminos-condiciones/',
        usuarios_views.documento_legal,
        {'slug': 'terminos-condiciones'},
        name='terminos_condiciones'
    ),
    path('catalogo/', include('catalogo.urls')),
    path('usuarios/', include('usuarios.urls')),
    path('reservas/', include('reservas.urls')),
    path('inventario/', include('inventario.urls')),
    path('proveedores/', include('proveedores.urls')),
    path('reportes/', include('reportes.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
