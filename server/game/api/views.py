from rest_framework.decorators import api_view
from rest_framework.response import Response
import models
import random
from django.contrib.auth.decorators import login_required

@api_view(['POST'])
@login_required
def create_game_api(request):
    try:
        new_game = models.GameRoom.objects.create(
            name=request.data.get('name', f"Игра {request.user.username}"),
            max_players=int(request.data.get('max_players', 2)),
            game_type=request.data.get('game_type', 'classic'),
            created_by=request.user
        )
        new_game.players.add(request.user)
        
        return Response({
            'success': True,
            'lobby_id': new_game.id,
            'message': 'Игра успешно создана'
        })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=400)

@api_view(['POST'])
def find_game(request):
    # Ищем случайную доступную игру
    available_games = models.GameRoom.objects.filter(
        players__lt=models.F('max_players'),
        is_active=False
    ).exclude(players=request.user)
    
    if available_games.exists():
        game = random.choice(available_games)
        game.players.add(request.user)
        return Response({
            'success': True,
            'room_id': game.id
        })
    else:
        return Response({
            'success': False,
            'error': 'Нет доступных игр'
        })

@api_view(['GET'])
def list_games(request):
    games = models.GameRoom.objects.filter(is_active=False).annotate(
        players_count=models.Count('players')
    ).values('id', 'name', 'players_count', 'max_players')
    
    return Response({
        'games': list(games)
    })

@api_view(['POST'])
def join_game(request, game_id):
    try:
        game = models.GameRoom.objects.get(id=game_id)
        if game.players.count() >= game.max_players:
            return Response({
                'success': False,
                'error': 'Комната заполнена'
            })
        
        game.players.add(request.user)
        return Response({
            'success': True
        })
    except models.GameRoom.DoesNotExist:
        return Response({
            'success': False,
            'error': 'Игра не найдена'
        }, status=404)