from __future__ import annotations
import random
import os
from django.conf import settings
from django.db import transaction
from .models import Game, GameRoom
from players.models import Player
import typing
import logging

logger = logging.getLogger(__name__)

class DurakGame:
    def __init__(self, room: GameRoom):
        self.room = room
        self.game_model_instance: typing.Optional[Game] = None
        self.players: list[Player] = list(room.players.all().order_by('id'))
        
        self.player_hands_data: dict[str, list[dict]] = {str(p.id): [] for p in self.players}
        self.deck: list[dict] = []
        self.trump_suit: typing.Optional[str] = None
        self.trump_card_revealed: typing.Optional[dict] = None
        self.table: list[dict] = []
        self.attacker_index: int = 0
        self.defender_index: int = (self.attacker_index + 1) % len(self.players) if self.players else 0
        
        self._load_game_state_if_exists()

    def _generate_deck(self) -> list[dict]:
        suits = ['hearts', 'diamonds', 'clubs', 'spades']
        ranks = ['6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = [{'rank': rank, 'suit': suit, 'id': f"{rank}-{suit}"} for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck

    def _load_game_state_if_exists(self):
        """Loads game state from the database if a Game record exists for this room."""
        try:
            self.game_model_instance = Game.objects.get(room=self.room)
            self.deck = list(self.game_model_instance.deck)
            self.trump_suit = self.game_model_instance.trump_suit
            self.table = list(self.game_model_instance.table)
            self.player_hands_data = dict(self.game_model_instance.player_hands)
            self.trump_card_revealed = self.game_model_instance.trump_card_revealed

            if self.game_model_instance.current_turn:
                try:
                    current_turn_user_id = self.game_model_instance.current_turn.id
                    self.attacker_index = next(i for i, p in enumerate(self.players) if p.id == current_turn_user_id)
                except (StopIteration, AttributeError):
                    logger.warning(f"Current turn player {self.game_model_instance.current_turn_id} not found in room {self.room.id} players. Re-determining attacker.")
                    self._set_initial_attacker_defender()
            else:
                self._set_initial_attacker_defender() 
            
            self.defender_index = (self.attacker_index + 1) % len(self.players) if self.players else 0

            for player_user in self.players:
                if str(player_user.id) not in self.player_hands_data:
                    self.player_hands_data[str(player_user.id)] = []
            logger.info(f"DurakGame state loaded from DB for room {self.room.id}")

        except Game.DoesNotExist:
            logger.info(f"No existing Game model for room {self.room.id}. DurakGame in pre-init state.")
            pass

    def initialize_new_game_setup(self):
        if self.game_model_instance:
            logger.warning(f"initialize_new_game_setup called for room {self.room.id}, but Game model already exists. Skipping.")
            return

        min_players = getattr(self.room, 'min_players_for_start', 2) 
        if not self.players or len(self.players) < min_players:
             logger.error(f"Not enough players ({len(self.players)}) to initialize game for room {self.room.id}. Needs {min_players}.")
             return

        logger.info(f"Initializing new game setup for room {self.room.id} with {len(self.players)} players.")
        self.deck = self._generate_deck()
        self.player_hands_data = {str(p.id): [] for p in self.players}
        
        self._initialize_hands_and_trump()
        self._set_initial_attacker_defender()
        
        self.game_model_instance = Game.objects.create(
            room=self.room,
            status=GameRoom.STATUS_PLAYING,
        )
        self.save_game_state()
        logger.info(f"New game setup complete and saved for room {self.room.id}. Trump: {self.trump_suit}. Attacker: {self.players[self.attacker_index].username if self.players else 'N/A'}")


    def _set_initial_attacker_defender(self):
        if not self.players:
            self.attacker_index = 0
            self.defender_index = 0
            return

        min_trump_holder_idx = -1
        min_trump_value = 100

        hands_are_populated = any(self.player_hands_data.values())

        if self.trump_suit and hands_are_populated:
            for idx, player_user in enumerate(self.players):
                player_hand = self._get_player_hand(player_user)
                for card in player_hand:
                    if card.get('suit') == self.trump_suit:
                        card_val = self.card_value(card.get('rank', ''))
                        if card_val < min_trump_value:
                            min_trump_value = card_val
                            min_trump_holder_idx = idx
        
        if min_trump_holder_idx != -1:
            self.attacker_index = min_trump_holder_idx
        else:
            self.attacker_index = 0 

        self.defender_index = (self.attacker_index + 1) % len(self.players) if self.players else 0


    def _initialize_hands_and_trump(self):
        """Deals initial cards to players and determines the trump card and suit."""
        if not self.players or not self.deck:
            logger.warning("Cannot initialize hands/trump: no players or empty deck.")
            return

        for _ in range(6):
            for player_user in self.players: 
                if self.deck: 
                    card = self.deck.pop(0)
                    self.player_hands_data.setdefault(str(player_user.id), []).append(card)
                else:
                    logger.warning("Deck ran out of cards during initial deal.")
                    break
            if not self.deck:
                break
        
        if self.deck: 
            self.trump_card_revealed = self.deck[0] 
            self.trump_suit = self.trump_card_revealed['suit']
        elif self.player_hands_data and any(self.player_hands_data.values()):
            logger.warning(f"Deck empty after initial deal for room {self.room.id}. Trump may not be set from deck.")
            if not self.trump_suit: 
                 logger.error(f"CRITICAL: No trump suit could be determined for room {self.room.id}")
        else: 
            self.trump_suit = None
            self.trump_card_revealed = None
            logger.error(f"Cannot determine trump: deck empty and no cards dealt for room {self.room.id}.")


    def _get_player_hand(self, player_user_obj: Player) -> list[dict]:
        return self.player_hands_data.get(str(player_user_obj.id), [])

    def _remove_card_from_hand(self, player_user_obj: Player, card_index_in_hand: int) -> typing.Optional[dict]:
        hand = self._get_player_hand(player_user_obj)
        if 0 <= card_index_in_hand < len(hand):
            removed_card = hand.pop(card_index_in_hand)
            return removed_card
        logger.warning(f"Invalid card index {card_index_in_hand} for hand of player {player_user_obj.id}")
        return None
    
    def _add_cards_to_hand(self, player_user_obj: Player, cards_to_add: list[dict]):
        hand = self._get_player_hand(player_user_obj)
        hand.extend(cards_to_add)


    def card_value(self, rank_str: str) -> int:
        values = {'6': 6, '7': 7, '8': 8, '9': 9, '10': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
        return values.get(rank_str.upper(), 0)

    def _can_beat(self, attack_card: dict, defense_card: dict, trump_suit: typing.Optional[str]) -> bool:
        if not trump_suit: 
            logger.error("Cannot determine beat: trump_suit is None.")
            return defense_card['suit'] == attack_card['suit'] and \
                   self.card_value(defense_card['rank']) > self.card_value(attack_card['rank'])

        if defense_card['suit'] == attack_card['suit']:
            return self.card_value(defense_card['rank']) > self.card_value(attack_card['rank'])
        elif defense_card['suit'] == trump_suit and attack_card['suit'] != trump_suit:
            return True
        return False

    def attack(self, attacking_player_user: Player, card_indices: list[int]) -> dict:
        if not self.game_model_instance or self.game_model_instance.status != GameRoom.STATUS_PLAYING:
            return {'success': False, 'message': "Игра не активна."}
        if not self.players or attacking_player_user != self.players[self.attacker_index]:
            return {'success': False, 'message': "Сейчас не ваш ход для атаки."}

        if not card_indices:
            return {'success': False, 'message': "Нужно выбрать карты для атаки."}

        attacker_hand = list(self._get_player_hand(attacking_player_user)) 
        cards_to_play_objects = []
        for idx in sorted(card_indices, reverse=True): 
            if 0 <= idx < len(attacker_hand):
                cards_to_play_objects.insert(0, attacker_hand[idx]) 
            else:
                return {'success': False, 'message': f"Неверный индекс карты: {idx}."}
        
        if not cards_to_play_objects: 
            return {'success': False, 'message': "Не выбрано ни одной валидной карты."}

        defender_user = self.players[self.defender_index]
        defender_hand_count = len(self._get_player_hand(defender_user))
        
        unbeaten_attack_cards_on_table = [pair['attack_card'] for pair in self.table if not pair.get('defense_card')]
        
        if not self.table or not unbeaten_attack_cards_on_table: 
            if not all(c['rank'] == cards_to_play_objects[0]['rank'] for c in cards_to_play_objects):
                return {'success': False, 'message': "Для первой атаки все карты должны быть одного ранга."}
            if len(cards_to_play_objects) > defender_hand_count and defender_hand_count > 0 : 
                 return {'success': False, 'message': f"Нельзя атаковать большим количеством карт ({len(cards_to_play_objects)}), чем есть у защищающегося ({defender_hand_count})."}
            if len(cards_to_play_objects) > 6:
                 return {'success': False, 'message': "Нельзя атаковать более чем 6 картами за раунд."}
        else: 
            if len(self.table) + len(cards_to_play_objects) > 6:
                return {'success': False, 'message': "Слишком много карт на столе (максимум 6)."}
            
            allowed_ranks_for_throw_in = set()
            for pair_on_table in self.table:
                allowed_ranks_for_throw_in.add(pair_on_table['attack_card']['rank'])
                if pair_on_table.get('defense_card'):
                    allowed_ranks_for_throw_in.add(pair_on_table['defense_card']['rank'])
            
            logger.debug(f"Room {self.room.id} - Attempting to throw in. Allowed ranks: {allowed_ranks_for_throw_in}")
            logger.debug(f"Room {self.room.id} - Cards to throw in: {[c['rank'] for c in cards_to_play_objects]}")

            if not all(c['rank'] in allowed_ranks_for_throw_in for c in cards_to_play_objects):
                return {'success': False, 'message': "Карты для подкидывания должны совпадать по рангу с картами на столе."}
            
            max_throw_in = defender_hand_count - len(unbeaten_attack_cards_on_table)
            if len(cards_to_play_objects) > max_throw_in and max_throw_in >= 0:
                 return {'success': False, 'message': f"Нельзя подкинуть больше карт ({len(cards_to_play_objects)}), чем может отбить защищающийся ({max_throw_in}). Защитнику не хватит карт."}
            if max_throw_in < 0 and len(cards_to_play_objects) > 0: 
                return {'success': False, 'message': "Защищающемуся уже не хватает карт отбиться, нельзя подкидывать."}

        played_cards_count = 0
        for card_idx_to_remove in sorted(card_indices, reverse=True):
            removed_card = self._remove_card_from_hand(attacking_player_user, card_idx_to_remove)
            if removed_card:
                self.table.append({'attack_card': removed_card, 'defense_card': None, 'attacker_id': attacking_player_user.id})
                played_cards_count += 1
            else:
                logger.error(f"Failed to remove card at index {card_idx_to_remove} for attack by {attacking_player_user.id}")
                return {'success': False, 'message': "Внутренняя ошибка: не удалось корректно снять карту с руки."}
        
        if played_cards_count == 0 and card_indices: 
             return {'success': False, 'message': "Не удалось сыграть выбранные карты."}

        self.save_game_state()
        return {'success': True, 'message': "Атака совершена."}


    def defend(self, defending_player_user: Player, attack_card_table_index: int, defense_card_hand_index: int) -> dict:
        if not self.game_model_instance or self.game_model_instance.status != GameRoom.STATUS_PLAYING:
            return {'success': False, 'message': "Игра не активна."}
        if not self.players or defending_player_user != self.players[self.defender_index]:
            return {'success': False, 'message': "Сейчас не ваш ход для защиты."}
        
        if not (0 <= attack_card_table_index < len(self.table)):
            return {'success': False, 'message': "Неверный индекс атакующей карты на столе."}

        table_pair = self.table[attack_card_table_index]
        if table_pair.get('defense_card'):
            return {'success': False, 'message': "Эта карта уже отбита."}

        attack_card = table_pair['attack_card']
        
        defender_hand = self._get_player_hand(defending_player_user)
        if not (0 <= defense_card_hand_index < len(defender_hand)):
            return {'success': False, 'message': "Неверный индекс карты в руке для защиты."}
        
        defense_card_obj = defender_hand[defense_card_hand_index] 

        if self._can_beat(attack_card, defense_card_obj, self.trump_suit):
            removed_defense_card = self._remove_card_from_hand(defending_player_user, defense_card_hand_index)
            if removed_defense_card: 
                table_pair['defense_card'] = removed_defense_card
                table_pair['defender_id'] = defending_player_user.id 
                self.save_game_state()
                return {'success': True, 'message': "Карта отбита."}
            else:
                 logger.error(f"Internal error removing defense card for player {defending_player_user.id}")
                 return {'success': False, 'message': "Внутренняя ошибка при удалении карты защиты."}
        else:
            return {'success': False, 'message': "Этой картой нельзя отбиться."}

    def _deal_cards_after_round(self):
        if not self.game_model_instance or self.game_model_instance.status != GameRoom.STATUS_PLAYING:
            return
        
        players_involved_in_round_needing_cards: list[Player] = []
        
        attacker_user = self.players[self.attacker_index]
        if len(self._get_player_hand(attacker_user)) < 6:
            players_involved_in_round_needing_cards.append(attacker_user)

        thrower_ids_in_table = set()
        for pair in self.table: 
            if 'attacker_id' in pair and pair['attacker_id'] != attacker_user.id:
                thrower_ids_in_table.add(pair['attacker_id'])
        
        for p_user in self.players: 
            if p_user.id in thrower_ids_in_table and p_user not in players_involved_in_round_needing_cards:
                 if len(self._get_player_hand(p_user)) < 6:
                    try:
                        player_instance = p_user 
                        players_involved_in_round_needing_cards.append(player_instance)
                    except Player.DoesNotExist:
                        logger.error(f"Player with ID {p_user.id} not found for dealing cards.")


        defender_user = self.players[self.defender_index]
        if not self.table: 
            if len(self._get_player_hand(defender_user)) < 6 and defender_user not in players_involved_in_round_needing_cards:
                players_involved_in_round_needing_cards.append(defender_user)

        for player_to_deal in players_involved_in_round_needing_cards:
            hand = self._get_player_hand(player_to_deal)
            while len(hand) < 6 and self.deck:
                card = self.deck.pop(0)
                hand.append(card)


    def take_cards_action(self, taking_player_user: Player) -> dict:
        if not self.game_model_instance or self.game_model_instance.status != GameRoom.STATUS_PLAYING:
            return {'success': False, 'message': "Игра не активна."}
        if not self.players or taking_player_user != self.players[self.defender_index]:
            return {'success': False, 'message': "Только защищающийся игрок может взять карты."}
        
        if not self.table: 
             return {'success': False, 'message': "Нет карт на столе, чтобы взять."}

        cards_to_take_from_table = []
        for pair in self.table:
            cards_to_take_from_table.append(pair['attack_card'])
            if pair.get('defense_card'): 
                cards_to_take_from_table.append(pair['defense_card'])
        
        self._add_cards_to_hand(taking_player_user, cards_to_take_from_table)
        
        self.table = [] 
        self._deal_cards_after_round() 
        
        self.attacker_index = (self.defender_index + 1) % len(self.players)
        self.defender_index = (self.attacker_index + 1) % len(self.players)
        
        game_end_result = self._check_game_over_conditions()
        if game_end_result and game_end_result['game_over']:
            self.save_game_state(game_over_result=game_end_result)
            return {**game_end_result, 'message': game_end_result.get('message', "Игра завершена."), 'success': True}

        self.save_game_state()
        return {'success': True, 'message': "Карты взяты."}

    def pass_or_bito_action(self, acting_player_user: Player) -> dict:
        if not self.game_model_instance or self.game_model_instance.status != GameRoom.STATUS_PLAYING:
            return {'success': False, 'message': "Игра не активна."}
        
        if not self.table:
            return {'success': False, 'message': "Стол пуст, действие 'пас/бито' не применимо в данный момент."}

        all_cards_on_table_defended = all(pair.get('defense_card') for pair in self.table)

        if all_cards_on_table_defended: 
            self.table = [] 
            self._deal_cards_after_round() 

            game_end_result = self._check_game_over_conditions()
            if game_end_result and game_end_result['game_over']:
                self.save_game_state(game_over_result=game_end_result)
                return {**game_end_result, 'message': game_end_result.get('message', "Бито! Игра завершена."), 'success': True}

            self.attacker_index = self.defender_index
            self.defender_index = (self.attacker_index + 1) % len(self.players)
            
            self.save_game_state()
            return {'success': True, 'action_type': 'bito', 'message': "Бито! Раунд завершен."}
        else: 
            self.save_game_state() 
            return {'success': True, 'action_type': 'attacker_passed_round', 'message': "Атакующий(е) завершили добавление карт. Защищающийся должен отбить оставшиеся или взять."}


    def _check_game_over_conditions(self) -> typing.Optional[dict]:
        if not self.game_model_instance: 
            return None

        if not self.deck: 
            players_with_cards_count = 0
            last_player_with_cards: typing.Optional[Player] = None
            
            for player_user in self.players: 
                if self._get_player_hand(player_user): 
                    players_with_cards_count += 1
                    last_player_with_cards = player_user

            if players_with_cards_count == 0: 
                return {'game_over': True, 'is_draw': True, 'winner': None, 'loser': None, 'message': "Игра окончена! Ничья (все вышли одновременно)."}
            
            if players_with_cards_count == 1: 
                loser: typing.Optional[Player] = last_player_with_cards
                winner: typing.Optional[Player] = None
                
                if len(self.players) == 2: 
                    winner = next((p for p in self.players if p != loser), None)
                else: 
                    if self.room.winner and self.room.winner != loser:
                        winner = self.room.winner
                
                return {'game_over': True, 'is_draw': False, 'winner': winner, 'loser': loser, 
                        'message': f"Игра окончена! Проигравший: {loser.username if loser else 'N/A'}."}
        
        if self.deck: 
            for player_user in self.players: 
                if not self._get_player_hand(player_user) and not self.room.winner:
                    pass 

        return None 


    def get_game_state(self, for_player_user_obj: typing.Optional[Player] = None) -> dict:
        """Возвращает текущее состояние игры, видимое для конкретного игрока."""
        
        game_status_from_model = GameRoom.STATUS_WAITING 
        winner_username = self.room.winner.username if self.room.winner else None
        game_over_info = None 

        is_game_initialized = bool(self.game_model_instance)

        if is_game_initialized and self.game_model_instance:
            game_status_from_model = self.game_model_instance.status 
            game_over_info = self._check_game_over_conditions()
            if game_over_info and game_over_info['game_over']:
                game_status_from_model = GameRoom.STATUS_FINISHED 
                winner_obj_from_game_over = game_over_info.get('winner')
                if winner_obj_from_game_over: 
                    winner_username = winner_obj_from_game_over.username
                elif game_over_info.get('is_draw'):
                    winner_username = "Ничья"
        else: 
            game_status_from_model = self.room.status
        attacker_id = self.players[self.attacker_index].id if self.players and is_game_initialized else None
        defender_id = self.players[self.defender_index].id if self.players and is_game_initialized else None

        state = {
            'room_id': str(self.room.id),
            'players': [],
            'attacker_id': attacker_id,
            'defender_id': defender_id,
            'attacker_username': self.players[self.attacker_index].username if attacker_id else "N/A",
            'defender_username': self.players[self.defender_index].username if defender_id else "N/A",
            'trump_suit': self.trump_suit,
            'trump_card_revealed': self.trump_card_revealed, 
            'deck_count': len(self.deck),
            'table': list(self.table),
            'status': game_status_from_model, 
            'winner_username': winner_username, 
            'is_game_over': game_over_info['game_over'] if game_over_info else False,
            'game_over_message': game_over_info.get('message') if game_over_info else None,
            'is_game_initialized': is_game_initialized,
        }

        for idx, p_user_loop in enumerate(self.players):
            hand_cards = self._get_player_hand(p_user_loop) 
            
            player_data = {
                'id': p_user_loop.id,
                'username': p_user_loop.username,
                'card_count': len(hand_cards),
                'is_current_player_for_state': p_user_loop == for_player_user_obj,
                'cards': [] 
            }

            if is_game_initialized and (p_user_loop == for_player_user_obj or game_status_from_model == GameRoom.STATUS_FINISHED):
                
                player_data['cards'] = []
                for card_idx_in_hand, card_in_hand in enumerate(hand_cards):
                     card_data_to_append = {
                        'rank': card_in_hand['rank'],
                        'suit': card_in_hand['suit'],
                        'id': card_in_hand.get('id', f"{card_in_hand['rank']}-{card_in_hand['suit']}"), 
                        'image_url': self._get_card_image_url(card_in_hand),
                        'hand_index': card_idx_in_hand
                    }
                     player_data['cards'].append(card_data_to_append)
            
            state['players'].append(player_data)
        
        if is_game_initialized:
            for table_pair_in_state in state['table']: 
                if table_pair_in_state.get('attack_card'):
                    table_pair_in_state['attack_card']['image_url'] = self._get_card_image_url(table_pair_in_state['attack_card'])
                if table_pair_in_state.get('defense_card'):
                    table_pair_in_state['defense_card']['image_url'] = self._get_card_image_url(table_pair_in_state['defense_card'])
            
            if state['trump_card_revealed'] and isinstance(state['trump_card_revealed'], dict):
                state['trump_card_revealed']['image_url'] = self._get_card_image_url(state['trump_card_revealed'])

        return state


    def _get_card_image_url(self, card_dict: dict) -> str:
        if not card_dict or not card_dict.get('suit') or not card_dict.get('rank'):
            return os.path.join(settings.STATIC_URL, 'cards/back.png') 
        
        suit = card_dict['suit'].lower() 
        rank = card_dict['rank'].upper() 
        return f"{settings.STATIC_URL}cards/{suit}/{rank}.png"


    def save_game_state(self, game_over_result: typing.Optional[dict] = None):
        if not self.game_model_instance:
            logger.warning(f"Attempted to save game state for room {self.room.id}, but no Game model instance exists.")
            return 

        with transaction.atomic():
            game = self.game_model_instance 

            current_attacker_user: typing.Optional[Player] = self.players[self.attacker_index] if self.players and 0 <= self.attacker_index < len(self.players) else None
            game.current_turn = current_attacker_user
            game.trump_suit = self.trump_suit
            game.trump_card_revealed = self.trump_card_revealed
            game.deck = self.deck
            game.table = self.table
            game.player_hands = self.player_hands_data 

            is_game_truly_over = game_over_result and game_over_result.get('game_over', False)

            if is_game_truly_over:
                game.status = GameRoom.STATUS_FINISHED
                self.room.status = GameRoom.STATUS_FINISHED 
                
                winner_obj: typing.Optional[Player] = game_over_result.get('winner')
                loser_obj: typing.Optional[Player] = game_over_result.get('loser')  
                is_draw = game_over_result.get('is_draw', False)

                if hasattr(self.room, 'end_game_from_logic'): 
                    self.room.end_game_from_logic(winner=winner_obj, loser=loser_obj, is_draw=is_draw, final_pot_value=None) 
                elif hasattr(self.room, 'end_game'): 
                     self.room.end_game(winner=winner_obj) 
                else: 
                    if winner_obj and not self.room.winner: 
                        self.room.winner = winner_obj
                
                self.room.save(update_fields=['status', 'winner'] if winner_obj and not is_draw else ['status'])

            else: 
                game.status = GameRoom.STATUS_PLAYING
                self.room.status = GameRoom.STATUS_PLAYING
                if self.deck: 
                    for p_user in self.players: # p_user is Player
                        if not self._get_player_hand(p_user) and not self.room.winner:
                            self.room.winner = p_user 
                            logger.info(f"Player {p_user.username} is out of cards (deck not empty), marked as potential winner for room {self.room.id}.")
                            break 
                self.room.save(update_fields=['status', 'winner'] if self.room.winner else ['status'])
            
            game.save()