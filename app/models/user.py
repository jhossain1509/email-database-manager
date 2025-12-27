from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(100), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='guest', index=True)
    # Roles: viewer, editor, user, guest, admin, super_admin
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_login = db.Column(db.DateTime)
    last_activity = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    
    # SMTP Verification Permission
    smtp_verification_allowed = db.Column(db.Boolean, default=False, nullable=False)
    
    # Relationships
    batches = db.relationship('Batch', backref='owner', lazy='dynamic', cascade='all, delete-orphan')
    jobs = db.relationship('Job', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    downloads = db.relationship('DownloadHistory', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    activities = db.relationship('ActivityLog', backref='user', lazy='dynamic', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def has_role(self, *roles):
        return self.role in roles
    
    def is_admin(self):
        return self.role in ['admin', 'super_admin']
    
    def is_guest(self):
        return self.role == 'guest'
    
    def can_access_main_db(self):
        """Guest users cannot access main DB"""
        return not self.is_guest()
    
    def __repr__(self):
        return f'<User {self.username} ({self.role})>'
