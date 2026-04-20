"""
Modelos del inventario de la Librería Bartleby.

Estructura:
- Categoria: Categorías de libros
- Libro: Información genérica de un libro
- Ejemplar: Copia específica de un libro en inventario
"""

from django.db import models
from django.db.models import Count, Q, F, Sum
from utils.helpers import generar_sku_mejorado


class Categoria(models.Model):
    """Categoría de libros."""
    nombre = models.CharField(max_length=100, unique=True)
    
    def __str__(self):
        return self.nombre
    
    class Meta:
        verbose_name_plural = "Categorías"


class Libro(models.Model):
    """Información genérica de un libro."""
    titulo = models.CharField(max_length=200)
    autor = models.CharField(max_length=200)
    isbn = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        db_index=True,
        help_text="ISBN-10 o ISBN-13"
    )
    edicion = models.CharField(max_length=100, blank=True, null=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True)
    descripcion = models.TextField(blank=True, null=True)
    portada = models.ImageField(upload_to='portadas/', blank=True, null=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.titulo} - {self.autor}"
    
    class Meta:
        ordering = ['-creado_en']
        indexes = [
            models.Index(fields=['isbn']),
            models.Index(fields=['categoria']),
        ]

    @property
    def precio_referencia(self):
        """Obtiene el precio del primer ejemplar disponible."""
        ejemplar = self.ejemplares.first()
        return ejemplar.precio_venta if ejemplar else 0.00
    
    @property
    def total_ejemplares(self):
        """Cuenta total de ejemplares."""
        return self.ejemplares.count()
    
    @property
    def total_en_stock(self):
        """Suma total del stock de todos los ejemplares."""
        return self.ejemplares.aggregate(
            total=Sum('stock')
        )['total'] or 0


class Ejemplar(models.Model):
    """
    Copia específica de un libro en inventario.
    
    Cada ejemplar tiene su propio SKU, estado físico, y precio.
    """
    ESTADOS = (
        ('nuevo', 'Nuevo'),
        ('como_nuevo', 'Como nuevo'),
        ('bueno', 'Bueno'),
        ('aceptable', 'Aceptable'),
        ('con_detalles', 'Con detalles'),
    )
    
    libro = models.ForeignKey(
        Libro,
        on_delete=models.CASCADE,
        related_name='ejemplares'
    )
    sku = models.CharField(
        max_length=10,
        unique=True,
        default=generar_sku_mejorado,
        db_index=True,
        help_text="Identificador único del ejemplar"
    )
    estado_fisico = models.CharField(
        max_length=20,
        choices=ESTADOS,
        help_text="Condición física del ejemplar"
    )
    descripcion_estado = models.TextField(
        blank=True,
        null=True,
        help_text="Detalles adicionales del estado"
    )
    precio_compra = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text="Precio de adquisición"
    )
    precio_venta = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Precio de venta al público"
    )
    stock = models.PositiveIntegerField(
        default=1,
        help_text="Cantidad en inventario"
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.sku} | {self.libro.titulo} ({self.get_estado_fisico_display()}) - ${self.precio_venta}"
    
    class Meta:
        ordering = ['-creado_en']
        indexes = [
            models.Index(fields=['sku']),
            models.Index(fields=['libro']),
            models.Index(fields=['estado_fisico']),
        ]
        verbose_name = "Ejemplar"
        verbose_name_plural = "Ejemplares"
    
    @property
    def stock_disponible(self):
        """
        Calcula el stock disponible (no reservado).
        
        Obtiene todas las reservas pendientes y las substrae del stock actual.
        """
        from reservas.models import Reserva
        
        reservados_count = Reserva.objects.filter(
            ejemplares=self,
            estado='pendiente'
        ).count()
        
        return max(0, self.stock - reservados_count)
    
    @property
    def esta_agotado_real(self):
        """Verifica si realmente está agotado (stock_disponible <= 0)."""
        return self.stock_disponible <= 0