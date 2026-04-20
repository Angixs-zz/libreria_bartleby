import string
import random
from django.db import models
from django.contrib.auth.models import User
from inventario.models import Libro, Ejemplar
from django.utils import timezone
from datetime import timedelta


# 1. Función para el vencimiento (72 horas)
def vencimiento_default():
    return timezone.now() + timedelta(hours=72)


# 2. Función para generar el código (BART-XXXX)
def generar_codigo_unico():
    caracteres = string.ascii_uppercase + string.digits
    codigo_azar = ''.join(random.choice(caracteres) for _ in range(4))
    return f"BART-{codigo_azar}"


# 3. El modelo que usa las funciones de arriba
class Reserva(models.Model):
    ESTADOS = (
        ('pendiente', 'Pendiente de recolección'),
        ('completada', 'Completada (Entregada y pagada)'),
        ('cancelada', 'Cancelada (Tiempo expirado)'),
    )

    # max_length=15 da margen si en el futuro cambia el formato del código
    codigo_ticket = models.CharField(max_length=15, unique=True, default=generar_codigo_unico)
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    libros = models.ManyToManyField(Libro)
    # Relación directa con Ejemplar para control de stock
    ejemplares = models.ManyToManyField(Ejemplar, blank=True, related_name='reservas_activas')
    fecha_reserva = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateTimeField(default=vencimiento_default)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='pendiente')
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"Reserva #{self.id} - {self.usuario.username} - {self.get_estado_display()}"

    def is_expired(self):
        """True si ya pasó la fecha límite."""
        return timezone.now() > self.fecha_vencimiento

    @property
    def horas_restantes(self):
        """Horas enteras que quedan. Negativo si ya expiró."""
        delta = self.fecha_vencimiento - timezone.now()
        return int(delta.total_seconds() / 3600)

    @property
    def urgencia(self):
        """'verde', 'amarillo' o 'rojo' para el código de colores del panel."""
        h = self.horas_restantes
        if h > 24:
            return 'verde'
        elif h > 6:
            return 'amarillo'
        else:
            return 'rojo'

    @property
    def fecha_vencimiento_iso(self):
        """Fecha en formato ISO 8601 para usar en JS sin problemas de timezone."""
        return self.fecha_vencimiento.isoformat()

    class Meta:
        verbose_name_plural = "Reservas y Apartados"
        ordering = ['-fecha_reserva']