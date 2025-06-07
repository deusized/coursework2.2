import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from game.models import GameRoom

class Command(BaseCommand):
    help = 'Deletes inactive game rooms'

    def handle(self, *args, **options):
        while True:
            inactive_rooms = GameRoom.objects.filter(
                last_activity__lt=timezone.now() - timezone.timedelta(seconds=10),
                players__isnull=True
            )
            count = inactive_rooms.count()
            inactive_rooms.delete()
            self.stdout.write(f"Deleted {count} inactive rooms")
            time.sleep(5)