"""
Vistas del catálogo de la Librería Bartleby.

Funcionalidades:
- Listado y búsqueda de libros
- Carrito de compras (basado en sesión, con cantidades)
- Reservas atómicas con servicios centralizados
- Búsqueda de ISBN en Google Books API
"""

import requests
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponseRedirect, JsonResponse
from urllib.parse import urlparse
from django.contrib import messages
from django.db.models import Q, Count, Prefetch
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from inventario.models import Ejemplar, Categoria
from reservas.models import Reserva
from services.inventario_service import InventarioService
from usuarios.auditoria import registrar_auditoria
from utils.helpers import buscar_por_isbn, validar_isbn
from decorators import rate_limit_por_ip, api_ajax_required


@require_http_methods(["GET"])
def conocenos(request):
    """
    Página institucional para presentar el proyecto Bartleby.
    """
    return render(request, 'catalogo/conocenos.html')


@require_http_methods(["GET"])
def lista_libros(request):
    """
    Listado filtrable de libros disponibles.

    Filtros:
    - q: búsqueda por título, autor, descripción, ISBN
    - genero: categoría
    - precio_max: precio máximo

    Optimizaciones:
    - select_related para evitar N+1 queries
    - prefetch_related para reservas
    - paginación de 20 por página
    """
    query = request.GET.get('q', '').strip()
    categoria_id = request.GET.get('genero', '')
    precio_min = request.GET.get('precio_min', '')
    precio_max = request.GET.get('precio_max', '')
    page = request.GET.get('page', 1)

    # Base query con optimizaciones
    ejemplares = Ejemplar.objects.select_related(
        'libro',
        'libro__categoria'
    ).filter(stock__gt=0).distinct()

    # Filtro de búsqueda
    if query:
        ejemplares = ejemplares.filter(
            Q(libro__titulo__icontains=query) |
            Q(libro__autor__icontains=query) |
            Q(libro__descripcion__icontains=query) |
            Q(libro__isbn__icontains=query)
        )

    # Filtro de categoría
    if categoria_id and categoria_id.isdigit():
        ejemplares = ejemplares.filter(libro__categoria_id=categoria_id)

    # Filtros de precio
    if precio_min:
        try:
            ejemplares = ejemplares.filter(precio_venta__gte=float(precio_min))
        except (ValueError, TypeError):
            pass

    if precio_max:
        try:
            ejemplares = ejemplares.filter(precio_venta__lte=float(precio_max))
        except (ValueError, TypeError):
            pass

    # Prefetch de reservas activas para stock_disponible
    reservas_activas = Reserva.objects.filter(
        estado='pendiente',
        fecha_vencimiento__gt=timezone.now()
    )

    ejemplares = ejemplares.prefetch_related(
        Prefetch('reservas_activas', queryset=reservas_activas, to_attr='activas_precargadas')
    )

    # Paginación
    paginator = Paginator(ejemplares, 10)
    try:
        ejemplares_page = paginator.page(page)
    except (PageNotAnInteger, EmptyPage):
        ejemplares_page = paginator.page(1)

    # Determinar si un ejemplar está totalmente agotado por reservas
    ejemplares_reservados = {}
    for ejemplar in ejemplares_page:
        activas = ejemplar.activas_precargadas
        reservados_count = len(activas)
        if reservados_count >= ejemplar.stock and activas:
            vencimiento_mas_cercano = min(r.fecha_vencimiento for r in activas)
            ejemplares_reservados[ejemplar.id] = vencimiento_mas_cercano.isoformat()

    categorias = Categoria.objects.all()

    return render(request, 'catalogo/lista_libros.html', {
        'ejemplares': ejemplares_page,
        'categorias': categorias,
        'query': query,
        'genero_seleccionado': int(categoria_id) if categoria_id.isdigit() else '',
        'precio_min_seleccionado': precio_min,
        'precio_max_seleccionado': precio_max,
        'paginator': paginator,
        'ejemplares_reservados': ejemplares_reservados,
    })


@require_http_methods(["GET"])
def detalle_libro(request, pk):
    """
    Detalle de un ejemplar específico.

    Muestra:
    - Información del libro
    - Disponibilidad real (stock - reservas)
    - Estado físico y precio
    """
    ejemplar = get_object_or_404(
        Ejemplar.objects.select_related('libro', 'libro__categoria'),
        pk=pk
    )

    return render(request, 'catalogo/detalle_libro.html', {'ejemplar': ejemplar})


# ─── Helpers internos del carrito ──────────────────────────────────────────────

