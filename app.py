#!/usr/bin/env python3
"""
ISODROP - Real-Time Local File Sharing Application
Backend Server with Flask and Socket.IO
"""

import os
import socket
import qrcode
import io
import base64
import uuid
import time
import tempfile
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional
from flask import Flask, render_template, request, send_file, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent

# Configuration
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'isodrop-secret-key-' + str(uuid.uuid4()))
    MAX_FILE_SIZE = 5 * 1024 * 1024 * 1024  # 5GB
    CHUNK_SIZE = 1024 * 1024  # 1MB chunks
    MEMORY_THRESHOLD = 100 * 1024 * 1024  # 100MB - files larger than this use disk
    UPLOAD_FOLDER = '/tmp/uploads' if os.environ.get('VERCEL') else 'uploads'
    FILE_EXPIRY_HOURS = 1
    RATE_LIMIT_MESSAGES = 100  # messages per minute
    ALLOWED_EXTENSIONS = {
        'images': ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'ico'],
        'videos': ['mp4', 'mkv', 'avi', 'mov', 'wmv', 'flv', 'webm', 'm4v'],
        'documents': ['pdf', 'doc', 'docx', 'txt', 'xlsx', 'xls', 'ppt', 'pptx', 'csv', 'odt'],
        'audio': ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'aac', 'wma']
    }

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)
CORS(app, resources={r"/*": {"origins": "*"}})

# Initialize Socket.IO
socketio = SocketIO(app, cors_allowed_origins="*", max_http_buffer_size=100 * 1024 * 1024)

# Create upload directory
os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)

# Global state management
connected_devices = {}  # {sid: {id, name, ip, connected_at, last_activity}}
file_storage = {}  # {file_id: {data, metadata, expiry}}
upload_progress = {}  # {upload_id: {chunks, total_chunks, file_id}}
session_history = []  # Unified list of messages and file metadata
rate_limiter = {}  # {sid: [timestamps]}


def get_local_ip():
    """Get the local IP address of the machine"""
    try:
        # Create a socket connection to determine local IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def generate_qr_code(url):
    """Generate QR code for the given URL"""
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        buf.seek(0)
        
        # Convert to base64 for embedding
        img_base64 = base64.b64encode(buf.getvalue()).decode()
        return f"data:image/png;base64,{img_base64}"
    except Exception as e:
        print(f"QR Code generation error: {e}")
        return None


def cleanup_expired_files():
    """Remove expired files from storage"""
    current_time = datetime.now()
    expired_files = []
    
    for file_id, file_info in file_storage.items():
        if current_time > file_info['expiry']:
            expired_files.append(file_id)
            # Clean up disk file if exists
            if 'disk_path' in file_info:
                try:
                    os.remove(file_info['disk_path'])
                except:
                    pass
    
    for file_id in expired_files:
        del file_storage[file_id]
    
    if expired_files:
        print(f"Cleaned up {len(expired_files)} expired files")


def check_rate_limit(sid):
    """Check if device has exceeded rate limit"""
    current_time = time.time()
    if sid not in rate_limiter:
        rate_limiter[sid] = []
    
    # Remove timestamps older than 1 minute
    rate_limiter[sid] = [ts for ts in rate_limiter[sid] if current_time - ts < 60]
    
    if len(rate_limiter[sid]) >= Config.RATE_LIMIT_MESSAGES:
        return False
    
    rate_limiter[sid].append(current_time)
    return True


def get_file_category(filename):
    """Determine file category based on extension"""
    ext = filename.rsplit('.', 1)[-1].lower()
    for category, extensions in Config.ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return category
    return 'other'


def format_file_size(size_bytes):
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} PB"


# Routes
@app.route('/')
def index():
    """Serve the main page"""
    return send_file(BASE_DIR / 'index.html')


