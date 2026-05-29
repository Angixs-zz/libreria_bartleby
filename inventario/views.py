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

from django.db import transaction
from django.db.models.deletion import ProtectedError

from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie

from inventario.models import Libro, Ejemplar, Categoria, EstadoFisico
from reservas.models import Reserva
from ventas.models import Venta
from services.inventario_service import InventarioService
from utils.helpers import (
    validar_precio,
    validar_isbn,
    validar_cantidad,
)
from decorators import rate_limit_por_usuario, json_response_handler, cajero_required, director_required
from usuarios.auditoria import registrar_auditoria


# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN DE LIBROS Y EJEMPLARES (ADMIN)
# ─────────────────────────────────────────────────────────────────────────────

def _serializar_libro_para_busqueda(libro):
    ejemplares = []
    for e in libro.ejemplares.all():
        ejemplares.append({
            'id': e.id,
            'sku': e.sku,
            'estado': e.estado_fisico.nombre if e.estado_fisico else 'Sin estado',
            'precio_venta': str(e.precio_venta),
            'stock': e.stock,
        })

    return {
        'id': libro.id,
        'titulo': libro.titulo,
        'autor': libro.autor,
        'isbn': libro.isbn or '',
        'editorial': libro.editorial or '',
        'anio': libro.anio_publicacion or '',
        'descripcion': libro.descripcion or '',
        'categoria': libro.categoria.nombre if libro.categoria else '',
        'portada_url': libro.portada.url if libro.portada else '',
        'ejemplares': ejemplares,
    }

def _redirect_ingreso_ejemplar(modo_compra_suelta=False, proveedor=None, lote=None):
    url_name = 'agregar_libro_compra' if modo_compra_suelta else 'agregar_libro'
    url = reverse(url_name)
    params = []
    if modo_compra_suelta:
        if lote:
            params.append(f"lote_id={lote.id}")
        elif proveedor:
            params.append(f"proveedor={proveedor.id}")
    if params:
        url = f"{url}?{'&'.join(params)}"
    return redirect(url)


def _get_proveedor_compra(request):
    proveedor_id = (
        request.POST.get('proveedor_compra')
        or request.GET.get('proveedor')
        or ''
    ).strip()
    if not proveedor_id:
        return None

    try:
        from proveedores.models import Proveedor
        return Proveedor.objects.filter(pk=proveedor_id, activo=True).first()
    except Exception:
        return None

def _get_lote_compra(request):
    lote_id = (
        request.POST.get('lote_compra')
        or request.GET.get('lote_id')
        or ''
    ).strip()
    if not lote_id:
        return None

    try:
        from proveedores.models import Adquisicion
        return Adquisicion.objects.filter(pk=lote_id).first()
    except Exception:
        return None


def _registrar_detalle_compra_suelta(request, proveedor, ejemplar, cantidad, costo_unitario, lote=None):
    from proveedores.models import Adquisicion, DetalleAdquisicion

    with transaction.atomic():
        if lote:
            adquisicion = lote
        else:
            adquisicion = None
            adquisicion_id = request.session.get('compra_suelta_adquisicion_id')
            if adquisicion_id:
                adquisicion = Adquisicion.objects.filter(
                    pk=adquisicion_id,
                    proveedor=proveedor,
                    tipo='identificado',
                ).first()

            if not adquisicion:
                adquisicion = Adquisicion.objects.create(
                    proveedor=proveedor,
                    tipo='identificado',
                    estado='completado',
                    creado_por=request.user,
                    observaciones='Compra de libros sueltos registrada desde Ingreso de Ejemplar.',
                )
                request.session['compra_suelta_adquisicion_id'] = adquisicion.id

        DetalleAdquisicion.objects.create(
            adquisicion=adquisicion,
            ejemplar=ejemplar,
            cantidad=cantidad,
            costo_unitario=costo_unitario,
        )

    registrar_auditoria(
        actor=request.user,
        accion='crear',
        modulo='proveedores',
        entidad_tipo='adquisicion',
        entidad_id=adquisicion.id,
        entidad_nombre=f'Compra suelta #{adquisicion.id}',
        descripcion=(
            f'Se registró una compra suelta de "{ejemplar.libro.titulo}" '
            f'para "{proveedor.nombre}".'
        ),
        metadata={
            'proveedor_id': proveedor.id,
            'ejemplar_id': ejemplar.id,
            'cantidad': cantidad,
            'costo_unitario': str(costo_unitario),
        },
    )
    return adquisicion

