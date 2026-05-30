from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from inventario.models import Libro, Ejemplar, Categoria, EstadoFisico
from reservas.models import Reserva

class ReservasViewTestCase(TestCase):
    def setUp(self):
        # Create users
        self.cliente = User.objects.create_user(
            username='lector1',
            password='password123',
            email='lector1@example.com'
        )
        self.otro_cliente = User.objects.create_user(
            username='lector2',
            password='password123',
            email='lector2@example.com'
        )
        
        # Create inventory items
        self.categoria = Categoria.objects.create(nombre='Ficción')
        self.estado = EstadoFisico.objects.create(nombre='Excelente')
        self.libro = Libro.objects.create(
            titulo='El Aleph',
            autor='Jorge Luis Borges',
            isbn='9788420633114',
            categoria=self.categoria
        )
        self.ejemplar = Ejemplar.objects.create(
            libro=self.libro,
            estado_fisico=self.estado,
            precio_venta=Decimal('150.00'),
            stock=1
        )
        
        # Create a pending reservation for self.cliente
        self.reserva = Reserva.objects.create(
            usuario=self.cliente,
            estado='pendiente',
            total=Decimal('150.00')
        )
        self.reserva.libros.add(self.libro)
        self.reserva.ejemplares.add(self.ejemplar)

    def test_cliente_puede_cancelar_propia_reserva_pendiente(self):
        """Un cliente puede cancelar su propia reserva cuando está pendiente."""
        self.client.force_login(self.cliente)
        
        url = reverse('cancelar_reserva', args=[self.reserva.id])
        response = self.client.post(url)
        
        # Redirects to mis_reservas
        self.assertRedirects(response, reverse('mis_reservas'))
        
        # Check that state has changed to 'cancelada'
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, 'cancelada')

    def test_cliente_no_puede_cancelar_reserva_de_otro(self):
        """Un cliente no puede acceder a cancelar la reserva de otro usuario."""
        self.client.force_login(self.otro_cliente)
        
        url = reverse('cancelar_reserva', args=[self.reserva.id])
        response = self.client.post(url)
        
        # Should return 404 since it queries get_object_or_404(Reserva, id=reserva_id, usuario=request.user)
        self.assertEqual(response.status_code, 404)
        
        # Verify state is still pending
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, 'pendiente')

    def test_cliente_no_puede_cancelar_reserva_completada(self):
        """Un cliente no puede cancelar una reserva que ya está completada."""
        self.reserva.estado = 'completada'
        self.reserva.save()
        
        self.client.force_login(self.cliente)
        
        url = reverse('cancelar_reserva', args=[self.reserva.id])
        response = self.client.post(url, follow=True)
        
        # Should redirect back to mis_reservas and show an error message
        self.assertRedirects(response, reverse('mis_reservas'))
        self.assertContains(response, 'No puedes cancelar una reserva completada')
        
        # Verify state is still completada
        self.reserva.refresh_from_db()
        self.assertEqual(self.reserva.estado, 'completada')
