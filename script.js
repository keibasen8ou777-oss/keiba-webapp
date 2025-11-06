document.addEventListener('DOMContentLoaded', () => {
    const loginButton = document.getElementById('login-button');
    const passwordInput = document.getElementById('password-input');
    const loginContainer = document.getElementById('login-container');
    const appContainer = document.getElementById('app-container');
    const errorMessage = document.getElementById('error-message');

    const correctPassword = '1192';

    const attemptLogin = () => {
        const enteredPassword = passwordInput.value;

        if (enteredPassword === correctPassword) {
            // パスワードが正しい場合
            loginContainer.classList.add('hidden');
            appContainer.classList.remove('hidden');
            errorMessage.textContent = '';
        } else {
            // パスワードが間違っている場合
            errorMessage.textContent = 'パスワードが違います。';
            passwordInput.value = '';
        }
    };

    // ログインボタンがクリックされたとき
    loginButton.addEventListener('click', attemptLogin);

    // パスワード入力欄でEnterキーが押されたとき
    passwordInput.addEventListener('keyup', (event) => {
        if (event.key === 'Enter') {
            attemptLogin();
        }
    });
});
