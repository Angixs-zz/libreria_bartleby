from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import EventoAuditoria


AUDITORIA_RETENCION_DIAS = getattr(settings, 'AUDITORIA_RETENCION_DIAS', 180)

LIMITES_AUDITORIA = [25, 50, 100, 250, 500]

ACCIONES_AUDITORIA = {
    'todas': 'Todas las acciones',
    'crear': 'Creación de registro',
    'editar': 'Edición / Modificación',
    'eliminar': 'Eliminación',
    'cancelar': 'Cancelación',
    'desactivar': 'Baja de acceso',
    'reactivar': 'Reactivación',
    'login': 'Inicio de sesión',
}

MODULOS_AUDITORIA = {
    'todos': 'Todos los módulos',
    'inventario': 'Catálogo e Inventario',
    'proveedores': 'Directorio Proveedores',
    'ventas': 'Punto de Venta (POS)',
    'reservas': 'Gestor de Reservas',
    'clientes': 'Panel de Clientes',
    'personal': 'Personal y Staff',
    'sistema': 'Autenticación y Sistema',
}

def obtener_limite_auditoria(limite_str):
    try:
        limite = int(limite_str)
        if limite in LIMITES_AUDITORIA:
            return limite
    except (TypeError, ValueError):
        pass
    return 50

def depurar_auditoria_antigua():
    if not AUDITORIA_RETENCION_DIAS:
        return 0

    limite = timezone.now() - timedelta(days=AUDITORIA_RETENCION_DIAS)
    eliminados, _ = EventoAuditoria.objects.filter(creado_en__lt=limite).delete()
    return eliminados


def registrar_auditoria(
    *,
    actor=None,
    accion,
    modulo,
    entidad_tipo,
    entidad_id=None,
    entidad_nombre='',
    descripcion='',
    metadata=None,
):
    evento = EventoAuditoria.objects.create(
        actor=actor,
        accion=accion,
        modulo=modulo,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        entidad_nombre=entidad_nombre,
        descripcion=descripcion,
        metadata=metadata or {},
    )
    depurar_auditoria_antigua()
    return evento