@director_required
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
    modo_compra_suelta = request.resolver_match.url_name == 'agregar_libro_compra'
    lote_compra = _get_lote_compra(request)
    proveedor_compra = lote_compra.proveedor if lote_compra else _get_proveedor_compra(request)

    if modo_compra_suelta and request.method == 'GET' and request.GET.get('nueva_compra') == '1':
        request.session.pop('compra_suelta_adquisicion_id', None)

    if request.method == 'POST':
        accion = request.POST.get('accion', '').strip()
        sin_proveedor = request.POST.get('sin_proveedor') == 'true'

        try:
            if modo_compra_suelta and not sin_proveedor and not proveedor_compra and not lote_compra:
                messages.error(request, 'Selecciona el proveedor o lote.')
                return _redirect_ingreso_ejemplar(modo_compra_suelta)

            # ─── ACCIÓN: Crear libro + ejemplar nuevo ───────────────────────
            if accion == 'crear_todo':
                titulo = request.POST.get('titulo', '').strip()
                autor = request.POST.get('autor', '').strip()
                isbn = request.POST.get('isbn', '').strip()
                editorial = request.POST.get('editorial', '').strip()
                anio_raw = request.POST.get('anio_publicacion', '').strip()
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
                    return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

                # Validar ISBN si se proporciona
                if isbn and not validar_isbn(isbn):
                    messages.error(request, '❌ Formato ISBN inválido.')
                    return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

                # Validar precios
                precio_venta, error = validar_precio(precio_venta_str)
                if error:
                    messages.error(request, f'❌ Precio venta: {error}')
                    return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

                precio_compra, error = validar_precio(precio_compra_str)
                if error:
                    if modo_compra_suelta and not lote_compra and not sin_proveedor:
                        messages.error(request, f'❌ Precio costo: {error}')
                        return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)
                    precio_compra = Decimal('0.00')

                if precio_venta < precio_compra:
                    messages.error(request, '❌ El precio de venta no puede ser menor que el precio de compra.')
                    return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

                # Validar stock
                stock, error = validar_cantidad(stock_str)
                if error:
                    messages.error(request, f'❌ Stock: {error}')
                    return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

                # Crear categoría si no existe
                categoria_obj = None
                if nombre_categoria:
                    categoria_obj, _ = Categoria.objects.get_or_create(
                        nombre=nombre_categoria.capitalize()
                    )

                # Parsear año
                anio_publicacion = None
                if anio_raw and anio_raw.isdigit():
                    anio_publicacion = int(anio_raw)

                # Crear libro
                libro_obj = Libro.objects.create(
                    titulo=titulo,
                    autor=autor,
                    isbn=isbn if isbn else None,
                    editorial=editorial if editorial else None,
                    anio_publicacion=anio_publicacion,
                    categoria=categoria_obj,
                    descripcion=descripcion if descripcion else None,
                    portada=portada if portada else None
                )

                # Si no se subió portada manual pero viene URL externa (desde ISBN), descargarla
                if not portada:
                    portada_url_ext = request.POST.get('portada_url_externa', '').strip()
                    if portada_url_ext:
                        import urllib.request
                        import urllib.error
                        import os
                        from django.core.files.base import ContentFile
                        try:
                            req = urllib.request.Request(
                                portada_url_ext,
                                headers={'User-Agent': 'LibreriaBartleby/1.0'}
                            )
                            with urllib.request.urlopen(req, timeout=8) as resp:
                                img_data = resp.read()
                            ext = portada_url_ext.split('.')[-1].split('?')[0].lower()
                            if ext not in ('jpg', 'jpeg', 'png', 'webp'):
                                ext = 'jpg'
                            filename = f'isbn_{isbn or titulo[:20].replace(" ","_")}.{ext}'
                            libro_obj.portada.save(filename, ContentFile(img_data), save=True)
                        except Exception:
                            pass  # Si falla la descarga, continúa sin portada

                estado_fisico_obj = EstadoFisico.objects.filter(nombre__iexact=estado_final).first()
                if not estado_fisico_obj:
                    estado_fisico_obj = EstadoFisico.objects.create(nombre=estado_final.capitalize())

                # Crear ejemplar
                ejemplar_obj = Ejemplar.objects.create(
                    # El SKU se asigna automáticamente en el modelo.
                    libro=libro_obj,
                    estado_fisico=estado_fisico_obj,
                    precio_compra=precio_compra,
                    precio_venta=precio_venta,
                    stock=0 if (modo_compra_suelta and not sin_proveedor) else stock
                )
                if modo_compra_suelta and not sin_proveedor:
                    adquisicion = _registrar_detalle_compra_suelta(
                        request,
                        proveedor_compra,
                        ejemplar_obj,
                        stock,
                        precio_compra,
                        lote=lote_compra,
                    )
                else:
                    adquisicion = None
                ejemplar_obj.refresh_from_db()
                registrar_auditoria(
                    actor=request.user,
                    accion='crear',
                    modulo='inventario',
                    entidad_tipo='libro',
                    entidad_id=libro_obj.id,
                    entidad_nombre=libro_obj.titulo,
                    descripcion=f'Se registró el libro "{libro_obj.titulo}" con su primer ejemplar.',
                    metadata={'ejemplar_id': ejemplar_obj.id},
                )

                if adquisicion:
                    messages.success(request, f'✅ "{titulo}" registrado y ligado a {"Lote cerrado" if lote_compra else proveedor_compra.nombre}.')
                else:
                    messages.success(request, f'✅ "{titulo}" registrado con su primer ejemplar.')
                return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

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
                    return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

                precio_compra, error = validar_precio(precio_compra_str)
                if not precio_compra:
                    if modo_compra_suelta and not lote_compra and not sin_proveedor:
                        messages.error(request, f'❌ Precio costo: {error or "El precio debe ser mayor a 0"}')
                        return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)
                    precio_compra = Decimal('0.00')

                if precio_venta < precio_compra:
                    messages.error(request, '❌ El precio de venta no puede ser menor que el precio de compra.')
                    return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

                stock, error = validar_cantidad(stock_str)
                if error:
                    messages.error(request, f'❌ Stock: {error}')
                    return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

                estado_fisico_obj = EstadoFisico.objects.filter(nombre__iexact=estado_final).first()
                if not estado_fisico_obj:
                    estado_fisico_obj = EstadoFisico.objects.create(nombre=estado_final.capitalize())

                # Crear ejemplar
                nuevo_ejemplar = Ejemplar.objects.create(
                    libro=libro_obj,
                    estado_fisico=estado_fisico_obj,
                    precio_compra=precio_compra,
                    precio_venta=precio_venta,
                    stock=0 if (modo_compra_suelta and not sin_proveedor) else stock
                )
                if modo_compra_suelta and not sin_proveedor:
                    adquisicion = _registrar_detalle_compra_suelta(
                        request,
                        proveedor_compra,
                        nuevo_ejemplar,
                        stock,
                        precio_compra,
                        lote=lote_compra,
                    )
                    nuevo_ejemplar.refresh_from_db()
                else:
                    adquisicion = None

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
                if adquisicion:
                    messages.success(request, f'Compra ligada a {"Lote cerrado" if lote_compra else proveedor_compra.nombre}.')
                return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

            # ─── ACCIÓN: Aumentar stock ──────────────────────────────────────
            elif accion == 'sumar_stock':
                ejemplar_id = request.POST.get('ejemplar_id')
                cantidad_str = request.POST.get('cantidad', '1')
                precio_compra_str = request.POST.get('precio_compra', '')
                
                ejemplar = get_object_or_404(Ejemplar, id=ejemplar_id)
                
                cantidad, error = validar_cantidad(cantidad_str)
                if error:
                    messages.error(request, f'❌ Cantidad: {error}')
                    return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

                if modo_compra_suelta and not sin_proveedor:
                    precio_compra, error = validar_precio(precio_compra_str)
                    if error:
                        if not lote_compra:
                            messages.error(request, f'❌ Precio costo: {error}')
                            return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)
                        else:
                            precio_compra = Decimal('0.00')
                    
                    if ejemplar.precio_venta < precio_compra:
                        messages.error(request, f'❌ El costo de adquisición (${precio_compra}) no puede ser mayor que el precio de venta actual (${ejemplar.precio_venta}).')
                        return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)
                    adquisicion = _registrar_detalle_compra_suelta(
                        request,
                        proveedor_compra,
                        ejemplar,
                        cantidad,
                        precio_compra,
                        lote=lote_compra,
                    )
                    ejemplar.refresh_from_db()
                else:
                    adquisicion = None
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
                if adquisicion:
                    messages.success(request, f'Compra ligada a {"Lote cerrado" if lote_compra else proveedor_compra.nombre}.')
                return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

        except Exception as e:
            messages.error(request, f'❌ Error: {str(e)}')
            return _redirect_ingreso_ejemplar(modo_compra_suelta, proveedor_compra, lote_compra)

    categorias = Categoria.objects.all()
    estados_fisicos = EstadoFisico.objects.all()
    proveedores = []
    if modo_compra_suelta:
        from proveedores.models import Proveedor
        proveedores = Proveedor.objects.filter(activo=True).order_by('nombre')

    return render(
        request,
        'inventario/agregar_libro.html',
        {
            'categorias': categorias,
            'estados_fisicos': estados_fisicos,
            'modo_compra_suelta': modo_compra_suelta,
            'proveedores': proveedores,
            'proveedor_compra': proveedor_compra,
            'lote_compra': lote_compra,
        }
    )


