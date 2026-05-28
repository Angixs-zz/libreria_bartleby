import random
from collections import defaultdict
from decimal import Decimal
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import transaction
from django.db.models import (
    Q,
    Count,
    Sum,
    OuterRef,
    Subquery,
    IntegerField,
    DecimalField,
    DateTimeField,
    F,
)
from django.db.models.functions import Coalesce, TruncDay
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from inventario.models import Libro
from reservas.models import Reserva
from ventas.models import Venta, DetalleVenta
from decorators import admin_required, director_required, cajero_required
from .forms import (
    RegistroClienteForm,
    StaffCreationForm,
    ProfileUpdateForm,
    StaffUpdateForm,
    StaffPasswordResetForm,
    ClienteNotaInternaForm,
)
from .models import PerfilUsuario, NotaClienteInterna, EventoAuditoria
from .auditoria import AUDITORIA_RETENCION_DIAS, registrar_auditoria
from .email_service import enviar_codigo_verificacion_email, enviar_codigo_login_email


DOCUMENTOS_LEGALES = {
    'aviso-privacidad': {
        'titulo': 'Aviso de Privacidad',
        'subtitulo': 'Tratamiento responsable de los datos personales recabados por Libreria Bartleby.',
        'template': 'legal/aviso_privacidad.html',
    },
    'terminos-condiciones': {
        'titulo': 'Terminos y Condiciones',
        'subtitulo': 'Reglas de uso del sistema, apartados y compraventa de libros usados.',
        'template': 'legal/terminos_condiciones.html',
    },
}

ACCIONES_AUDITORIA = {
    'todas': 'Todas',
    'crear': 'Crear',
    'editar': 'Editar',
    'cancelar': 'Cancelar',
    'reactivar': 'Reactivar',
    'desactivar': 'Desactivar',
    'completar': 'Completar',
    'eliminar': 'Eliminar',
    'seguridad': 'Seguridad',
}

MODULOS_AUDITORIA = {
    'todos': 'Todos',
    'usuarios': 'Usuarios',
    'clientes': 'Clientes',
    'reservas': 'Reservas',
    'inventario': 'Inventario',
    'ventas': 'Ventas',
    'proveedores': 'Proveedores',
}

LIMITES_AUDITORIA = [25, 50, 120, 250]
LIMITE_AUDITORIA_DEFAULT = 120


def obtener_limite_auditoria(valor):
    try:
        limite = int(valor)
    except (TypeError, ValueError):
        return LIMITE_AUDITORIA_DEFAULT

    if limite in LIMITES_AUDITORIA:
        return limite

    return LIMITE_AUDITORIA_DEFAULT


def registrar(request):
    if request.user.is_authenticated:
        return redirect('lista_libros')
    if request.method == 'POST':
        if request.POST.get('acepta_privacidad') != 'on':
            form = RegistroClienteForm(request.POST)
            messages.error(
                request,
                'Debes aceptar el Aviso de Privacidad para crear tu cuenta.'
            )
            return render(request, 'usuarios/registrar.html', {'form': form})

        form = RegistroClienteForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                user = form.save(commit=False)
                user.is_active = True
                user.first_name = form.cleaned_data['first_name']
                user.last_name = form.cleaned_data['last_name']
                user.email = form.cleaned_data['email']
                user.save()

                perfil, _ = PerfilUsuario.objects.get_or_create(usuario=user)
                perfil.telefono = form.cleaned_data['telefono']
                perfil.direccion = form.cleaned_data.get('direccion', '')
                perfil.codigo_verificacion = None
                perfil.save()

            messages.success(request, 'Cuenta creada con éxito. Ya puedes entrar.')
            return redirect('login')
    else:
        form = RegistroClienteForm()
        
    return render(request, 'usuarios/registrar.html', {'form': form})

