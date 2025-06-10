from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.urls import reverse
from django.db import transaction, models
from django.db.models import Count
from django.contrib import messages
from django.forms import Form, IntegerField, CharField
from .models import GameRoom, PlayerActivity
from players.models import Player
from .game_logic import DurakGame
import logging
import json
logger = logging.getLogger(__name__)

class CreateRoomForm(Form):
    name = CharField(max_length=50, label="Название комнаты (необязательно)", required=False)
    max_players = IntegerField(min_value=2, max_value=4, label="Количество игроков")
    bet_amount = IntegerField(min_value=0, label="Ставка")

@login_required
def lobby_view(request):
    rooms = GameRoom.objects.filter(status=GameRoom.STATUS_WAITING)\
                            .annotate(players_count=Count('players'))\
                            .filter(players_count__lt=models.F('max_players'))\
                            .exclude(players=request.user)\
                            .order_by('-created_at')[:20]

    context = {
        'rooms': rooms,
        'user_balance': request.user.cash,
    }
    return render(request, 'game/lobby.html', context)

@login_required
def create_room(request):
    if request.method == 'POST':
        form = CreateRoomForm(request.POST)
        if form.is_valid():
            max_players = form.cleaned_data['max_players']
            bet_amount = form.cleaned_data['bet_amount']
            name = form.cleaned_data.get('name')
            if not name:
                name = f"Игра {request.user.username}"

            if bet_amount > request.user.cash:
                messages.error(request, 'Недостаточно средств на счете для такой ставки.')
                return render(request, 'game/create_room.html', {
                    'form': form,
                    'max_players_range': range(2, 5),
                    'max_bet': request.user.cash,
                })

            if GameRoom.objects.filter(players=request.user, status__in=[GameRoom.STATUS_WAITING, GameRoom.STATUS_PLAYING]).exists():
                messages.error(request, 'Вы уже находитесь в другой игре или ожидаете ее начала.')
                return redirect('game:lobby')

            try:
                with transaction.atomic():
                    room = GameRoom.objects.create(
                        name=name,
                        creator=request.user,
                        max_players=max_players,
                        bet_amount=bet_amount,
                        status=GameRoom.STATUS_WAITING
                    )
                    room.players.add(request.user)
                    
                    request.user.current_room = room
                    if bet_amount > 0:
                        request.user.cash -= bet_amount
                    request.user.save(update_fields=['cash', 'current_room'])
                    
                    PlayerActivity.objects.create(
                        player=request.user,
                        room=room,
                        is_active=True
                    )
                    
                    messages.success(request, f'Комната "{room.name}" успешно создана!')
                    return redirect('game:game_room', room_id=room.id)
            except Exception as e:
                logger.error(f"Ошибка при создании комнаты пользователем {request.user.username}: {e}")
                messages.error(request, "Произошла ошибка при создании комнаты. Попробуйте позже.")
                return render(request, 'game/create_room.html', {
                    'form': form,
                    'max_players_range': range(2, 5),
                    'max_bet': request.user.cash,
                })
        else:
            messages.error(request, "Пожалуйста, исправьте ошибки в форме.")
    else:
        form = CreateRoomForm()

    context = {
        'form': form,
        'max_players_range': range(2, 5),
        'max_bet': request.user.cash,
    }
    return render(request, 'game/create_room.html', context)


