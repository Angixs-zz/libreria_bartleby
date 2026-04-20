from django.db import models 
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class PerfilUsuario(models.Model):
    ROLES = [
        ('admin', 'Administrador'),
        ('cajero', 'Cajero'),
        ('cliente', 'Cliente'),
    ]

    # Vincula este perfil de forma única al usuario de Django
    usuario = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='perfil'
    )

    rol = models.CharField(
        max_length=20, 
        choices=ROLES, 
        default='cliente'
    )

    telefono = models.CharField(max_length=20, blank=True)
    direccion = models.TextField(blank=True)

    # --- NUEVO CAMPO PARA CÓDIGO DE VERIFICACIÓN ---
    codigo_verificacion = models.CharField(
        max_length=6,
        blank=True,
        null=True
    )

    def __str__(self):
        return f"{self.usuario.username} — {self.get_rol_display()}"

    class Meta:
        verbose_name_plural = "Perfiles de Usuario"


class NotaClienteInterna(models.Model):
    cliente = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='notas_internas',
    )
    autor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='notas_clientes_creadas',
    )
    contenido = models.TextField()
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Nota para {self.cliente.username} ({self.creado_en:%d/%m/%Y %H:%M})"

    class Meta:
        verbose_name_plural = "Notas internas de clientes"
        ordering = ['-creado_en']


class EventoAuditoria(models.Model):
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='eventos_auditoria',
    )
    accion = models.CharField(max_length=30)
    modulo = models.CharField(max_length=40)
    entidad_tipo = models.CharField(max_length=40)
    entidad_id = models.PositiveIntegerField(null=True, blank=True)
    entidad_nombre = models.CharField(max_length=255, blank=True)
    descripcion = models.TextField()
    metadata = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.modulo}:{self.accion} - {self.entidad_tipo} #{self.entidad_id or '-'}"

    class Meta:
        verbose_name_plural = "Eventos de auditoria"
        ordering = ['-creado_en']


# --- SEÑALES PARA AUTOMATIZAR LA CREACIÓN DEL PERFIL ---

@receiver(post_save, sender=User)
def crear_perfil_usuario(sender, instance, created, **kwargs):
    """Crea un perfil automáticamente cuando se crea un nuevo User."""
    if created:
        rol_asignado = 'admin' if instance.is_superuser else 'cliente'
        PerfilUsuario.objects.create(
            usuario=instance,
            rol=rol_asignado
        )


@receiver(post_save, sender=User)
def guardar_perfil_usuario(sender, instance, **kwargs):
    """Guarda el perfil automáticamente cuando se guarda el User."""
    instance.perfil.save()
