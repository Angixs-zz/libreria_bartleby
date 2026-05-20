from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from decorators import admin_required
from inventario.models import Libro, Ejemplar, Categoria
from usuarios.auditoria import registrar_auditoria
from utils.helpers import buscar_por_isbn, generar_sku_mejorado
from .forms import ProveedorForm, AdquisicionForm, LibroRapidoForm, EjemplarRapidoForm
from .models import Proveedor, Adquisicion, DetalleAdquisicion


def _guardar_portada_externa(libro, portada_url, nombre_base):
    if not portada_url or libro.portada:
        return

    import urllib.request
    from django.core.files.base import ContentFile

    try:
        req = urllib.request.Request(
            portada_url,
            headers={'User-Agent': 'LibreriaBartleby/1.0'}
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            img_data = resp.read()

        ext = portada_url.split('.')[-1].split('?')[0].lower()
        if ext not in ('jpg', 'jpeg', 'png', 'webp'):
            ext = 'jpg'
        nombre_limpio = ''.join(c if c.isalnum() else '_' for c in nombre_base[:30]).strip('_') or 'portada'
        libro.portada.save(f'isbn_{nombre_limpio}.{ext}', ContentFile(img_data), save=True)
    except Exception:
        pass


def _build_filas_desde_post(request):
    ejemplares = request.POST.getlist('ejemplar_id')
    cantidades = request.POST.getlist('cantidad')
    costos = request.POST.getlist('costo_unitario')

    filas = []
    max_len = max(len(ejemplares), len(cantidades), len(costos), 1)
    for idx in range(max_len):
        filas.append({
            'ejemplar_id': ejemplares[idx] if idx < len(ejemplares) else '',
            'cantidad': cantidades[idx] if idx < len(cantidades) else '',
            'costo_unitario': costos[idx] if idx < len(costos) else '',
        })
    return filas


@login_required
@admin_required
@require_http_methods(["GET"])
def directorio_proveedores(request):
    query = request.GET.get('q', '').strip()

    proveedores = Proveedor.objects.annotate(
        total_adquisiciones=Count('adquisiciones', distinct=True),
        gasto_acumulado=Coalesce(Sum('adquisiciones__total'), Decimal('0.00')),
    )
    if query:
        proveedores = proveedores.filter(
            Q(nombre__icontains=query) |
            Q(contacto__icontains=query) |
            Q(email__icontains=query) |
            Q(telefono__icontains=query)
        )

    proveedores = proveedores.order_by('nombre')
    editar_forms = {
        proveedor.id: ProveedorForm(instance=proveedor, prefix=f'proveedor-{proveedor.id}')
        for proveedor in proveedores
    }

    context = {
        'proveedores': proveedores,
        'query': query,
        'proveedor_form': ProveedorForm(prefix='nuevo'),
        'editar_forms': editar_forms,
        'total_proveedores': Proveedor.objects.count(),
        'proveedores_activos': Proveedor.objects.filter(activo=True).count(),
        'compras_registradas': Adquisicion.objects.count(),
        'gasto_total': Adquisicion.objects.aggregate(
            total=Coalesce(Sum('total'), Decimal('0.00'))
        )['total'],
    }
    return render(request, 'proveedores/directorio_proveedores.html', context)


@login_required
@admin_required
@require_http_methods(["POST"])
def crear_proveedor(request):
    form = ProveedorForm(request.POST, prefix='nuevo')
    if form.is_valid():
        proveedor = form.save()
        registrar_auditoria(
            actor=request.user,
            accion='crear',
            modulo='proveedores',
            entidad_tipo='proveedor',
            entidad_id=proveedor.id,
            entidad_nombre=proveedor.nombre,
            descripcion=f'Se registró el proveedor "{proveedor.nombre}".',
        )
        messages.success(request, 'Proveedor registrado correctamente.')
    else:
        messages.error(request, 'No se pudo registrar el proveedor. Revisa los datos ingresados.')
    return redirect('directorio_proveedores')


@login_required
@admin_required
@require_http_methods(["POST"])
def editar_proveedor(request, proveedor_id):
    proveedor = get_object_or_404(Proveedor, pk=proveedor_id)
    form = ProveedorForm(request.POST, instance=proveedor, prefix=f'proveedor-{proveedor.id}')
    if form.is_valid():
        proveedor = form.save()
        registrar_auditoria(
            actor=request.user,
            accion='editar',
            modulo='proveedores',
            entidad_tipo='proveedor',
            entidad_id=proveedor.id,
            entidad_nombre=proveedor.nombre,
            descripcion=f'Se actualizó el proveedor "{proveedor.nombre}".',
        )
        messages.success(request, f'Se actualizo el proveedor "{proveedor.nombre}".')
    else:
        messages.error(request, 'No se pudo actualizar el proveedor. Revisa los campos del formulario.')
    return redirect('directorio_proveedores')


@login_required
@admin_required
@require_http_methods(["GET", "POST"])
def registrar_adquisicion(request):
    ejemplares = Ejemplar.objects.select_related('libro').order_by('libro__titulo', 'sku')
    categorias = Categoria.objects.all().order_by('nombre')
    filas = [{'ejemplar_id': '', 'cantidad': '', 'costo_unitario': ''}]

    if request.method == 'POST':
        form = AdquisicionForm(request.POST)
        tipo = request.POST.get('tipo', 'identificado')

        # ── LOTE CERRADO: guarda solo la cabecera, sin detalles ─────────────────
        if tipo == 'lote_cerrado':
            if form.is_valid():
                with transaction.atomic():
                    adquisicion = form.save(commit=False)
                    adquisicion.creado_por = request.user
                    adquisicion.estado = 'por_inventariar'
                    if adquisicion.costo_lote:
                        adquisicion.total = adquisicion.costo_lote
                    adquisicion.save()
                    registrar_auditoria(
                        actor=request.user,
                        accion='crear',
                        modulo='proveedores',
                        entidad_tipo='adquisicion',
                        entidad_id=adquisicion.id,
                        entidad_nombre=f'Lote cerrado #{adquisicion.id}',
                        descripcion=(
                            f'Lote cerrado #{adquisicion.id} registrado para "{adquisicion.proveedor.nombre}". '
                            f'Pendiente de inventariar.'
                        ),
                        metadata={'tipo': 'lote_cerrado'},
                    )
                messages.success(
                    request,
                    f'✅ Lote cerrado #{adquisicion.id} guardado. '
                    f'Puedes inventariar los libros cuando los abras.'
                )
                return redirect('inventariar_lote', adquisicion_id=adquisicion.id)
            else:
                messages.error(request, 'Corrige los datos del formulario.')

        # ── IDENTIFICADO: flujo normal con detalles ──────────────────────────
        else:
            filas = _build_filas_desde_post(request)
            detalles_limpios = []
            hay_error = False

            for fila in filas:
                ejemplar_id = str(fila['ejemplar_id']).strip()
                cantidad = str(fila['cantidad']).strip()
                costo_unitario = str(fila['costo_unitario']).strip()

                if not ejemplar_id and not cantidad and not costo_unitario:
                    continue

                try:
                    ejemplar = Ejemplar.objects.get(pk=ejemplar_id)
                except Ejemplar.DoesNotExist:
                    messages.error(request, 'Selecciona un libro/lote válido para cada renglon.')
                    hay_error = True
                    continue

                try:
                    cantidad_int = int(cantidad)
                    if cantidad_int <= 0:
                        raise ValueError
                except (TypeError, ValueError):
                    messages.error(request, f'La cantidad para "{ejemplar.libro.titulo}" debe ser mayor a 0.')
                    hay_error = True
                    continue

                try:
                    costo_decimal = Decimal(costo_unitario)
                    if costo_decimal <= 0:
                        raise InvalidOperation
                except (InvalidOperation, TypeError, ValueError):
                    messages.error(request, f'El costo de compra para "{ejemplar.libro.titulo}" debe ser mayor a 0.')
                    hay_error = True
                    continue

                detalles_limpios.append({
                    'ejemplar': ejemplar,
                    'cantidad': cantidad_int,
                    'costo_unitario': costo_decimal,
                })

            if not detalles_limpios:
                hay_error = True
                messages.error(request, 'Debes agregar al menos un libro al lote de adquisicion.')

            if form.is_valid() and not hay_error:
                with transaction.atomic():
                    adquisicion = form.save(commit=False)
                    adquisicion.creado_por = request.user
                    adquisicion.estado = 'completado'
                    adquisicion.save()

                    for detalle in detalles_limpios:
                        DetalleAdquisicion.objects.create(
                            adquisicion=adquisicion,
                            ejemplar=detalle['ejemplar'],
                            cantidad=detalle['cantidad'],
                            costo_unitario=detalle['costo_unitario'],
                        )
                    adquisicion.refresh_from_db()
                    registrar_auditoria(
                        actor=request.user,
                        accion='crear',
                        modulo='proveedores',
                        entidad_tipo='adquisicion',
                        entidad_id=adquisicion.id,
                        entidad_nombre=f'Lote #{adquisicion.id}',
                        descripcion=f'Se registró la adquisición #{adquisicion.id} para "{adquisicion.proveedor.nombre}".',
                        metadata={
                            'proveedor_id': adquisicion.proveedor_id,
                            'renglones': len(detalles_limpios),
                            'total': str(adquisicion.total),
                        },
                    )

                messages.success(request, f'Lote #{adquisicion.id} registrado y stock actualizado.')
                return redirect('detalle_proveedor', proveedor_id=adquisicion.proveedor_id)
    else:
        initial = {}
        proveedor_id = request.GET.get('proveedor')
        if proveedor_id and Proveedor.objects.filter(pk=proveedor_id).exists():
            initial['proveedor'] = proveedor_id
        form = AdquisicionForm(initial=initial)

    context = {
        'form': form,
        'ejemplares': ejemplares,
        'categorias': categorias,
        'filas': filas,
        'libro_form': LibroRapidoForm(),
        'ejemplar_form': EjemplarRapidoForm(),
    }
    return render(request, 'proveedores/registrar_adquisicion.html', context)


@login_required
@admin_required
@require_http_methods(["GET"])
def historial_adquisiciones(request):
    query = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    estado = request.GET.get('estado', '').strip()

    adquisiciones = Adquisicion.objects.select_related(
        'proveedor',
        'creado_por',
    ).prefetch_related(
        'detalles__ejemplar__libro',
        'detalles__ejemplar__estado_fisico',
    )

    if query:
        adquisiciones = adquisiciones.filter(
            Q(proveedor__nombre__icontains=query) |
            Q(observaciones__icontains=query) |
            Q(detalles__ejemplar__libro__titulo__icontains=query) |
            Q(detalles__ejemplar__libro__autor__icontains=query) |
            Q(detalles__ejemplar__sku__icontains=query)
        ).distinct()

    if tipo in dict(Adquisicion.TIPO_CHOICES):
        adquisiciones = adquisiciones.filter(tipo=tipo)

    if estado in dict(Adquisicion.ESTADO_CHOICES):
        adquisiciones = adquisiciones.filter(estado=estado)

    adquisicion_ids = list(adquisiciones.values_list('id', flat=True))
    resumen = Adquisicion.objects.filter(id__in=adquisicion_ids).aggregate(
        gasto_total=Coalesce(Sum('total'), Decimal('0.00')),
        unidades=Coalesce(Sum('detalles__cantidad'), 0),
        total_registros=Count('id', distinct=True),
    )
    pendientes = Adquisicion.objects.filter(
        id__in=adquisicion_ids,
        estado='por_inventariar',
    ).count()

    adquisiciones = adquisiciones.annotate(
        total_unidades=Coalesce(Sum('detalles__cantidad'), 0),
        total_renglones=Count('detalles', distinct=True),
    ).order_by('-fecha', '-creado_en')

    context = {
        'adquisiciones': adquisiciones,
        'query': query,
        'tipo': tipo,
        'estado': estado,
        'tipo_choices': Adquisicion.TIPO_CHOICES,
        'estado_choices': Adquisicion.ESTADO_CHOICES,
        'gasto_total': resumen['gasto_total'],
        'unidades_adquiridas': resumen['unidades'],
        'total_registros': resumen['total_registros'],
        'pendientes': pendientes,
    }
    return render(request, 'proveedores/historial_adquisiciones.html', context)


@login_required
@admin_required
@require_http_methods(["GET"])
def detalle_proveedor(request, proveedor_id):
    proveedor = get_object_or_404(Proveedor, pk=proveedor_id)
    adquisiciones = proveedor.adquisiciones.select_related(
        'creado_por'
    ).prefetch_related(
        'detalles__ejemplar__libro'
    ).order_by('-fecha', '-creado_en')

    resumen = adquisiciones.aggregate(
        gasto_total=Coalesce(Sum('total'), Decimal('0.00')),
        total_lotes=Count('id'),
        unidades=Coalesce(Sum('detalles__cantidad'), 0),
    )

    context = {
        'proveedor': proveedor,
        'adquisiciones': adquisiciones,
        'gasto_total': resumen['gasto_total'],
        'total_lotes': resumen['total_lotes'],
        'unidades_adquiridas': resumen['unidades'],
    }
    return render(request, 'proveedores/detalle_proveedor.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# NUEVAS VISTAS: Crear Ejemplar Inline + Inventariar Lote Cerrado
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@admin_required
@require_http_methods(["GET"])
def buscar_libro_isbn(request):
    """
    AJAX: Busca metadatos de un libro por ISBN usando la utilidad ya existente.
    También verifica si el libro ya existe en la BD local.
    """
    isbn = request.GET.get('isbn', '').strip()
    if not isbn:
        return JsonResponse({'ok': False, 'error': 'ISBN requerido'})

    # Verificar si ya existe en BD local
    libro_local = Libro.objects.filter(isbn=isbn).first()
    if libro_local:
        return JsonResponse({
            'ok': True,
            'fuente': 'local',
            'titulo': libro_local.titulo,
            'autor': libro_local.autor,
            'editorial': libro_local.editorial or '',
            'categoria': libro_local.categoria.nombre if libro_local.categoria else '',
            'libro_id': libro_local.id,
        })

    # Buscar en API externa (Open Library / Google Books)
    try:
        datos = buscar_por_isbn(isbn)
        if datos:
            return JsonResponse({
                'ok': True,
                'fuente': 'externa',
                'titulo': datos.get('titulo', ''),
                'autor': datos.get('autor', ''),
                'editorial': datos.get('editorial', ''),
                'categoria': datos.get('categoria', ''),
            })
    except Exception:
        pass

    return JsonResponse({'ok': False, 'error': 'No se encontró info para ese ISBN'})


@login_required
@admin_required
@require_http_methods(["POST"])
def crear_ejemplar_rapido(request):
    """
    AJAX: Crea un Libro (o lo recupera por ISBN) + Ejemplar sin salir de la
    pantalla de adquisición. Devuelve el ID y etiqueta del nuevo Ejemplar
    para que el JS lo inyecte en el <select> de la fila.
    """
    libro_form = LibroRapidoForm(request.POST, request.FILES)
    ejemplar_form = EjemplarRapidoForm(request.POST)

    errores = {}
    if not libro_form.is_valid():
        errores.update(libro_form.errors)
    if not ejemplar_form.is_valid():
        errores.update(ejemplar_form.errors)

    if errores:
        return JsonResponse({'ok': False, 'errores': errores}, status=400)

    isbn = libro_form.cleaned_data.get('isbn') or None
    titulo = libro_form.cleaned_data['titulo']
    autor = libro_form.cleaned_data['autor']
    categoria_nombre = libro_form.cleaned_data.get('categoria_texto', '').strip()
    portada = libro_form.cleaned_data.get('portada')
    portada_url_externa = request.POST.get('portada_url_externa', '').strip()

    categoria = None
    if categoria_nombre:
        categoria, _ = Categoria.objects.get_or_create(nombre=categoria_nombre.capitalize())

    with transaction.atomic():
        # Reutilizar libro si ya existe con ese ISBN
        if isbn:
            libro, _ = Libro.objects.get_or_create(
                isbn=isbn,
                defaults={
                    'titulo': titulo,
                    'autor': autor,
                    'editorial': libro_form.cleaned_data.get('editorial') or '',
                    'anio_publicacion': libro_form.cleaned_data.get('anio_publicacion'),
                    'categoria': categoria,
                    'descripcion': libro_form.cleaned_data.get('descripcion') or '',
                    'portada': portada,
                }
            )
        else:
            libro = Libro.objects.create(
                titulo=titulo,
                autor=autor,
                editorial=libro_form.cleaned_data.get('editorial') or '',
                anio_publicacion=libro_form.cleaned_data.get('anio_publicacion'),
                categoria=categoria,
                descripcion=libro_form.cleaned_data.get('descripcion') or '',
                portada=portada,
            )

        if isbn and categoria and not libro.categoria_id:
            libro.categoria = categoria
            libro.save(update_fields=['categoria', 'actualizado_en'])

        if portada and not libro.portada:
            libro.portada = portada
            libro.save(update_fields=['portada', 'actualizado_en'])
        elif not portada:
            _guardar_portada_externa(libro, portada_url_externa, isbn or titulo)

        ejemplar = Ejemplar.objects.create(
            libro=libro,
            estado_fisico=ejemplar_form.cleaned_data['estado_fisico'],
            precio_venta=ejemplar_form.cleaned_data['precio_venta'],
            descripcion_estado=ejemplar_form.cleaned_data.get('descripcion_estado') or '',
            precio_compra=Decimal('0.00'),  # se actualiza al guardar el DetalleAdquisicion
            stock=0,                         # el DetalleAdquisicion lo sube
        )

    registrar_auditoria(
        actor=request.user,
        accion='crear',
        modulo='inventario',
        entidad_tipo='ejemplar',
        entidad_id=ejemplar.id,
        entidad_nombre=str(ejemplar),
        descripcion=f'Ejemplar creado inline desde adquisición: "{libro.titulo}" ({ejemplar.sku})',
    )

    return JsonResponse({
        'ok': True,
        'ejemplar_id': ejemplar.id,
        'label': f'{libro.titulo} · {libro.autor} · {ejemplar.sku} · Stock actual: 0',
        'libro_titulo': libro.titulo,
        'libro_autor': libro.autor,
    })


@login_required
@admin_required
@require_http_methods(["GET", "POST"])
def inventariar_lote(request, adquisicion_id):
    """
    Permite agregar libros uno por uno a un lote cerrado (estado=por_inventariar).
    Cuando ya no hay más libros que registrar, el staff marca el lote como completado.
    """
    adquisicion = get_object_or_404(Adquisicion, pk=adquisicion_id)
    ejemplares = Ejemplar.objects.select_related('libro').order_by('libro__titulo', 'sku')
    categorias = Categoria.objects.all().order_by('nombre')

    if request.method == 'POST':
        accion = request.POST.get('accion')

        # Marcar lote como completado
        if accion == 'completar':
            adquisicion.estado = 'completado'
            adquisicion.save(update_fields=['estado', 'actualizado_en'])
            registrar_auditoria(
                actor=request.user, accion='editar', modulo='proveedores',
                entidad_tipo='adquisicion', entidad_id=adquisicion.id,
                entidad_nombre=f'Lote #{adquisicion.id}',
                descripcion=f'Lote #{adquisicion.id} marcado como completado.',
            )
            messages.success(request, f'Lote #{adquisicion.id} marcado como completado. ✅')
            return redirect('detalle_proveedor', proveedor_id=adquisicion.proveedor_id)

        # Agregar un renglon al lote
        ejemplar_id = request.POST.get('ejemplar_id', '').strip()
        cantidad_str = request.POST.get('cantidad', '').strip()
        costo_str = request.POST.get('costo_unitario', '').strip()

        try:
            ejemplar = Ejemplar.objects.get(pk=ejemplar_id)
        except Ejemplar.DoesNotExist:
            messages.error(request, 'Selecciona un libro válido.')
            return redirect('inventariar_lote', adquisicion_id=adquisicion_id)

        try:
            cantidad_int = int(cantidad_str)
            assert cantidad_int > 0
        except (ValueError, AssertionError):
            messages.error(request, 'La cantidad debe ser mayor a 0.')
            return redirect('inventariar_lote', adquisicion_id=adquisicion_id)

        try:
            costo_decimal = Decimal(costo_str)
            assert costo_decimal > 0
        except Exception:
            messages.error(request, 'El costo debe ser mayor a 0.')
            return redirect('inventariar_lote', adquisicion_id=adquisicion_id)

        with transaction.atomic():
            DetalleAdquisicion.objects.create(
                adquisicion=adquisicion,
                ejemplar=ejemplar,
                cantidad=cantidad_int,
                costo_unitario=costo_decimal,
            )

        messages.success(
            request,
            f'Se agregó «{ejemplar.libro.titulo}» (×{cantidad_int}) al lote. '
            f'Total acumulado: ${adquisicion.total:.2f}'
        )
        return redirect('inventariar_lote', adquisicion_id=adquisicion_id)

    context = {
        'adquisicion': adquisicion,
        'detalles': adquisicion.detalles.select_related('ejemplar__libro').order_by('creado_en'),
        'ejemplares': ejemplares,
        'categorias': categorias,
        'libro_form': LibroRapidoForm(),
        'ejemplar_form': EjemplarRapidoForm(),
    }
    return render(request, 'proveedores/inventariar_lote.html', context)