def _carrito_normalizado(session):
    """
    Devuelve el carrito de sesión como dict {str(id): int(cantidad)}.
    Migra automáticamente el formato antiguo (lista) al nuevo (dict).
    """
    carrito = session.get('carrito', {})
    if isinstance(carrito, list):
        carrito = {k: 1 for k in carrito}
    return carrito


def _redirigir_seguro(request, fallback='lista_libros'):
    """Redirige a la URL anterior si es del mismo origen, o al fallback."""
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or fallback
    parsed = urlparse(next_url)
    if parsed.netloc and parsed.netloc != request.get_host():
        return redirect(fallback)
    return HttpResponseRedirect(next_url)


# ──────────────────────────────────────────────────────────────────────────────

@require_http_methods(["POST"])
def agregar_al_carrito(request, ejemplar_id):
    """
    Agrega un ejemplar al carrito de sesión con la cantidad indicada.

    El carrito se almacena en sesión como dict {str(ejemplar_id): cantidad}.
    Un usuario puede pedir varias unidades del mismo lote siempre que
    no supere el stock disponible ni el límite global de la reserva.
    """
    if not request.user.is_authenticated:
        messages.warning(
            request,
            '🔐 Únete al Archivo Bartleby para apartar libros. '
            'Por favor, regístrate o inicia sesión.'
        )
        return redirect('login')

    # Cantidad solicitada (mín. 1)
    try:
        cantidad_nueva = max(1, int(request.POST.get('cantidad', 1)))
    except (ValueError, TypeError):
        cantidad_nueva = 1

    # Verificar que el ejemplar existe
    try:
        ejemplar = Ejemplar.objects.get(id=ejemplar_id)
    except Ejemplar.DoesNotExist:
        messages.error(request, 'Ejemplar no encontrado.')
        return redirect('lista_libros')

    stock_libre = InventarioService.get_stock_disponible(ejemplar_id)
    if stock_libre <= 0:
        messages.error(request, f'"{ejemplar.libro.titulo}" está agotado.')
        return redirect('lista_libros')

    carrito = _carrito_normalizado(request.session)
    ejemplar_id_str = str(ejemplar_id)
    cantidad_actual = carrito.get(ejemplar_id_str, 0)
    cantidad_total = cantidad_actual + cantidad_nueva

    # No superar el stock disponible
    if cantidad_total > stock_libre:
        if cantidad_actual == 0:
            messages.error(
                request,
                f'❌ Solo hay {stock_libre} unidad(es) disponibles de "{ejemplar.libro.titulo}".'
            )
        else:
            messages.warning(
                request,
                f'⚠️ Ya tienes {cantidad_actual} en tu bolsa y solo hay '
                f'{stock_libre} disponibles. No se añadieron más.'
            )
        return _redirigir_seguro(request)

    # Límite global de la reserva
    total_unidades = sum(carrito.values()) - cantidad_actual + cantidad_total
    if total_unidades > InventarioService.MAX_EJEMPLARES_POR_RESERVA:
        messages.warning(
            request,
            f'⚠️ Máximo {InventarioService.MAX_EJEMPLARES_POR_RESERVA} '
            f'ejemplares por reserva. Ve a tu carrito para confirmar.'
        )
        return _redirigir_seguro(request)

    carrito[ejemplar_id_str] = cantidad_total
    request.session['carrito'] = carrito
    request.session.modified = True

    if cantidad_actual == 0:
        messages.success(request, f'✅ "{ejemplar.libro.titulo}" añadido a tu bolsa ({cantidad_total}x).')
    else:
        messages.success(request, f'✅ "{ejemplar.libro.titulo}" actualizado en tu bolsa ({cantidad_total}x).')

    return _redirigir_seguro(request)


@require_http_methods(["GET"])
def ver_carrito(request):
    """
    Muestra el carrito de sesión del usuario.

    El carrito en sesión es dict {str(ejemplar_id): cantidad}.
    Se pasa al template una lista de dicts con el ejemplar y su cantidad.
    """
    carrito = _carrito_normalizado(request.session)
    if isinstance(request.session.get('carrito'), list):
        request.session['carrito'] = carrito

    if not carrito:
        items = []
        total = 0.00
        total_unidades = 0
    else:
        ejemplares_qs = Ejemplar.objects.filter(
            id__in=[int(k) for k in carrito.keys()]
        ).select_related('libro')
        items = [
            {
                'ejemplar': e,
                'cantidad': carrito[str(e.id)],
                'subtotal': e.precio_venta * carrito[str(e.id)],
                'stock_disponible': InventarioService.get_stock_disponible(e.id),
            }
            for e in ejemplares_qs
        ]
        total = sum(i['subtotal'] for i in items)
        total_unidades = sum(i['cantidad'] for i in items)

    return render(request, 'catalogo/carrito.html', {
        'items': items,
        'total': total,
        'total_unidades': total_unidades,
    })


