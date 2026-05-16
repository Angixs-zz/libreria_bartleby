"""
Vistas de reservas de la Librería Bartleby.

Funcionalidades:
- Cliente: ver sus reservas
- Admin: gestionar reservas, marcar como entregadas, cancelar

Protecciones:
- @login_required: autenticación obligatoria
- @admin_required: solo staff
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from reservas.models import Reserva
from inventario.models import Ejemplar
from services.inventario_service import InventarioService
from decorators import admin_required, cajero_required
from usuarios.auditoria import registrar_auditoria


# ── Vistas del Cliente ─────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET"])
def mis_reservas(request):
    """
    Muestra todas las reservas del usuario autenticado.

    Estados:
    - pendiente: en proceso
    - completada: entregada al cliente
    - cancelada: cancelada o vencida
    """
    reservas = Reserva.objects.filter(
        usuario=request.user
    ).prefetch_related('ejemplares').order_by('-fecha_vencimiento')

    return render(request, 'reservas/mis_reservas.html', {'reservas': reservas})


@login_required
@require_http_methods(["GET"])
def detalle_ticket(request, reserva_id):
    """
    Detalle de una reserva específica (ticket).

    Solo el propietario o admin puede verlo.
    """
    reserva = get_object_or_404(
        Reserva.objects.prefetch_related('ejemplares'),
        id=reserva_id
    )

    # Verificar permisos
    if reserva.usuario != request.user and not request.user.is_staff:
        messages.error(request, '❌ No tienes permiso para ver esta reserva.')
        return redirect('mis_reservas')

    return render(request, 'reservas/ticket.html', {'reserva': reserva})


@login_required
@require_http_methods(["POST"])
def cancelar_reserva(request, reserva_id):
    """
    Cliente cancela su propia reserva.

    Solo puede cancelar reservas en estado 'pendiente'.
    """
    reserva = get_object_or_404(Reserva, id=reserva_id, usuario=request.user)

    if reserva.estado != 'pendiente':
        messages.error(
            request,
            f'❌ No puedes cancelar una reserva {reserva.estado}.'
        )
        return redirect('mis_reservas')

    try:
        InventarioService.liberar_reserva(reserva.id)
        registrar_auditoria(
            actor=request.user,
            accion='cancelar',
            modulo='reservas',
            entidad_tipo='reserva',
            entidad_id=reserva.id,
            entidad_nombre=reserva.codigo_ticket,
            descripcion=f'El cliente "{request.user.username}" canceló su reserva {reserva.codigo_ticket}.',
        )
        messages.success(
            request,
            f'✅ Reserva #{reserva.id} cancelada. '
            f'Los ejemplares vuelven al catálogo.'
        )
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')

    return redirect('mis_reservas')


# ── Vistas del Panel Admin ─────────────────────────────────────────────────

@login_required
@cajero_required
@require_http_methods(["GET"])
def gestor_reservas(request):
    """
    Panel de control de todas las reservas (solo staff).

    Muestra:
    - Reservas pendientes (ordenadas por fecha de vencimiento)
    - Reservas completadas (últimas 10)
    - Reservas canceladas (últimas 10)

    Nota: Las reservas vencidas se cancelan automáticamente
    con el comando: python manage.py cancel_expired_reservations
    """
    pendientes = Reserva.objects.filter(
        estado='pendiente'
    ).prefetch_related('ejemplares').select_related('usuario').order_by(
        'fecha_vencimiento'
    )

    completadas = Reserva.objects.filter(
        estado='completada'
    ).prefetch_related('ejemplares').select_related('usuario').order_by(
        '-fecha_reserva'
    )[:10]

    canceladas = Reserva.objects.filter(
        estado__in=['cancelada', 'expirada']
    ).prefetch_related('ejemplares').select_related('usuario').order_by(
        '-fecha_reserva'
    )[:10]

    context = {
        'pendientes': pendientes,
        'completadas': completadas,
        'canceladas': canceladas,
        'total_pendientes': pendientes.count(),
        'total_completadas': Reserva.objects.filter(estado='completada').count(),
        'total_canceladas': Reserva.objects.filter(
            estado__in=['cancelada', 'expirada']
        ).count(),
    }
    return render(request, 'reservas/gestor_reservas.html', context)


@login_required
@cajero_required
@require_http_methods(["POST"])
def marcar_entregada(request, reserva_id):
    """
    Admin marca una reserva como entregada.

    Cambios:
    - Estado: pendiente → completada
    - Stock: se descuenta por cada ejemplar de la reserva
    """
    reserva = get_object_or_404(Reserva, id=reserva_id)

    if reserva.estado != 'pendiente':
        messages.warning(
            request,
            f'❌ Reserva ya está en estado "{reserva.estado}".'
        )
        return redirect('gestor_reservas')

    try:
        # Confirmar reserva y generar la venta
        InventarioService.confirmar_reserva_a_venta(
            reserva_id=reserva.id,
            metodo_pago='efectivo',  # Por defecto al entregar físicamente
            usuario_cajero=request.user
        )

        # Actualizar el objeto reserva local para auditoría si es necesario
        reserva.refresh_from_db()

        registrar_auditoria(
            actor=request.user,
            accion='completar',
            modulo='reservas',
            entidad_tipo='reserva',
            entidad_id=reserva.id,
            entidad_nombre=reserva.codigo_ticket,
            descripcion=f'Se marcó como entregada la reserva {reserva.codigo_ticket} y se generó la venta correspondiente.',
            metadata={'cliente': reserva.usuario.username},
        )

        messages.success(
            request,
            f'✅ Reserva #{reserva.id} entregada. Venta registrada y stock descontado.'
        )
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')

    return redirect('gestor_reservas')


@login_required
@cajero_required
@require_http_methods(["POST"])
def liberar_reserva(request, reserva_id):
    """
    Admin cancela una reserva pendiente.

    El ejemplar vuelve al catálogo disponible.
    """
    reserva = get_object_or_404(Reserva, id=reserva_id)

    if reserva.estado != 'pendiente':
        messages.warning(
            request,
            f'❌ No puedes liberar una reserva {reserva.estado}.'
        )
        return redirect('gestor_reservas')

    try:
        InventarioService.liberar_reserva(reserva.id)
        registrar_auditoria(
            actor=request.user,
            accion='cancelar',
            modulo='reservas',
            entidad_tipo='reserva',
            entidad_id=reserva.id,
            entidad_nombre=reserva.codigo_ticket,
            descripcion=f'Se liberó administrativamente la reserva {reserva.codigo_ticket}.',
            metadata={'cliente': reserva.usuario.username},
        )
        messages.success(
            request,
            f'✅ Reserva #{reserva.id} liberada. '
            f'Los ejemplares vuelven al catálogo.'
        )
    except Exception as e:
        messages.error(request, f'❌ Error: {str(e)}')

    return redirect('gestor_reservas')