@cajero_required
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
    
    # Prioridad: ISBN exacto o normalizado
    if isbn:
        isbn_limpio = isbn.replace('-', '').replace(' ', '')
        libros = Libro.objects.filter(isbn__in=[isbn, isbn_limpio])[:1]
        if not libros:
            libros = Libro.objects.filter(isbn__icontains=isbn_limpio)[:1]
    
    # Si no by ISBN, buscar por título
    elif len(titulo) >= 2:
        libros = Libro.objects.filter(
            titulo__icontains=titulo
        ).select_related('categoria')[:8]

    for libro in libros:
        resultados.append(_serializar_libro_para_busqueda(libro))

    return JsonResponse({'libros': resultados})


@cajero_required
@require_http_methods(["GET"])
def buscar_isbn_enriquecido(request):
    """
    Busca informaci\u00f3n completa de un libro por ISBN consultando APIs externas.
    
    Nivel 1: Base de datos local
    Nivel 2: OpenLibrary /isbn/<isbn>.json  (metadatos + descripci\u00f3n)
    Nivel 3: OpenLibrary /search.json       (fallback)
    
    Devuelve: titulo, autor, editorial, anio, descripcion, categoria, portada_url
    """
    import urllib.request
    import urllib.error

    isbn_raw = request.GET.get('isbn', '').strip()
    if not isbn_raw:
        return JsonResponse({'error': 'ISBN requerido'}, status=400)

    isbn = isbn_raw.replace('-', '').replace(' ', '')

    # ── Nivel 1: inventario local (solo si tiene ejemplares activos) ─────────
    libro_local = Libro.objects.filter(isbn__in=[isbn_raw, isbn]).first()
    if libro_local and libro_local.ejemplares.exists():
        data = _serializar_libro_para_busqueda(libro_local)
        data.update({
            'fuente': 'local',
        })
        return JsonResponse(data)

    def _fetch_json(url, timeout=6):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'LibreriaBartleby/1.0'})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception:
            return None

    resultado = {
        'fuente': None,
        'titulo': '',
        'autor': '',
        'editorial': '',
        'anio': '',
        'descripcion': '',
        'categoria': '',
        'portada_url': '',
    }

    # ── Nivel 2: OpenLibrary /isbn/<isbn>.json ────────────────────────────
    data_isbn = _fetch_json(f'https://openlibrary.org/isbn/{isbn}.json')
    if data_isbn and data_isbn.get('title'):
        resultado['fuente'] = 'openlibrary_isbn'
        resultado['titulo'] = data_isbn.get('title', '')

        # A\u00f1o de publicaci\u00f3n
        publish_date = data_isbn.get('publish_date', '')
        if publish_date:
            import re
            m = re.search(r'\d{4}', publish_date)
            resultado['anio'] = m.group() if m else ''

        # Editorial
        publishers = data_isbn.get('publishers', [])
        if publishers:
            resultado['editorial'] = publishers[0]

        # Portada  
        covers = data_isbn.get('covers', [])
        if covers:
            resultado['portada_url'] = f'https://covers.openlibrary.org/b/id/{covers[0]}-L.jpg'

        # Autor desde obra principal
        works = data_isbn.get('works', [])
        obra_data = None
        if works:
            obra_key = works[0].get('key', '')
            obra_data = _fetch_json(f'https://openlibrary.org{obra_key}.json')
            if obra_data:
                # Descripci\u00f3n
                desc = obra_data.get('description', '')
                if isinstance(desc, dict):
                    desc = desc.get('value', '')
                resultado['descripcion'] = desc[:1200] if desc else ''

                # Categor\u00eda / g\u00e9nero desde subjects
                subjects = obra_data.get('subjects', [])
                if subjects:
                    resultado['categoria'] = subjects[0]

        # Autores
        authors = data_isbn.get('authors', [])
        if authors:
            autor_key = authors[0].get('key', '')
            autor_data = _fetch_json(f'https://openlibrary.org{autor_key}.json')
            if autor_data:
                resultado['autor'] = (
                    autor_data.get('name') or
                    autor_data.get('personal_name') or ''
                )

        if resultado['titulo']:
            return JsonResponse(resultado)

    # ── Nivel 3: OpenLibrary /search.json ────────────────────────────────
    data_search = _fetch_json(
        f'https://openlibrary.org/search.json?isbn={isbn}'
        f'&fields=title,author_name,publisher,first_publish_year,subject,cover_i&limit=1'
    )
    if data_search and data_search.get('docs'):
        doc = data_search['docs'][0]
        resultado['fuente'] = 'openlibrary_search'
        resultado['titulo'] = doc.get('title', '')
        autores = doc.get('author_name', [])
        resultado['autor'] = autores[0] if autores else ''
        editores = doc.get('publisher', [])
        resultado['editorial'] = editores[0] if editores else ''
        resultado['anio'] = str(doc.get('first_publish_year', '') or '')
        subjects = doc.get('subject', [])
        resultado['categoria'] = subjects[0] if subjects else ''
        cover_id = doc.get('cover_i')
        if cover_id:
            resultado['portada_url'] = f'https://covers.openlibrary.org/b/id/{cover_id}-L.jpg'

        if resultado['titulo']:
            return JsonResponse(resultado)

    # ── Nivel 4: Google Books ─────────────────────────────────────────────
    data_gbooks = _fetch_json(
        f'https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&maxResults=1'
    )
    if data_gbooks and data_gbooks.get('items'):
        info = data_gbooks['items'][0].get('volumeInfo', {})
        resultado['fuente'] = 'google_books'
        resultado['titulo'] = info.get('title', '') or resultado['titulo']
        authors = info.get('authors', [])
        resultado['autor'] = ', '.join(authors) if authors else resultado['autor']
        resultado['editorial'] = info.get('publisher', '') or resultado['editorial']
        pub_date = info.get('publishedDate', '')
        if pub_date:
            import re as _re
            m = _re.search(r'\d{4}', pub_date)
            resultado['anio'] = m.group() if m else resultado['anio']
        cats = info.get('categories', [])
        resultado['categoria'] = cats[0] if cats else resultado['categoria']
        desc = info.get('description', '') or ''
        resultado['descripcion'] = desc[:1200] if desc else resultado['descripcion']
        img_links = info.get('imageLinks', {})
        cover = img_links.get('thumbnail') or img_links.get('smallThumbnail') or ''
        if cover:
            # Asegurar https y pedir tamaño grande
            cover = cover.replace('http://', 'https://').replace('zoom=1', 'zoom=3')
            resultado['portada_url'] = cover

        if resultado['titulo']:
            return JsonResponse(resultado)

    return JsonResponse({'error': 'No se encontró información para este ISBN'}, status=404)


