from django.contrib import admin
from .models import PerfilUsuario, EventoAuditoria, NotaClienteInterna

@admin.register(PerfilUsuario)
class PerfilUsuarioAdmin(admin.ModelAdmin):
    list_display = ['usuario', 'rol', 'telefono']
    list_filter = ['rol']
    search_fields = ['usuario__username', 'usuario__email']


@admin.register(EventoAuditoria)
class EventoAuditoriaAdmin(admin.ModelAdmin):
    list_display = ['creado_en', 'actor', 'modulo', 'accion', 'entidad_tipo', 'entidad_nombre']
    list_filter = ['modulo', 'accion', 'entidad_tipo', 'creado_en']
    search_fields = ['actor__username', 'entidad_nombre', 'descripcion']
    readonly_fields = ['creado_en']


@admin.register(NotaClienteInterna)
class NotaClienteInternaAdmin(admin.ModelAdmin):
    list_display = ['creado_en', 'cliente', 'autor']
    list_filter = ['creado_en']
    search_fields = ['cliente__username', 'autor__username', 'contenido']
