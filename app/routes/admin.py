from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.email import IgnoreDomain, Email, Batch
from app.models.job import ActivityLog, DownloadHistory
from app.utils.decorators import admin_required
from app.utils.helpers import log_activity
from sqlalchemy import desc, func
from datetime import datetime
import os

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.route('/')
@admin_required
def index():
    """Admin dashboard"""
    # System statistics
    total_users = User.query.count()
    total_emails = Email.query.count()
    total_batches = Batch.query.count()
    
    # User breakdown by role
    user_roles = db.session.query(
        User.role,
        func.count(User.id).label('count')
    ).group_by(User.role).all()
    
    # Recent users
    recent_users = User.query.order_by(desc(User.created_at)).limit(10).all()
    
    # Recent activity
    recent_activities = ActivityLog.query.order_by(desc(ActivityLog.created_at)).limit(20).all()
    
    return render_template(
        'admin/index.html',
        total_users=total_users,
        total_emails=total_emails,
        total_batches=total_batches,
        user_roles=user_roles,
        recent_users=recent_users,
        recent_activities=recent_activities
    )

@bp.route('/users')
@admin_required
def users():
    """Manage users"""
    all_users = User.query.order_by(desc(User.created_at)).all()
    return render_template('admin/users.html', users=all_users)

@bp.route('/user/create', methods=['GET', 'POST'])
@admin_required
def create_user():
    """Create new user from admin panel"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'user')
        
        # Validation
        if not username or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('admin/create_user.html')
        
        if role not in ['viewer', 'editor', 'user', 'guest', 'admin', 'super_admin']:
            flash('Invalid role.', 'danger')
            return render_template('admin/create_user.html')
        
        # Super admin restriction
        if role == 'super_admin' and current_user.role != 'super_admin':
            flash('Only super admin can create super admin users.', 'danger')
            return render_template('admin/create_user.html')
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.', 'danger')
            return render_template('admin/create_user.html')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return render_template('admin/create_user.html')
        
        # Create user
        user = User(
            username=username,
            email=email,
            role=role
        )
        user.set_password(password)
        
        db.session.add(user)
        db.session.commit()
        
        log_activity('admin_action', f'Created user: {username} with role: {role}', 'user', user.id)
        
        flash(f'User {username} created successfully with role: {role}.', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/create_user.html')

@bp.route('/user/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def edit_user(user_id):
    """Edit user"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        role = request.form.get('role')
        is_active = request.form.get('is_active') == 'on'
        
        # Super admin restriction
        if role == 'super_admin' and current_user.role != 'super_admin':
            flash('Only super admin can assign super admin role.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        
        if user.id == current_user.id and not is_active:
            flash('You cannot deactivate your own account.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))
        
        user.role = role
        user.is_active = is_active
        db.session.commit()
        
        log_activity('admin_action', f'Updated user: {user.username}', 'user', user.id)
        
        flash(f'User {user.username} updated successfully.', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/edit_user.html', user=user)

@bp.route('/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Delete user"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'danger')
        return redirect(url_for('admin.users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    log_activity('admin_action', f'Deleted user: {username}')
    
    flash(f'User {username} deleted successfully.', 'success')
    return redirect(url_for('admin.users'))

@bp.route('/user/<int:user_id>/reset-password', methods=['GET', 'POST'])
@admin_required
def reset_user_password(user_id):
    """Reset user password"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        # Validation
        if not new_password or not confirm_password:
            flash('Both password fields are required.', 'danger')
            return redirect(url_for('admin.reset_user_password', user_id=user_id))
        
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('admin.reset_user_password', user_id=user_id))
        
        if len(new_password) < 6:
            flash('Password must be at least 6 characters long.', 'danger')
            return redirect(url_for('admin.reset_user_password', user_id=user_id))
        
        # Reset password
        user.set_password(new_password)
        db.session.commit()
        
        log_activity('admin_action', f'Reset password for user: {user.username}', 'user', user.id)
        
        flash(f'Password for user {user.username} reset successfully.', 'success')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/reset_password.html', user=user)

@bp.route('/ignore-domains')
@admin_required
def ignore_domains():
    """Manage ignore domains"""
    domains = IgnoreDomain.query.order_by(IgnoreDomain.domain).all()
    return render_template('admin/ignore_domains.html', domains=domains)

@bp.route('/ignore-domains/add', methods=['POST'])
@admin_required
def add_ignore_domain():
    """Add domain to ignore list"""
    domain = request.form.get('domain', '').strip().lower()
    reason = request.form.get('reason', '').strip()
    
    if not domain:
        flash('Domain is required.', 'danger')
        return redirect(url_for('admin.ignore_domains'))
    
    # Check if already exists
    if IgnoreDomain.query.filter_by(domain=domain).first():
        flash(f'Domain {domain} is already in the ignore list.', 'warning')
        return redirect(url_for('admin.ignore_domains'))
    
    # Add domain
    ignore_domain = IgnoreDomain(
        domain=domain,
        added_by=current_user.id,
        reason=reason
    )
    db.session.add(ignore_domain)
    db.session.commit()
    
    log_activity('admin_action', f'Added ignore domain: {domain}', 'ignore_domain', ignore_domain.id)
    
    flash(f'Domain {domain} added to ignore list.', 'success')
    return redirect(url_for('admin.ignore_domains'))

@bp.route('/ignore-domains/bulk-add', methods=['POST'])
@admin_required
def bulk_add_ignore_domains():
    """Bulk add domains to ignore list"""
    domains_text = request.form.get('domains_text', '').strip()
    
    if not domains_text:
        flash('No domains provided.', 'danger')
        return redirect(url_for('admin.ignore_domains'))
    
    # Parse domains (newline or comma separated)
    domains = []
    for line in domains_text.split('\n'):
        for domain in line.split(','):
            domain = domain.strip().lower()
            if domain:
                domains.append(domain)
    
    added_count = 0
    skipped_count = 0
    
    for domain in domains:
        # Check if already exists
        if IgnoreDomain.query.filter_by(domain=domain).first():
            skipped_count += 1
            continue
        
        # Add domain
        ignore_domain = IgnoreDomain(
            domain=domain,
            added_by=current_user.id,
            reason='Bulk import'
        )
        db.session.add(ignore_domain)
        added_count += 1
    
    db.session.commit()
    
    log_activity('admin_action', f'Bulk added {added_count} ignore domains')
    
    flash(f'Added {added_count} domains, skipped {skipped_count} duplicates.', 'success')
    return redirect(url_for('admin.ignore_domains'))

@bp.route('/ignore-domains/<int:domain_id>/delete', methods=['POST'])
@admin_required
def delete_ignore_domain(domain_id):
    """Delete ignore domain"""
    domain = IgnoreDomain.query.get_or_404(domain_id)
    
    domain_name = domain.domain
    db.session.delete(domain)
    db.session.commit()
    
    log_activity('admin_action', f'Deleted ignore domain: {domain_name}')
    
    flash(f'Domain {domain_name} removed from ignore list.', 'success')
    return redirect(url_for('admin.ignore_domains'))

@bp.route('/download-history')
@admin_required
def download_history():
    """View download history"""
    history = DownloadHistory.query.order_by(desc(DownloadHistory.downloaded_at)).limit(100).all()
    return render_template('admin/download_history.html', history=history)

@bp.route('/download-history/<int:history_id>/redownload')
@admin_required
def redownload(history_id):
    """Re-download a file from history"""
    history = DownloadHistory.query.get_or_404(history_id)
    
    # Check if file exists
    if not os.path.exists(history.file_path):
        flash('File no longer exists.', 'danger')
        return redirect(url_for('admin.download_history'))
    
    log_activity('admin_action', f'Re-downloaded file: {history.filename}', 'download_history', history.id)
    
    return send_file(history.file_path, as_attachment=True, download_name=history.filename)

@bp.route('/activity-logs')
@admin_required
def activity_logs():
    """View activity logs"""
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    pagination = ActivityLog.query.order_by(desc(ActivityLog.created_at)).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/activity_logs.html', pagination=pagination)
