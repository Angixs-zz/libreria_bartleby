from django.db import models
from django.contrib.auth.models import User
from inventario.models import Libro, Ejemplar

class Venta(models.Model):
    METODOS_PAGO = [
        ('efectivo', 'Efectivo'),
        ('tarjeta', 'Tarjeta'),
        ('transferencia', 'Transferencia'),
    ]

    cajero = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='ventas_realizadas')
    cliente = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='compras_realizadas')
    fecha_venta = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    metodo_pago = models.CharField(max_length=20, choices=METODOS_PAGO, default='efectivo')
    ticket_pdf = models.FileField(upload_to='tickets/', null=True, blank=True)

    def __str__(self):
        return f"Ticket #{self.id} - {self.fecha_venta.strftime('%d/%m/%Y %H:%M')}"

    class Meta:
        verbose_name_plural = "Ventas"
        ordering = ['-fecha_venta']

class DetalleVenta(models.Model):
    """
    Detalle de cada ejemplar en una venta.
    
    Cambio importante: Ahora referencia Ejemplar específico (no Libro genérico).
    Esto permite rastrear qué ejemplar exacto se vendió.
    """
    venta = models.ForeignKey(Venta, on_delete=models.CASCADE, related_name='detalles')
    ejemplar = models.ForeignKey(
        Ejemplar,
        on_delete=models.PROTECT,
        help_text="Ejemplar específico vendido"
    )
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        help_text="Precio al momento de la venta"
    )
    subtotal = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Calcular subtotal automáticamente
        if not self.precio_unitario:
            self.precio_unitario = self.ejemplar.precio_venta
        
        self.subtotal = self.cantidad * self.precio_unitario
        super().save(*args, **kwargs)

    @property
    def libro(self):
        """Propiedad de conveniencia para acceder al libro."""
        return self.ejemplar.libro

    def __str__(self):
        return f"{self.cantidad}x {self.ejemplar.libro.titulo} ({self.ejemplar.sku}) - Venta #{self.venta.id}"

    class Meta:
        verbose_name_plural = "Detalles de Venta"
        ordering = ['-creado_en']
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum


# --- SEÑAL PARA ACTUALIZAR EL TOTAL DE LA VENTA ---

@receiver(post_save, sender=DetalleVenta)
@receiver(post_delete, sender=DetalleVenta)
def actualizar_total_venta(sender, instance, **kwargs):
    """
    Suma automáticamente todos los subtotales de los detalles
    y actualiza el Total del ticket principal.
    
    NOTA: El descuento de stock ahora se maneja en InventarioService
    para operaciones atómicas.
    """
    venta = instance.venta
    total_calculado = venta.detalles.aggregate(
        Sum('subtotal')
    )['subtotal__sum']
    
    venta.total = total_calculado if total_calculado else 0.00
    venta.save()