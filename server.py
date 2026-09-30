from flask import Flask, request, jsonify

app = Flask(__name__)

# Arbeitsspeicher-Datenspeicher (RAM only)
online_users = set()
user_inboxes = {}   # { 'Username': ['ABSENDER|ZIEL|TAG|PAYLOAD', ...] }
room_messages = {}  # { 'Lobby': ['ABSENDER|ZIEL|TAG|PAYLOAD', ...] }

@app.route('/login', methods=['POST'])
def login():
    username = request.json.get('username', '').strip()
    if not username:
        return jsonify({"status": "error", "message": "Name darf nicht leer sein"}), 400
    if username in online_users:
        return jsonify({"status": "error", "message": "Username bereits vergeben"}), 409
    
    online_users.add(username)
    user_inboxes[username] = []
    return jsonify({"status": "ok"}), 200

@app.route('/send_room', methods=['POST'])
def send_room():
    data = request.json
    room_id = data.get('room')
    message = data.get('message')
    if room_id not in room_messages:
        room_messages[room_id] = []
    room_messages[room_id].append(message)
    return jsonify({"status": "ok"}), 200

@app.route('/get_room/<room_id>', methods=['GET'])
def get_room(room_id):
    messages = room_messages.get(room_id, [])
    return jsonify({"messages": messages}), 200

@app.route('/send_direct', methods=['POST'])
def send_direct():
    data = request.json
    target = data.get('target')
    message = data.get('message')
    if target in user_inboxes:
        user_inboxes[target].append(message)
        return jsonify({"status": "ok"}), 200
    return jsonify({"status": "error", "message": "User nicht gefunden"}), 404

@app.route('/get_direct/<username>', methods=['GET'])
def get_direct(username):
    messages = user_inboxes.get(username, [])
    user_inboxes[username] = []  # Postfach nach Abruf leeren
    return jsonify({"messages": messages}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)