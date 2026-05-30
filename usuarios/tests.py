from decimal import Decimal
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from inventario.models import EstadoFisico, Categoria, Libro, Ejemplar
from reservas.models import Reserva
from usuarios.auditoria import registrar_auditoria
from usuarios.models import NotaClienteInterna, EventoAuditoria
from ventas.models import Venta, DetalleVenta


class PanelClientesTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username='adminpanel',
            password='testpass123',
            is_staff=True,
        )
        self.cliente = User.objects.create_user(
            username='lectora',
            password='testpass123',
            first_name='Ada',
            last_name='Lovelace',
            email='ada@example.com',
        )
        self.cliente.perfil.telefono = '5551234567'
        self.cliente.perfil.direccion = 'Calle de los Libros 42'
        self.cliente.perfil.save()
        self.otro_cliente = User.objects.create_user(
            username='visitante',
            password='testpass123',
            first_name='Otro',
            last_name='Cliente',
            email='otro@example.com',
        )

        categoria = Categoria.objects.create(nombre='Novela')
        libro = Libro.objects.create(
            titulo='Ficciones',
            autor='Jorge Luis Borges',
            categoria=categoria,
        )
        ejemplar = Ejemplar.objects.create(
            libro=libro,
            estado_fisico=EstadoFisico.objects.get_or_create(nombre='nuevo')[0],
            precio_compra=Decimal('100.00'),
            precio_venta=Decimal('250.00'),
            stock=3,
        )

        self.reserva = Reserva.objects.create(
            usuario=self.cliente,
            estado='pendiente',
            total=Decimal('250.00'),
        )
        self.reserva.libros.add(libro)
        self.reserva.ejemplares.add(ejemplar)

        self.venta = Venta.objects.create(
            cajero=self.admin,
            cliente=self.cliente,
            metodo_pago='efectivo',
        )
        DetalleVenta.objects.create(
            venta=self.venta,
            ejemplar=ejemplar,
            cantidad=1,
            precio_unitario=Decimal('250.00'),
        )
        self.venta.refresh_from_db()

        self.reserva_otro = Reserva.objects.create(
            usuario=self.otro_cliente,
            estado='completada',
            total=Decimal('250.00'),
        )
        self.reserva_otro.libros.add(libro)
        self.reserva_otro.ejemplares.add(ejemplar)

    def test_panel_clientes_disponible_para_staff(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('panel_clientes'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Clientes')
        self.assertContains(response, 'lectora')
        self.assertContains(response, 'ada@example.com')

    def test_panel_clientes_restringido_para_cliente_normal(self):
        self.client.force_login(self.cliente)

        response = self.client.get(reverse('panel_clientes'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_panel_clientes_filtra_clientes_sin_movimiento(self):
        sin_movimiento = User.objects.create_user(
            username='nuevo',
            password='testpass123',
            email='nuevo@example.com',
        )

        self.client.force_login(self.admin)
        response = self.client.get(reverse('panel_clientes'), {'filtro': 'sin_movimiento'})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'nuevo')
        self.assertNotContains(response, 'lectora')

    def test_staff_puede_ver_ficha_individual_de_cliente(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('detalle_cliente', args=[self.cliente.id]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ficha integral del cliente')
        self.assertContains(response, 'Ada Lovelace')
        self.assertContains(response, self.reserva.codigo_ticket)
        self.assertContains(response, f'Ticket #{self.venta.id}')
        self.assertNotContains(response, self.reserva_otro.codigo_ticket)

    def test_cliente_normal_no_puede_ver_ficha_individual(self):
        self.client.force_login(self.cliente)

        response = self.client.get(reverse('detalle_cliente', args=[self.cliente.id]))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_staff_puede_agregar_nota_interna_a_cliente(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse('detalle_cliente', args=[self.cliente.id]),
            {'contenido': 'Cliente frecuente. Prefiere narrativa latinoamericana.'},
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        nota = NotaClienteInterna.objects.get(cliente=self.cliente)
        self.assertEqual(nota.autor, self.admin)
        self.assertContains(response, 'Cliente frecuente. Prefiere narrativa latinoamericana.')


class PanelPersonalTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(
            username='director',
            password='testpass123',
            is_staff=True,
            is_superuser=True,
            first_name='Melville',
            last_name='Director',
        )
        self.staff = User.objects.create_user(
            username='cajero1',
            password='testpass123',
            is_staff=True,
            first_name='Carmen',
            last_name='Caja',
        )
        self.staff.perfil.rol = 'cajero'
        self.staff.perfil.save()

        self.cliente = User.objects.create_user(
            username='cliente_simple',
            password='testpass123',
        )

    def test_panel_personal_disponible_solo_para_director(self):
        self.client.force_login(self.director)

        response = self.client.get(reverse('panel_personal'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Gestión de Personal')
        self.assertContains(response, 'cajero1')

    def test_panel_personal_restringido_para_staff_no_director(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('panel_personal'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_director_puede_crear_staff(self):
        self.client.force_login(self.director)

        response = self.client.post(
            reverse('crear_staff'),
            {
                'first_name': 'Laura',
                'last_name': 'Turner',
                'username': 'laura.staff',
                'email': 'laura@bartleby.com',
                'password1': 'ClaveSegura123!',
                'password2': 'ClaveSegura123!',
                'admin_password': 'testpass123',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        nuevo_staff = User.objects.get(username='laura.staff')
        self.assertTrue(nuevo_staff.is_staff)
        self.assertFalse(nuevo_staff.is_superuser)
        self.assertTrue(nuevo_staff.is_active)
        self.assertEqual(nuevo_staff.perfil.rol, 'cajero')
        self.assertContains(response, 'laura.staff')
        self.assertTrue(
            EventoAuditoria.objects.filter(
                accion='crear',
                modulo='usuarios',
                entidad_id=nuevo_staff.id,
            ).exists()
        )

    def test_director_puede_desactivar_staff(self):
        self.client.force_login(self.director)

        response = self.client.post(
            reverse('desactivar_personal', args=[self.staff.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)

    def test_director_no_puede_desactivarse_a_si_mismo(self):
        self.client.force_login(self.director)

        response = self.client.post(
            reverse('desactivar_personal', args=[self.director.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.director.refresh_from_db()
        self.assertTrue(self.director.is_active)

    def test_director_puede_reactivar_staff(self):
        self.staff.is_active = False
        self.staff.is_staff = False
        self.staff.save(update_fields=['is_active', 'is_staff'])
        self.client.force_login(self.director)

        response = self.client.post(
            reverse('reactivar_personal', args=[self.staff.id]),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)
        self.assertTrue(self.staff.is_staff)
        self.assertTrue(
            EventoAuditoria.objects.filter(
                accion='reactivar',
                modulo='usuarios',
                entidad_id=self.staff.id,
            ).exists()
        )

    def test_director_puede_editar_datos_basicos_del_staff(self):
        self.client.force_login(self.director)

        response = self.client.post(
            reverse('editar_personal', args=[self.staff.id]),
            {
                f'editar-{self.staff.id}-first_name': 'Carmina',
                f'editar-{self.staff.id}-last_name': 'Ventas',
                f'editar-{self.staff.id}-username': 'cajera.principal',
                f'editar-{self.staff.id}-email': 'carmina@bartleby.com',
                f'editar-{self.staff.id}-telefono': '5511223344',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.staff.perfil.refresh_from_db()
        self.assertEqual(self.staff.first_name, 'Carmina')
        self.assertEqual(self.staff.last_name, 'Ventas')
        self.assertEqual(self.staff.username, 'cajera.principal')
        self.assertEqual(self.staff.email, 'carmina@bartleby.com')
        self.assertEqual(self.staff.perfil.telefono, '5511223344')
        self.assertEqual(self.staff.perfil.rol, 'cajero')

    def test_director_puede_resetear_password_del_staff(self):
        self.client.force_login(self.director)

        response = self.client.post(
            reverse('resetear_password_personal', args=[self.staff.id]),
            {
                f'password-{self.staff.id}-password1': 'NuevaClaveSegura123!',
                f'password-{self.staff.id}-password2': 'NuevaClaveSegura123!',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password('NuevaClaveSegura123!'))


class MiPerfilActividadTests(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user(
            username='perfil_cliente',
            password='testpass123',
            first_name='Ana',
            last_name='Lectora',
            email='ana@correo.com',
        )
        self.cliente.perfil.telefono = '5512345678'
        self.cliente.perfil.direccion = 'Calle Central 10'
        self.cliente.perfil.save()

        self.otro_cliente = User.objects.create_user(
            username='otro_cliente',
            password='testpass123',
        )

        self.staff = User.objects.create_user(
            username='staff_turno',
            password='testpass123',
            is_staff=True,
        )
        self.staff.perfil.rol = 'cajero'
        self.staff.perfil.save()

        self.admin = User.objects.create_user(
            username='admin_jefe',
            password='testpass123',
            is_staff=True,
            is_superuser=True,
        )
        self.admin.perfil.rol = 'admin'
        self.admin.perfil.save()

        categoria = Categoria.objects.create(nombre='Perfil')
        self.libro = Libro.objects.create(
            titulo='La invencion de Morel',
            autor='Adolfo Bioy Casares',
            categoria=categoria,
        )
        self.ejemplar = Ejemplar.objects.create(
            libro=self.libro,
            estado_fisico=EstadoFisico.objects.get_or_create(nombre='nuevo')[0],
            precio_compra=Decimal('80.00'),
            precio_venta=Decimal('160.00'),
            stock=2,
        )

        self.reserva_cliente = Reserva.objects.create(
            usuario=self.cliente,
            estado='pendiente',
            total=Decimal('160.00'),
        )
        self.reserva_cliente.libros.add(self.libro)
        self.reserva_cliente.ejemplares.add(self.ejemplar)

        reserva_otro = Reserva.objects.create(
            usuario=self.otro_cliente,
            estado='pendiente',
            total=Decimal('160.00'),
        )
        reserva_otro.libros.add(self.libro)
        reserva_otro.ejemplares.add(self.ejemplar)

        self.venta_cliente = Venta.objects.create(
            cajero=self.staff,
            cliente=self.cliente,
            metodo_pago='efectivo',
        )
        DetalleVenta.objects.create(
            venta=self.venta_cliente,
            ejemplar=self.ejemplar,
            cantidad=1,
            precio_unitario=Decimal('160.00'),
        )
        self.venta_cliente.refresh_from_db()

        self.venta_staff = Venta.objects.create(
            cajero=self.staff,
            cliente=self.cliente,
            metodo_pago='tarjeta',
        )
        DetalleVenta.objects.create(
            venta=self.venta_staff,
            ejemplar=self.ejemplar,
            cantidad=1,
            precio_unitario=Decimal('160.00'),
        )
        self.venta_staff.refresh_from_db()

    def test_cliente_ve_solo_sus_reservas_y_compras(self):
        self.client.force_login(self.cliente)

        response = self.client.get(reverse('mi_perfil'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['perfil_tipo'], 'cliente')
        self.assertContains(response, self.reserva_cliente.codigo_ticket)
        self.assertContains(response, f'Ticket #{self.venta_cliente.id}')
        self.assertNotContains(response, 'otro_cliente')

    def test_staff_ve_resumen_de_jornada(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('mi_perfil'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['perfil_tipo'], 'staff')
        self.assertEqual(response.context['ventas_hoy_count'], 2)
        self.assertEqual(response.context['ventas_hoy_total'], Decimal('320.00'))

    def test_admin_ve_metricas_del_mes(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('mi_perfil'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['perfil_tipo'], 'admin')
        self.assertIn('chart_labels', response.context)
        self.assertIn('chart_totals', response.context)

    def test_usuario_puede_actualizar_su_perfil(self):
        self.client.force_login(self.cliente)

        response = self.client.post(
            reverse('mi_perfil'),
            {
                'first_name': 'Ana Maria',
                'last_name': 'Lectora',
                'email': 'nuevo@correo.com',
                'telefono': '5599988877',
                'direccion': 'Nueva direccion 123',
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.cliente.refresh_from_db()
        self.cliente.perfil.refresh_from_db()
        self.assertEqual(self.cliente.first_name, 'Ana Maria')
        self.assertEqual(self.cliente.email, 'nuevo@correo.com')
        self.assertEqual(self.cliente.perfil.telefono, '5599988877')


class DocumentosLegalesYRegistroTests(TestCase):
    def test_aviso_privacidad_disponible(self):
        response = self.client.get(reverse('aviso_privacidad'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Aviso de Privacidad')
        self.assertContains(response, 'Derechos ARCO')

    def test_terminos_condiciones_disponible(self):
        response = self.client.get(reverse('terminos_condiciones'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Terminos y Condiciones')
        self.assertContains(response, '72 horas')

    @staticmethod
    def _payload_registro(**overrides):
        payload = {
            'first_name': 'Luis',
            'last_name': 'Lector',
            'username': 'sinaviso',
            'email': 'sinaviso@example.com',
            'telefono': '5512345678',
            'direccion': 'Centro 100',
            'password1': 'ClaveSegura123!',
            'password2': 'ClaveSegura123!',
        }
        payload.update(overrides)
        return payload

    def test_registro_requiere_aceptar_aviso_privacidad(self):
        response = self.client.post(
            reverse('registrar'),
            self._payload_registro(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Debes aceptar el Aviso de Privacidad')
        self.assertFalse(User.objects.filter(username='sinaviso').exists())

    def test_registro_con_aceptacion_crea_usuario_activo(self):
        response = self.client.post(
            reverse('registrar'),
            self._payload_registro(
                username='conaviso',
                email='conaviso@example.com',
                acepta_privacidad='on',
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verificar_codigo'))
        usuario = User.objects.get(username='conaviso')
        self.assertFalse(usuario.is_active)
        self.assertEqual(usuario.email, 'conaviso@example.com')
        self.assertEqual(usuario.first_name, 'Luis')
        self.assertEqual(usuario.perfil.telefono, '5512345678')
        self.assertIsNotNone(usuario.perfil.codigo_verificacion)

    def test_registro_rechaza_correo_con_formato_invalido(self):
        response = self.client.post(
            reverse('registrar'),
            self._payload_registro(
                username='correo_invalido',
                email='correo-invalido',
                acepta_privacidad='on',
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ingresa un correo electronico valido.')
        self.assertFalse(User.objects.filter(username='correo_invalido').exists())


class PanelAuditoriaTests(TestCase):
    def setUp(self):
        self.director = User.objects.create_user(
            username='director_auditoria',
            password='testpass123',
            is_staff=True,
            is_superuser=True,
        )
        self.staff = User.objects.create_user(
            username='staff_auditoria',
            password='testpass123',
            is_staff=True,
        )
        EventoAuditoria.objects.create(
            actor=self.director,
            accion='crear',
            modulo='usuarios',
            entidad_tipo='usuario_staff',
            entidad_id=self.staff.id,
            entidad_nombre=self.staff.username,
            descripcion='Alta inicial de staff.',
        )

    def test_panel_auditoria_disponible_para_director(self):
        self.client.force_login(self.director)

        response = self.client.get(reverse('panel_auditoria'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Auditoría')
        self.assertContains(response, 'Alta inicial de staff.')

    def test_panel_auditoria_restringido_para_staff_no_director(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse('panel_auditoria'))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)

    def test_panel_auditoria_filtra_por_accion(self):
        EventoAuditoria.objects.create(
            actor=self.director,
            accion='cancelar',
            modulo='reservas',
            entidad_tipo='reserva',
            entidad_id=99,
            entidad_nombre='BART-TEST',
            descripcion='Reserva cancelada.',
        )
        self.client.force_login(self.director)

        response = self.client.get(reverse('panel_auditoria'), {'accion': 'cancelar'})

        self.assertEqual(response.status_code, 200)
        eventos = list(response.context['eventos'])
        self.assertEqual(len(eventos), 1)
        self.assertEqual(eventos[0].accion, 'cancelar')

    def test_panel_auditoria_respeta_limite_seleccionado(self):
        for indice in range(30):
            EventoAuditoria.objects.create(
                actor=self.director,
                accion='editar',
                modulo='inventario',
                entidad_tipo='libro',
                entidad_id=indice + 1,
                entidad_nombre=f'Libro {indice + 1}',
                descripcion='Cambio de inventario.',
            )
        self.client.force_login(self.director)

        response = self.client.get(reverse('panel_auditoria'), {'limite': '25'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['eventos']), 25)
        self.assertEqual(response.context['limite_activo'], 25)

    def test_panel_auditoria_ignora_limite_no_permitido(self):
        self.client.force_login(self.director)

        response = self.client.get(reverse('panel_auditoria'), {'limite': '9999'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['limite_activo'], 120)

    def test_registrar_auditoria_depura_eventos_antiguos(self):
        antiguo = EventoAuditoria.objects.create(
            actor=self.director,
            accion='crear',
            modulo='usuarios',
            entidad_tipo='usuario_staff',
            entidad_id=self.staff.id,
            entidad_nombre='registro_antiguo',
            descripcion='Registro antiguo.',
        )
        EventoAuditoria.objects.filter(pk=antiguo.pk).update(
            creado_en=timezone.now() - timedelta(days=181)
        )

        registrar_auditoria(
            actor=self.director,
            accion='editar',
            modulo='usuarios',
            entidad_tipo='usuario_staff',
            entidad_id=self.staff.id,
            entidad_nombre=self.staff.username,
            descripcion='Registro reciente.',
        )

        self.assertFalse(EventoAuditoria.objects.filter(pk=antiguo.pk).exists())
        self.assertTrue(EventoAuditoria.objects.filter(descripcion='Registro reciente.').exists())


class PerfilUsuarioTests(TestCase):
    def setUp(self):
        self.cliente = User.objects.create_user(
            username='lector_perfil',
            password='password123',
            email='lector_perfil@example.com',
            first_name='Gabriel',
            last_name='García'
        )
        self.cliente.perfil.telefono = '5512345678'
        self.cliente.perfil.direccion = 'Aracataca'
        self.cliente.perfil.save()

    def test_actualizar_perfil_sin_cambiar_email(self):
        """Si se actualiza el perfil pero el email sigue igual, el usuario sigue activo."""
        self.client.force_login(self.cliente)
        payload = {
            'first_name': 'Gabriel José',
            'last_name': 'García Márquez',
            'email': 'lector_perfil@example.com',
            'telefono': '5587654321',
            'direccion': 'Macondo'
        }
        response = self.client.post(reverse('mi_perfil'), payload)
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('mi_perfil'))
        
        # Verify update
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.first_name, 'Gabriel José')
        self.assertEqual(self.cliente.last_name, 'García Márquez')
        self.assertEqual(self.cliente.email, 'lector_perfil@example.com')
        self.assertEqual(self.cliente.perfil.telefono, '5587654321')
        self.assertEqual(self.cliente.perfil.direccion, 'Macondo')
        self.assertTrue(self.cliente.is_active)

    def test_actualizar_perfil_cambiando_email_requiere_verificacion(self):
        """Si un cliente cambia su email, se desactiva y se le redirige a verificar_codigo."""
        self.client.force_login(self.cliente)
        payload = {
            'first_name': 'Gabriel José',
            'last_name': 'García Márquez',
            'email': 'lector_nuevo@example.com',
            'telefono': '5587654321',
            'direccion': 'Macondo'
        }
        response = self.client.post(reverse('mi_perfil'), payload)
        
        # Should redirect to verificar_codigo
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('verificar_codigo'))
        
        # Verify state
        self.cliente.refresh_from_db()
        self.assertFalse(self.cliente.is_active)
        self.assertEqual(self.cliente.email, 'lector_nuevo@example.com')
        self.assertIsNotNone(self.cliente.perfil.codigo_verificacion)
        
        # Session should contain user_id_verificar
        self.assertEqual(self.client.session.get('user_id_verificar'), self.cliente.id)

