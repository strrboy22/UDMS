from operator import truediv
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from flask_migrate import Migrate
from dotenv import load_dotenv
from flask_jwt_extended import JWTManager
from flask_socketio import SocketIO
import os
import redis
from flask_mail import Mail

redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
redis_client = redis.from_url(redis_url)

db = SQLAlchemy()
migrate = Migrate()
socketio = SocketIO()
mail = Mail()


def create_app():
    load_dotenv()
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config["JWT_SECRET_KEY"] = os.getenv('JWT_SECRET_KEY')
    app.config['JWT_TOKEN_LOCATION'] = ['headers', 'cookies']
    app.config["JWT_HEADER_NAME"] = "Authorization"
    app.config["JWT_HEADER_TYPE"] = "Bearer"    
    
    #cookies settings (secure=False; secure=True in production)
    app.config['JWT_COOKIE_SECURE'] = False
    app.config['JWT_COOKIE_SAMESITE'] = 'Lax'
    app.config['JWT_ACCESS_COOKIE_NAME'] = 'access_token'
    app.config['JWT_REFRESH_COOKIE_NAME'] = 'refresh_token'

    #email configuration
    app.config['MAIL_SERVER'] = os.getenv('SMTP_SERVER')
    app.config['MAIL_PORT'] = int(os.getenv('SMTP_PORT'))
    app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USER')
    app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASSWORD')
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USE_SSL'] = False
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('EMAIL_USER')


    db.init_app(app)
    migrate.init_app(app, db)
    JWTManager(app)
    mail.init_app(app)

    # Initialize CORS
    CORS(app, origins=['http://localhost:5173', 'http://localhost:3000', 'http://localhost:8080'], supports_credentials=True)

    # Initialize SocketIO with CORS settings
    socketio.init_app(app, cors_allowed_origins=["http://localhost:5173", "http://localhost:3000", "http://localhost:8080"], 
                      async_mode='threading', logger=True, engineio_logger=True)

    from app.routes import register_routes
    register_routes(app)

    # Import socket handlers to register events
    from . import socket_handlers

    
    return app, socketio
    