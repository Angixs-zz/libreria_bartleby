from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from inventario.models import EstadoFisico, Categoria, Libro, Ejemplar
from usuarios.models import EventoAuditoria
from .models import Proveedor, Adquisicion, DetalleAdquisicion


class ProveedoresModuleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='compras_admin',
            password='testpass123',
            is_staff=True,
        )
        self.cliente = User.objects.create_user(
            username='cliente_normal',
            password='testpass123',
        )
        self.proveedor = Proveedor.objects.create(
            nombre='Lotes del Sur',
            contacto='Marina Ramos',
            telefono='5550001122',
            email='marina@lotesdelsur.com',
        )

        categoria = Categoria.objects.create(nombre='Clasicos')
        libro = Libro.objects.create(
            titulo='Rayuela',
            autor='Julio Cortazar',
            categoria=categoria,
        )
        self.ejemplar = Ejemplar.objects.create(
            libro=libro,
            estado_fisico=EstadoFisico.objects.get_or_create(nombre='bueno')[0],
            precio_compra=Decimal('90.00'),
            precio_venta=Decimal('180.00'),
            stock=2,
        )

    def test_directorio_restringido_para_no_staff(self):
        self.client.force_login(self.cliente)

        response = self.client.get(reverse('directorio_proveedores'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_directorio_visible_para_staff(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('directorio_proveedores'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Directorio de Proveedores')
        self.assertContains(response, 'Lotes del Sur')

    def test_registrar_adquisicion_crea_lote_y_actualiza_stock(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('registrar_adquisicion'),
            {
                'proveedor': self.proveedor.id,
                'fecha': '2026-04-08',
                'tipo': 'identificado',
                'observaciones': 'Compra de lote semanal',
                'ejemplar_id': [str(self.ejemplar.id)],
                'cantidad': ['3'],
                'costo_unitario': ['110.00'],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.ejemplar.refresh_from_db()

        self.assertEqual(Adquisicion.objects.count(), 1)
        self.assertEqual(DetalleAdquisicion.objects.count(), 1)
        self.assertEqual(self.ejemplar.stock, 5)

        adquisicion = Adquisicion.objects.first()
        self.assertEqual(adquisicion.total, Decimal('330.00'))
        self.assertContains(response, 'Lote #')
        self.assertTrue(
            EventoAuditoria.objects.filter(
                modulo='proveedores',
                accion='crear',
                entidad_tipo='adquisicion',
                entidad_id=adquisicion.id,
            ).exists()
        )

    def test_registrar_adquisicion_preselecciona_proveedor_desde_querystring(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('registrar_adquisicion'),
            {'proveedor': self.proveedor.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['form'].initial['proveedor'], str(self.proveedor.id))

    def test_crear_ejemplar_rapido_crea_libro_con_categoria_nueva(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('crear_ejemplar_rapido'),
            {
                'titulo': 'La ciudad y sus muros inciertos',
                'autor': 'Haruki Murakami',
                'isbn': '9786073910123',
                'editorial': 'Tusquets',
                'anio_publicacion': '2024',
                'categoria_texto': 'Narrativa japonesa',
                'descripcion': 'Novela contemporanea.',
                'estado_fisico': EstadoFisico.objects.get(nombre='bueno').id,
                'precio_venta': '260.00',
                'descripcion_estado': 'Ejemplar en buen estado.',
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['ok'])

        libro = Libro.objects.get(isbn='9786073910123')
        self.assertEqual(libro.categoria.nombre, 'Narrativa japonesa')
        self.assertEqual(libro.anio_publicacion, 2024)
        self.assertEqual(libro.ejemplares.count(), 1)
        self.assertEqual(libro.ejemplares.first().stock, 0)

    def test_historial_proveedor_muestra_totales(self):
        adquisicion = Adquisicion.objects.create(
            proveedor=self.proveedor,
            creado_por=self.admin,
        )
        DetalleAdquisicion.objects.create(
            adquisicion=adquisicion,
            ejemplar=self.ejemplar,
            cantidad=2,
            costo_unitario=Decimal('100.00'),
        )

        self.client.force_login(self.admin)
        response = self.client.get(reverse('detalle_proveedor', args=[self.proveedor.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Historial por proveedor')
        self.assertEqual(response.context['gasto_total'], Decimal('200.00'))
        self.assertEqual(response.context['unidades_adquiridas'], 2)
