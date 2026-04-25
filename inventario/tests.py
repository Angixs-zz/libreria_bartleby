"""
Tests unitarios y de integración para inventario y servicios.

Cubre:
- Operaciones atómicas de stock (reservas, ventas)
- Validaciones de models
- Race conditions prevenidas
"""

from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from inventario.models import EstadoFisico, Libro, Ejemplar, Categoria
from reservas.models import Reserva
from ventas.models import Venta, DetalleVenta
from services.inventario_service import InventarioService
from utils.helpers import (
    generar_sku_mejorado,
    buscar_por_isbn,
    validar_precio,
    validar_isbn,
    validar_cantidad
)


class HelperTestCase(TestCase):
    """Tests para funciones helper."""
    
    def test_generar_sku_mejorado(self):
        """SKU generado debe tener formato correcto."""
        sku = generar_sku_mejorado()
        self.assertTrue(sku.startswith('BRT-'))
        self.assertEqual(len(sku), 8)  # BRT- + 4 caracteres
    
    def test_generar_sku_unico(self):
        """Múltiples SKUs generados deben ser únicos."""
        skus = {generar_sku_mejorado() for _ in range(10)}
        self.assertEqual(len(skus), 10)
    
    def test_validar_precio_valido(self):
        """Precio válido debe parsear correctamente."""
        precio, error = validar_precio('19.99')
        self.assertEqual(precio, Decimal('19.99'))
        self.assertIsNone(error)
    
    def test_validar_precio_cero(self):
        """Precio zero debe fallar."""
        precio, error = validar_precio('0')
        self.assertIsNone(precio)
        self.assertIsNotNone(error)
    
    def test_validar_precio_negativo(self):
        """Precio negativo debe fallar."""
        precio, error = validar_precio('-10')
        self.assertIsNone(precio)
        self.assertIsNotNone(error)
    
    def test_validar_isbn_10(self):
        """ISBN-10 válido debe pasar."""
        # 0306406559 es un ISBN-10 válido
        self.assertTrue(validar_isbn('0306406559'))
    
    def test_validar_isbn_13(self):
        """ISBN-13 válido debe pasar."""
        # 9780306406559 es un ISBN-13 válido
        self.assertTrue(validar_isbn('9780306406559'))
    
    def test_validar_isbn_invalido(self):
        """ISBN inválido debe fallar."""
        self.assertFalse(validar_isbn('12345'))
    
    def test_validar_cantidad_valida(self):
        """Cantidad válida debe parsear."""
        cantidad, error = validar_cantidad('5')
        self.assertEqual(cantidad, 5)
        self.assertIsNone(error)
    
    def test_validar_cantidad_supera_stock(self):
        """Cantidad > stock debe fallar."""
        cantidad, error = validar_cantidad('10', stock_disponible=5)
        self.assertIsNone(cantidad)
        self.assertIsNotNone(error)


class LibroEjemplarTestCase(TestCase):
    """Tests para modelos de inventario."""
    
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='Ficción')
        self.libro = Libro.objects.create(
            titulo='1984',
            autor='George Orwell',
            isbn='9780451524935',
            categoria=self.categoria,
            descripcion='Una novela de ciencia ficción'
        )
    
    def test_crear_libro(self):
        """Crear libro debe funcionar."""
        self.assertEqual(self.libro.titulo, '1984')
        self.assertEqual(self.libro.autor, 'George Orwell')
    
    def test_crear_ejemplar(self):
        """Crear ejemplar debe generar SKU automático."""
        ejemplar = Ejemplar.objects.create(
            libro=self.libro,
            estado_fisico=EstadoFisico.objects.get_or_create(nombre='nuevo')[0],
            precio_venta=Decimal('15.99')
        )
        self.assertTrue(ejemplar.sku.startswith('BRT-'))
        self.assertEqual(ejemplar.stock, 1)
    
    def test_precio_referencia_libro(self):
        """Precio referencia debe ser el del primer ejemplar."""
        ejemplar = Ejemplar.objects.create(
            libro=self.libro,
            estado_fisico=EstadoFisico.objects.get_or_create(nombre='nuevo')[0],
            precio_venta=Decimal('15.99')
        )
        self.assertEqual(self.libro.precio_referencia, Decimal('15.99'))
    
    def test_total_ejemplares(self):
        """Total ejemplares debe contar correctamente."""
        for i in range(3):
            Ejemplar.objects.create(
                libro=self.libro,
                estado_fisico=EstadoFisico.objects.get_or_create(nombre='nuevo')[0],
                precio_venta=Decimal('15.99')
            )
        self.assertEqual(self.libro.total_ejemplares, 3)


