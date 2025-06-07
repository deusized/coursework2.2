document.addEventListener('DOMContentLoaded', function() {
    const createBtn = document.getElementById('create-game-btn');
    
    createBtn.addEventListener('click', function() {
        const gameName = document.getElementById('game-name').value;
        const playersCount = document.querySelector('input[name="players"]:checked').value;
        const gameType = document.getElementById('game-type').value;
        
        // Показываем индикатор загрузки
        createBtn.disabled = true;
        createBtn.textContent = 'Создание...';
        
        // Отправка данных на сервер
        fetch('/api/game/create/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCSRFToken(),
            },
            body: JSON.stringify({
                name: gameName,
                max_players: playersCount,
                game_type: gameType
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                window.location.href = `/game/${data.game_id}/`;
            } else {
                alert('Ошибка: ' + (data.error || 'Не удалось создать игру'));
                createBtn.disabled = false;
                createBtn.textContent = 'Создать игру';
            }
        })
        .catch(error => {
            console.error('Error:', error);
            createBtn.disabled = false;
            createBtn.textContent = 'Создать игру';
        });
    });
    
    function getCSRFToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }
});