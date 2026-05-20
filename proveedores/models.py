from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models, transaction
from django.db.models import Sum, F
from django.db.models.functions import Coalesce
from django.utils import timezone

from inventario.models import Ejemplar


class Proveedor(models.Model):
    nombre = models.CharField(max_length=200)
    contacto = models.CharField(max_length=200, blank=True, help_text="Nombre de la persona de contacto")
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    direccion = models.TextField(blank=True)
    activo = models.BooleanField(default=True)
    fecha_registro = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

    @property
    def gasto_total(self):
        return self.adquisiciones.aggregate(
            total=Coalesce(Sum('total'), Decimal('0.00'))
        )['total']

    class Meta:
        verbose_name_plural = "Proveedores"
        ordering = ['nombre']


class Adquisicion(models.Model):
    TIPO_CHOICES = [
        ('identificado', 'Identificado'),    # se saben los libros al momento de comprar
        ('lote_cerrado', 'Lote cerrado'),     # caja o bulto sin inventariar todavía
    ]
    ESTADO_CHOICES = [
        ('por_inventariar', 'Por inventariar'),
        ('completado', 'Completado'),
    ]
    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        related_name='adquisiciones'
    )
    tipo = models.CharField(
        max_length=20,
        choices=TIPO_CHOICES,
        default='identificado',
        help_text="Lote cerrado: cuando recibes una caja sin saber el contenido exacto"
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADO_CHOICES,
        default='completado',
    )
    fecha = models.DateField(default=timezone.localdate)
    observaciones = models.TextField(blank=True)
    codigo_lote = models.CharField(max_length=50, blank=True, null=True, unique=True, help_text="ID único del lote")
    cantidad_libros_lote = models.PositiveIntegerField(null=True, blank=True, help_text="Cantidad de libros en la caja (opcional)")
    costo_lote = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, help_text="Costo de la caja cerrada")
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    creado_por = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adquisiciones_registradas'
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Adquisicion {self.codigo_lote or '#'+str(self.id)} - {self.proveedor.nombre}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.codigo_lote:
            self.codigo_lote = f"LOT-{self.fecha.strftime('%y%m%d')}-{self.id:04d}"
            kwargs['force_insert'] = False
            super().save(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Adquisiciones"
        ordering = ['-fecha', '-creado_en']


class DetalleAdquisicion(models.Model):
    adquisicion = models.ForeignKey(
        Adquisicion,
        on_delete=models.CASCADE,
        related_name='detalles'
    )
    ejemplar = models.ForeignKey(
        Ejemplar,
        on_delete=models.PROTECT,
        related_name='adquisiciones'
    )
    cantidad = models.PositiveIntegerField(default=1)
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.cantidad}x {self.ejemplar.libro.titulo} - Adquisicion #{self.adquisicion_id}"

    @property
    def libro(self):
        return self.ejemplar.libro

    def save(self, *args, **kwargs):
        with transaction.atomic():
            incremento_stock = self.cantidad
            ejemplar_anterior_id = None
            cantidad_anterior = 0

            if self.pk:
                previo = DetalleAdquisicion.objects.select_for_update().get(pk=self.pk)
                ejemplar_anterior_id = previo.ejemplar_id
                cantidad_anterior = previo.cantidad

                if previo.ejemplar_id == self.ejemplar_id:
                    incremento_stock = self.cantidad - previo.cantidad
                else:
                    ejemplar_anterior = Ejemplar.objects.select_for_update().get(pk=previo.ejemplar_id)
                    ejemplar_anterior.stock = F('stock') - previo.cantidad
                    ejemplar_anterior.save(update_fields=['stock'])

            self.subtotal = self.cantidad * self.costo_unitario
            super().save(*args, **kwargs)

            ejemplar_actual = Ejemplar.objects.select_for_update().get(pk=self.ejemplar_id)
            ejemplar_actual.stock = F('stock') + incremento_stock
            ejemplar_actual.precio_compra = self.costo_unitario
            ejemplar_actual.save(update_fields=['stock', 'precio_compra'])

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            ejemplar = Ejemplar.objects.select_for_update().get(pk=self.ejemplar_id)
            ejemplar.stock = F('stock') - self.cantidad
            ejemplar.save(update_fields=['stock'])
            super().delete(*args, **kwargs)

    class Meta:
        verbose_name_plural = "Detalles de Adquisicion"
        ordering = ['creado_en']

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver


@receiver(post_save, sender=DetalleAdquisicion)
@receiver(post_delete, sender=DetalleAdquisicion)
def actualizar_total_adquisicion(sender, instance, **kwargs):
    adquisicion = instance.adquisicion
    adquisicion.total = adquisicion.detalles.aggregate(
        total=Coalesce(Sum('subtotal'), Decimal('0.00'))
    )['total']
    adquisicion.save(update_fields=['total', 'actualizado_en'])