class ReservaTestCase(TransactionTestCase):
    """
    Tests para transacciones de reserva.
    Usa TransactionTestCase para probar transacciones atómicas.
    """
    
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='Ficción')
        self.libro = Libro.objects.create(
            titulo='1984',
            autor='George Orwell',
            isbn='9780451524935',
            categoria=self.categoria
        )
        self.ejemplar = Ejemplar.objects.create(
            libro=self.libro,
            estado_fisico=EstadoFisico.objects.get_or_create(nombre='nuevo')[0],
            precio_venta=Decimal('15.99'),
            stock=2
        )
        self.usuario = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_reservar_ejemplar_valido(self):
        """Reserva válida debe crear Reserva con ejemplar."""
        reserva = InventarioService.reservar_ejemplar(
            self.usuario,
            self.ejemplar.id
        )
        self.assertEqual(reserva.usuario, self.usuario)
        self.assertTrue(reserva.ejemplares.filter(id=self.ejemplar.id).exists())
        self.assertEqual(reserva.estado, 'pendiente')
    
    def test_reservar_sin_stock(self):
        """Reserva sin stock debe fallar."""
        # Agotar el stock
        self.ejemplar.stock = 0
        self.ejemplar.save()
        
        with self.assertRaises(ValueError) as ctx:
            InventarioService.reservar_ejemplar(
                self.usuario,
                self.ejemplar.id
            )
        self.assertIn('agotado', str(ctx.exception).lower())
    
    def test_reserva_tiene_vencimiento(self):
        """Reserva debe establecer vencimiento automáticamente."""
        reserva = InventarioService.reservar_ejemplar(
            self.usuario,
            self.ejemplar.id
        )
        
        # Debe vencer aprox en 72 horas
        tiempo_esperado = timezone.now() + timedelta(hours=72)
        diff = abs((reserva.fecha_vencimiento - tiempo_esperado).total_seconds())
        self.assertLess(diff, 60)  # Margen de 60 segundos
    
    def test_reservar_multiples(self):
        """Reservar múltiples ejemplares funciona."""
        ej2 = Ejemplar.objects.create(
            libro=self.libro,
            estado_fisico=EstadoFisico.objects.get_or_create(nombre='bueno')[0],
            precio_venta=Decimal('14.99'),
            stock=1
        )
        
        reserva = InventarioService.reservar_multiples(
            self.usuario,
            [self.ejemplar.id, ej2.id]
        )
        
        self.assertEqual(reserva.ejemplares.count(), 2)
    
    def test_reservar_exceso_ejemplares(self):
        """Reservar más del máximo debe fallar."""
        ejemplares = []
        for i in range(InventarioService.MAX_EJEMPLARES_POR_RESERVA + 1):
            ej = Ejemplar.objects.create(
                libro=self.libro,
                estado_fisico=EstadoFisico.objects.get_or_create(nombre='nuevo')[0],
                precio_venta=Decimal('15.99'),
                sku=f'BRT-TEST{i:04d}'
            )
            ejemplares.append(ej.id)
        
        with self.assertRaises(ValueError) as ctx:
            InventarioService.reservar_multiples(
                self.usuario,
                ejemplares
            )
        self.assertIn('máximo', str(ctx.exception).lower())


class VentaTestCase(TransactionTestCase):
    """Tests para transacciones de venta."""
    
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='Ficción')
        self.libro = Libro.objects.create(
            titulo='1984',
            autor='George Orwell',
            isbn='9780451524935',
            categoria=self.categoria
        )
        self.ejemplar = Ejemplar.objects.create(
            libro=self.libro,
            estado_fisico=EstadoFisico.objects.get_or_create(nombre='nuevo')[0],
            precio_venta=Decimal('15.99'),
            stock=5
        )
        self.cajero = User.objects.create_user(
            username='cajero',
            is_staff=True,
            password='pass123'
        )
    
    def test_confirmar_venta_descuenta_stock(self):
        """Venta debe descontar stock automáticamente."""
        stock_inicial = self.ejemplar.stock
        
        venta = InventarioService.confirmar_venta(
            [self.ejemplar.id],
            'efectivo',
            self.cajero
        )
        
        # Refrescar desde BD
        self.ejemplar.refresh_from_db()
        
        self.assertEqual(self.ejemplar.stock, stock_inicial - 1)
        self.assertEqual(venta.total, Decimal('15.99'))
    
    def test_confirmar_venta_sin_stock(self):
        """Venta sin stock debe fallar."""
        self.ejemplar.stock = 0
        self.ejemplar.save()
        
        with self.assertRaises(ValueError) as ctx:
            InventarioService.confirmar_venta(
                [self.ejemplar.id],
                'efectivo',
                self.cajero
            )
        self.assertIn('agotado', str(ctx.exception).lower())
    
    def test_detalle_venta_usa_ejemplar(self):
        """DetalleVenta debe referenciar ejemplar específico."""
        venta = InventarioService.confirmar_venta(
            [self.ejemplar.id],
            'efectivo',
            self.cajero
        )
        
        detalle = venta.detalles.first()
        self.assertEqual(detalle.ejemplar, self.ejemplar)
        self.assertEqual(detalle.precio_unitario, self.ejemplar.precio_venta)


class CancelacionReservaTestCase(TransactionTestCase):
    """Tests para cancelación de reservas vencidas."""
    
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre='Ficción')
        self.libro = Libro.objects.create(
            titulo='1984',
            autor='George Orwell',
            categoria=self.categoria
        )
        self.ejemplar = Ejemplar.objects.create(
            libro=self.libro,
            estado_fisico=EstadoFisico.objects.get_or_create(nombre='nuevo')[0],
            precio_venta=Decimal('15.99')
        )
        self.usuario = User.objects.create_user(
            username='user',
            password='pass123'
        )
    
    def test_cancelar_reservas_vencidas(self):
        """Cancelación de vencidas debe actualizar estado."""
        # Crear reserva con vencimiento pasado
        reserva = Reserva.objects.create(
            usuario=self.usuario,
            estado='pendiente',
            fecha_vencimiento=timezone.now() - timedelta(hours=1),
            total=Decimal('15.99')
        )
        reserva.ejemplares.add(self.ejemplar)
        
        # Ejecutar servicio
        count = InventarioService.cancelar_reservas_vencidas()
        
        self.assertEqual(count, 1)
        reserva.refresh_from_db()
        self.assertEqual(reserva.estado, 'expirada')