@require_http_methods(["POST"])
def quitar_del_carrito(request, ejemplar_id):
    """
    Quita completamente un ejemplar del carrito.
    """
    carrito = _carrito_normalizado(request.session)
    ejemplar_id_str = str(ejemplar_id)

    if ejemplar_id_str in carrito:
        del carrito[ejemplar_id_str]
        request.session['carrito'] = carrito
        request.session.modified = True
        messages.success(request, '✅ Ejemplar eliminado de la bolsa.')

    return redirect('ver_carrito')


@require_http_methods(["POST"])
def confirmar_reserva(request):
    """
    Confirma la reserva del carrito actual.

    El carrito es dict {str(ejemplar_id): cantidad}.
    Se expande en una lista de IDs repetidos para que el servicio
    registre tantos registros en la M2M como unidades reservadas.

    Errors:
    - 401: No autenticado
    - 400: Carrito vacío
    - 409: Stock insuficiente
    """
    if not request.user.is_authenticated:
        messages.error(request, "🔐 Necesitas iniciar sesión para confirmar tu apartado.")
        return redirect('login')

    carrito = _carrito_normalizado(request.session)

    if not carrito:
        messages.error(request, "📦 Tu bolsa está vacía.")
        return redirect('lista_libros')

    # Expandir a lista de IDs repetidos: {5: 3} → [5, 5, 5]
    ejemplar_ids_expandidos = []
    for id_str, cant in carrito.items():
        ejemplar_ids_expandidos.extend([int(id_str)] * cant)

    try:
        reserva = InventarioService.reservar_multiples(
            request.user,
            ejemplar_ids_expandidos
        )
        registrar_auditoria(
            actor=request.user,
            accion='crear',
            modulo='reservas',
            entidad_tipo='reserva',
            entidad_id=reserva.id,
            entidad_nombre=reserva.codigo_ticket,
            descripcion=f'El cliente "{request.user.username}" confirmó la reserva {reserva.codigo_ticket}.',
            metadata={'total': str(reserva.total)},
        )

        del request.session['carrito']
        request.session.modified = True

        messages.success(
            request,
            f"✅ ¡Reserva #{reserva.id} confirmada! "
            f"Tienes 72 horas para recoger tus libros. "
            f"Total: ${reserva.total}"
        )
        return redirect('mis_reservas')

    except ValueError as e:
        messages.error(request, f"❌ {str(e)}")
        return redirect('ver_carrito')
    except Exception as e:
        messages.error(request, f"❌ Error al confirmar: {str(e)}")
        return redirect('ver_carrito')


@rate_limit_por_ip('20/h')
@require_http_methods(["GET"])
@api_ajax_required
def buscar_isbn(request):
    """
    Busca información de un libro en Google Books API por ISBN.

    Rate limit: 20 por hora por IP
    Requiere: header X-Requested-With: XMLHttpRequest (AJAX)

    Params:
    - isbn: ISBN a buscar (ISBN-10 o ISBN-13)

    Returns JSON:
    {
        "titulo": "...",
        "autor": "...",
        "descripcion": "...",
        "portada": "..."
    }
    """
    isbn = request.GET.get('isbn', '').strip()

    if not isbn:
        return JsonResponse(
            {'error': 'ISBN requerido'},
            status=400
        )

    # Validar formato ISBN
    if not validar_isbn(isbn):
        return JsonResponse(
            {'error': 'Formato ISBN inválido'},
            status=400
        )

    try:
        # Timeout de 5 segundos
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}"
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        data = response.json()

        if 'items' not in data or len(data['items']) == 0:
            return JsonResponse(
                {'error': 'Libro no encontrado en Google Books'},
                status=404
            )

        libro = data['items'][0]['volumeInfo']

        resultado = {
            'titulo': libro.get('title', ''),
            'autor': ', '.join(libro.get('authors', [])),
            'descripcion': libro.get('description', '')[:500],
            'portada': libro.get('imageLinks', {}).get('thumbnail', '')
        }

        return JsonResponse(resultado)

    except requests.exceptions.Timeout:
        return JsonResponse(
            {'error': 'Timeout en API de Google Books'},
            status=504
        )
    except requests.exceptions.RequestException as e:
        return JsonResponse(
            {'error': 'Error al consultar API'},
            status=500
        )
