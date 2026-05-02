/**
 * SMS 验证码发送按钮 — 公共组件
 * 依赖: 页面需存在 <input id="id_sms_code"> 和 CSRF token
 * 用法: <script src="{% static 'baykeshop/js/sms_verify.js' %}"></script>
 */
(function () {
    setTimeout(function () {
        const smsCodeInput = document.getElementById('id_sms_code');
        if (!smsCodeInput) return;

        const sendButton = document.createElement('button');
        sendButton.type = 'button';
        sendButton.className = 'button is-link is-small mt-1';
        sendButton.textContent = '发送验证码';
        sendButton.id = 'send-sms-btn';

        const buttonContainer = document.createElement('div');
        buttonContainer.className = 'mt-1';
        buttonContainer.appendChild(sendButton);

        const inputContainer = smsCodeInput.closest('.field, .bk-field, .control, .bk-control');
        if (inputContainer) {
            inputContainer.appendChild(buttonContainer);
        } else {
            smsCodeInput.parentNode.insertBefore(buttonContainer, smsCodeInput.nextSibling);
        }

        let countdown = 0;
        let countdownInterval = null;

        function updateButtonState() {
            if (countdown > 0) {
                sendButton.disabled = true;
                sendButton.textContent = '重新发送(' + countdown + 's)';
                sendButton.className = 'button is-light is-small mt-1';
            } else {
                sendButton.disabled = false;
                sendButton.textContent = '发送验证码';
                sendButton.className = 'button is-link is-small mt-1';
            }
        }

        function startCountdown(seconds) {
            countdown = seconds;
            updateButtonState();
            if (countdownInterval) clearInterval(countdownInterval);
            countdownInterval = setInterval(function () {
                countdown--;
                updateButtonState();
                if (countdown <= 0) {
                    clearInterval(countdownInterval);
                    countdownInterval = null;
                }
            }, 1000);
        }

        function showMessage(message, isSuccess) {
            if (isSuccess === undefined) isSuccess = true;
            var existingMessage = buttonContainer.querySelector('.message');
            if (existingMessage) existingMessage.remove();

            var messageDiv = document.createElement('div');
            messageDiv.className = 'message ' + (isSuccess ? 'is-success' : 'is-danger') + ' is-small mt-1';
            messageDiv.innerHTML = '<div class="message-body">' + message + '</div>';
            buttonContainer.appendChild(messageDiv);

            setTimeout(function () {
                if (messageDiv.parentNode) messageDiv.remove();
            }, 3000);
        }

        sendButton.addEventListener('click', function () {
            if (countdown > 0) return;

            sendButton.disabled = true;
            sendButton.textContent = '发送中...';

            var csrfInput = document.querySelector('[name=csrfmiddlewaretoken]');
            if (!csrfInput) {
                showMessage('系统错误: 找不到CSRF token', false);
                sendButton.disabled = false;
                sendButton.textContent = '发送验证码';
                return;
            }

            fetch('/api/send-sms/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfInput.value,
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ operation_type: 'general' }),
            })
                .then(function (response) {
                    if (!response.ok) throw new Error('HTTP ' + response.status);
                    return response.json();
                })
                .then(function (data) {
                    if (data.code === 0) {
                        showMessage('验证码已发送，请查收短信', true);
                        startCountdown(60);
                    } else {
                        showMessage('发送失败: ' + data.msg, false);
                        sendButton.disabled = false;
                        sendButton.textContent = '发送验证码';
                    }
                })
                .catch(function (error) {
                    showMessage('请求失败: ' + error.message, false);
                    sendButton.disabled = false;
                    sendButton.textContent = '发送验证码';
                });
        });
    }, 100);
})();
