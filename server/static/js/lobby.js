$(document).ready(function() {
  // Функция для обновления списка игр
  function updateGamesList() {
      $.get('/game/list/', function(data) {
          $('#games-list').empty();
          if (data.games.length === 0) {
              $('#games-list').append('<div class="no-games">Нет активных игр</div>');
          } else {
              data.games.forEach(function(game) {
                  const gameItem = `
                      <div class="game-item">
                          <span>Игра #${game.id} (${game.players_count}/${game.max_players})</span>
                          <button class="join-game" data-game-id="${game.id}">Присоединиться</button>
                      </div>
                  `;
                  $('#games-list').append(gameItem);
              });
          }
      }).fail(function() {
          alert('Ошибка при загрузке списка игр');
      });
  }

  // Создание игры
  $('#create-lobby-btn').click(function() {
      const btn = $(this);
      btn.prop('disabled', true).text('Создание...');
      
      $.ajax({
          url: '/game/create/',
          method: 'POST',
          headers: {
              'X-CSRFToken': getCookie('csrftoken')
          },
          success: function(data) {
              if (data.success && data.redirect_url) {
                window.location.href = data.redirect_url;
              } else {
                  alert('Ошибка: ' + (data.error || 'Не удалось создать игру'));
                  btn.prop('disabled', false).text('Создать игру');
              }
          },
          error: function() {
              alert('Ошибка соединения');
              btn.prop('disabled', false).text('Создать игру');
          }
      });
  });

  // Поиск случайной игры
  $('#find-game-btn').click(function() {
      const btn = $(this);
      btn.prop('disabled', true).text('Поиск игры...');
      
      $.ajax({
          url: '/game/find/',
          method: 'POST',
          headers: {
              'X-CSRFToken': getCookie('csrftoken')
          },
          success: function(data) {
              if (data.success) {
                  window.location.href = '/game/' + data.room_id + '/';
              } else {
                  alert('Нет доступных игр. Создайте новую!');
                  btn.prop('disabled', false).text('Найти игру');
              }
          },
          error: function() {
              alert('Ошибка соединения');
              btn.prop('disabled', false).text('Найти игру');
          }
      });
  });

  // Обработка присоединения к игре (делегирование событий)
  $('#games-list').on('click', '.join-game', function() {
      const gameId = $(this).data('game-id');
      const btn = $(this);
      btn.prop('disabled', true).text('Вход...');
      
      $.ajax({
          url: '/game/join/' + gameId + '/',
          method: 'POST',
          headers: {
              'X-CSRFToken': getCookie('csrftoken')
          },
          success: function(data) {
              if (data.success) {
                  window.location.href = '/game/' + gameId + '/';
              } else {
                  alert('Ошибка: ' + (data.error || 'Не удалось присоединиться'));
                  btn.prop('disabled', false).text('Присоединиться');
                  updateGamesList(); // Обновляем список
              }
          },
          error: function() {
              alert('Ошибка соединения');
              btn.prop('disabled', false).text('Присоединиться');
          }
      });
  });

  // Функция для получения CSRF токена
  function getCookie(name) {
      let cookieValue = null;
      if (document.cookie && document.cookie !== '') {
          const cookies = document.cookie.split(';');
          for (let i = 0; i < cookies.length; i++) {
              const cookie = cookies[i].trim();
              if (cookie.substring(0, name.length + 1) === (name + '=')) {
                  cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                  break;
              }
          }
      }
      return cookieValue;
  }

  // Первоначальная загрузка списка игр
  updateGamesList();
  
  // Обновляем список каждые 5 секунд
  setInterval(updateGamesList, 5000);
});