@login_required
@transaction.atomic
def join_game(request, game_id):
    if request.method != 'POST':
        messages.error(request, "Неверный метод запроса для присоединения к игре.")
        return redirect('game:lobby')

    room = get_object_or_404(GameRoom, id=game_id)
    user = request.user

    if room.status != GameRoom.STATUS_WAITING:
        messages.error(request, 'Игра уже началась или завершена.')
        return redirect('game:lobby')
        
    if user in room.players.all():
        messages.info(request, 'Вы уже находитесь в этой комнате.')
        return redirect('game:game_room', room_id=room.id)
        
    if room.players.count() >= room.max_players:
        messages.error(request, 'Комната заполнена.')
        return redirect('game:lobby')
        
    if room.bet_amount > user.cash:
        messages.error(request, 'Недостаточно средств для входа в эту комнату.')
        return redirect('game:lobby')
    
    try:
        room.players.add(user)
        user.current_room = room
        
        if room.bet_amount > 0:
            user.cash -= room.bet_amount
        user.save(update_fields=['cash', 'current_room'])
        
        PlayerActivity.objects.update_or_create(
            player=user, room=room,
            defaults={'is_active': True, 'last_ping': timezone.now()}
        )
        
        messages.success(request, f'Вы успешно присоединились к комнате "{room.name}"!')
        
        game_started_auto = False
        if room.players.count() >= room.max_players:
            # room.start_game() is a method on GameRoom model
            # It should handle DurakGame initialization and card dealing.
            if room.start_game(): 
                game_started_auto = True
                messages.info(request, "Комната заполнена, игра начинается!")
            else:
                # start_game might fail if, e.g., min_players not met (though max_players implies min met)
                # or some other internal error during game setup.
                messages.error(request, "Не удалось автоматически начать игру, хотя комната заполнена.")
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': 'Вы успешно присоединились к игре!',
                'redirect_url': reverse('game:game_room', args=[room.id]),
                'game_started': game_started_auto
            })
        
        return redirect('game:game_room', room_id=room.id)
        
    except Exception as e:
        logger.error(f"Ошибка при присоединении пользователя {user.username} к комнате {room.id}: {str(e)}")
        messages.error(request, "Произошла ошибка при присоединении к комнате.")
        return redirect('game:lobby')


@login_required
def game_room(request, room_id):
    try:
        room = GameRoom.objects.select_related('creator').prefetch_related('players').get(id=room_id)
    except GameRoom.DoesNotExist:
        messages.error(request, "Игровая комната не найдена.")
        return redirect('game:lobby') # Or raise Http404
    
    user = request.user
    if user not in room.players.all():
        messages.error(request, "Вы не являетесь участником этой игры.")
        return redirect('game:lobby')
    
    PlayerActivity.objects.update_or_create(
        player=user, room=room,
        defaults={'is_active': True, 'last_ping': timezone.now()}
    )
    
    game_instance_logic = None
    game_state_for_template = None

    try:
        # DurakGame constructor will load existing game state if Game model exists for this room,
        # or will be in a pre-initialized state if not (e.g., waiting for start).
        game_instance_logic = DurakGame(room)
        game_state_for_template = game_instance_logic.get_game_state(for_player_user_obj=request.user)
    except Exception as e:
        logger.error(f"Ошибка при инициализации/загрузке DurakGame для комнаты {room.id}: {e}")
        messages.error(request, "Произошла ошибка при загрузке состояния игры.")
        # game_state_for_template will remain None or be a basic error state
        game_state_for_template = { # Fallback state
            'room_id': str(room.id), 
            'status': room.status, 
            'error': "Ошибка загрузки состояния игры"
        }


    context = {
        'room': room,
        'game_state': game_state_for_template,
        'is_creator': user == room.creator,
        'user_id_json': user.id,
        'room_id_json': str(room.id),
    }
    return render(request, 'game/game_room.html', context)


@login_required
@require_POST
def start_game(request, room_id):
    room = get_object_or_404(GameRoom, id=room_id)
    if request.user != room.creator:
        return JsonResponse({'success': False, 'error': 'Только создатель может начать игру.'}, status=403)
    
    if room.status != GameRoom.STATUS_WAITING:
        return JsonResponse({'success': False, 'error': 'Игра уже начата или завершена.'})
    
    if room.players.count() < getattr(room, 'min_players_for_start', 2):
        return JsonResponse({'success': False, 'error': f'Недостаточно игроков (минимум {getattr(room, "min_players_for_start", 2)}).'})
    
    if room.start_game():
        return JsonResponse({'success': True, 'message': 'Игра успешно начата!'})
    else:
        return JsonResponse({'success': False, 'error': 'Не удалось начать игру. Проверьте логи сервера.'})


