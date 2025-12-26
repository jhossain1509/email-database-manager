from datetime import datetime
from flask_login import current_user
from flask import request
from app import db
from app.models.user import User
from app.models.job import ActivityLog

def update_user_activity():
    """Update last activity timestamp for current user"""
    if current_user.is_authenticated:
        current_user.last_activity = datetime.utcnow()
        db.session.commit()

def log_activity(action, description=None, resource_type=None, resource_id=None):
    """Log user activity"""
    if current_user.is_authenticated:
        activity = ActivityLog(
            user_id=current_user.id,
            action=action,
            description=description,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:500] if request.user_agent else None,
            resource_type=resource_type,
            resource_id=resource_id
        )
        db.session.add(activity)
        db.session.commit()

def check_session_timeout():
    """
    Check if user session should timeout.
    Non-admin users: 30 min idle timeout unless job is running
    Admin users: unlimited session
    """
    if not current_user.is_authenticated:
        return False
    
    # Admin has unlimited session
    if current_user.is_admin():
        return False
    
    # Check if user has running jobs
    from app.models.job import Job
    running_jobs = Job.query.filter_by(
        user_id=current_user.id,
        status='running'
    ).first()
    
    if running_jobs:
        # Job is running, don't timeout
        return False
    
    # Check idle time
    if current_user.last_activity:
        from flask import current_app
        timeout = current_app.config.get('PERMANENT_SESSION_LIFETIME', 1800)
        idle_seconds = (datetime.utcnow() - current_user.last_activity).total_seconds()
        
        if idle_seconds > timeout:
            return True
    
    return False
