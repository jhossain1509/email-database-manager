from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.email import IgnoreDomain, Email, Batch, RejectedEmail
from app.models.job import ActivityLog, DownloadHistory, SMTPConfig
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

@bp.route('/cleanup')
@admin_required
def cleanup():
    """Email cleanup management page"""
    from app.models.email import RejectedEmail
    
    # Get counts
    invalid_count = Email.query.filter_by(is_validated=True, is_valid=False).count()
    rejected_count = RejectedEmail.query.count()
    
    # Get batch breakdown
    from sqlalchemy import func
    invalid_by_batch = db.session.query(
        Batch.id,
        Batch.name,
        func.count(Email.id).label('count')
    ).join(Email, Email.batch_id == Batch.id).filter(
        Email.is_validated == True,
        Email.is_valid == False
    ).group_by(Batch.id, Batch.name).all()
    
    rejected_by_batch = db.session.query(
        Batch.id,
        Batch.name,
        func.count(RejectedEmail.id).label('count')
    ).join(RejectedEmail, RejectedEmail.batch_id == Batch.id).group_by(
        Batch.id, Batch.name
    ).all()
    
    return render_template('admin/cleanup.html',
                         invalid_count=invalid_count,
                         rejected_count=rejected_count,
                         invalid_by_batch=invalid_by_batch,
                         rejected_by_batch=rejected_by_batch)

@bp.route('/cleanup/delete-invalid', methods=['POST'])
@admin_required
def delete_invalid_emails():
    """Delete invalid emails"""
    batch_id = request.form.get('batch_id', type=int)
    
    if batch_id:
        # Delete invalid emails from specific batch
        deleted = Email.query.filter_by(
            batch_id=batch_id,
            is_validated=True,
            is_valid=False
        ).delete(synchronize_session='fetch')
        
        batch = Batch.query.get(batch_id)
        batch_name = batch.name if batch else f"Batch {batch_id}"
        
        db.session.commit()
        log_activity('admin_action', f'Deleted {deleted} invalid emails from {batch_name}')
        flash(f'Deleted {deleted} invalid emails from {batch_name}.', 'success')
    else:
        # Delete all invalid emails
        deleted = Email.query.filter_by(is_validated=True, is_valid=False).delete(synchronize_session='fetch')
        db.session.commit()
        
        log_activity('admin_action', f'Deleted {deleted} invalid emails from all batches')
        flash(f'Deleted {deleted} invalid emails from all batches.', 'success')
    
    return redirect(url_for('admin.cleanup'))

@bp.route('/cleanup/delete-rejected', methods=['POST'])
@admin_required
def delete_rejected_emails():
    """Delete rejected emails"""
    from app.models.email import RejectedEmail
    
    batch_id = request.form.get('batch_id', type=int)
    
    if batch_id:
        # Delete rejected emails from specific batch
        deleted = RejectedEmail.query.filter_by(batch_id=batch_id).delete(synchronize_session='fetch')
        
        batch = Batch.query.get(batch_id)
        batch_name = batch.name if batch else f"Batch {batch_id}"
        
        db.session.commit()
        log_activity('admin_action', f'Deleted {deleted} rejected emails from {batch_name}')
        flash(f'Deleted {deleted} rejected emails from {batch_name}.', 'success')
    else:
        # Delete all rejected emails
        deleted = RejectedEmail.query.delete(synchronize_session='fetch')
        db.session.commit()
        
        log_activity('admin_action', f'Deleted {deleted} rejected emails from all batches')
        flash(f'Deleted {deleted} rejected emails from all batches.', 'success')
    
    return redirect(url_for('admin.cleanup'))

@bp.route('/cleanup/delete-both', methods=['POST'])
@admin_required
def delete_invalid_and_rejected():
    """Delete both invalid and rejected emails"""
    from app.models.email import RejectedEmail
    
    batch_id = request.form.get('batch_id', type=int)
    
    if batch_id:
        # Delete from specific batch
        invalid_deleted = Email.query.filter_by(
            batch_id=batch_id,
            is_validated=True,
            is_valid=False
        ).delete(synchronize_session='fetch')
        
        rejected_deleted = RejectedEmail.query.filter_by(batch_id=batch_id).delete(synchronize_session='fetch')
        
        batch = Batch.query.get(batch_id)
        batch_name = batch.name if batch else f"Batch {batch_id}"
        
        db.session.commit()
        
        total = invalid_deleted + rejected_deleted
        log_activity('admin_action', f'Deleted {total} emails ({invalid_deleted} invalid, {rejected_deleted} rejected) from {batch_name}')
        flash(f'Deleted {total} emails ({invalid_deleted} invalid, {rejected_deleted} rejected) from {batch_name}.', 'success')
    else:
        # Delete all
        invalid_deleted = Email.query.filter_by(is_validated=True, is_valid=False).delete(synchronize_session='fetch')
        rejected_deleted = RejectedEmail.query.delete(synchronize_session='fetch')
        
        db.session.commit()
        
        total = invalid_deleted + rejected_deleted
        log_activity('admin_action', f'Deleted {total} emails ({invalid_deleted} invalid, {rejected_deleted} rejected) from all batches')
        flash(f'Deleted {total} emails ({invalid_deleted} invalid, {rejected_deleted} rejected) from all batches.', 'success')
    
    return redirect(url_for('admin.cleanup'))