@director_required
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


@director_required
@require_http_methods(["GET"])
def exportar_inventario(request):
    """
    Exporta todo el inventario (libros + ejemplares) a un archivo JSON.
    """
    from django.http import HttpResponse
    import json
    from django.utils.timezone import now
    
    ejemplares = Ejemplar.objects.select_related('libro', 'libro__categoria', 'estado_fisico').all()
    
    export_data = {
        'version': '1.0',
        'exportado_en': now().isoformat(),
        'libreria': 'Librería Bartleby',
        'inventario': []
    }
    
    import base64
    for e in ejemplares:
        portada_base64 = ''
        portada_nombre = ''
        if e.libro.portada:
            try:
                with e.libro.portada.open('rb') as f:
                    portada_base64 = base64.b64encode(f.read()).decode('utf-8')
                portada_nombre = e.libro.portada.name.split('/')[-1]
            except Exception:
                pass

        item = {
            'sku': e.sku,
            'estado_fisico': e.estado_fisico.nombre if e.estado_fisico else 'Nuevo',
            'descripcion_estado': e.descripcion_estado or '',
            'precio_compra': str(e.precio_compra),
            'precio_venta': str(e.precio_venta),
            'stock': e.stock,
            'libro': {
                'titulo': e.libro.titulo,
                'autor': e.libro.autor,
                'isbn': e.libro.isbn or '',
                'editorial': e.libro.editorial or '',
                'anio_publicacion': e.libro.anio_publicacion,
                'categoria': e.libro.categoria.nombre if e.libro.categoria else '',
                'descripcion': e.libro.descripcion or '',
                'portada_nombre': portada_nombre,
                'portada_base64': portada_base64
            }
        }
        export_data['inventario'].append(item)
        
    response = HttpResponse(
        json.dumps(export_data, indent=4, ensure_ascii=False),
        content_type='application/json; charset=utf-8'
    )
    filename = f"inventario_bartleby_{now().strftime('%Y%m%d_%H%M%S')}.json"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    
    registrar_auditoria(
        actor=request.user,
        accion='exportar',
        modulo='inventario',
        entidad_tipo='inventario',
        entidad_id=0,
        entidad_nombre='Copia de Seguridad de Inventario',
        descripcion=f'Se exportó el inventario completo ({len(export_data["inventario"])} registros).',
    )
    return response


