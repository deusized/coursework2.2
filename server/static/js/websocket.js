class GameConnection {
    constructor(roomId) {
        this.socket = new WebSocket(
            `ws://${window.location.host}/ws/game/${roomId}/`
        );
        
        this.socket.onmessage = (e) => {
            const data = JSON.parse(e.data);
            this.handleMessage(data);
        };
    }

    handleMessage(data) {
        switch(data.action) {
            case 'game_state':
                this.updateGameState(data.state);
                break;
            case 'player_joined':
                this.notifyPlayerJoined(data.player);
                break;
            // ... другие обработчики
        }
    }

    sendAction(action, data = {}) {
        this.socket.send(JSON.stringify({
            action,
            ...data
        }));
    }
}