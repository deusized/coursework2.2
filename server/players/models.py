from django.contrib.auth.models import AbstractUser
from django.db import models

class Player(AbstractUser):
    cash = models.IntegerField(default=1000)
    current_room = models.ForeignKey(
        'game.GameRoom',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='current_players_in_room'
    )

    games_played = models.IntegerField(default=0)
    games_won = models.IntegerField(default=0)

    def __str__(self):
        return self.username

    @property
    def win_rate(self):
        return (self.games_won / self.games_played * 100) if self.games_played > 0 else 0

    def join_room(self, room):
        if self.current_room and self.current_room != room:
            return False, "Вы уже в другой комнате."

        if self.current_room == room:
            return True, "Вы уже в этой комнате."

        if room.players.count() >= room.max_players:
            return False, "Комната заполнена."

        self.current_room = room
        room.players.add(self)
        self.save()
        return True, "Успешно присоединились."

    def leave_room(self):
        """Выход из текущей комнаты. Этот метод может быть частью логики view."""
        if self.current_room:
            room = self.current_room
            room.players.remove(self)
            if self.current_room == room:
                self.current_room = None
            self.save()
            return True
        return False