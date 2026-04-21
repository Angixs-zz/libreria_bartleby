import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from inventario.models import Ejemplar, EstadoFisico

# Create the states based on ESTADOS choices
estados_map = dict(Ejemplar.ESTADOS)
for key, value in estados_map.items():
    EstadoFisico.objects.get_or_create(nombre=value)

# Update existing Ejemplares
for ejemplar in Ejemplar.objects.all():
    estado_display = estados_map.get(ejemplar.estado_fisico)
    if estado_display:
        nuevo_estado = EstadoFisico.objects.get(nombre=estado_display)
        ejemplar.nuevo_estado_fisico = nuevo_estado
        ejemplar.save()

print("Data migration completed successfully.")
