from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0002_perfilusuario_codigo_verificacion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotaClienteInterna',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('contenido', models.TextField()),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('autor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='notas_clientes_creadas', to=settings.AUTH_USER_MODEL)),
                ('cliente', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notas_internas', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Notas internas de clientes',
                'ordering': ['-creado_en'],
            },
        ),
    ]
