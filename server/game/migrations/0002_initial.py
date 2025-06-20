# Generated by Django 5.2.1 on 2025-06-10 22:20

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('game', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='current_turn',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='current_game_turns', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='gameroom',
            name='creator',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='created_rooms', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='gameroom',
            name='players',
            field=models.ManyToManyField(blank=True, related_name='joined_game_rooms', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='gameroom',
            name='winner',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='won_game_rooms', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='game',
            name='room',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='game_instance', to='game.gameroom'),
        ),
        migrations.AddField(
            model_name='playeractivity',
            name='player',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='playeractivity',
            name='room',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='game.gameroom'),
        ),
        migrations.AlterUniqueTogether(
            name='playeractivity',
            unique_together={('player', 'room')},
        ),
    ]
