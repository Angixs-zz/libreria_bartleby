"""
Comando management para cancelar automáticamente reservas vencidas.

Uso:
    python manage.py cancel_expired_reservations

Pensado para ejecutarse periodicamente con Celery beat o cron:
    celery -A config beat --loglevel=info
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from reservas.models import Reserva
from services.inventario_service import InventarioService


class Command(BaseCommand):
    help = 'Cancela automáticamente todas las reservas vencidas'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simula la cancelación sin hacer cambios'
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        
        # Contar reservas vencidas
        vencidas = Reserva.objects.filter(
            estado='pendiente',
            fecha_vencimiento__lt=timezone.now()
        )
        
        count = vencidas.count()
        
        if count == 0:
            self.stdout.write(
                self.style.SUCCESS('✓ No hay reservas vencidas para cancelar')
            )
            return
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f'[DRY-RUN] Se cancelarían {count} reserva(s):'
                )
            )
            for reserva in vencidas.select_related('usuario')[:10]:
                self.stdout.write(
                    f"  - Reserva #{reserva.id} - {reserva.usuario.username} "
                    f"(vence: {reserva.fecha_vencimiento})"
                )
            if count > 10:
                self.stdout.write(f"  ... y {count - 10} más")
            return
        
        # Cancelar efectivamente
        cancelled_count = InventarioService.cancelar_reservas_vencidas()
        
        self.stdout.write(
            self.style.SUCCESS(
                f'✓ Se cancelaron {cancelled_count} reserva(s) vencida(s)'
            )
        )
