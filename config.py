import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'postgresql://postgres:postgres@localhost:5432/email_manager'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload settings
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', 104857600))  # 100MB
    # Use absolute paths to avoid path resolution issues
    UPLOAD_FOLDER = os.path.abspath(os.environ.get('UPLOAD_FOLDER', 'uploads'))
    EXPORT_FOLDER = os.path.abspath(os.environ.get('EXPORT_FOLDER', 'exports'))
    
    # Session settings
    SESSION_TYPE = 'filesystem'
    PERMANENT_SESSION_LIFETIME = int(os.environ.get('PERMANENT_SESSION_LIFETIME', 1800))  # 30 minutes
    
    # Redis and Celery
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    
    # Top domains for classification
    TOP_DOMAINS = [
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'aol.com', 'icloud.com', 'protonmail.com', 'mail.com',
        'zoho.com', 'gmx.com'
    ]
    
    # Policy suffixes to block
    BLOCKED_POLICY_SUFFIXES = ['.gov', '.edu']
    
    # Allowed generic TLDs (partial list - common ones)
    GENERIC_TLDS = [
        '.com', '.net', '.org', '.info', '.biz', '.mobi', '.name',
        '.pro', '.tel', '.travel', '.xxx', '.asia', '.cat', '.coop',
        '.jobs', '.aero', '.museum', '.int', '.post', '.xyz', '.online',
        '.site', '.tech', '.store', '.web', '.app', '.blog', '.cloud',
        '.dev', '.live', '.email', '.news', '.space', '.shop'
    ]
