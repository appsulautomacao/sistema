# extensions.py
from flask_socketio import SocketIO

socketio = SocketIO(cors_allowed_origins="*")

from flask_login import LoginManager

socketio = SocketIO()
login_manager = LoginManager()