def verificar_codigo(request):
    if request.user.is_authenticated:
        return redirect('lista_libros')
    user_id = request.session.get('user_id_verificar')
    if not user_id:
        return redirect('registrar')

    user = User.objects.get(id=user_id)

    if request.method == 'POST':
        if 'reenviar_codigo' in request.POST:
            codigo = str(random.randint(100000, 999999))
            # Actualizar directamente en DB sin pasar por la señal
            PerfilUsuario.objects.filter(usuario=user).update(codigo_verificacion=codigo)
            try:
                enviar_codigo_verificacion_email(user, codigo)
                messages.success(request, 'Te reenviamos un nuevo código de verificación.')
            except Exception as exc:
                messages.error(request, f'No se pudo reenviar el código: {exc}')
            return redirect('verificar_codigo')

        codigo_ingresado = request.POST.get('codigo', '').strip()

        # Recargar el perfil fresco desde la DB (evita datos cacheados por la señal)
        perfil = PerfilUsuario.objects.get(usuario=user)
        codigo_guardado = perfil.codigo_verificacion or ''

        # Debug en consola — quitar en producción
        print(f'[VERIFICAR] Ingresado: "{codigo_ingresado}" | Guardado: "{codigo_guardado}" | Coincide: {codigo_guardado == codigo_ingresado}')

        if codigo_guardado == codigo_ingresado:
            # Activar usuario directo en DB (evita disparar señal que cachea perfil)
            User.objects.filter(id=user.id).update(is_active=True)
            PerfilUsuario.objects.filter(usuario=user).update(codigo_verificacion=None)
            request.session.pop('user_id_verificar', None)
            messages.success(request, "¡Cuenta activada con éxito! Ya puedes entrar.")
            return redirect('login')

        messages.error(request, "El código es incorrecto. Inténtalo de nuevo.")

    return render(request, 'usuarios/verificar.html', {'correo_destino': user.email})


def login_con_codigo(request):
    """
    Vista para solicitar código de login por email.
    """
    if request.user.is_authenticated:
        return redirect('lista_libros')
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if not email:
            messages.error(request, "Por favor ingresa tu email.")
            return render(request, 'usuarios/login_codigo.html')
        
        try:
            user = User.objects.get(email=email, is_active=True)
        except User.DoesNotExist:
            messages.error(request, "No se encontró una cuenta activa con ese email.")
            return render(request, 'usuarios/login_codigo.html')
        
        # Generar código de 6 dígitos
        codigo = str(random.randint(100000, 999999))
        
        # Guardar código en el perfil
        perfil, created = PerfilUsuario.objects.get_or_create(usuario=user)
        perfil.codigo_verificacion = codigo
        perfil.save()
        
        try:
            enviar_codigo_login_email(user, codigo)
        except Exception as exc:
            messages.error(request, f'No se pudo enviar el código de acceso: {exc}')
            return render(request, 'usuarios/login_codigo.html')
        
        # Guardar email en sesión para verificación
        request.session['email_login'] = email
        return redirect('verificar_codigo_login')
    
    return render(request, 'usuarios/login_codigo.html')


def verificar_codigo_login(request):
    """
    Vista para verificar el código de login.
    """
    if request.user.is_authenticated:
        return redirect('lista_libros')
    email = request.session.get('email_login')
    if not email:
        return redirect('login_con_codigo')
    
    if request.method == 'POST':
        codigo_ingresado = request.POST.get('codigo')
        try:
            user = User.objects.get(email=email, is_active=True)
            perfil = PerfilUsuario.objects.get(usuario=user)
            
            if perfil.codigo_verificacion == codigo_ingresado:
                # Limpiar código usado
                perfil.codigo_verificacion = None
                perfil.save()
                
                # Loguear al usuario
                from django.contrib.auth import login
                login(request, user)
                
                messages.success(request, f"¡Bienvenido {user.username}!")
                return redirect('lista_libros')  # O la página principal
            else:
                messages.error(request, "El código es incorrecto.")
        except User.DoesNotExist:
            messages.error(request, "Usuario no encontrado.")
            return redirect('login_con_codigo')
    
    return render(request, 'usuarios/verificar_codigo_login.html')


@require_http_methods(["GET"])
def documento_legal(request, slug):
    documento = DOCUMENTOS_LEGALES.get(slug)
    if not documento:
        return redirect('lista_libros')

    context = {
        'documento_slug': slug,
        'titulo_documento': documento['titulo'],
        'subtitulo_documento': documento['subtitulo'],
    }
    return render(request, documento['template'], context)


