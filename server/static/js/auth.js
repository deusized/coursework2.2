function focusNextField(event, nextFieldId)
{ 
    if (event.key === 'Enter') 
    { 
        event.preventDefault(); 
        document.getElementById(nextFieldId).focus(); 
    } 
}

document.addEventListener('DOMContentLoaded', () => {
    const enteringForm = document.getElementById('entering-form');
    const registeringForm = document.getElementById('registering-form');
    const switchToRegister = document.getElementById('switch-to-register');
    const switchToLogin = document.getElementById('switch-to-login');
    const heading = document.querySelector('.title');
    const loginInput = document.getElementById('login');
    const passInput = document.getElementById('password');
    const loginReg = document.getElementById('reg-login');
    const passReg = document.getElementById('reg-password');
    const confirmPassInput = document.getElementById('confirm-password')

    switchToRegister.addEventListener('click', (e) => {
        e.preventDefault();
        enteringForm.classList.add('hidden');
        registeringForm.classList.remove('hidden');
        switchToRegister.classList.add('hidden');
        switchToLogin.classList.remove('hidden');
        heading.textContent = 'Регистрация';
    });

    switchToLogin.addEventListener('click', (e) => {
        e.preventDefault();
        registeringForm.classList.add('hidden');
        enteringForm.classList.remove('hidden');
        switchToLogin.classList.add('hidden');
        switchToRegister.classList.remove('hidden');
        heading.textContent = 'Добро пожаловать!';
    });

    registeringForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const login = loginReg.value.trim();
        const password = passReg.value.trim();
        const confirmPassword = confirmPassInput.value.trim();

        if (login === "" || password === "" || confirmPassword === "") {
            alert("Пожалуйста, заполните все поля.");
        } else if (password !== confirmPassword) {
            alert("Пароли не совпадают.");
        } else {
            // Отправка запроса на сервер для регистрации
            fetch('http://localhost:3000/register',
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ login, password })
            })
            .then(response => {
                if (!response.ok) {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data => {
                if (data.success)
                {
                    switchToLogin;
                }
                else
                {
                    alert(data.message || "Ошибка регистрации. Попробуйте снова.");
                }
            })
            .catch(error => {
                console.error('Ошибка:', error);
                alert('Произошла ошибка. Пожалуйста, попробуйте снова.');
            });
        }
    });

    enteringForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const login = loginInput.value.trim();
        const password = passInput.value.trim();
        if (login === "" || password === "")
        {
            alert("Пожалуйста, заполните все поля.");
        }
        else
        {
            fetch('http://localhost:3000/check-login', //сменить при выкладке на сервер
            {
                method: 'POST',
                headers:
                {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ login, password })
            })
            .then(response =>
            {
                if (!response.ok)
                {
                    throw new Error('Network response was not ok');
                }
                return response.json();
            })
            .then(data =>
            {
                if (data.success)
                {
                    window.location.href = 'lobby_page.html';
                }
                else
                {
                    alert("Неверный логин или пароль.");
                }
            })
            .catch(error => {
                console.error('Ошибка:', error);
                alert('Произошла ошибка. Пожалуйста, попробуйте снова.');
            });
        }
    });
});
