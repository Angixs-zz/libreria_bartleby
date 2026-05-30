from django import forms

from inventario.models import Libro, Ejemplar, Categoria
from .models import Proveedor, Adquisicion
from utils.helpers import validar_nombre_humano, validar_telefono_mexico, validar_email_robusto


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = ['nombre', 'contacto', 'telefono', 'email', 'direccion', 'activo']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre comercial'}),
            'contacto': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Persona de contacto'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Teléfono'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@proveedor.com'}),
            'direccion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Dirección o referencias'}),
            'activo': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }



    def clean_telefono(self):
        telefono = self.cleaned_data.get('telefono')
        valido, resultado = validar_telefono_mexico(telefono)
        if not valido:
            raise forms.ValidationError(resultado)
        return resultado

    def clean_email(self):
        email = self.cleaned_data.get('email')
        valido, resultado = validar_email_robusto(email)
        if not valido:
            raise forms.ValidationError(resultado)
        return resultado


class AdquisicionForm(forms.ModelForm):
    class Meta:
        model = Adquisicion
        fields = ['proveedor', 'fecha', 'tipo', 'observaciones', 'cantidad_libros_lote', 'costo_lote']
        widgets = {
            'proveedor': forms.Select(attrs={'class': 'form-select'}),
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Notas del lote: factura, descripción de la caja, etc.'
            }),
            'cantidad_libros_lote': forms.NumberInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Ej. 50'
            }),
            'costo_lote': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'placeholder': '0.00'
            }),
        }


# ── Inline: crear libro + ejemplar desde el formulario de adquisición ─────────────────

class LibroRapidoForm(forms.ModelForm):
    """Crea o recupera un Libro por ISBN o título+autor desde el modal inline."""
    categoria_texto = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'list': 'categorias_rapidas_list',
            'placeholder': 'Escribe o crea una categoría',
        })
    )

    class Meta:
        model = Libro
        fields = [
            'isbn',
            'titulo',
            'autor',
            'editorial',
            'anio_publicacion',
            'descripcion',
            'portada',
        ]
        widgets = {
            'isbn':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ISBN-10 o ISBN-13 (opcional)'}),
            'titulo':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Título'}),
            'autor':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Autor'}),
            'editorial':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Editorial (opcional)'}),
            'anio_publicacion': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1000',
                'max': '2099',
                'placeholder': 'Ej. 2023',
            }),
            'descripcion': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Sinopsis o notas generales del libro',
            }),
            'portada': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }

    def clean_isbn(self):
        isbn = self.cleaned_data.get('isbn')
        if isbn:
            from utils.helpers import validar_isbn
            if not validar_isbn(isbn):
                raise forms.ValidationError('El ISBN no es válido. Debe tener 10 o 13 caracteres numéricos (el último de 10 dígitos puede ser X).')
        return isbn


class EjemplarRapidoForm(forms.ModelForm):
    """Crea el ejemplar (condición + precio venta) desde el modal inline."""
    class Meta:
        model = Ejemplar
        fields = ['estado_fisico', 'precio_venta', 'descripcion_estado']
        widgets = {
            'estado_fisico':     forms.Select(attrs={'class': 'form-select'}),
            'precio_venta':      forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
            'descripcion_estado': forms.Textarea(attrs={'class': 'form-control', 'rows': 2,
                                                         'placeholder': 'Detalles opcionales del estado físico'}),
        }