@login_required
@require_POST
@transaction.atomic
def leave_room(request, room_id):
    room = get_object_or_404(GameRoom, id=room_id)
    user = request.user
    
    if user not in room.players.all():
        return JsonResponse({'success': False, 'error': 'Вы не в этой комнате.'}, status=403)
    
    try:
        returned_bet = False
        if room.status == GameRoom.STATUS_WAITING and room.bet_amount > 0:
            user.cash += room.bet_amount
            user.save(update_fields=['cash'])
            returned_bet = True
        
        room.players.remove(user)
        if user.current_room == room:
            user.current_room = None
            user.save(update_fields=['current_room'])

        PlayerActivity.objects.filter(player=user, room=room).delete()
        
        message = "Вы покинули комнату."
        if returned_bet:
            message += " Ваша ставка возвращена."

        room_canceled_by_leave = False
        if user == room.creator:
            if hasattr(room, 'cancel_game'): # Assumes cancel_game method on GameRoom model
                room.cancel_game() 
                room_canceled_by_leave = True
                message = 'Комната отменена, так как создатель вышел.'
            else: # Fallback if model method not present
                room.status = GameRoom.STATUS_CANCELLED 
                room.save(update_fields=['status'])
                # Basic refund if model method doesn't handle it
                for p in room.players.all(): # refund remaining players if creator leaves
                    if room.bet_amount > 0:
                        p.cash += room.bet_amount
                        p.save(update_fields=['cash'])
                if room.bet_amount > 0 and not returned_bet: # if creator's bet wasn't returned yet
                     user.cash += room.bet_amount
                     user.save(update_fields=['cash'])

        elif room.status == GameRoom.STATUS_WAITING and room.players.count() == 0:
            if hasattr(room, 'cancel_game'):
                room.cancel_game()
                room_canceled_by_leave = True # Or a different message
            else:
                room.status = GameRoom.STATUS_CANCELLED
                room.save(update_fields=['status'])
        
        if room.status == GameRoom.STATUS_PLAYING:
            # Handle player leaving mid-game. This might involve:
            # - Forfeiting the game for this player.
            # - Ending the game if too few players remain.
            # - Alerting other players.
            # This logic would typically be in DurakGame or GameRoom model.
            # For now, just logging.
            logger.info(f"Player {user.username} left active game room {room.id}. Game state might need update.")
            # Example: game_logic = DurakGame(room); game_logic.handle_player_quit(user);
            pass # Placeholder for more complex logic

        return JsonResponse({'success': True, 'message': message, 'room_canceled': room_canceled_by_leave})
    
    except Exception as e:
        logger.error(f"Ошибка при выходе пользователя {user.username} из комнаты {room.id}: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Ошибка сервера при выходе из комнаты.'}, status=500)


@login_required
@require_POST
@transaction.atomic
def end_game(request, room_id):
    room = get_object_or_404(GameRoom, id=room_id)
    
    if not (request.user == room.creator or request.user.is_staff):
        return JsonResponse({'success': False, 'error': 'У вас нет прав для завершения этой игры.'}, status=403)
    
    if room.status != GameRoom.STATUS_PLAYING:
        return JsonResponse({'success': False, 'error': 'Игра не находится в активном состоянии для завершения.'}, status=400)
    
    winner_id = request.POST.get('winner_id')
    winner = None
    if winner_id:
        try:
            winner = room.players.get(id=winner_id)
        except Player.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Указанный победитель не найден в этой комнате.'}, status=400)
    
    try:
        # Assumes end_game method on GameRoom model that updates balances, status etc.
        # and interacts with DurakGame if needed.
        if hasattr(room, 'end_game'):
            room.end_game(winner=winner) 
        else: # Basic fallback
            room.status = GameRoom.STATUS_FINISHED
            if winner:
                room.winner = winner
            # Pot distribution logic would be here if not in model method
            room.save()

        # Optionally, send a WebSocket message about game end
        return JsonResponse({
            'success': True,
            'message': f'Игра в комнате "{room.name}" завершена.',
            'winner_username': winner.username if winner else "Победитель не указан или ничья"
        })
    except Exception as e:
        logger.error(f"Ошибка при завершении игры {room.id} пользователем {request.user.username}: {str(e)}")
        return JsonResponse({'success': False, 'error': 'Внутренняя ошибка сервера при завершении игры.'}, status=500)


@login_required
def game_status(request, room_id):
    try:
        room = GameRoom.objects.select_related('creator').prefetch_related('players').get(id=room_id)
    except GameRoom.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Комната не найдена.'}, status=404)

    if request.user not in room.players.all():
        return JsonResponse({'success': False, 'error': 'Вы не участник этой игры.'}, status=403)
    
    game_state_data = None
    try:
        # DurakGame constructor handles loading or pre-init state.
        game_logic = DurakGame(room)
        game_state_data = game_logic.get_game_state(for_player_user_obj=request.user)
            
    except Exception as e:
        logger.error(f"Ошибка при получении статуса игры для комнаты {room.id}: {e}")
        return JsonResponse({'success': False, 'error': 'Ошибка при получении состояния игры.'}, status=500)
            
    return JsonResponse({'success': True, 'game_state': game_state_data})


@login_required
@require_POST
@transaction.atomic
def make_move_view(request, room_id):
    room = get_object_or_404(GameRoom, id=room_id)
    user = request.user

    if user not in room.players.all():
        return JsonResponse({'success': False, 'error': 'Вы не являетесь участником этой игры.'}, status=403)

    if room.status != GameRoom.STATUS_PLAYING:
        return JsonResponse({'success': False, 'error': 'Игра не активна.'}, status=400)

    try:
        data = json.loads(request.body)
        action_type = data.get('action_type')
        
        game_logic = DurakGame(room)

        if not game_logic.game_model_instance:
             logger.warning(f"make_move_view: Game model instance for room {room.id} not found/initialized in DurakGame.")
             return JsonResponse({'success': False, 'error': 'Состояние игры не найдено или не инициализировано в DurakGame.'}, status=500)

        response_data = {'success': False, 'message': 'Неизвестное действие или ошибка.'}

        if action_type == 'play_card':
            card_hand_index_str = data.get('card_hand_index')
            if card_hand_index_str is None:
                return JsonResponse({'success': False, 'error': 'Не указан индекс карты для хода.'}, status=400)
            try:
                card_hand_index = int(card_hand_index_str)
            except ValueError:
                 return JsonResponse({'success': False, 'error': 'Индекс карты должен быть числом.'}, status=400)
            
            result = game_logic.play_card(user, card_hand_index)
            response_data.update(result)
        
        elif action_type == 'attack':
            card_indices_str = data.get('card_indices') 
            if card_indices_str is None or not isinstance(card_indices_str, list):
                return JsonResponse({'success': False, 'error': 'Не указаны карты для атаки (ожидался список).'}, status=400)
            
            try:
                card_indices = [int(idx) for idx in card_indices_str]
                if not card_indices:
                    return JsonResponse({'success': False, 'error': 'Список карт для атаки пуст.'}, status=400)
                result = game_logic.attack(user, card_indices[0])
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Индексы карт должны быть числами.'}, status=400)
            response_data.update(result)

        elif action_type == 'defend':
            attack_card_table_index_str = data.get('attack_card_table_index')
            defense_card_hand_index_str = data.get('defense_card_hand_index')
            if attack_card_table_index_str is None or defense_card_hand_index_str is None:
                 return JsonResponse({'success': False, 'error': 'Не указаны карты для защиты.'}, status=400)
            try:
                attack_card_table_index = int(attack_card_table_index_str)
                defense_card_hand_index = int(defense_card_hand_index_str)
            except ValueError:
                return JsonResponse({'success': False, 'error': 'Индексы карт должны быть числами.'}, status=400)

            result = game_logic.defend(user, attack_card_table_index, defense_card_hand_index)
            response_data.update(result)

        elif action_type == 'pass_bito':
            result = game_logic.pass_or_bito_action(user)
            response_data.update(result)
            
        elif action_type == 'take':
            result = game_logic.take_cards_action(user)
            response_data.update(result)
        else:
            logger.warning(f"Неизвестный action_type '{action_type}' от пользователя {user.username} в комнате {room_id}")
            return JsonResponse({'success': False, 'error': 'Неизвестный тип действия.'}, status=400)

        return JsonResponse(response_data)

    except json.JSONDecodeError:
        logger.warning(f"Ошибка JSONDecodeError в make_move_view для комнаты {room_id}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Некорректный JSON в теле запроса.'}, status=400)
    except Exception as e:
        logger.error(f"Ошибка при обработке хода в комнате {room_id} игроком {user.username}: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': 'Внутренняя ошибка сервера при обработке хода.'}, status=500)

@login_required
@require_POST
def ping(request, room_id):
    try:
        room = GameRoom.objects.get(id=room_id)
    except GameRoom.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Комната не найдена'}, status=404)

    if not room.players.filter(id=request.user.id).exists():
        return JsonResponse({'success': False, 'error': 'Вы не участник этой комнаты.'}, status=403) 
    
    PlayerActivity.objects.update_or_create(
        player=request.user,
        room_id=room_id,
        defaults={'is_active': True, 'last_ping': timezone.now()}
    )

    return JsonResponse({'success': True, 'message': 'Ping successful'})