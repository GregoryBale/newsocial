from flask import Flask, render_template_string, request, jsonify
from flask_socketio import SocketIO, emit, join_room
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'super-secret-key-change-in-prod'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', allow_reissue_request=True)  # Фикс для туннелей

# In-memory данные
users = []  # [{'id': int, 'username': str, 'password': str}]
messages = []  # [{'from': str, 'to': str, 'text': str, 'timestamp': str}]
online_users = set()
sid_to_user = {}  # {sid: username} — для 'from' в сообщениях

# HTML шаблон (встроенный)
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Моя СоцСеть Python</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.5/socket.io.js"></script>
    <style>
        body { font-family: Arial; margin: 20px; }
        #auth { display: block; }
        #chat { display: none; }
        #messages { height: 300px; overflow-y: scroll; border: 1px solid #ccc; padding: 10px; }
        button { margin: 5px; }
        .general { color: green; }
        .private { color: blue; }
    </style>
</head>
<body>
    <h1>Моя СоцСеть</h1>
    <div id="auth">
        <h2>Регистрация</h2>
        <input id="regUser" placeholder="Логин" /><input id="regPass" type="password" placeholder="Пароль" />
        <button onclick="register()">Зарегистрироваться</button>
        <h2>Вход</h2>
        <input id="loginUser" placeholder="Логин" /><input id="loginPass" type="password" placeholder="Пароль" />
        <button onclick="login()">Войти</button>
    </div>
    <div id="chat">
        <p>Онлайн: <span id="userCount">0</span> | Всего: <span id="totalCount">0</span></p>
        <button onclick="setMode('general')">Общий чат</button>
        <button onclick="setMode('private')">Приват</button>
        <div id="privateSelect" style="display:none;">
            <select id="toUser"><option value="all">Общий</option></select>
        </div>
        <input id="msgInput" placeholder="Сообщение" onkeypress="if(event.key==='Enter') sendMessage()" />
        <button onclick="sendMessage()">Отправить</button>
        <div id="messages"></div>
    </div>
    <script>
        const socket = io({ transports: ['websocket', 'polling'] });
        let currentUser = null;
        let mode = 'general';
        
        async function loadUsers() {
            const res = await fetch('/users');
            const data = await res.json();
            document.getElementById('totalCount').textContent = data.count;
            const select = document.getElementById('toUser');
            select.innerHTML = '<option value="all">Общий чат</option>';
            data.users.forEach(u => {
                if (u.username !== currentUser?.username) {
                    const opt = document.createElement('option');
                    opt.value = u.username; opt.text = u.username;
                    select.add(opt);
                }
            });
        }
        
        async function register() {
            const user = document.getElementById('regUser').value;
            const pass = document.getElementById('regPass').value;
            const res = await fetch('/register', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: user, password: pass}) });
            const data = await res.json();
            alert(data.success ? 'Зарегистрирован!' : data.error);
            if (data.success) loadUsers();
        }
        
        async function login() {
            const user = document.getElementById('loginUser').value;
            const pass = document.getElementById('loginPass').value;
            const res = await fetch('/login', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: user, password: pass}) });
            const data = await res.json();
            if (data.success) {
                currentUser = data.user;
                document.getElementById('auth').style.display = 'none';
                document.getElementById('chat').style.display = 'block';
                socket.emit('join', {username: user});
                loadUsers();
                loadMessages();
            } else alert(data.error);
        }
        
        async function loadMessages() {
            const res = await fetch('/messages');
            const msgs = await res.json();
            const div = document.getElementById('messages');
            div.innerHTML = msgs.map(m => {
                if (m.to !== 'all' && m.to !== currentUser.username && m.from !== currentUser.username) return '';
                const cls = m.to === 'all' ? 'general' : 'private';
                return `<p class="${cls}"><strong>${m.from}:</strong> ${m.text} (${new Date(m.timestamp).toLocaleString()})</p>`;
            }).join('');
            div.scrollTop = div.scrollHeight;
        }
        
        function setMode(m) {
            mode = m;
            document.getElementById('privateSelect').style.display = m === 'private' ? 'block' : 'none';
            document.getElementById('msgInput').placeholder = m === 'general' ? 'Для всех' : 'Приватно';
            loadMessages();
        }
        
        function sendMessage() {
            const text = document.getElementById('msgInput').value.trim();
            if (!text || !currentUser) return;
            let to = 'all';
            if (mode === 'private') to = document.getElementById('toUser').value;
            socket.emit('message', { text, to });
            document.getElementById('msgInput').value = '';
        }
        
        socket.on('message', (msg) => {
            if (msg.to === 'all' || msg.from === currentUser.username || msg.to === currentUser.username) {
                const div = document.getElementById('messages');
                const cls = msg.to === 'all' ? 'general' : 'private';
                div.innerHTML += `<p class="${cls}"><strong>${msg.from}:</strong> ${msg.text} (${new Date(msg.timestamp).toLocaleString()})</p>`;
                div.scrollTop = div.scrollHeight;
            }
        });
        
        socket.on('privateMessage', (msg) => {
            if (msg.to === currentUser.username || msg.from === currentUser.username) {
                const div = document.getElementById('messages');
                div.innerHTML += `<p class="private"><strong>${msg.from} (приват):</strong> ${msg.text} (${new Date(msg.timestamp).toLocaleString()})</p>`;
                div.scrollTop = div.scrollHeight;
            }
        });
        
        socket.on('notification', (notif) => alert(`Уведомление: ${notif.type} от ${notif.from}`));
        
        socket.on('userCount', (count) => document.getElementById('userCount').textContent = count);
        
        setInterval(loadMessages, 10000);
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data['username']
    password = data['password']
    if any(u['username'] == username for u in users):
        return jsonify({'success': False, 'error': 'Пользователь существует'})
    new_user = {'id': len(users) + 1, 'username': username, 'password': password}
    users.append(new_user)
    return jsonify({'success': True, 'user': new_user})

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data['username']
    password = data['password']
    user = next((u for u in users if u['username'] == username and u['password'] == password), None)
    if not user:
        return jsonify({'success': False, 'error': 'Неверные данные'})
    return jsonify({'success': True, 'user': user})

@app.route('/users')
def get_users():
    return jsonify({'users': users, 'count': len(users)})

@app.route('/messages')
def get_messages():
    return jsonify(messages)

@socketio.on('join')
def on_join(data):
    username = data['username']
    join_room(username)
    online_users.add(username)
    sid_to_user[request.sid] = username
    emit('userCount', len(online_users), broadcast=True)
    print(f'{username} подключился')

@socketio.on('message')
def handle_message(msg):
    from_user = sid_to_user.get(request.sid, 'Unknown')
    to = msg['to'] or 'all'
    message = {'from': from_user, 'to': to, 'text': msg['text'], 'timestamp': datetime.now().isoformat()}
    messages.append(message)
    if to == 'all':
        emit('message', message, broadcast=True)
    else:
        emit('privateMessage', message, room=to)
        emit('privateMessage', message)
    emit('notification', {'type': 'newMessage', 'from': from_user}, broadcast=True)

@socketio.on('disconnect')
def on_disconnect():
    if request.sid in sid_to_user:
        username = sid_to_user.pop(request.sid)
        online_users.discard(username)
        emit('userCount', len(online_users), broadcast=True)
        print(f'{username} отключился')

if __name__ == '__main__':
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
