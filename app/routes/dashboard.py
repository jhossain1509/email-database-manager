from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from app import db
from app.models.email import Email, Batch, RejectedEmail
from app.models.job import Job, ActivityLog, DomainReputation
from app.utils.helpers import update_user_activity, check_session_timeout
from sqlalchemy import func, desc
from datetime import datetime, timedelta

bp = Blueprint('dashboard', __name__, url_prefix='/dashboard')

@bp.before_request
@login_required
def before_request():
    """Check session timeout and update activity"""
    if check_session_timeout():
        from flask_login import logout_user
        from flask import flash, redirect, url_for, session
        logout_user()
        session.clear()
        flash('Your session has expired due to inactivity.', 'warning')
        return redirect(url_for('auth.login'))
    
    update_user_activity()

@bp.route('/')
@login_required
def index():
    """Main dashboard - different views for guest vs regular users"""
    
    if current_user.is_guest():
        return guest_dashboard()
    else:
        return user_dashboard()

def guest_dashboard():
    """Dashboard for guest users - only their own uploads"""
    user_id = current_user.id
    
    # Get guest's own batches
    batches = Batch.query.filter_by(user_id=user_id).all()
    batch_ids = [b.id for b in batches]
    
    # Statistics - only guest's own data
    total_uploaded = Email.query.filter(
        Email.uploaded_by == user_id
    ).count()
    
    total_verified = Email.query.filter(
        Email.uploaded_by == user_id,
        Email.is_validated == True,
        Email.is_valid == True
    ).count()
    
    total_unverified = Email.query.filter(
        Email.uploaded_by == user_id,
        Email.is_validated == False
    ).count()
    
    total_downloaded = Email.query.filter(
        Email.uploaded_by == user_id,
        Email.downloaded == True
    ).count()
    
    total_rejected = RejectedEmail.query.filter(
        RejectedEmail.batch_id.in_(batch_ids) if batch_ids else False
    ).count()
    
    available_download = Email.query.filter(
        Email.uploaded_by == user_id,
        Email.is_validated == True,
        Email.is_valid == True,
        Email.downloaded == False
    ).count()
    
    # Recent jobs
    recent_jobs = Job.query.filter_by(user_id=user_id)\
        .order_by(desc(Job.created_at))\
        .limit(5)\
        .all()
    
    # Recent activity
    recent_activities = ActivityLog.query.filter_by(user_id=user_id)\
        .order_by(desc(ActivityLog.created_at))\
        .limit(10)\
        .all()
    
    # Top domains from guest's uploads
    top_domains = db.session.query(
        Email.domain_category,
        func.count(Email.id).label('count')
    ).filter(
        Email.uploaded_by == user_id
    ).group_by(
        Email.domain_category
    ).order_by(
        desc('count')
    ).limit(11).all()
    
    stats = {
        'total_uploaded': total_uploaded,
        'total_verified': total_verified,
        'total_unverified': total_unverified,
        'total_downloaded': total_downloaded,
        'total_rejected': total_rejected,
        'available_download': available_download
    }
    
    return render_template(
        'dashboard/guest_dashboard.html',
        stats=stats,
        top_domains=top_domains,
        recent_jobs=recent_jobs,
        recent_activities=recent_activities,
        batches=batches
    )

def user_dashboard():
    """Dashboard for regular users - access to main DB"""
    
    # Check if admin for system-wide stats
    if current_user.is_admin():
        # System-wide statistics
        total_uploaded = Email.query.count()
        total_verified = Email.query.filter_by(is_validated=True, is_valid=True).count()
        total_unverified = Email.query.filter_by(is_validated=False).count()
        total_downloaded = Email.query.filter_by(downloaded=True).count()
        total_rejected = RejectedEmail.query.count()
        
        # Recent jobs - all users
        recent_jobs = Job.query.order_by(desc(Job.created_at)).limit(5).all()
        
        # Recent activities - all users
        recent_activities = ActivityLog.query.order_by(desc(ActivityLog.created_at)).limit(10).all()
    else:
        # User can see main DB stats but recent activity is limited
        total_uploaded = Email.query.count()
        total_verified = Email.query.filter_by(is_validated=True, is_valid=True).count()
        total_unverified = Email.query.filter_by(is_validated=False).count()
        total_downloaded = Email.query.filter_by(downloaded=True).count()
        total_rejected = RejectedEmail.query.count()
        
        # Recent jobs - own jobs
        recent_jobs = Job.query.filter_by(user_id=current_user.id)\
            .order_by(desc(Job.created_at))\
            .limit(5)\
            .all()
        
        # Recent activities - own activities
        recent_activities = ActivityLog.query.filter_by(user_id=current_user.id)\
            .order_by(desc(ActivityLog.created_at))\
            .limit(10)\
            .all()
    
    available_download = Email.query.filter_by(
        is_validated=True,
        is_valid=True,
        downloaded=False
    ).count()
    
    # Top domains from entire DB
    top_domains = db.session.query(
        Email.domain_category,
        func.count(Email.id).label('count')
    ).group_by(
        Email.domain_category
    ).order_by(
        desc('count')
    ).limit(11).all()
    
    # Get all batches (admin) or user's batches
    if current_user.is_admin():
        batches = Batch.query.order_by(desc(Batch.created_at)).limit(10).all()
    else:
        batches = Batch.query.filter_by(user_id=current_user.id)\
            .order_by(desc(Batch.created_at))\
            .all()
    
    stats = {
        'total_uploaded': total_uploaded,
        'total_verified': total_verified,
        'total_unverified': total_unverified,
        'total_downloaded': total_downloaded,
        'total_rejected': total_rejected,
        'available_download': available_download
    }
    
    return render_template(
        'dashboard/user_dashboard.html',
        stats=stats,
        top_domains=top_domains,
        recent_jobs=recent_jobs,
        recent_activities=recent_activities,
        batches=batches
    )