@app.route('/api/qr-code')
def get_qr_code():
    """Generate and return QR code for connection"""
    # If running on Vercel or public cloud, use the host header
    if os.environ.get('VERCEL') or 'localhost' not in request.host:
        protocol = 'https' if request.is_secure or os.environ.get('VERCEL') else 'http'
        url = f"{protocol}://{request.host}"
    else:
        local_ip = get_local_ip()
        port = request.host.split(':')[-1] if ':' in request.host else '5000'
        url = f"http://{local_ip}:{port}"
        
    qr_code = generate_qr_code(url)
    
    return jsonify({
        'url': url,
        'qr_code': qr_code
    })


@app.route('/api/download/<file_id>')
def download_file(file_id):
    """Download a file"""
    cleanup_expired_files()
    
    if file_id not in file_storage:
        return jsonify({'error': 'File not found or expired'}), 404
    
    file_info = file_storage[file_id]
    
    try:
        # Check if file is on disk or in memory
        if 'disk_path' in file_info:
            return send_file(
                file_info['disk_path'],
                as_attachment=True,
                download_name=file_info['metadata']['filename'],
                mimetype=file_info['metadata']['mime_type']
            )
        else:
            # File is in memory
            data_io = io.BytesIO(file_info['data'])
            return send_file(
                data_io,
                as_attachment=True,
                download_name=file_info['metadata']['filename'],
                mimetype=file_info['metadata']['mime_type']
            )
    except Exception as e:
        print(f"Download error: {e}")
        return jsonify({'error': 'Download failed'}), 500


# Socket.IO Events
@socketio.on('connect')
def handle_connect():
    """Handle new device connection"""
    sid = request.sid
    device_id = str(uuid.uuid4())[:8]
    
    # Get client IP
    client_ip = request.environ.get('HTTP_X_REAL_IP', request.environ.get('REMOTE_ADDR', 'unknown'))
    
    # Register device
    connected_devices[sid] = {
        'id': device_id,
        'name': f'Device-{device_id}',
        'ip': client_ip,
        'connected_at': datetime.now().isoformat(),
        'last_activity': datetime.now()
    }
    
    print(f"✓ Device connected: {device_id} ({client_ip})")
    
    # Send device info to the new client
    emit('device_registered', {
        'device_id': device_id,
        'device_name': connected_devices[sid]['name']
    })
    
    # Broadcast updated device list to all clients
    broadcast_device_list()
    
    # Send full session history to new client
    emit('session_history', session_history)
    
    # Broadcast join notification
    socketio.emit('user_joined', {
        'device_id': device_id,
        'device_name': connected_devices[sid]['name'],
        'timestamp': datetime.now().isoformat()
    })


@socketio.on('disconnect')
def handle_disconnect():
    """Handle device disconnection"""
    sid = request.sid
    
    if sid in connected_devices:
        device_info = connected_devices[sid]
        device_id = device_info['id']
        device_name = device_info['name']
        
        print(f"✗ Device disconnected: {device_id}")
        
        # Remove device
        del connected_devices[sid]
        
        # Clean up rate limiter
        if sid in rate_limiter:
            del rate_limiter[sid]
        
        # Broadcast updated device list
        broadcast_device_list()
        
        # Broadcast leave notification
        socketio.emit('user_left', {
            'device_id': device_id,
            'device_name': device_name,
            'timestamp': datetime.now().isoformat()
        })


@socketio.on('set_device_name')
def handle_set_device_name(data):
    """Update device name"""
    sid = request.sid
    
    if sid in connected_devices:
        new_name = data.get('name', '').strip()
        if new_name and len(new_name) <= 50:
            old_name = connected_devices[sid]['name']
            connected_devices[sid]['name'] = new_name
            connected_devices[sid]['last_activity'] = datetime.now()
            
            print(f"Device renamed: {old_name} → {new_name}")
            
            emit('name_updated', {'device_name': new_name})
            broadcast_device_list()


