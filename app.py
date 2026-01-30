import os
import socket
import qrcode
import io
import base64
import uuid
from flask import Flask, render_template, request, send_file, jsonify
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId

app = Flask(__name__)
CORS(app) # Enable CORS for all routes
app.config['SECRET_KEY'] = 'secret!'
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 

# MongoDB Setup
MONGO_URI = "mongodb+srv://bharatbytecom_db_user:1oDh5dhxaXHnR9Cv@cluster0.bzkmity.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
db = client['isodrop_db']
history_col = db['history']
files_col = db['files']

# Enable cors for socketio as well
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading' if not os.environ.get('VERCEL') else None)

CLIENTS = {} # { sid: { 'id': short_uuid, 'name': str } }

def get_local_ip():
    """Detects the local IP address of the machine on the network."""
    try:
        # Connect to an external server (doesn't actually send data) to get the interface IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

LOCAL_IP = get_local_ip()
PORT = 5000

# Detect if running in a cloud environment (simple check)
IS_CLOUD = os.environ.get('VERCEL') or os.environ.get('PORT')

def get_server_url():
    if IS_CLOUD:
        return None # Will be determined at request time
    return f"http://{LOCAL_IP}:{PORT}"

SERVER_URL = get_server_url()

def generate_qr(url):
    """Generates a QR code for the given URL and returns it as a base64 string."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode("utf-8")

# QR code is generated dynamically per request if SERVER_URL is None

@app.route('/')
def index():
    # Dynamic URL handling for Cloud/Vercel
    current_url = SERVER_URL
    if not current_url:
        current_url = request.host_url.rstrip('/')
    
    qr_b64 = generate_qr(current_url)
    return render_template('index.html', server_url=current_url, qr_code=qr_b64)

@app.route('/manifest.json')
def serve_manifest():
    return send_file('static/manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_file('static/sw.js', mimetype='application/javascript')

@app.route('/static/icon.png')
def serve_icon():
    return send_file('static/icon.png')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        file_id = str(uuid.uuid4())
        file_data = file.read()
        
        # Save to MongoDB
        files_col.insert_one({
            'file_id': file_id,
            'name': file.filename,
            'data': base64.b64encode(file_data).decode('utf-8'), # Simplest for BSON
            'mime': file.content_type
        })
        
        # Broadcast file message
        msg = {
            'id': str(uuid.uuid4()),
            'type': 'file',
            'filename': file.filename,
            'file_id': file_id,
            'size': len(file_data)
        }
        history_col.insert_one(msg)
        del msg['_id'] # Remove MongoDB internal ID for socket emission
        socketio.emit('new_message', msg)
        
        return jsonify({'success': True, 'file_id': file_id})

@app.route('/download/<file_id>')
def download_file(file_id):
    file_info = files_col.find_one({'file_id': file_id})
    if not file_info:
        return "File not found or expired", 404
    
    return send_file(
        io.BytesIO(base64.b64decode(file_info['data'])),
        mimetype=file_info['mime'],
        as_attachment=True,
        download_name=file_info['name']
    )

@socketio.on('connect')
def handle_connect():
    sid = request.sid
    # Set a temporary placeholder until client identifies
    CLIENTS[sid] = {
        'id': sid[:4].upper(),
        'name': "Joining...",
        'platform': 'unknown'
    }
    # Load history from MongoDB
    history = list(history_col.find({}, {'_id': 0}).sort('_id', -1).limit(50))
    history.reverse()
    emit('load_history', history)

@socketio.on('identify')
def handle_identify(data):
    sid = request.sid
    if sid in CLIENTS:
        CLIENTS[sid]['name'] = data.get('name', 'Unknown Device')
        CLIENTS[sid]['platform'] = data.get('platform', 'unknown').lower()
        emit('user_update', list(CLIENTS.values()), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    if sid in CLIENTS:
        del CLIENTS[sid]
    emit('user_update', list(CLIENTS.values()), broadcast=True)

@socketio.on('send_message')
def handle_message(data):
    msg = {
        'id': str(uuid.uuid4()),
        'type': 'text',
        'content': data['content']
    }
    history_col.insert_one(msg.copy()) # Copy to avoid mutation issues
    if '_id' in msg: del msg['_id']
    emit('new_message', msg, broadcast=True)

@socketio.on('clear_history')
def handle_clear():
    history_col.delete_many({})
    files_col.delete_many({})
    emit('history_cleared', broadcast=True)

if __name__ == '__main__':
    print(f"Starting server at {SERVER_URL}")
    socketio.run(app, host='0.0.0.0', port=PORT, debug=True, allow_unsafe_werkzeug=True)