@login_required
@require_http_methods(["GET", "POST"])
def mi_perfil_actividad(request):
    perfil, _ = PerfilUsuario.objects.get_or_create(usuario=request.user)

    if request.method == 'POST':
        form = ProfileUpdateForm(request.POST, instance=perfil, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Tu perfil fue actualizado.')
            return redirect('mi_perfil')
        messages.error(request, 'No se pudo actualizar tu perfil. Revisa los datos capturados.')
    else:
        form = ProfileUpdateForm(instance=perfil, user=request.user)

    user = request.user
    if user.is_superuser:
        perfil_tipo = 'admin'
    elif user.is_staff:
        perfil_tipo = 'staff'
    else:
        perfil_tipo = 'cliente'

    avatar_text = (user.get_full_name() or user.username or 'U')[0].upper()
    context = {
        'perfil_form': form,
        'perfil': perfil,
        'perfil_tipo': perfil_tipo,
        'avatar_text': avatar_text,
        'usuario_objetivo': user,
    }

    if perfil_tipo == 'cliente':
        reservas_activas = Reserva.objects.filter(
            usuario=user,
            estado='pendiente'
        ).prefetch_related('libros').order_by('fecha_vencimiento')

        reservas_historial = Reserva.objects.filter(
            usuario=user
        ).exclude(
            estado='pendiente'
        ).prefetch_related('libros').order_by('-fecha_reserva')[:5]

        compras_historial = Venta.objects.filter(
            cliente=user
        ).prefetch_related('detalles__ejemplar__libro').order_by('-fecha_venta')[:5]

        context.update({
            'reservas_activas': reservas_activas,
            'reservas_historial': reservas_historial,
            'compras_historial': compras_historial,
        })

    elif perfil_tipo == 'staff':
        inicio_hoy = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        ventas_hoy = Venta.objects.filter(
            cajero=user,
            fecha_venta__gte=inicio_hoy
        )
        context.update({
            'ventas_hoy_count': ventas_hoy.count(),
            'ventas_hoy_total': ventas_hoy.aggregate(
                total=Coalesce(Sum('total'), Decimal('0.00'))
            )['total'],
        })

    else:
        ahora = timezone.localtime()
        inicio_mes = ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        ventas_mes_qs = Venta.objects.filter(
            fecha_venta__gte=inicio_mes,
            fecha_venta__lte=ahora,
        ).annotate(
            dia=TruncDay('fecha_venta')
        ).values('dia').annotate(
            total=Coalesce(Sum('total'), Decimal('0.00'))
        ).order_by('dia')

        ventas_map = {item['dia'].date(): item['total'] for item in ventas_mes_qs}
        chart_labels = []
        chart_totals = []
        cursor = inicio_mes.date()
        while cursor <= ahora.date():
            chart_labels.append(cursor.strftime('%d %b'))
            chart_totals.append(float(ventas_map.get(cursor, 0)))
            cursor += timedelta(days=1)

        inventario_resumen = Libro.objects.aggregate(
            titulos=Count('id'),
            unidades=Coalesce(Sum('ejemplares__stock'), 0),
            criticos=Count('id', filter=Q(ejemplares__stock__lt=1), distinct=True),
        )

        context.update({
            'chart_labels': chart_labels,
            'chart_totals': chart_totals,
            'ventas_mes_total': Venta.objects.filter(
                fecha_venta__gte=inicio_mes,
                fecha_venta__lte=ahora,
            ).aggregate(
                total=Coalesce(Sum('total'), Decimal('0.00'))
            )['total'],
            'inventario_titulos': inventario_resumen['titulos'],
            'inventario_unidades': inventario_resumen['unidades'],
            'inventario_critico': inventario_resumen['criticos'],
        })

    return render(request, 'usuarios/mi_perfil.html', context)


@login_required
@director_required
@require_http_methods(["GET"])
def panel_personal(request):
    """
    Vista del Director General para gestionar cuentas de staff.
    """
    query = request.GET.get('q', '').strip()

    personal = User.objects.filter(
        Q(is_staff=True) | Q(is_superuser=True)
    ).select_related('perfil').order_by('-is_superuser', '-is_active', 'first_name', 'username')

    if query:
        personal = personal.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query)
        )

    for empleado in personal:
        empleado.rol_panel = 'Director General' if empleado.is_superuser else 'Cajero / Staff'
        empleado.badge_clase = 'director' if empleado.is_superuser else 'staff'

    editar_forms = {
        empleado.id: StaffUpdateForm(instance=empleado.perfil, user=empleado, prefix=f'editar-{empleado.id}')
        for empleado in personal if not empleado.is_superuser
    }
    password_forms = {
        empleado.id: StaffPasswordResetForm(prefix=f'password-{empleado.id}')
        for empleado in personal if not empleado.is_superuser
    }

    context = {
        'personal': personal,
        'query': query,
        'staff_form': StaffCreationForm(),
        'editar_forms': editar_forms,
        'password_forms': password_forms,
        'total_personal': User.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).count(),
        'staff_activo': User.objects.filter(is_staff=True, is_active=True, is_superuser=False).count(),
        'directores': User.objects.filter(is_superuser=True, is_active=True).count(),
        'cuentas_inactivas': User.objects.filter(
            Q(is_staff=True) | Q(is_superuser=True),
            is_active=False
        ).count(),
    }
    return render(request, 'usuarios/panel_personal.html', context)


