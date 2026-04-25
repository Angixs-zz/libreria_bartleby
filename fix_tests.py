import os
import re

files = [
    'usuarios/tests.py',
    'proveedores/tests.py',
    'reportes/tests.py',
    'inventario/tests.py',
    'ventas/tests.py',
    'reservas/tests.py',
]

for file in files:
    if not os.path.exists(file):
        continue
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace estado_fisico='nuevo' with estado_fisico=cls.estado_nuevo or similar
    # Actually, the easiest is to just use a property or create it in setUpTestData.
    # Let's import EstadoFisico at the top and replace estado_fisico='...' with EstadoFisico.objects.get_or_create(nombre='...')[0]
    
    if 'EstadoFisico' not in content:
        content = content.replace('from inventario.models import ', 'from inventario.models import EstadoFisico, ')
    
    content = re.sub(r"estado_fisico='([a-zA-Z_]+)'", r"estado_fisico=EstadoFisico.objects.get_or_create(nombre='\1')[0]", content)
    
    with open(file, 'w', encoding='utf-8') as f:
        f.write(content)
