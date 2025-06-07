from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from players import views as player_views
from game import views as game_views

urlpatterns = [
    path('', game_views.lobby_view, name='lobby'),
    path('admin/', admin.site.urls),

    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('register/', player_views.register_view, name='register'),

    path('game/', include(('game.urls', 'game'), namespace='game')),

    path('accounts/login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='account_login_duplicate_check'),
]