@login_required
@director_required
@require_http_methods(["GET"])
def panel_auditoria(request):
    query = request.GET.get('q', '').strip()
    accion = request.GET.get('accion', 'todas').strip()
    modulo = request.GET.get('modulo', 'todos').strip()
    limite = obtener_limite_auditoria(request.GET.get('limite'))

    eventos = EventoAuditoria.objects.select_related('actor')

    if query:
        eventos = eventos.filter(
            Q(actor__username__icontains=query) |
            Q(entidad_nombre__icontains=query) |
            Q(descripcion__icontains=query) |
            Q(entidad_tipo__icontains=query)
        )

    if accion != 'todas':
        eventos = eventos.filter(accion=accion)

    if modulo != 'todos':
        eventos = eventos.filter(modulo=modulo)

    eventos = eventos.order_by('-creado_en')[:limite]

    context = {
        'eventos': eventos,
        'query': query,
        'accion_activa': accion,
        'modulo_activo': modulo,
        'limite_activo': limite,
        'limites_auditoria': LIMITES_AUDITORIA,
        'retencion_auditoria_dias': AUDITORIA_RETENCION_DIAS,
        'acciones_auditoria': ACCIONES_AUDITORIA,
        'modulos_auditoria': MODULOS_AUDITORIA,
        'total_eventos': EventoAuditoria.objects.count(),
        'eventos_hoy': EventoAuditoria.objects.filter(
            creado_en__gte=timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        ).count(),
        'usuarios_activos': EventoAuditoria.objects.filter(
            actor__isnull=False
        ).values('actor').distinct().count(),
    }
    return render(request, 'usuarios/panel_auditoria.html', context)


@login_required
@director_required
@require_http_methods(["POST"])
def crear_staff(request):
    admin_password = request.POST.get('admin_password', '')
    if not request.user.check_password(admin_password):
        messages.error(request, 'La contraseña de autorización es incorrecta. No se pudo registrar al empleado.')
        return redirect('panel_personal')

    form = StaffCreationForm(request.POST)
    if form.is_valid():
        rol_seleccionado = request.POST.get('rol_empleado', 'cajero')
        
        user = form.save(commit=False)
        user.is_staff = True
        if rol_seleccionado == 'director':
            user.is_superuser = True
        else:
            user.is_superuser = False
        user.is_active = True
        user.save()

        perfil, _ = PerfilUsuario.objects.get_or_create(usuario=user)
        perfil.rol = rol_seleccionado
        perfil.save()
        registrar_auditoria(
            actor=request.user,
            accion='crear',
            modulo='usuarios',
            entidad_tipo='usuario_staff',
            entidad_id=user.id,
            entidad_nombre=user.username,
            descripcion=f'Se creó la cuenta de {rol_seleccionado} "{user.username}".',
            metadata={'rol': perfil.rol},
        )

        messages.success(request, f'La cuenta de {rol_seleccionado} para "{user.username}" fue creada correctamente.')
    else:
        errores = []
        for field_errors in form.errors.values():
            errores.extend(field_errors)
        messages.error(request, 'No se pudo crear la cuenta: ' + ' '.join(errores))
    return redirect('panel_personal')


@login_required
@director_required
@require_http_methods(["POST"])
def desactivar_personal(request, user_id):
    usuario = get_object_or_404(User, pk=user_id)

    if usuario == request.user:
        messages.error(request, 'No puedes desactivar tu propia cuenta desde este panel.')
        return redirect('panel_personal')

    if usuario.is_superuser:
        messages.error(request, 'No puedes desactivar a otro Director General desde esta pantalla.')
        return redirect('panel_personal')

    usuario.is_active = False
    usuario.save(update_fields=['is_active'])
    registrar_auditoria(
        actor=request.user,
        accion='desactivar',
        modulo='usuarios',
        entidad_tipo='usuario_staff',
        entidad_id=usuario.id,
        entidad_nombre=usuario.username,
        descripcion=f'Se desactivó el acceso de "{usuario.username}".',
    )
    messages.success(request, f'El acceso de "{usuario.username}" fue desactivado.')
    return redirect('panel_personal')