@director_required
@require_http_methods(["POST"])
def importar_inventario(request):
    """
    Importa libros y ejemplares desde un archivo JSON.
    Soporta inserción de nuevos registros e incremento/actualización de existentes.
    """
    import json
    
    archivo = request.FILES.get('archivo_importar')
    if not archivo:
        messages.error(request, '❌ Por favor, selecciona un archivo JSON para importar.')
        return redirect('gestion_inventario')
        
    try:
        data = json.load(archivo)
    except Exception as e:
        messages.error(request, f'❌ Error al leer el archivo JSON: {str(e)}')
        return redirect('gestion_inventario')
        
    inventario_items = data.get('inventario')
    if not isinstance(inventario_items, list):
        messages.error(request, '❌ El archivo JSON no tiene un formato válido de inventario.')
        return redirect('gestion_inventario')
        
    libros_creados = 0
    libros_usados = 0
    ejemplares_creados = 0
    ejemplares_actualizados = 0
    
    try:
        with transaction.atomic():
            for item in inventario_items:
                libro_data = item.get('libro')
                if not libro_data or not libro_data.get('titulo') or not libro_data.get('autor'):
                    continue
                    
                titulo = libro_data['titulo'].strip()
                autor = libro_data['autor'].strip()
                isbn = libro_data.get('isbn', '').strip() or None
                editorial = libro_data.get('editorial', '').strip() or None
                anio = libro_data.get('anio_publicacion')
                categoria_nombre = libro_data.get('categoria', '').strip()
                descripcion = libro_data.get('descripcion', '').strip() or None
                
                # Obtener o crear Categoria
                categoria_obj = None
                if categoria_nombre:
                    categoria_obj, _ = Categoria.objects.get_or_create(
                        nombre=categoria_nombre.capitalize()
                    )
                    
                # Buscar Libro existente
                libro_obj = None
                if isbn:
                    libro_obj = Libro.objects.filter(isbn=isbn).first()
                if not libro_obj:
                    libro_obj = Libro.objects.filter(titulo__iexact=titulo, autor__iexact=autor).first()
                    
                if not libro_obj:
                    libro_obj = Libro.objects.create(
                        titulo=titulo,
                        autor=autor,
                        isbn=isbn,
                        editorial=editorial,
                        anio_publicacion=anio,
                        categoria=categoria_obj,
                        descripcion=descripcion
                    )
                    libros_creados += 1
                else:
                    libros_usados += 1
                    # Opcionalmente rellenar campos vacíos del libro existente
                    actualizado = False
                    if not libro_obj.isbn and isbn:
                        libro_obj.isbn = isbn
                        actualizado = True
                    if not libro_obj.editorial and editorial:
                        libro_obj.editorial = editorial
                        actualizado = True
                    if not libro_obj.descripcion and descripcion:
                        libro_obj.descripcion = descripcion
                        actualizado = True
                    if not libro_obj.categoria and categoria_obj:
                        libro_obj.categoria = categoria_obj
                        actualizado = True
                    if actualizado:
                        libro_obj.save()

                # Sincronizar portada si el libro no tiene una aún
                portada_nombre = libro_data.get('portada_nombre', '')
                portada_base64 = libro_data.get('portada_base64', '')
                if portada_nombre and portada_base64 and not libro_obj.portada:
                    try:
                        from django.core.files.base import ContentFile
                        import base64
                        
                        raw_data = portada_base64
                        if ';base64,' in raw_data:
                            _, raw_data = raw_data.split(';base64,', 1)
                        
                        decoded_file = base64.b64decode(raw_data)
                        libro_obj.portada.save(portada_nombre, ContentFile(decoded_file), save=True)
                    except Exception:
                        pass
                        
                # Obtener o crear Estado Fisico
                estado_nombre = item.get('estado_fisico', '').strip() or 'Nuevo'
                estado_fisico_obj, _ = EstadoFisico.objects.get_or_create(
                    nombre=estado_nombre.capitalize()
                )
                
                sku = item.get('sku', '').strip()
                stock = int(item.get('stock', 1))
                precio_compra = Decimal(str(item.get('precio_compra', '0.00')))
                precio_venta = Decimal(str(item.get('precio_venta', '0.00')))
                descripcion_estado = item.get('descripcion_estado', '').strip() or None
                
                # Buscar Ejemplar por SKU
                ejemplar_obj = None
                if sku:
                    ejemplar_obj = Ejemplar.objects.filter(sku=sku).first()
                    
                if ejemplar_obj:
                    # Actualizar stock
                    ejemplar_obj.stock = stock
                    ejemplar_obj.precio_compra = precio_compra
                    ejemplar_obj.precio_venta = precio_venta
                    ejemplar_obj.estado_fisico = estado_fisico_obj
                    if descripcion_estado:
                        ejemplar_obj.descripcion_estado = descripcion_estado
                    ejemplar_obj.save()
                    ejemplares_actualizados += 1
                else:
                    # Crear nuevo ejemplar
                    kwargs = {
                        'libro': libro_obj,
                        'estado_fisico': estado_fisico_obj,
                        'precio_compra': precio_compra,
                        'precio_venta': precio_venta,
                        'stock': stock,
                        'descripcion_estado': descripcion_estado
                    }
                    if sku:
                        kwargs['sku'] = sku
                    Ejemplar.objects.create(**kwargs)
                    ejemplares_creados += 1
                    
        messages.success(
            request,
            f'✅ Importación finalizada con éxito. '
            f'Libros: {libros_creados} creados / {libros_usados} asociados. '
            f'Ejemplares (lotes): {ejemplares_creados} creados / {ejemplares_actualizados} sincronizados.'
        )
        
        registrar_auditoria(
            actor=request.user,
            accion='importar',
            modulo='inventario',
            entidad_tipo='inventario',
            entidad_id=0,
            entidad_nombre='Importador de Inventario',
            descripcion=f'Se importó un archivo JSON de inventario. Libros creados: {libros_creados}, ejemplares creados: {ejemplares_creados}, ejemplares actualizados: {ejemplares_actualizados}.',
        )
        
    except Exception as e:
        messages.error(request, f'❌ Error durante la importación (Transacción revertida): {str(e)}')
        
    return redirect('gestion_inventario')


