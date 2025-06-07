from django.urls import path
from django.views.decorators.http import require_POST
from . import views

urlpatterns = [
    # Основные маршруты
    path('', views.lobby_view, name='lobby'),
    path('create/', views.create_room, name='create_room'),
    #path('find/', views.find_game, name='find_game'),
    path('join/<int:game_id>/', views.join_game, name='join_game'),
    path('<int:room_id>/', views.game_room, name='game_room'),
    
    # Управление игрой
    path('start/<int:room_id>/', views.start_game, name='start_game'),
    path('end/<int:room_id>/', 
         require_POST(views.end_game), 
         name='end_game'),
    path('leave/<int:room_id>/', views.leave_room, name='leave_room'),
    
    # API для игрового процесса
    path('status/<int:room_id>/', views.game_status, name='game_status'),
    path('ping/<int:room_id>/', views.ping, name='ping'),
    path('room/<int:room_id>/make_move/', views.make_move_view, name='make_move'),
]