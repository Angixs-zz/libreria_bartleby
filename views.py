from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Libro, Categoria
from django.contrib.admin.views.decorators import staff_member_required

@staff_member_required
def agregar_libro(request):
    if request.method == 'POST':
        # Atrapamos todos los datos según tu modelo [cite: 105, 1409]
        titulo = request.POST.get('titulo')
        autor = request.POST.get('autor')
        isbn = request.POST.get('isbn', '')
        editorial = request.POST.get('editorial', '')
        categoria_id = request.POST.get('categoria')
        estado_fisico = request.POST.get('estado_fisico')
        descripcion_estado = request.POST.get('descripcion_estado', '') # Anotaciones, desgaste, etc. [cite: 106]
        precio_venta = request.POST.get('precio_venta')
        precio_compra = request.POST.get('precio_compra') # Para análisis de márgenes [cite: 487, 1691]
        stock = request.POST.get('stock', 1)
        portada = request.FILES.get('portada')

        try:
            # Buscamos la categoría real en la BD
            categoria_obj = Categoria.objects.get(id=categoria_id) if categoria_id else None
            
            # Guardamos el libro [cite: 18, 1641]
            Libro.objects.create(
                titulo=titulo,
                autor=autor,
                isbn=isbn,
                editorial=editorial,
                categoria=categoria_obj,
                estado_fisico=estado_fisico,
                descripcion_estado=descripcion_estado,
                precio_venta=precio_venta,
                precio_compra=precio_compra,
                stock=stock,
                portada=portada
            )
            messages.success(request, f'El ejemplar "{titulo}" ha sido catalogado exitosamente.')
            return redirect('agregar_libro')
        except Exception as e:
            messages.error(request, f'Hubo un error al guardar: {e}')

    # Pasamos las categorías al formulario para que el admin pueda elegirlas
    categorias = Categoria.objects.all()
    return render(request, 'inventario/agregar_libro.html', {'categorias': categorias})