from django.apps import AppConfig

class GameConfig(AppConfig):
    name = 'game'
    
    def ready(self):
        from django.db.models.signals import post_save
        from .models import GameRoom
        
        def handle_game_end(sender, instance, **kwargs):
            if instance.status == 'finished':
                # Отправка уведомлений, аналитика и т.д.
                pass
                
        post_save.connect(handle_game_end, sender=GameRoom)