@socketio.on('send_message')
def handle_send_message(data):
    """Handle text message broadcasting"""
    sid = request.sid
    
    if sid not in connected_devices:
        return
    
    # Check rate limit
    if not check_rate_limit(sid):
        emit('error', {'message': 'Rate limit exceeded. Please slow down.'})
        return
    
    device_info = connected_devices[sid]
    message_text = data.get('message', '').strip()
    
    if not message_text or len(message_text) > 5000:
        emit('error', {'message': 'Invalid message length'})
        return
    
    message = {
        'id': str(uuid.uuid4()),
        'sender_id': device_info['id'],
        'sender_name': device_info['name'],
        'message': message_text,
        'timestamp': datetime.now().isoformat(),
        'type': 'message'
    }
    
    # Add to history
    session_history.append(message)
    
    # Keep only last 100 items
    if len(session_history) > 100:
        session_history.pop(0)
    
    # Broadcast to all clients
    socketio.emit('new_message', message)
    
    connected_devices[sid]['last_activity'] = datetime.now()


@socketio.on('upload_start')
def handle_upload_start(data):
    """Initialize file upload"""
    sid = request.sid
    
    if sid not in connected_devices:
        emit('error', {'message': 'Not connected'})
        return
    
    filename = secure_filename(data.get('filename', 'unnamed'))
    file_size = data.get('fileSize', 0)
    mime_type = data.get('mimeType', 'application/octet-stream')
    total_chunks = data.get('totalChunks', 0)
    
    # Validate file size
    if file_size > Config.MAX_FILE_SIZE:
        emit('error', {'message': f'File too large. Maximum size is {format_file_size(Config.MAX_FILE_SIZE)}'})
        return
    
    # Validate file type
    category = get_file_category(filename)
    if category == 'other':
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        # Allow other extensions but warn
        print(f"Warning: Uploading file with extension: {ext}")
    
    upload_id = str(uuid.uuid4())
    
    # Initialize upload tracking
    upload_progress[upload_id] = {
        'chunks': {},
        'total_chunks': total_chunks,
        'received_chunks': 0,
        'filename': filename,
        'file_size': file_size,
        'mime_type': mime_type,
        'sender_id': connected_devices[sid]['id'],
        'sender_name': connected_devices[sid]['name'],
        'category': category,
        'use_disk': file_size > Config.MEMORY_THRESHOLD
    }
    
    if upload_progress[upload_id]['use_disk']:
        # Create temporary file for large uploads
        temp_file = tempfile.NamedTemporaryFile(delete=False, dir=Config.UPLOAD_FOLDER)
        upload_progress[upload_id]['temp_path'] = temp_file.name
        temp_file.close()
    
    emit('upload_ready', {'upload_id': upload_id})
    print(f"Upload started: {filename} ({format_file_size(file_size)}) - {'disk' if upload_progress[upload_id]['use_disk'] else 'memory'}")


@socketio.on('upload_chunk')
def handle_upload_chunk(data):
    """Receive file chunk"""
    sid = request.sid
    
    if sid not in connected_devices:
        return
    
    upload_id = data.get('upload_id')
    chunk_index = data.get('chunk_index')
    chunk_data = data.get('data')  # Base64 encoded
    
    if upload_id not in upload_progress:
        emit('error', {'message': 'Invalid upload ID'})
        return
    
    try:
        # Decode chunk data
        chunk_bytes = base64.b64decode(chunk_data)
        
        upload_info = upload_progress[upload_id]
        
        if upload_info['use_disk']:
            # Write to disk
            with open(upload_info['temp_path'], 'ab') as f:
                f.write(chunk_bytes)
        else:
            # Store in memory
            upload_info['chunks'][chunk_index] = chunk_bytes
        
        upload_info['received_chunks'] += 1
        
        # Calculate progress
        progress = (upload_info['received_chunks'] / upload_info['total_chunks']) * 100
        
        # Broadcast progress to all clients
        socketio.emit('upload_progress', {
            'upload_id': upload_id,
            'progress': round(progress, 2),
            'filename': upload_info['filename'],
            'sender_name': upload_info['sender_name']
        })
        
        connected_devices[sid]['last_activity'] = datetime.now()
        
    except Exception as e:
        print(f"Chunk upload error: {e}")
        emit('error', {'message': 'Chunk upload failed'})