@login_required
@director_required
@require_http_methods(["POST"])
def reactivar_personal(request, user_id):
    usuario = get_object_or_404(User, pk=user_id)

    if usuario.is_superuser:
        messages.error(request, 'No necesitas reactivar una cuenta de Director desde esta pantalla.')
        return redirect('panel_personal')

    usuario.is_active = True
    usuario.is_staff = True
    usuario.save(update_fields=['is_active', 'is_staff'])
    registrar_auditoria(
        actor=request.user,
        accion='reactivar',
        modulo='usuarios',
        entidad_tipo='usuario_staff',
        entidad_id=usuario.id,
        entidad_nombre=usuario.username,
        descripcion=f'Se reactivó la cuenta de "{usuario.username}".',
    )
    messages.success(request, f'La cuenta de "{usuario.username}" fue reactivada.')
    return redirect('panel_personal')


@login_required
@director_required
@require_http_methods(["POST"])
def editar_personal(request, user_id):
    usuario = get_object_or_404(User.objects.select_related('perfil'), pk=user_id)

    if usuario.is_superuser:
        messages.error(request, 'La cuenta del Director no se edita desde este panel.')
        return redirect('panel_personal')

    form = StaffUpdateForm(
        request.POST,
        instance=usuario.perfil,
        user=usuario,
        prefix=f'editar-{usuario.id}'
    )

    if form.is_valid():
        form.save()
        usuario.perfil.rol = 'cajero'
        usuario.perfil.save(update_fields=['rol'])
        registrar_auditoria(
            actor=request.user,
            accion='editar',
            modulo='usuarios',
            entidad_tipo='usuario_staff',
            entidad_id=usuario.id,
            entidad_nombre=usuario.username,
            descripcion=f'Se editaron los datos de "{usuario.username}".',
            metadata={
                'email': usuario.email,
                'telefono': usuario.perfil.telefono,
            },
        )
        messages.success(request, f'Se actualizaron los datos de "{usuario.username}".')
    else:
        errores = []
        for field_errors in form.errors.values():
            errores.extend(field_errors)
        messages.error(request, 'No se pudo actualizar el empleado: ' + ' '.join(errores))
    return redirect('panel_personal')


@login_required
@director_required
@require_http_methods(["POST"])
def resetear_password_personal(request, user_id):
    usuario = get_object_or_404(User, pk=user_id)

    if usuario.is_superuser:
        messages.error(request, 'La contrasena del Director no se modifica desde este panel.')
        return redirect('panel_personal')

    form = StaffPasswordResetForm(request.POST, prefix=f'password-{usuario.id}')
    if form.is_valid():
        usuario.set_password(form.cleaned_data['password1'])
        usuario.save(update_fields=['password'])
        registrar_auditoria(
            actor=request.user,
            accion='seguridad',
            modulo='usuarios',
            entidad_tipo='usuario_staff',
            entidad_id=usuario.id,
            entidad_nombre=usuario.username,
            descripcion=f'Se reseteó la contraseña de "{usuario.username}".',
        )
        messages.success(request, f'Se actualizo la contrasena de "{usuario.username}".')
    else:
        errores = []
        for field_errors in form.errors.values():
            errores.extend(field_errors)
        messages.error(request, 'No se pudo resetear la contrasena: ' + ' '.join(errores))
    return redirect('panel_personal')


