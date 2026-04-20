from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('usuarios', '0003_notaclienteinterna'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='EventoAuditoria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('accion', models.CharField(max_length=30)),
                ('modulo', models.CharField(max_length=40)),
                ('entidad_tipo', models.CharField(max_length=40)),
                ('entidad_id', models.PositiveIntegerField(blank=True, null=True)),
                ('entidad_nombre', models.CharField(blank=True, max_length=255)),
                ('descripcion', models.TextField()),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='eventos_auditoria', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Eventos de auditoria',
                'ordering': ['-creado_en'],
            },
        ),
    ]
