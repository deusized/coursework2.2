from rest_framework import serializers
from .models import GameRoom, Game
from players.models import Player

class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = ['id', 'username', 'cash']

class GameRoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameRoom
        fields = '__all__'

class GameSerializer(serializers.ModelSerializer):
    players = PlayerSerializer(many=True)
    current_turn = PlayerSerializer()
    
    class Meta:
        model = Game
        fields = '__all__'