@socketio.on('upload_complete')
def handle_upload_complete(data):
    """Finalize file upload"""
    sid = request.sid
    
    if sid not in connected_devices:
        return
    
    upload_id = data.get('upload_id')
    
    if upload_id not in upload_progress:
        emit('error', {'message': 'Invalid upload ID'})
        return
    
    upload_info = upload_progress[upload_id]
    
    try:
        file_id = str(uuid.uuid4())
        
        if upload_info['use_disk']:
            # File is already on disk
            file_storage[file_id] = {
                'disk_path': upload_info['temp_path'],
                'metadata': {
                    'filename': upload_info['filename'],
                    'size': upload_info['file_size'],
                    'mime_type': upload_info['mime_type'],
                    'category': upload_info['category'],
                    'sender_id': upload_info['sender_id'],
                    'sender_name': upload_info['sender_name'],
                    'uploaded_at': datetime.now().isoformat()
                },
                'expiry': datetime.now() + timedelta(hours=Config.FILE_EXPIRY_HOURS)
            }
        else:
            # Combine chunks from memory
            sorted_chunks = [upload_info['chunks'][i] for i in sorted(upload_info['chunks'].keys())]
            file_data = b''.join(sorted_chunks)
            
            file_storage[file_id] = {
                'data': file_data,
                'metadata': {
                    'filename': upload_info['filename'],
                    'size': upload_info['file_size'],
                    'mime_type': upload_info['mime_type'],
                    'category': upload_info['category'],
                    'sender_id': upload_info['sender_id'],
                    'sender_name': upload_info['sender_name'],
                    'uploaded_at': datetime.now().isoformat()
                },
                'expiry': datetime.now() + timedelta(hours=Config.FILE_EXPIRY_HOURS)
            }
        
        # Clean up upload progress
        del upload_progress[upload_id]
        
        # Prepare file info for broadcast
        file_broadcast = {
            'id': file_id,
            'file_id': file_id,
            'filename': file_storage[file_id]['metadata']['filename'],
            'size': file_storage[file_id]['metadata']['size'],
            'mime_type': file_storage[file_id]['metadata']['mime_type'],
            'category': file_storage[file_id]['metadata']['category'],
            'sender_id': file_storage[file_id]['metadata']['sender_id'],
            'sender_name': file_storage[file_id]['metadata']['sender_name'],
            'uploaded_at': file_storage[file_id]['metadata']['uploaded_at'],
            'download_url': f'/api/download/{file_id}',
            'type': 'file'
        }

        # Add to history
        session_history.append(file_broadcast)
        if len(session_history) > 100:
            session_history.pop(0)
        
        # Broadcast file uploaded event
        socketio.emit('file_uploaded', file_broadcast)
        
        print(f"✓ Upload complete: {upload_info['filename']} → {file_id}")
        
        # Cleanup old files
        cleanup_expired_files()
        
    except Exception as e:
        print(f"Upload finalization error: {e}")
        emit('error', {'message': 'Upload failed to complete'})


@socketio.on('device_list_request')
def handle_device_list_request():
    """Send current device list to requester"""
    broadcast_device_list(broadcast=False)


def broadcast_device_list(broadcast=True):
    """Send device list to all connected clients"""
    device_list = [
        {
            'id': info['id'],
            'name': info['name'],
            'connected_at': info['connected_at']
        }
        for info in connected_devices.values()
    ]
    
    event_data = {
        'devices': device_list,
        'count': len(device_list)
    }
    
    if broadcast:
        socketio.emit('device_list', event_data)
    else:
        emit('device_list', event_data)


if __name__ == '__main__':
    # Get local IP and port
    local_ip = get_local_ip()
    port = 5000
    
    # Generate QR code
    url = f"http://{local_ip}:{port}"
    qr = qrcode.QRCode(version=1, box_size=10, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    
    # Print startup info
    print("\n" + "="*60)
    print("🚀 ISODROP - Real-Time Local File Sharing")
    print("="*60)
    print(f"\n📡 Server URL: {url}")
    print(f"🌐 Local IP: {local_ip}")
    print(f"🔌 Port: {port}")
    print(f"\n📱 Scan this QR code to connect:\n")
    qr.print_ascii(invert=True)
    print("\n" + "="*60)
    print("💡 Open the URL above in your browser to start sharing!")
    print("="*60 + "\n")
    
    # Start server
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)
