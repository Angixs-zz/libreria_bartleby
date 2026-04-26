"""
Vistas de inventario y administración de la Librería Bartleby.

Funcionalidades:
- Agregar libros y ejemplares
- Gestión del inventario
- Punto de venta (POS) con descáner
- API AJAX para búsquedas

Protecciones:
- @staff_member_required: solo administradores
- @ensure_csrf_cookie: inyecta token CSRF
- Validación centralizada de precios y cantidad
"""

import json
from decimal import Decimal

from django.db.models.deletion import ProtectedError

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import ensure_csrf_cookie

from inventario.models import Libro, Ejemplar, Categoria, EstadoFisico
from reservas.models import Reserva
from ventas.models import Venta
from services.inventario_service import InventarioService
from utils.helpers import (
    validar_precio,
    validar_isbn,
    validar_cantidad,
    buscar_por_isbn,
    generar_sku_mejorado
)
from decorators import admin_required, api_ajax_required, rate_limit_por_usuario, json_response_handler
from usuarios.auditoria import registrar_auditoria


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE LIBROS Y EJEMPLARES (ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

@staff_member_required
@require_http_methods(["GET", "POST"])
def agregar_libro(request):
    """
    Admin puede agregar libros nuevos o ejemplares a libros existentes.
    
    Acciones:
    1. crear_todo: Libro nuevo + Ejemplar
    2. nuevo_ejemplar: Ejemplar a libro existente
    3. sumar_stock: Aumentar stock de ejemplar
    
    Validaciones:
    - Precio mayor a 0
    - ISBN formato válido (opcional)
    - Stock positivo
    """
    if request.method == 'POST':
        accion = request.POST.get('accion', '').strip()

        try:
            # ─── ACCIÓN: Crear libro + ejemplar nuevo ───────────────────────
            if accion == 'crear_todo':
                titulo = request.POST.get('titulo', '').strip()
                autor = request.POST.get('autor', '').strip()
                isbn = request.POST.get('isbn', '').strip()
                editorial = request.POST.get('editorial', '').strip()
                descripcion = request.POST.get('descripcion', '').strip()
                portada = request.FILES.get('portada')
                nombre_categoria = request.POST.get('categoria_texto', '').strip()
                estado_fisico_select = request.POST.get('estado_fisico_select', '').strip()
                estado_fisico_texto = request.POST.get('estado_fisico_texto', '').strip()
                estado_final = estado_fisico_texto if estado_fisico_select == '__nuevo__' else estado_fisico_select
                if not estado_final: estado_final = 'Nuevo'
                precio_venta_str = request.POST.get('precio_venta', '')
                precio_compra_str = request.POST.get('precio_compra', '0')
                stock_str = request.POST.get('stock', '1')

                # Validaciones
                if not titulo or not autor:
                    messages.error(request, '❌ Título y autor son requeridos.')
                    return redirect('agregar_libro')

                # Validar ISBN si se proporciona
                if isbn and not validar_isbn(isbn):
                    messages.error(request, '❌ Formato ISBN inválido.')
                    return redirect('agregar_libro')

                # Validar precios
                precio_venta, error = validar_precio(precio_venta_str)
                if error:
                    messages.error(request, f'❌ Precio venta: {error}')
                    return redirect('agregar_libro')

                precio_compra, error = validar_precio(precio_compra_str)
                if error:
                    precio_compra = Decimal('0.00')

                # Validar stock
                stock, error = validar_cantidad(stock_str)
                if error:
                    messages.error(request, f'❌ Stock: {error}')
                    return redirect('agregar_libro')

                # Crear categoría si no existe
                categoria_obj = None
                if nombre_categoria:
                    categoria_obj, _ = Categoria.objects.get_or_create(
                        nombre=nombre_categoria.capitalize()
                    )

                # Crear libro
                libro_obj = Libro.objects.create(
                    titulo=titulo,
                    autor=autor,
                    isbn=isbn if isbn else None,
                    editorial=editorial if editorial else None,
                    categoria=categoria_obj,
                    descripcion=descripcion if descripcion else None,
                    portada=portada if portada else None
                )

                estado_fisico_obj = EstadoFisico.objects.filter(nombre__iexact=estado_final).first()
                if not estado_fisico_obj:
                    estado_fisico_obj = EstadoFisico.objects.create(nombre=estado_final.capitalize())

                # Crear ejemplar
                Ejemplar.objects.create(
                    # El SKU se asigna automáticamente en el modelo.
                    libro=libro_obj,
                    estado_fisico=estado_fisico_obj,
                    precio_compra=precio_compra,
                    precio_venta=precio_venta,
                    stock=stock
                )
                primer_ejemplar = libro_obj.ejemplares.order_by('-creado_en').first()
                registrar_auditoria(
                    actor=request.user,
                    accion='crear',
                    modulo='inventario',
                    entidad_tipo='libro',
                    entidad_id=libro_obj.id,
                    entidad_nombre=libro_obj.titulo,
                    descripcion=f'Se registró el libro "{libro_obj.titulo}" con su primer ejemplar.',
                    metadata={'ejemplar_id': primer_ejemplar.id if primer_ejemplar else None},
                )

                messages.success(
                    request,
                    f'✅ "{titulo}" registrado con su primer ejemplar (SKU: {generar_sku_mejorado()}).'
                )
                return redirect('agregar_libro')

            # ─── ACCIÓN: Nuevo ejemplar a libro existente ────────────────────
            elif accion == 'nuevo_ejemplar':
                libro_id = request.POST.get('libro_id')
                libro_obj = get_object_or_404(Libro, id=libro_id)
                estado_fisico_select = request.POST.get('estado_fisico_select', '').strip()
                estado_fisico_texto = request.POST.get('estado_fisico_texto', '').strip()
                estado_final = estado_fisico_texto if estado_fisico_select == '__nuevo__' else estado_fisico_select
                if not estado_final: estado_final = 'Nuevo'
                precio_venta_str = request.POST.get('precio_venta', '')
                precio_compra_str = request.POST.get('precio_compra', '0')
                stock_str = request.POST.get('stock', '1')
                portada = request.FILES.get('portada')

                # Validaciones
                precio_venta, error = validar_precio(precio_venta_str)
                if error:
                    messages.error(request, f'❌ Precio venta: {error}')
                    return redirect('agregar_libro')

                precio_compra, _ = validar_precio(precio_compra_str)
                if not precio_compra:
                    precio_compra = Decimal('0.00')

                stock, error = validar_cantidad(stock_str)
                if error:
                    messages.error(request, f'❌ Stock: {error}')
                    return redirect('agregar_libro')

                estado_fisico_obj = EstadoFisico.objects.filter(nombre__iexact=estado_final).first()
                if not estado_fisico_obj:
                    estado_fisico_obj = EstadoFisico.objects.create(nombre=estado_final.capitalize())

                # Crear ejemplar
                Ejemplar.objects.create(
                    libro=libro_obj,
                    estado_fisico=estado_fisico_obj,
                    precio_compra=precio_compra,
                    precio_venta=precio_venta,
                    stock=stock
                )
                nuevo_ejemplar = libro_obj.ejemplares.order_by('-creado_en').first()

                if portada:
                    libro_obj.portada = portada
                    libro_obj.save()
                registrar_auditoria(
                    actor=request.user,
                    accion='crear',
                    modulo='inventario',
                    entidad_tipo='ejemplar',
                    entidad_id=nuevo_ejemplar.id if nuevo_ejemplar else None,
                    entidad_nombre=nuevo_ejemplar.sku if nuevo_ejemplar else libro_obj.titulo,
                    descripcion=f'Se añadió un nuevo ejemplar a "{libro_obj.titulo}".',
                    metadata={'libro_id': libro_obj.id, 'stock': stock},
                )

                messages.success(
                    request,
                    f'✅ Nuevo ejemplar añadido a "{libro_obj.titulo}".'
                )
                return redirect('agregar_libro')

            # ─── ACCIÓN: Aumentar stock ──────────────────────────────────────
            elif accion == 'sumar_stock':
                ejemplar_id = request.POST.get('ejemplar_id')
                cantidad_str = request.POST.get('cantidad', '1')
                
                ejemplar = get_object_or_404(Ejemplar, id=ejemplar_id)
                
                cantidad, error = validar_cantidad(cantidad_str)
                if error:
                    messages.error(request, f'❌ Cantidad: {error}')
                    return redirect('agregar_libro')

                ejemplar.stock += cantidad
                ejemplar.save()
                registrar_auditoria(
                    actor=request.user,
                    accion='editar',
                    modulo='inventario',
                    entidad_tipo='ejemplar',
                    entidad_id=ejemplar.id,
                    entidad_nombre=ejemplar.sku,
                    descripcion=f'Se incrementó el stock del ejemplar {ejemplar.sku}.',
                    metadata={'cantidad_agregada': cantidad, 'stock_resultante': ejemplar.stock},
                )
                
                messages.success(
                    request,
                    f'✅ +{cantidad} unidades al {ejemplar.sku}. '
                    f'Stock actual: {ejemplar.stock}'
                )
                return redirect('agregar_libro')

        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return redirect('agregar_libro')

    categorias = Categoria.objects.all()
    estados_fisicos = EstadoFisico.objects.all()
    return render(
        request,
        'inventario/agregar_libro.html',
        {'categorias': categorias, 'estados_fisicos': estados_fisicos}
    )


@staff_member_required
@require_http_methods(["GET"])
@json_response_handler
def buscar_libro_ajax(request):
    """
    Búsqueda AJAX de libros mientras escribe.
    
    Busca por:
    - ISBN exacto o normalizado
    - Título (substring)
    
    Returns JSON con lista de libros y sus ejemplares.
    """
    titulo = request.GET.get('titulo', '').strip()
    isbn = request.GET.get('isbn', '').strip()
    resultados = []

    libros = []
    
    # Prioridad: ISBN exacto
    if isbn:
        libros = Libro.objects.filter(isbn=isbn)[:1]
        if not libros:
            isbn_limpio = isbn.replace('-', '').replace(' ', '')
            libros = Libro.objects.filter(isbn__icontains=isbn_limpio)[:1]
    
    # Si no by ISBN, buscar por título
    elif len(titulo) >= 2:
        libros = Libro.objects.filter(
            titulo__icontains=titulo
        ).select_related('categoria')[:8]

    for libro in libros:
        ejemplares = []
        for e in libro.ejemplares.all():
            ejemplares.append({
                'id': e.id,
                'sku': e.sku,
                'estado': e.estado_fisico.nombre if e.estado_fisico else 'Sin estado',
                'precio_venta': str(e.precio_venta),
                'stock': e.stock,
            })
        resultados.append({
            'id': libro.id,
            'titulo': libro.titulo,
            'autor': libro.autor,
            'isbn': libro.isbn or '',
            'editorial': libro.editorial or '',
            'ejemplares': ejemplares,
        })

    return JsonResponse({'libros': resultados})


@staff_member_required
@require_http_methods(["GET", "POST"])
def gestion_inventario(request):
    """
    Panel de gestión del inventario (admin).
    
    Muestra:
    - Todos los ejemplares con stock
    - Estadísticas rápidas
    - Ejemplares agotados
    - Reservas pendientes
    """
    ejemplares = Ejemplar.objects.select_related('libro').order_by('-creado_en')
    
    # Estadísticas
    total_ejemplares = ejemplares.count()
    agotados = ejemplares.filter(stock=0).count()
    reservas_pendientes = Reserva.objects.filter(estado='pendiente').count()

    context = {
        'ejemplares': ejemplares,
        'total_ejemplares': total_ejemplares,
        'agotados': agotados,
        'reservas_pendientes': reservas_pendientes,
    }
    return render(request, 'gestion_inventario.html', context)


@staff_member_required
@require_http_methods(["GET", "POST"])
def detalle_ejemplar(request, ejemplar_id):
    """
    Pagina dedicada de un ejemplar para el administrador.

    GET:  Muestra todos los datos del ejemplar y formulario de edicion.
    POST: Guarda los cambios (precio, stock, estado fisico, descripcion, portada).
    """
    ejemplar = get_object_or_404(
        Ejemplar.objects.select_related('libro', 'libro__categoria'),
        id=ejemplar_id
    )

    if request.method == 'POST':
        try:
            cambios = []

            estado_fisico_select = request.POST.get('estado_fisico_select', '').strip()
            estado_fisico_texto = request.POST.get('estado_fisico_texto', '').strip()
            estado_final = estado_fisico_texto if estado_fisico_select == '__nuevo__' else estado_fisico_select

            descripcion_estado = request.POST.get('descripcion_estado', '').strip()
            precio_venta_str = request.POST.get('precio_venta', '')
            precio_compra_str = request.POST.get('precio_compra', '')
            stock_str = request.POST.get('stock', '')

            if estado_final and estado_final.lower() != (ejemplar.estado_fisico.nombre.lower() if ejemplar.estado_fisico else ''):
                cambios.append('estado fisico actualizado')
                estado_fisico_obj = EstadoFisico.objects.filter(nombre__iexact=estado_final).first()
                if not estado_fisico_obj:
                    estado_fisico_obj = EstadoFisico.objects.create(nombre=estado_final.capitalize())
                ejemplar.estado_fisico = estado_fisico_obj

            if descripcion_estado != (ejemplar.descripcion_estado or ''):
                cambios.append('descripcion de estado actualizada')
                ejemplar.descripcion_estado = descripcion_estado or None

            if precio_venta_str:
                precio_venta, error = validar_precio(precio_venta_str)
                if error:
                    messages.error(request, '❌ Precio venta: ' + error)
                    return redirect('detalle_ejemplar', ejemplar_id=ejemplar_id)
                if precio_venta != ejemplar.precio_venta:
                    cambios.append('precio venta actualizado')
                    ejemplar.precio_venta = precio_venta

            if precio_compra_str:
                precio_compra, error = validar_precio(precio_compra_str)
                if not error and precio_compra != ejemplar.precio_compra:
                    cambios.append('precio compra actualizado')
                    ejemplar.precio_compra = precio_compra

            if stock_str:
                stock, error = validar_cantidad(stock_str)
                if error:
                    messages.error(request, '❌ Stock: ' + error)
                    return redirect('detalle_ejemplar', ejemplar_id=ejemplar_id)
                if stock != ejemplar.stock:
                    cambios.append('stock actualizado')
                    ejemplar.stock = stock

            ejemplar.save()

            libro = ejemplar.libro
            titulo = request.POST.get('titulo', '').strip()
            autor = request.POST.get('autor', '').strip()
            isbn = request.POST.get('isbn', '').strip()
            editorial = request.POST.get('editorial', '').strip()
            descripcion_libro = request.POST.get('descripcion', '').strip()
            portada = request.FILES.get('portada')
            categoria_texto = request.POST.get('categoria_texto', '').strip()

            if titulo and titulo != libro.titulo:
                cambios.append('titulo actualizado')
                libro.titulo = titulo
            if autor and autor != libro.autor:
                cambios.append('autor actualizado')
                libro.autor = autor
            if isbn and isbn != (libro.isbn or ''):
                if not validar_isbn(isbn):
                    messages.error(request, '❌ Formato ISBN invalido.')
                    return redirect('detalle_ejemplar', ejemplar_id=ejemplar_id)
                cambios.append('ISBN actualizado')
                libro.isbn = isbn
            if editorial != (libro.editorial or ''):
                libro.editorial = editorial or None
            if descripcion_libro != (libro.descripcion or ''):
                libro.descripcion = descripcion_libro or None
            if portada:
                libro.portada = portada
                cambios.append('portada actualizada')
            if categoria_texto:
                cat, _ = Categoria.objects.get_or_create(nombre=categoria_texto.capitalize())
                if cat != libro.categoria:
                    cambios.append('categoria actualizada')
                    libro.categoria = cat

            libro.save()

            if cambios:
                registrar_auditoria(
                    actor=request.user,
                    accion='editar',
                    modulo='inventario',
                    entidad_tipo='ejemplar',
                    entidad_id=ejemplar.id,
                    entidad_nombre=ejemplar.sku,
                    descripcion='Ejemplar ' + ejemplar.sku + ' editado desde panel detalle.',
                    metadata={'cambios': cambios},
                )
                messages.success(request, '✅ Ejemplar ' + ejemplar.sku + ' actualizado correctamente.')
            else:
                messages.info(request, '📌 No se detectaron cambios.')

            return redirect('detalle_ejemplar', ejemplar_id=ejemplar_id)

        except Exception as e:
            messages.error(request, '❌ Error al guardar: ' + str(e))
            return redirect('detalle_ejemplar', ejemplar_id=ejemplar_id)

    try:
        reservas_qs = Reserva.objects.filter(
            ejemplares=ejemplar
        ).select_related('usuario').order_by('-fecha_reserva')[:10]
    except Exception:
        reservas_qs = []

    categorias = Categoria.objects.all()
    estados_fisicos = EstadoFisico.objects.all()

    return render(request, 'inventario/detalle_ejemplar.html', {
        'ejemplar': ejemplar,
        'reservas': reservas_qs,
        'categorias': categorias,
        'estados_fisicos': estados_fisicos,
    })


@staff_member_required
@require_http_methods(["POST"])
def eliminar_ejemplar(request, ejemplar_id):
    """
    Elimina un ejemplar del inventario.

    ⚠️ Si el ejemplar está referenciado en ventas (DetalleVenta con
    on_delete=PROTECT), se captura el ProtectedError y se muestra un
    mensaje de error amigable en lugar de un crash 500.
    """
    ejemplar = get_object_or_404(Ejemplar, id=ejemplar_id)
    sku = ejemplar.sku
    titulo = ejemplar.libro.titulo
    entidad_id = ejemplar.id

    try:
        ejemplar.delete()
    except ProtectedError:
        messages.error(
            request,
            f'❌ No se puede eliminar el ejemplar {sku} porque está '
            f'asociado a una o más ventas registradas. '
            f'Si ya no deseas mostrarlo, puedes poner su stock en 0.'
        )
        return redirect('gestion_inventario')

    registrar_auditoria(
        actor=request.user,
        accion='eliminar',
        modulo='inventario',
        entidad_tipo='ejemplar',
        entidad_id=entidad_id,
        entidad_nombre=sku,
        descripcion=f'Se eliminó el ejemplar {sku} de "{titulo}".',
    )

    messages.success(
        request,
        f'✅ Ejemplar {sku} de "{titulo}" eliminado.'
    )
    return redirect('gestion_inventario')


# ─────────────────────────────────────────────────────────────────────────────
# PUNTO DE VENTA (POS)
# ─────────────────────────────────────────────────────────────────────────────

@staff_member_required
@ensure_csrf_cookie
@require_http_methods(["GET"])
def punto_de_venta(request):
    """
    Carga la pantalla del Punto de Venta.
    
    @ensure_csrf_cookie: Inyecta token CSRF en el template para AJAX.
    """
    return render(request, 'pos.html')


@staff_member_required
@rate_limit_por_usuario('30/m')
@require_http_methods(["GET"])
@json_response_handler
def api_buscar_codigo(request):
    """
    Búsqueda por escáner (SKU o ISBN) en el POS.

    Prioridad:
    1. SKU exacto
    2. ISBN + estado 'nuevo' + stock > 0
    3. ISBN + cualquier estado + stock > 0

    Rate limit: 30 por minuto por usuario

    Retorna:
    - Datos del ejemplar (id, título, precio, stock)
    - Portada del libro
    """
    codigo = request.GET.get('codigo', '').strip()

    if not codigo:
        raise ValueError('Código requerido')

    # 1. Buscar por SKU primero (coincidencia exacta)
    ejemplar = Ejemplar.objects.filter(
        sku=codigo
    ).select_related('libro').first()

    # 2. Buscar por ISBN: priorizar estado 'nuevo' con stock
    if not ejemplar:
        ejemplar = Ejemplar.objects.filter(
            libro__isbn=codigo,
            estado_fisico__nombre__iexact='nuevo',
            stock__gt=0
        ).select_related('libro').first()

    # 3. Si no hay 'nuevo', tomar cualquier ejemplar con ese ISBN y stock > 0
    if not ejemplar:
        ejemplar = Ejemplar.objects.filter(
            libro__isbn=codigo,
            stock__gt=0
        ).select_related('libro').first()

    if not ejemplar:
        raise ValueError('Libro no encontrado o sin stock')

    if ejemplar.stock == 0:
        raise ValueError(f'"{ejemplar.libro.titulo}" está agotado')

    return JsonResponse({
        'id': ejemplar.id,
        'titulo': ejemplar.libro.titulo,
        'autor': ejemplar.libro.autor,
        'sku': ejemplar.sku,
        'precio': float(ejemplar.precio_venta),
        'stock': ejemplar.stock,
        'portada': ejemplar.libro.portada.url if ejemplar.libro.portada else None,
    })


@staff_member_required
@require_http_methods(["POST"])
@json_response_handler
def api_procesar_venta(request):
    """
    Procesa una venta en el POS.
    
    Body JSON:
    {
        "carrito": [
            {"id": 1, "cantidad": 1, "subtotal": 15.99},
            ...
        ],
        "metodo_pago": "efectivo"
    }
    
    Operación atómica:
    - Valida stock
    - Crea Venta y DetalleVenta
    - Descuenta stock automáticamente
    """
    try:
        data = json.loads(request.body)
        carrito = data.get('carrito', [])
        metodo_pago = data.get('metodo_pago', 'efectivo').lower()

        if not carrito:
            raise ValueError('Carrito vacío')

        if metodo_pago not in ['efectivo', 'tarjeta', 'transferencia']:
            raise ValueError('Método de pago inválido')

        # Extraer IDs
        ejemplar_ids = [item['id'] for item in carrito]

        # Usar servicio para venta atómica
        venta = InventarioService.confirmar_venta(
            ejemplar_ids,
            metodo_pago,
            request.user
        )
        registrar_auditoria(
            actor=request.user,
            accion='crear',
            modulo='ventas',
            entidad_tipo='venta',
            entidad_id=venta.id,
            entidad_nombre=f'Ticket #{venta.id}',
            descripcion=f'Se registró la venta #{venta.id} por {request.user.username}.',
            metadata={
                'metodo_pago': metodo_pago,
                'cliente_id': venta.cliente_id,
                'total': str(venta.total),
            },
        )

        return JsonResponse({
            'success': True,
            'venta_id': venta.id,
            'total': float(venta.total),
            'mensaje': f'✅ Venta #{venta.id} completada'
        })

    except ValueError as e:
        raise
    except Exception as e:
        raise Exception(f'Error al procesar venta: {str(e)}')
