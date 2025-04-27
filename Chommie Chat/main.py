# Imports here
import os
import random
import logging
from datetime import datetime
from typing import Dict, List, Optional

from flask import Flask, render_template, request, session
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.middleware.proxy_fix import ProxyFix

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# App Configuration Settings
class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24)
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ('true', '1', 't')
    CORS_ORIGINS = os.environ.get('CORS_ORIGINS', '*')
    
    CHAT_ROOMS = [
        'General',
        'Academics',
        'Running Club',
        'Anime Club'
    ]

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Handle reverse proxy headers
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

# Initialize SocketIO
socketIo = SocketIO(
    app,
    cors_allowed_origins=app.config['CORS_ORIGINS'],
    logger=True,
    engineio_logger=True
)

# In-memory storage for active users
activeUsers: Dict[str, dict] = {}

# Generate a unique guest username
def generateGuestUsername() -> str:
    timestamp = datetime.now().strftime('%H%M')
    return f'Guest{timestamp}{random.randint(1000,9999)}'

# Home Route
@app.route('/')
def index():
    if 'username' not in session:
        session['username'] = generateGuestUsername()
        logger.info(f"New user session created: {session['username']}")
    
    return render_template(
        'index.html',
        username=session['username'],
        rooms=app.config['CHAT_ROOMS']
    )

@socketIo.event
def connect():
    try:
        if 'username' not in session:
            session['username'] = generateGuestUsername()
        
        activeUsers[request.sid] = {
            'username': session['username'],
            'connectedAt': datetime.now().isoformat()
        }
        
        emit('activeUsers', {
            'users': [user['username'] for user in activeUsers.values()]
        }, broadcast=True)
        
        logger.info(f"User connected: {session['username']}")
    
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        return False

@socketIo.event
def disconnect():
    try:
        if request.sid in activeUsers:
            username = activeUsers[request.sid]['username']
            del activeUsers[request.sid]
            
            emit('activeUsers', {
                'users': [user['username'] for user in activeUsers.values()]
            }, broadcast=True)
            
            logger.info(f"User disconnected: {username}")
    
    except Exception as e:
        logger.error(f"Disconnection error: {str(e)}")

@socketIo.on('join')
def onJoin(data: dict):
    try:
        username = session['username']
        room = data['room']
        
        if room not in app.config['CHAT_ROOMS']:
            logger.warning(f"Invalid room join attempt: {room}")
            return
        
        join_room(room)
        activeUsers[request.sid]['room'] = room
        
        emit('status', {
            'msg': f'{username} has joined the room.',
            'type': 'join',
            'timestamp': datetime.now().isoformat()
        }, room=room)
        
        logger.info(f"User {username} joined room: {room}")
    
    except Exception as e:
        logger.error(f"Join room error: {str(e)}")

@socketIo.on('leave')
def onLeave(data: dict):
    try:
        username = session['username']
        room = data['room']
        
        leave_room(room)
        if request.sid in activeUsers:
            activeUsers[request.sid].pop('room', None)
        
        emit('status', {
            'msg': f'{username} has left the room.',
            'type': 'leave',
            'timestamp': datetime.now().isoformat()
        }, room=room)
        
        logger.info(f"User {username} left room: {room}")
    
    except Exception as e:
        logger.error(f"Leave room error: {str(e)}")

@socketIo.on('message')
def handleMessage(data: dict):
    try:
        username = session['username']
        room = data.get('room', 'General')
        msgType = data.get('type', 'message')
        message = data.get('msg', '').strip()
        
        if not message:
            return
        
        timestamp = datetime.now().isoformat()
        
        if msgType == 'private':
            targetUser = data.get('target')
            if not targetUser:
                return
                
            for sid, userData in activeUsers.items():
                if userData['username'] == targetUser:
                    emit('privateMessage', {
                        'msg': message,
                        'from': username,
                        'to': targetUser,
                        'timestamp': timestamp
                    }, room=sid)
                    logger.info(f"Private message sent: {username} -> {targetUser}")
                    return
                    
            logger.warning(f"Private message failed - user not found: {targetUser}")
        
        else:
            if room not in app.config['CHAT_ROOMS']:
                logger.warning(f"Message to invalid room: {room}")
                return
                
            emit('message', {
                'msg': message,
                'username': username,
                'room': room,
                'timestamp': timestamp
            }, room=room)
            
            logger.info(f"Message sent in {room} by {username}")
    
    except Exception as e:
        logger.error(f"Message handling error: {str(e)}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketIo.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=app.config['DEBUG'],
        use_reloader=app.config['DEBUG']
    )