@login_required
@cajero_required
@require_http_methods(["GET"])
def panel_clientes(request):
    """
    Vista administrativa para consultar clientes, reservas y compras.
    """
    query = request.GET.get('q', '').strip()
    filtro = request.GET.get('filtro', 'todos').strip()
    page = request.GET.get('page', 1)

    reservas_por_usuario = Reserva.objects.filter(usuario=OuterRef('pk'))
    ventas_por_usuario = Venta.objects.filter(cliente=OuterRef('pk'))

    clientes = User.objects.filter(is_staff=False).select_related('perfil').annotate(
        reservas_totales=Coalesce(
            Subquery(
                reservas_por_usuario.values('usuario')
                .annotate(total=Count('id'))
                .values('total')[:1],
                output_field=IntegerField(),
            ),
            0,
        ),
        reservas_activas=Coalesce(
            Subquery(
                reservas_por_usuario.filter(estado='pendiente')
                .values('usuario')
                .annotate(total=Count('id'))
                .values('total')[:1],
                output_field=IntegerField(),
            ),
            0,
        ),
        compras_totales=Coalesce(
            Subquery(
                ventas_por_usuario.values('cliente')
                .annotate(total=Count('id'))
                .values('total')[:1],
                output_field=IntegerField(),
            ),
            0,
        ),
        gasto_total=Coalesce(
            Subquery(
                ventas_por_usuario.values('cliente')
                .annotate(total=Sum('total'))
                .values('total')[:1],
                output_field=DecimalField(max_digits=10, decimal_places=2),
            ),
            Decimal('0.00'),
        ),
        ultima_reserva=Subquery(
            reservas_por_usuario.order_by('-fecha_reserva').values('fecha_reserva')[:1],
            output_field=DateTimeField(),
        ),
        ultima_compra=Subquery(
            ventas_por_usuario.order_by('-fecha_venta').values('fecha_venta')[:1],
            output_field=DateTimeField(),
        ),
    )

    if query:
        clientes = clientes.filter(
            Q(username__icontains=query) |
            Q(first_name__icontains=query) |
            Q(last_name__icontains=query) |
            Q(email__icontains=query) |
            Q(perfil__telefono__icontains=query)
        )

    if filtro == 'reservando':
        clientes = clientes.filter(reservas_activas__gt=0)
    elif filtro == 'compradores':
        clientes = clientes.filter(compras_totales__gt=0)
    elif filtro == 'sin_movimiento':
        clientes = clientes.filter(reservas_totales=0, compras_totales=0)

    clientes = clientes.order_by('-date_joined', 'username')

    paginator = Paginator(clientes, 9)
    try:
        clientes_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        clientes_page = paginator.page(1)

    clientes_ids = [cliente.id for cliente in clientes_page.object_list]

    reservas_recientes = (
        Reserva.objects.filter(usuario_id__in=clientes_ids)
        .select_related('usuario')
        .prefetch_related('libros')
        .order_by('-fecha_reserva')
    )
    ventas_recientes = (
        Venta.objects.filter(cliente_id__in=clientes_ids)
        .select_related('cliente', 'cajero')
        .prefetch_related('detalles__ejemplar__libro')
        .order_by('-fecha_venta')
    )

    reservas_por_cliente = defaultdict(list)
    for reserva in reservas_recientes:
        if len(reservas_por_cliente[reserva.usuario_id]) < 3:
            reservas_por_cliente[reserva.usuario_id].append(reserva)

    ventas_por_cliente_map = defaultdict(list)
    for venta in ventas_recientes:
        if len(ventas_por_cliente_map[venta.cliente_id]) < 3:
            ventas_por_cliente_map[venta.cliente_id].append(venta)

    for cliente in clientes_page.object_list:
        try:
            cliente.perfil_data = cliente.perfil
        except PerfilUsuario.DoesNotExist:
            cliente.perfil_data = None

        cliente.reservas_recientes = reservas_por_cliente.get(cliente.id, [])
        cliente.compras_recientes = ventas_por_cliente_map.get(cliente.id, [])
        cliente.ultima_actividad = max(
            [fecha for fecha in [cliente.ultima_reserva, cliente.ultima_compra] if fecha],
            default=None,
        )

        if cliente.reservas_activas:
            cliente.estado_panel = 'Reservando'
            cliente.estado_clase = 'warning'
        elif cliente.compras_totales:
            cliente.estado_panel = 'Comprador'
            cliente.estado_clase = 'success'
        else:
            cliente.estado_panel = 'Sin movimiento'
            cliente.estado_clase = 'muted'

    clientes_base = User.objects.filter(is_staff=False)
    context = {
        'clientes_page': clientes_page,
        'query': query,
        'filtro_activo': filtro,
        'total_clientes': clientes_base.count(),
        'clientes_reservando': Reserva.objects.filter(
            estado='pendiente'
        ).values('usuario').distinct().count(),
        'clientes_compradores': Venta.objects.filter(
            cliente__isnull=False
        ).values('cliente').distinct().count(),
        'ingresos_clientes': Venta.objects.filter(
            cliente__isnull=False
        ).aggregate(total=Sum('total'))['total'] or Decimal('0.00'),
    }
    return render(request, 'usuarios/panel_clientes.html', context)


