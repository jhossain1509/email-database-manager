from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_socketio import SocketIO
from celery import Celery
from config import Config
import os

db = SQLAlchemy()
login_manager = LoginManager()
migrate = Migrate()
socketio = SocketIO()

# Create Celery instance
celery = Celery(__name__)

def make_celery(app):
    """Configure Celery with Flask app context"""
    celery.conf.update(
        broker_url=app.config['CELERY_BROKER_URL'],
        result_backend=app.config['CELERY_RESULT_BACKEND'],
        task_serializer='json',
        result_serializer='json',
        accept_content=['json'],
        timezone='UTC',
        enable_utc=True,
        task_track_started=True,
        task_send_sent_event=True,
    )
    
    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)
    
    celery.Task = ContextTask
    return celery

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    
    # Initialize SocketIO with Redis message queue for production
    socketio.init_app(app, 
                      message_queue=app.config['REDIS_URL'],
                      cors_allowed_origins="*",
                      async_mode='threading')
    
    # Configure login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'
    
    # Create upload and export folders
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(app.config['EXPORT_FOLDER'], exist_ok=True)
    
    # Initialize Celery
    make_celery(app)
    
    # Register blueprints
    from app.routes import auth, dashboard, email, admin, api
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(email.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(api.bp)
    
    # Register SocketIO event handlers
    with app.app_context():
        from app.routes import socketio_events
    
    # User loader
    from app.models.user import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    # Root route handler
    @app.route('/')
    def index():
        """Root route - redirect to dashboard if authenticated, otherwise to login"""
        from flask_login import current_user
        from flask import redirect, url_for
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.login'))
    
    return app

# For Celery worker - create app and configure celery
app = create_app()
celery_app = make_celery(app)