@director_required
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
                    if precio_venta < ejemplar.precio_compra:
                        messages.error(request, '❌ El precio de venta no puede ser menor que el precio de compra.')
                        return redirect('detalle_ejemplar', ejemplar_id=ejemplar_id)
                    cambios.append('precio venta actualizado')
                    ejemplar.precio_venta = precio_venta

            # El precio de compra no se permite modificar una vez registrado en el inventario

            if stock_str:
                stock, error = validar_cantidad(stock_str)
                if error:
                    messages.error(request, '❌ Stock: ' + error)
                    return redirect('detalle_ejemplar', ejemplar_id=ejemplar_id)
                
                # Validar que el nuevo stock no sea menor que las reservas activas
                from reservas.models import Reserva
                reservas_activas = Reserva.objects.filter(
                    ejemplares=ejemplar,
                    estado='pendiente'
                ).count()
                if stock < reservas_activas:
                    messages.error(request, f'❌ El stock ({stock}) no puede ser menor que el número de reservas pendientes ({reservas_activas}).')
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


@director_required
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

    # Verificar si el ejemplar tiene reservas pendientes
    reservas_activas = ejemplar.reservas_activas.filter(estado='pendiente')
    if reservas_activas.exists():
        messages.error(
            request,
            f'❌ No se puede eliminar el ejemplar {sku} porque tiene '
            f'reservas pendientes de recolección. '
            f'Libera las reservas antes de eliminarlo.'
        )
        return redirect('gestion_inventario')

    try:
        libro = ejemplar.libro
        ejemplar.delete()
        # Si el Libro ya no tiene ningún ejemplar, eliminarlo también
        if not libro.ejemplares.exists():
            libro.delete()
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

@cajero_required
@ensure_csrf_cookie
@require_http_methods(["GET"])
def punto_de_venta(request):
    """
    Carga la pantalla del Punto de Venta.
    
    @ensure_csrf_cookie: Inyecta token CSRF en el template para AJAX.
    """
    return render(request, 'pos.html')


@cajero_required
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


@cajero_required
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
