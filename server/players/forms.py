from django.contrib.auth.forms import UserCreationForm
from .models import Player

class PlayerRegistrationForm(UserCreationForm):
    class Meta(UserCreationForm.Meta):
        model = Player
        fields = ('username',)