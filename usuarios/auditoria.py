from .models import EventoAuditoria


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
    return EventoAuditoria.objects.create(
        actor=actor,
        accion=accion,
        modulo=modulo,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        entidad_nombre=entidad_nombre,
        descripcion=descripcion,
        metadata=metadata or {},
    )
