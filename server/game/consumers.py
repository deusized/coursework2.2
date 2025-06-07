import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import GameRoom
import logging

logger = logging.getLogger(__name__)


class GameRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.user = self.scope['user']
        
        if not self.user.is_authenticated:
            await self.close()
            return

        await self.channel_layer.group_add(
            f"game_{self.room_id}",
            self.channel_name
        )
        await self.accept()
        await self.update_activity()
        await self.check_room_status()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            f"game_{self.room_id}",
            self.channel_name
        )
        await self.check_room_status()

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data.get('type') == 'ping':
            await self.update_activity()
            await self.send(text_data=json.dumps({'type': 'pong'}))

    @database_sync_to_async
    def update_activity(self):
        room = GameRoom.objects.get(id=self.room_id)
        room.last_activity = timezone.now()
        room.save()

    @database_sync_to_async
    def check_room_status(self):
        room = GameRoom.objects.get(id=self.room_id)
        active_players = room.players.count()  # В реальности нужно проверять активные WebSocket соединения
        
        if active_players == 0:
            # Удаляем комнату если нет активных игроков 10 секунд
            if (timezone.now() - room.last_activity).total_seconds() > 10:
                room.delete()
                return 'deleted'
        
        elif active_players == room.max_players and room.status == 'waiting':
            room.start_game()
            return 'started'
        
        return 'active'

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'game_{self.room_id}'

        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get('action')

        if action == 'join':
            await self.handle_join(data)
        elif action == 'play_card':
            await self.handle_play_card(data)
        # ... другие действия

    async def handle_join(self, data):
        # Логика присоединения к игре
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'game_message',
                'message': {
                    'action': 'player_joined',
                    'player': data['player']
                }
            }
        )

    async def game_message(self, event):
        await self.send(text_data=json.dumps(event['message']))