@login_required
@cajero_required
@require_http_methods(["GET", "POST"])
def detalle_cliente(request, user_id):
    cliente = get_object_or_404(
        User.objects.select_related('perfil'),
        pk=user_id,
        is_staff=False,
    )

    if request.method == 'POST':
        nota_form = ClienteNotaInternaForm(request.POST)
        if nota_form.is_valid():
            nota = nota_form.save(commit=False)
            nota.cliente = cliente
            nota.autor = request.user
            nota.save()
            registrar_auditoria(
                actor=request.user,
                accion='crear',
                modulo='clientes',
                entidad_tipo='nota_cliente',
                entidad_id=nota.id,
                entidad_nombre=cliente.username,
                descripcion=f'Se agregó una nota interna al cliente "{cliente.username}".',
                metadata={'cliente_id': cliente.id},
            )
            messages.success(request, 'La nota interna fue registrada.')
            return redirect('detalle_cliente', user_id=cliente.id)
        messages.error(request, 'No se pudo guardar la nota interna.')
    else:
        nota_form = ClienteNotaInternaForm()

    reservas = list(
        Reserva.objects.filter(usuario=cliente)
        .prefetch_related('libros', 'ejemplares')
        .order_by('-fecha_reserva')
    )
    compras = list(
        Venta.objects.filter(cliente=cliente)
        .select_related('cajero')
        .prefetch_related('detalles__ejemplar__libro')
        .order_by('-fecha_venta')
    )
    notas = list(
        NotaClienteInterna.objects.filter(cliente=cliente)
        .select_related('autor')
        .order_by('-creado_en')
    )

    reservas_activas = [reserva for reserva in reservas if reserva.estado == 'pendiente']
    gasto_total = sum((venta.total for venta in compras), Decimal('0.00'))
    ticket_promedio = (gasto_total / len(compras)) if compras else Decimal('0.00')

    timeline = []
    for reserva in reservas:
        titulos = ', '.join(libro.titulo for libro in reserva.libros.all()) or 'Reserva sin titulos asociados'
        timeline.append({
            'tipo': 'reserva',
            'fecha': reserva.fecha_reserva,
            'titulo': reserva.codigo_ticket,
            'subtitulo': reserva.get_estado_display(),
            'descripcion': titulos,
            'monto': reserva.total,
            'meta': (
                f"Vence {timezone.localtime(reserva.fecha_vencimiento).strftime('%d/%m/%Y %H:%M')}"
                if reserva.estado == 'pendiente'
                else timezone.localtime(reserva.fecha_reserva).strftime('%d/%m/%Y %H:%M')
            ),
        })

    for venta in compras:
        titulos = ', '.join(detalle.ejemplar.libro.titulo for detalle in venta.detalles.all()) or 'Compra sin detalle'
        timeline.append({
            'tipo': 'compra',
            'fecha': venta.fecha_venta,
            'titulo': f'Ticket #{venta.id}',
            'subtitulo': venta.get_metodo_pago_display(),
            'descripcion': titulos,
            'monto': venta.total,
            'meta': f'Cajero: {venta.cajero.username}' if venta.cajero else 'Sin cajero registrado',
        })

    for nota in notas:
        timeline.append({
            'tipo': 'nota',
            'fecha': nota.creado_en,
            'titulo': 'Nota interna',
            'subtitulo': nota.autor.get_full_name() or nota.autor.username if nota.autor else 'Sistema',
            'descripcion': nota.contenido,
            'monto': None,
            'meta': 'Seguimiento administrativo',
        })

    timeline.sort(key=lambda evento: evento['fecha'], reverse=True)

    perfil = getattr(cliente, 'perfil', None)
    ultima_actividad = timeline[0]['fecha'] if timeline else None

    context = {
        'cliente': cliente,
        'perfil_cliente': perfil,
        'nota_form': nota_form,
        'notas': notas,
        'reservas': reservas,
        'reservas_activas': reservas_activas,
        'compras': compras,
        'timeline': timeline[:20],
        'gasto_total': gasto_total,
        'ticket_promedio': ticket_promedio.quantize(Decimal('0.01')) if compras else Decimal('0.00'),
        'ultima_actividad': ultima_actividad,
        'valor_reservado': sum((reserva.total for reserva in reservas_activas), Decimal('0.00')),
    }
    return render(request, 'usuarios/detalle_cliente.html', context)
