from django import forms

from inventario.models import Libro, Ejemplar, Categoria
from .models import Proveedor, Adquisicion


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


class AdquisicionForm(forms.ModelForm):
    class Meta:
        model = Adquisicion
        fields = ['proveedor', 'fecha', 'tipo', 'observaciones']
        widgets = {
            'proveedor': forms.Select(attrs={'class': 'form-select'}),
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'observaciones': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 2,
                'placeholder': 'Notas del lote: costo total, factura, descripción de la caja, etc.'
            }),
        }


# ── Inline: crear libro + ejemplar desde el formulario de adquisición ─────────────────

class LibroRapidoForm(forms.ModelForm):
    """Crea o recupera un Libro por ISBN o título+autor desde el modal inline."""
    class Meta:
        model = Libro
        fields = ['isbn', 'titulo', 'autor', 'editorial', 'categoria']
        widgets = {
            'isbn':     forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ISBN-10 o ISBN-13 (opcional)'}),
            'titulo':   forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Título'}),
            'autor':    forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Autor'}),
            'editorial':  forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Editorial (opcional)'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
        }


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