@bp.route('/smtp-config', methods=['GET', 'POST'])
@admin_required
def smtp_config():
    """SMTP Configuration for email validation"""
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'test':
            # Test SMTP connection
            import smtplib
            import socket
            
            host = request.form.get('smtp_host')
            port = int(request.form.get('smtp_port', 25))
            username = request.form.get('smtp_username')
            password = request.form.get('smtp_password')
            use_tls = request.form.get('use_tls') == 'on'
            use_ssl = request.form.get('use_ssl') == 'on'
            
            try:
                if use_ssl:
                    server = smtplib.SMTP_SSL(host, port, timeout=10)
                else:
                    server = smtplib.SMTP(host, port, timeout=10)
                    if use_tls:
                        server.starttls()
                
                if username and password:
                    server.login(username, password)
                
                server.quit()
                return jsonify({'success': True, 'message': 'SMTP connection successful!'})
            except socket.timeout:
                return jsonify({'success': False, 'message': 'Connection timeout. Please check host and port.'})
            except smtplib.SMTPAuthenticationError:
                return jsonify({'success': False, 'message': 'Authentication failed. Please check username and password.'})
            except Exception as e:
                return jsonify({'success': False, 'message': f'Connection failed: {str(e)}'})
        
        elif action == 'bulk_upload':
            # Bulk upload SMTP servers
            bulk_list = request.form.get('bulk_smtp_list', '').strip()
            thread_count = int(request.form.get('thread_count', 5))
            enable_rotation = request.form.get('enable_rotation') == 'on'
            
            if not bulk_list:
                flash('Please provide SMTP server list.', 'danger')
                return redirect(url_for('admin.smtp_config'))
            
            lines = bulk_list.split('\n')
            added_count = 0
            error_count = 0
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                parts = line.split('|')
                if len(parts) != 4:
                    error_count += 1
                    continue
                
                host, port, username, password = parts
                
                try:
                    # Check if already exists
                    existing = SMTPConfig.query.filter_by(
                        smtp_host=host.strip(),
                        smtp_port=int(port.strip()),
                        smtp_username=username.strip()
                    ).first()
                    
                    if existing:
                        continue
                    
                    config = SMTPConfig(
                        name=f'{host.strip()}:{port.strip()}',
                        smtp_host=host.strip(),
                        smtp_port=int(port.strip()),
                        smtp_username=username.strip(),
                        smtp_password=password.strip(),
                        use_tls=int(port.strip()) == 587,
                        use_ssl=int(port.strip()) == 465,
                        timeout=30,
                        is_active=True,
                        thread_count=thread_count,
                        enable_rotation=enable_rotation
                    )
                    db.session.add(config)
                    added_count += 1
                except Exception as e:
                    error_count += 1
                    continue
            
            db.session.commit()
            
            log_activity('admin_action', f'Bulk uploaded {added_count} SMTP servers')
            
            if added_count > 0:
                flash(f'Successfully added {added_count} SMTP servers. {error_count} errors.', 'success')
            else:
                flash(f'No servers added. {error_count} errors.', 'warning')
            
            return redirect(url_for('admin.smtp_config'))
        
        elif action == 'delete':
            # Delete SMTP server
            server_id = request.form.get('server_id')
            config = SMTPConfig.query.get(server_id)
            if config:
                db.session.delete(config)
                db.session.commit()
                log_activity('admin_action', f'Deleted SMTP server: {config.name}')
                flash('SMTP server deleted successfully.', 'success')
            return redirect(url_for('admin.smtp_config'))
        
        elif action == 'save':
            # Save SMTP configuration
            config = SMTPConfig.query.first()
            if not config:
                config = SMTPConfig()
            
            config.name = request.form.get('name', 'Default SMTP Config')
            config.smtp_host = request.form.get('smtp_host')
            config.smtp_port = int(request.form.get('smtp_port', 25))
            config.smtp_username = request.form.get('smtp_username')
            config.smtp_password = request.form.get('smtp_password')
            config.use_tls = request.form.get('use_tls') == 'on'
            config.use_ssl = request.form.get('use_ssl') == 'on'
            config.timeout = int(request.form.get('timeout', 30))
            config.is_active = request.form.get('is_active') == 'on'
            
            db.session.add(config)
            db.session.commit()
            
            log_activity('admin_action', 'Updated SMTP configuration')
            flash('SMTP configuration saved successfully.', 'success')
            return redirect(url_for('admin.smtp_config'))
    
    # GET request - show form
    config = SMTPConfig.query.first()
    smtp_servers = SMTPConfig.query.order_by(SMTPConfig.is_active.desc(), SMTPConfig.last_used_at.desc()).all()
    return render_template('admin/smtp_config.html', config=config, smtp_servers=smtp_servers)
