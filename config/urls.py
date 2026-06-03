# config/urls.py
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
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
    path('', include('catalogo.urls')),
    path('catalogo/', include('catalogo.urls')),
    path('usuarios/', include('usuarios.urls')),
    path('reservas/', include('reservas.urls')),
    path('inventario/', include('inventario.urls')),
    path('proveedores/', include('proveedores.urls')),
    path('reportes/', include('reportes.urls')),
]

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve, {
        'document_root': settings.MEDIA_ROOT,
    }),
]
