from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventario.models import Categoria, Libro, Ejemplar
from proveedores.models import Proveedor, Adquisicion
from reservas.models import Reserva
from ventas.models import Venta, DetalleVenta


class DashboardReportesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='director',
            password='testpass123',
            is_staff=True,
        )
        self.cliente = User.objects.create_user(
            username='cliente1',
            password='testpass123',
        )
        self.url = reverse('dashboard_reportes')

        categoria = Categoria.objects.create(nombre='Ensayo')
        self.libro_top = Libro.objects.create(titulo='El Aleph', autor='Jorge Luis Borges', categoria=categoria)
        self.libro_stock_bajo = Libro.objects.create(titulo='Pedro Paramo', autor='Juan Rulfo', categoria=categoria)

        self.ejemplar_top = Ejemplar.objects.create(
            libro=self.libro_top,
            estado_fisico='nuevo',
            precio_compra=Decimal('100.00'),
            precio_venta=Decimal('180.00'),
            stock=5,
        )
        self.ejemplar_stock_bajo = Ejemplar.objects.create(
            libro=self.libro_stock_bajo,
            estado_fisico='bueno',
            precio_compra=Decimal('80.00'),
            precio_venta=Decimal('120.00'),
            stock=2,
        )

        self.venta_hoy = Venta.objects.create(
            cajero=self.admin,
            cliente=self.cliente,
            metodo_pago='efectivo',
        )
        DetalleVenta.objects.create(
            venta=self.venta_hoy,
            ejemplar=self.ejemplar_top,
            cantidad=2,
            precio_unitario=Decimal('180.00'),
        )
        self.venta_hoy.refresh_from_db()

        self.venta_semana = Venta.objects.create(
            cajero=self.admin,
            cliente=self.cliente,
            metodo_pago='tarjeta',
        )
        fecha_semana = timezone.now() - timedelta(days=2)
        Venta.objects.filter(pk=self.venta_semana.pk).update(fecha_venta=fecha_semana)
        self.venta_semana.refresh_from_db()
        DetalleVenta.objects.create(
            venta=self.venta_semana,
            ejemplar=self.ejemplar_top,
            cantidad=1,
            precio_unitario=Decimal('180.00'),
        )
        self.venta_semana.refresh_from_db()

        self.reserva = Reserva.objects.create(
            usuario=self.cliente,
            estado='pendiente',
            total=Decimal('120.00'),
        )
        self.reserva.libros.add(self.libro_stock_bajo)
        self.reserva.ejemplares.add(self.ejemplar_stock_bajo)
        Reserva.objects.filter(pk=self.reserva.pk).update(
            fecha_vencimiento=timezone.now() + timedelta(hours=2)
        )

        self.alertas_url = reverse('centro_alertas')
        self.proveedor_inactivo = Proveedor.objects.create(
            nombre='Proveedor Dormido',
            contacto='Teresa',
            telefono='5550001111',
            activo=True,
        )
        adquisicion = Adquisicion.objects.create(
            proveedor=self.proveedor_inactivo,
            fecha=timezone.localdate() - timedelta(days=120),
            creado_por=self.admin,
        )
        adquisicion.save(update_fields=['fecha', 'creado_por'])

        self.venta_sin_cliente = Venta.objects.create(
            cajero=self.admin,
            cliente=None,
            metodo_pago='efectivo',
        )
        DetalleVenta.objects.create(
            venta=self.venta_sin_cliente,
            ejemplar=self.ejemplar_stock_bajo,
            cantidad=1,
            precio_unitario=Decimal('120.00'),
        )
        self.venta_sin_cliente.refresh_from_db()

        self.cliente_frecuente = User.objects.create_user(
            username='frecuente',
            password='testpass123',
            first_name='Cliente',
            last_name='Frecuente',
            email='frecuente@example.com',
        )
        venta_frecuente_1 = Venta.objects.create(
            cajero=self.admin,
            cliente=self.cliente_frecuente,
            metodo_pago='tarjeta',
        )
        DetalleVenta.objects.create(
            venta=venta_frecuente_1,
            ejemplar=self.ejemplar_top,
            cantidad=1,
            precio_unitario=Decimal('180.00'),
        )
        venta_frecuente_1.refresh_from_db()
        Venta.objects.filter(pk=venta_frecuente_1.pk).update(
            fecha_venta=timezone.now() - timedelta(days=80)
        )

        venta_frecuente_2 = Venta.objects.create(
            cajero=self.admin,
            cliente=self.cliente_frecuente,
            metodo_pago='efectivo',
        )
        DetalleVenta.objects.create(
            venta=venta_frecuente_2,
            ejemplar=self.ejemplar_top,
            cantidad=1,
            precio_unitario=Decimal('180.00'),
        )
        venta_frecuente_2.refresh_from_db()
        Venta.objects.filter(pk=venta_frecuente_2.pk).update(
            fecha_venta=timezone.now() - timedelta(days=79)
        )

        reserva_antigua = Reserva.objects.create(
            usuario=self.cliente_frecuente,
            estado='completada',
            total=Decimal('180.00'),
        )
        reserva_antigua.libros.add(self.libro_top)
        reserva_antigua.ejemplares.add(self.ejemplar_top)
        Reserva.objects.filter(pk=reserva_antigua.pk).update(
            fecha_reserva=timezone.now() - timedelta(days=78)
        )

    def test_dashboard_requiere_staff(self):
        self.client.force_login(self.cliente)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_dashboard_muestra_metricas_para_periodo_hoy(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.url, {'periodo': 'today'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Dashboard Ejecutivo')
        self.assertEqual(response.context['periodo'], 'today')
        self.assertEqual(response.context['ventas_tickets'], 2)
        self.assertEqual(response.context['ventas_monto'], Decimal('480'))
        self.assertEqual(response.context['ganancia_neta'], Decimal('200'))
        self.assertEqual(response.context['apartados_activos'], 1)
        self.assertEqual(len(response.context['chart_labels']), 7)

    def test_dashboard_top_libros_y_stock_bajo(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.url, {'periodo': 'week'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['top_libros'][0]['ejemplar__libro__titulo'], 'El Aleph')
        self.assertEqual(response.context['top_libros'][0]['unidades_vendidas'], 3)
        self.assertEqual(response.context['stock_bajo'][0].titulo, 'Pedro Paramo')

    def test_centro_alertas_requiere_staff(self):
        self.client.force_login(self.cliente)

        response = self.client.get(self.alertas_url)

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_centro_alertas_muestra_bloques_operativos(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.alertas_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Centro de Alertas')
        self.assertEqual(len(response.context['reservas_por_vencer']), 1)
        self.assertEqual(response.context['stock_critico'][0].titulo, 'Pedro Paramo')
        self.assertEqual(response.context['ventas_sin_cliente'][0].id, self.venta_sin_cliente.id)
        self.assertEqual(response.context['proveedores_inactivos'][0].id, self.proveedor_inactivo.id)
        self.assertEqual(response.context['clientes_frecuentes_inactivos'][0].id, self.cliente_frecuente.id)
