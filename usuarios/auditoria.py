from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import EventoAuditoria


AUDITORIA_RETENCION_DIAS = getattr(settings, 'AUDITORIA_RETENCION_DIAS', 180)


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
