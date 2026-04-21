"""
Servicio centralizado para gestionar inventario y operaciones de stock.

Este módulo proporciona métodos atómicos para:
- Reservar ejemplares
- Confirmar ventas
- Liberar stock
- Consultar disponibilidad

Utiliza transacciones y select_for_update para evitar race conditions.
"""

from decimal import Decimal
from django.db import transaction
from django.db.models import F, Count
from django.utils import timezone
from datetime import timedelta


class InventarioService:
    """
    Servicio para operaciones de inventario con transacciones atómicas.
    Evita race conditions y centraliza lógica de negocio.
    """
    
    # Máximos permitidos
    MAX_EJEMPLARES_POR_RESERVA = 10
    HORAS_VENCIMIENTO_RESERVA = 72
    
    @staticmethod
    @transaction.atomic
    def reservar_ejemplar(usuario, ejemplar_id):
        """
        Reserva un ejemplar específico para un usuario.
        
        Operación atómica:
        - Verifica stock disponible
        - Crea la reserva
        - Asocia el ejemplar
        
        Args:
            usuario: User instance
            ejemplar_id: ID del Ejemplar a reservar
            
        Returns:
            Reserva: Objeto Reserva creado
            
        Raises:
            ValueError: Si no hay stock o límites excedidos
        """
        from inventario.models import Ejemplar
        from reservas.models import Reserva
        
        # Lock pessimista: bloquear fila para evitar race conditions
        ejemplar = Ejemplar.objects.select_for_update().get(id=ejemplar_id)
        
        # Calcular stock disponible (stock actual - ejemplares reservados)
        reservados = Reserva.objects.filter(
            ejemplares=ejemplar,
            estado='pendiente'
        ).count()
        
        stock_libre = ejemplar.stock - reservados
        
        if stock_libre <= 0:
            raise ValueError(
                f"'{ejemplar.libro.titulo}' está agotado. "
                f"Stock disponible: 0"
            )
        
        # Crear reserva con vencimiento
        fecha_vencimiento = timezone.now() + timedelta(
            hours=InventarioService.HORAS_VENCIMIENTO_RESERVA
        )
        
        reserva = Reserva.objects.create(
            usuario=usuario,
            estado='pendiente',
            fecha_vencimiento=fecha_vencimiento,
            total=ejemplar.precio_venta
        )
        
        # Asociar ejemplar
        reserva.ejemplares.add(ejemplar)
        
        return reserva
    
    @staticmethod
    @transaction.atomic
    def reservar_multiples(usuario, ejemplar_ids):
        """
        Reserva múltiples ejemplares (con posibles repeticiones de ID).

        Soporta cantidades: si ejemplar_ids = [5, 5, 5] se interpreta
        como 3 unidades del ejemplar 5.

        Args:
            usuario: User instance
            ejemplar_ids: Lista de IDs de Ejemplar (puede contener duplicados)

        Returns:
            Reserva: Objeto Reserva con todos los ejemplares

        Raises:
            ValueError: Si excede límites o no hay stock suficiente
        """
        from inventario.models import Ejemplar
        from reservas.models import Reserva

        # Validar límite global
        if len(ejemplar_ids) > InventarioService.MAX_EJEMPLARES_POR_RESERVA:
            raise ValueError(
                f"Máximo {InventarioService.MAX_EJEMPLARES_POR_RESERVA} "
                f"unidades por reserva"
            )

        # Agrupar por id → cantidad pedida
        from collections import Counter
        conteo = Counter(ejemplar_ids)

        # Obtener ejemplares con lock (ordenar por ID para evitar deadlocks)
        ids_unicos = sorted(conteo.keys())
        ejemplares_qs = Ejemplar.objects.filter(
            id__in=ids_unicos
        ).select_for_update()

        if ejemplares_qs.count() != len(ids_unicos):
            raise ValueError("Uno o más ejemplares no existen")

        total_reserva = 0
        from decimal import Decimal
        total_reserva = Decimal('0.00')
        ejemplares_validos = []

        # Verificar disponibilidad con la cantidad solicitada
        for ejemplar in ejemplares_qs:
            cantidad_pedida = conteo[ejemplar.id]
            reservados = Reserva.objects.filter(
                ejemplares=ejemplar,
                estado='pendiente'
            ).count()

            stock_libre = ejemplar.stock - reservados
            if stock_libre < cantidad_pedida:
                raise ValueError(
                    f"'{ejemplar.libro.titulo}' solo tiene {stock_libre} "
                    f"unidad(es) disponibles (pediste {cantidad_pedida})"
                )

            ejemplares_validos.append(ejemplar)
            total_reserva += ejemplar.precio_venta * cantidad_pedida

        # Crear reserva
        fecha_vencimiento = timezone.now() + timedelta(
            hours=InventarioService.HORAS_VENCIMIENTO_RESERVA
        )

        reserva = Reserva.objects.create(
            usuario=usuario,
            estado='pendiente',
            fecha_vencimiento=fecha_vencimiento,
            total=total_reserva
        )

        # Asociar ejemplares únicos (M2M no admite duplicados)
        reserva.ejemplares.set(ejemplares_validos)

        return reserva

    
    @staticmethod
    @transaction.atomic
    def confirmar_venta(ejemplar_ids, metodo_pago, usuario_cajero, usuario_cliente=None):
        """
        Crea una venta y descuenta stock automáticamente.
        
        Operación atómica:
        - Verifica stock
        - Crea Venta
        - Crea DetalleVenta
        - Descuenta stock
        
        Args:
            ejemplar_ids: IDs de Ejemplar a vender
            metodo_pago: Método de pago ('efectivo', 'tarjeta', etc)
            usuario_cajero: User del cajero
            usuario_cliente: User del cliente (opcional)
            
        Returns:
            Venta: Objeto venta creado
            
        Raises:
            ValueError: Si no hay stock
        """
        from inventario.models import Ejemplar
        from ventas.models import Venta, DetalleVenta
        
        # Obtener ejemplares con lock, ordenados para evitar deadlock
        ejemplares = Ejemplar.objects.filter(
            id__in=sorted(ejemplar_ids)
        ).select_for_update()
        
        if ejemplares.count() != len(ejemplar_ids):
            raise ValueError("Uno o más ejemplares no existen")
        
        total_venta = Decimal('0.00')
        detalles = []
        
        # Validar y acumular
        for ejemplar in ejemplares:
            if ejemplar.stock < 1:
                raise ValueError(
                    f"'{ejemplar.libro.titulo}' agotado"
                )
            
            total_venta += ejemplar.precio_venta
            detalles.append({
                'ejemplar': ejemplar,
                'precio': ejemplar.precio_venta
            })
        
        # Crear venta
        venta = Venta.objects.create(
            cajero=usuario_cajero,
            cliente=usuario_cliente,
            total=total_venta,
            metodo_pago=metodo_pago
        )
        
        # Crear detalles y descontar stock
        for detalle_info in detalles:
            ejemplar = detalle_info['ejemplar']
            
            # Crear detalle de venta
            DetalleVenta.objects.create(
                venta=venta,
                ejemplar=ejemplar,  # Cambio: referencia al Ejemplar específico
                cantidad=1,
                precio_unitario=detalle_info['precio']
            )
            
            # Descontar stock directamente (atomicamente)
            ejemplar.stock = F('stock') - 1
            ejemplar.save(update_fields=['stock'])
        
        return venta
    
    @staticmethod
    @transaction.atomic
    def liberar_reserva(reserva_id):
        """
        Cancela una reserva y libera el stock.
        
        Args:
            reserva_id: ID de la Reserva
            
        Returns:
            Reserva: La reserva cancelada
        """
        from reservas.models import Reserva
        
        reserva = Reserva.objects.select_for_update().get(id=reserva_id)
        
        if reserva.estado != 'pendiente':
            raise ValueError(
                f"Solo se pueden cancelar reservas pendientes. "
                f"Estado actual: {reserva.estado}"
            )
        
        reserva.estado = 'cancelada'
        reserva.save()
        
        return reserva
    
    @staticmethod
    @transaction.atomic
    def confirmar_reserva_a_venta(reserva_id, metodo_pago, usuario_cajero):
        """
        Convierte una reserva pendiente en venta.
        
        Args:
            reserva_id: ID de la Reserva
            metodo_pago: Método de pago
            usuario_cajero: User del cajero
            
        Returns:
            Venta: La venta creada
        """
        from inventario.models import Ejemplar
        from reservas.models import Reserva
        from ventas.models import Venta, DetalleVenta
        
        reserva = Reserva.objects.select_for_update().get(id=reserva_id)
        
        if reserva.estado != 'pendiente':
            raise ValueError(
                f"Solo se pueden confirmar reservas pendientes. "
                f"Estado actual: {reserva.estado}"
            )
        
        # Obtener ejemplares con lock
        ejemplares = reserva.ejemplares.select_for_update()
        
        total_venta = Decimal('0.00')
        
        # Crear venta
        venta = Venta.objects.create(
            cajero=usuario_cajero,
            cliente=reserva.usuario,
            total=0,  # Se actualizará en señal
            metodo_pago=metodo_pago
        )
        
        from decimal import ROUND_HALF_UP
        # Crear detalles y descontar stock
        for ejemplar in ejemplares:
            # Replicar lógica de cálculo de cantidad de la vista antigua
            if ejemplar.precio_venta and ejemplar.precio_venta > 0:
                if ejemplares.count() == 1:
                    cantidad = int(
                        (reserva.total / ejemplar.precio_venta)
                        .quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                    )
                else:
                    cantidad = 1
                cantidad = max(1, min(cantidad, ejemplar.stock))
            else:
                cantidad = 1

            # Verificar que aún hay stock
            if ejemplar.stock < cantidad:
                raise ValueError(
                    f"'{ejemplar.libro.titulo}' no tiene stock suficiente (requerido: {cantidad})"
                )
            
            DetalleVenta.objects.create(
                venta=venta,
                ejemplar=ejemplar,
                cantidad=cantidad,
                precio_unitario=ejemplar.precio_venta
            )
            
            # Descontar stock
            ejemplar.stock = F('stock') - cantidad
            ejemplar.save(update_fields=['stock'])
            
            total_venta += (ejemplar.precio_venta * cantidad)
        
        # Actualizar total de venta
        venta.total = total_venta
        venta.save()
        
        # Marcar reserva como completada
        reserva.estado = 'completada'
        reserva.save()
        
        return venta
    
    @staticmethod
    def get_stock_disponible(ejemplar_id):
        """
        Obtiene el stock disponible (no reservado) de un ejemplar.
        
        Args:
            ejemplar_id: ID del Ejemplar
            
        Returns:
            int: Stock disponible >= 0
        """
        from inventario.models import Ejemplar
        from reservas.models import Reserva
        
        try:
            ejemplar = Ejemplar.objects.get(id=ejemplar_id)
        except Ejemplar.DoesNotExist:
            return 0
        
        reservados = Reserva.objects.filter(
            ejemplares=ejemplar,
            estado='pendiente'
        ).count()
        
        return max(0, ejemplar.stock - reservados)
    
    @staticmethod
    @transaction.atomic
    def cancelar_reservas_vencidas():
        """
        Cancela automáticamente todas las reservas vencidas.
        Pensado para ejecutarse por Celery o comando management.
        
        Returns:
            int: Cantidad de reservas canceladas
        """
        from reservas.models import Reserva
        
        vencidas = Reserva.objects.filter(
            estado='pendiente',
            fecha_vencimiento__lt=timezone.now()
        ).select_for_update()
        
        count = vencidas.update(estado='expirada')
        return count
