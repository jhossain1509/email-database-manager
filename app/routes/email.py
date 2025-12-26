from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app import db
from app.models.email import Email, Batch, RejectedEmail
from app.models.job import Job, DownloadHistory
from app.jobs.tasks import import_emails_task, validate_emails_task, export_emails_task
from app.utils.helpers import log_activity
from app.utils.decorators import guest_cannot_access_main_db
import os
import csv
import zipfile
from datetime import datetime
from sqlalchemy import desc

bp = Blueprint('email', __name__, url_prefix='/email')

ALLOWED_EXTENSIONS = {'csv', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    """Upload email file"""
    if request.method == 'POST':
        # Check if file is present
        if 'file' not in request.files:
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        file = request.files['file']
        
        if file.filename == '':
            flash('No file selected.', 'danger')
            return redirect(request.url)
        
        if not allowed_file(file.filename):
            flash('Invalid file type. Only CSV and TXT files are allowed.', 'danger')
            return redirect(request.url)
        
        # Get form data
        batch_name = request.form.get('batch_name', '').strip()
        consent_granted = request.form.get('consent_granted') == 'on'
        
        if not batch_name:
            batch_name = f"Upload {datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        
        if not consent_granted:
            flash('You must grant consent to upload emails.', 'warning')
            return redirect(request.url)
        
        # Save file
        filename = secure_filename(file.filename)
        from flask import current_app
        upload_folder = current_app.config['UPLOAD_FOLDER']
        os.makedirs(upload_folder, exist_ok=True)
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        saved_filename = f"{current_user.id}_{timestamp}_{filename}"
        file_path = os.path.join(upload_folder, saved_filename)
        file.save(file_path)
        
        # Create batch record
        batch = Batch(
            name=batch_name,
            filename=saved_filename,
            user_id=current_user.id,
            status='processing'
        )
        db.session.add(batch)
        db.session.commit()
        
        # Start import job
        task = import_emails_task.delay(
            batch.id,
            file_path,
            current_user.id,
            consent_granted
        )
        
        # Create job record
        job = Job(
            job_id=task.id,
            job_type='import',
            user_id=current_user.id,
            batch_id=batch.id,
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        log_activity('upload', f'Uploaded batch: {batch_name}', 'batch', batch.id)
        
        flash(f'File uploaded successfully! Import job started.', 'success')
        return redirect(url_for('email.job_status', job_id=task.id))
    
    return render_template('email/upload.html')

@bp.route('/batches')
@login_required
def batches():
    """List all batches"""
    if current_user.is_guest():
        # Guest sees only their batches
        user_batches = Batch.query.filter_by(user_id=current_user.id)\
            .order_by(desc(Batch.created_at))\
            .all()
    elif current_user.is_admin():
        # Admin sees all batches
        user_batches = Batch.query.order_by(desc(Batch.created_at)).all()
    else:
        # Regular users see their batches
        user_batches = Batch.query.filter_by(user_id=current_user.id)\
            .order_by(desc(Batch.created_at))\
            .all()
    
    return render_template('email/batches.html', batches=user_batches)

@bp.route('/batch/<int:batch_id>')
@login_required
def batch_detail(batch_id):
    """View batch details"""
    batch = Batch.query.get_or_404(batch_id)
    
    # Check access
    if current_user.is_guest() and batch.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('email.batches'))
    
    # Get batch statistics
    emails = Email.query.filter_by(batch_id=batch_id).limit(100).all()
    rejected = RejectedEmail.query.filter_by(batch_id=batch_id).limit(100).all()
    jobs = Job.query.filter_by(batch_id=batch_id).order_by(desc(Job.created_at)).all()
    
    return render_template(
        'email/batch_detail.html',
        batch=batch,
        emails=emails,
        rejected=rejected,
        jobs=jobs
    )

@bp.route('/validate', methods=['GET', 'POST'])
@login_required
def validate():
    """Validate emails in a batch"""
    if request.method == 'POST':
        batch_id = request.form.get('batch_id', type=int)
        check_dns = request.form.get('check_dns') == 'on'
        check_role = request.form.get('check_role') == 'on'
        
        if not batch_id:
            flash('Please select a batch.', 'danger')
            return redirect(request.url)
        
        batch = Batch.query.get(batch_id)
        if not batch:
            flash('Batch not found.', 'danger')
            return redirect(request.url)
        
        # Check access
        if current_user.is_guest() and batch.user_id != current_user.id:
            flash('Access denied.', 'danger')
            return redirect(request.url)
        
        # Start validation job
        task = validate_emails_task.delay(
            batch_id,
            current_user.id,
            check_dns,
            check_role
        )
        
        # Create job record
        job = Job(
            job_id=task.id,
            job_type='validate',
            user_id=current_user.id,
            batch_id=batch_id,
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        log_activity('validate', f'Started validation for batch: {batch.name}', 'batch', batch.id)
        
        flash(f'Validation started for batch: {batch.name}', 'success')
        return redirect(url_for('email.job_status', job_id=task.id))
    
    # Get batches for selection
    if current_user.is_guest():
        user_batches = Batch.query.filter_by(user_id=current_user.id).all()
    else:
        user_batches = Batch.query.filter_by(user_id=current_user.id).all()
    
    return render_template('email/validate.html', batches=user_batches)

@bp.route('/job/<job_id>')
@login_required
def job_status(job_id):
    """View job status"""
    job = Job.query.filter_by(job_id=job_id).first_or_404()
    
    # Check access
    if not current_user.is_admin() and job.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    return render_template('email/job_status.html', job=job)

@bp.route('/api/job/<job_id>/status')
@login_required
def api_job_status(job_id):
    """API endpoint for job status polling"""
    job = Job.query.filter_by(job_id=job_id).first_or_404()
    
    # Check access
    if not current_user.is_admin() and job.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({
        'id': job.id,
        'job_id': job.job_id,
        'job_type': job.job_type,
        'status': job.status,
        'total': job.total,
        'processed': job.processed,
        'errors': job.errors,
        'progress_percent': job.progress_percent,
        'result_message': job.result_message,
        'error_message': job.error_message
    })

@bp.route('/download-rejected/<int:batch_id>')
@login_required
def download_rejected(batch_id):
    """Download rejected emails for a batch"""
    batch = Batch.query.get_or_404(batch_id)
    
    # Check access
    if current_user.is_guest() and batch.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('email.batches'))
    
    # Get rejected emails
    rejected = RejectedEmail.query.filter_by(batch_id=batch_id).all()
    
    if not rejected:
        flash('No rejected emails found for this batch.', 'info')
        return redirect(url_for('email.batch_detail', batch_id=batch_id))
    
    # Create CSV file
    from flask import current_app
    export_folder = current_app.config['EXPORT_FOLDER']
    os.makedirs(export_folder, exist_ok=True)
    
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    filename = f"rejected_{batch_id}_{timestamp}.csv"
    file_path = os.path.join(export_folder, filename)
    
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['Email', 'Domain', 'Reason', 'Details', 'Rejected At'])
        
        for r in rejected:
            writer.writerow([
                r.email,
                r.domain,
                r.reason,
                r.details or '',
                r.rejected_at.strftime('%Y-%m-%d %H:%M:%S')
            ])
    
    log_activity('download', f'Downloaded rejected emails for batch: {batch.name}', 'batch', batch.id)
    
    return send_file(file_path, as_attachment=True, download_name=filename)

@bp.route('/export', methods=['GET', 'POST'])
@login_required
def export():
    """Export emails with advanced filtering"""
    if request.method == 'POST':
        export_type = request.form.get('export_type', 'verified')
        batch_id = request.form.get('batch_id', type=int)
        filter_domains_str = request.form.get('filter_domains', '').strip()
        export_format = request.form.get('export_format', 'csv')
        split_files = request.form.get('split_files') == 'on'
        split_size = request.form.get('split_size', 10000, type=int)
        custom_fields = request.form.get('custom_fields', '').strip()
        
        # Parse domain limits (format: domain1:limit1,domain2:limit2)
        domain_limits = {}
        domain_limit_str = request.form.get('domain_limits', '').strip()
        if domain_limit_str:
            for item in domain_limit_str.split(','):
                if ':' in item:
                    domain, limit = item.split(':', 1)
                    domain = domain.strip()
                    try:
                        domain_limits[domain] = int(limit.strip())
                    except ValueError:
                        pass
        
        # Parse filter domains (for backward compatibility)
        filter_domains = None
        if filter_domains_str:
            filter_domains = [d.strip() for d in filter_domains_str.split(',') if d.strip()]
        
        # Parse custom fields
        fields_list = None
        if custom_fields:
            fields_list = [f.strip() for f in custom_fields.split(',') if f.strip()]
        
        # Check batch access for guest users
        if batch_id:
            batch = Batch.query.get(batch_id)
            if batch and current_user.is_guest() and batch.user_id != current_user.id:
                flash('Access denied.', 'danger')
                return redirect(request.url)
        
        # Guest users can only export from their own batches
        if current_user.is_guest() and not batch_id:
            flash('Guest users must select a specific batch to export.', 'warning')
            return redirect(request.url)
        
        # Start export job with enhanced parameters
        task = export_emails_task.delay(
            current_user.id,
            export_type,
            batch_id,
            filter_domains,
            domain_limits,
            split_files,
            split_size,
            export_format,
            fields_list
        )
        
        # Create job record
        job = Job(
            job_id=task.id,
            job_type='export',
            user_id=current_user.id,
            batch_id=batch_id,
            status='pending'
        )
        db.session.add(job)
        db.session.commit()
        
        log_activity('export', f'Started export: {export_type}', 'job', job.id)
        
        flash(f'Export started! Job ID: {task.id}', 'success')
        return redirect(url_for('email.job_status', job_id=task.id))
    
    # Get batches for selection
    if current_user.is_guest():
        user_batches = Batch.query.filter_by(user_id=current_user.id).all()
        base_query = Email.query.filter_by(uploaded_by=current_user.id)
    elif current_user.is_admin():
        user_batches = Batch.query.all()
        base_query = Email.query
    else:
        user_batches = Batch.query.filter_by(user_id=current_user.id).all()
        base_query = Email.query.filter_by(uploaded_by=current_user.id)
    
    # Get domain statistics
    from flask import current_app
    from sqlalchemy import func
    
    TOP_DOMAINS = current_app.config.get('TOP_DOMAINS', [
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'aol.com', 'icloud.com', 'protonmail.com', 'mail.com',
        'zoho.com', 'gmx.com'
    ])
    
    domain_stats = []
    for domain in TOP_DOMAINS:
        count = base_query.filter_by(domain=domain).count()
        if count > 0:
            domain_stats.append({
                'domain': domain,
                'count': count,
                'category': domain
            })
    
    # Get mixed domain count
    mixed_count = base_query.filter_by(domain_category='mixed').count()
    if mixed_count > 0:
        domain_stats.append({
            'domain': 'mixed',
            'count': mixed_count,
            'category': 'mixed'
        })
    
    return render_template('email/export.html', batches=user_batches, domain_stats=domain_stats)

@bp.route('/download/<int:history_id>')
@login_required
def download_export(history_id):
    """Download exported file from history"""
    history = DownloadHistory.query.get_or_404(history_id)
    
    # Check access
    if not current_user.is_admin() and history.user_id != current_user.id:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    # Check if file exists
    if not os.path.exists(history.file_path):
        flash('File no longer exists.', 'danger')
        return redirect(url_for('dashboard.index'))
    
    log_activity('download', f'Downloaded export: {history.filename}', 'download_history', history.id)
    
    return send_file(history.file_path, as_attachment=True, download_name=history.filename)

@bp.route('/download-history')
@login_required
def download_history():
    """View user's download history"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Get user's download history
    if current_user.is_guest():
        query = DownloadHistory.query.filter_by(user_id=current_user.id)
    elif current_user.is_admin():
        # Admin can see all history (optional - uncomment if needed)
        # query = DownloadHistory.query
        query = DownloadHistory.query.filter_by(user_id=current_user.id)
    else:
        query = DownloadHistory.query.filter_by(user_id=current_user.id)
    
    # Add search filter
    search = request.args.get('search', '').strip()
    if search:
        query = query.filter(DownloadHistory.filename.ilike(f'%{search}%'))
    
    # Order by recent first
    query = query.order_by(desc(DownloadHistory.downloaded_at))
    
    # Paginate
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    histories = pagination.items
    
    return render_template('email/download_history.html', 
                         histories=histories, 
                         pagination=pagination,
                         search=search)

@bp.route('/search', methods=['GET', 'POST'])
@login_required
def email_search():
    """Search for emails in database"""
    results = []
    search_query = ''
    
    if request.method == 'POST' or request.args.get('q'):
        search_query = request.form.get('search', '') or request.args.get('q', '')
        search_query = search_query.strip().lower()
        
        if search_query:
            # Build base query based on user role
            if current_user.is_guest():
                base_query = Email.query.filter_by(uploaded_by=current_user.id)
            else:
                base_query = Email.query
            
            # Search for email
            results = base_query.filter(
                Email.email.ilike(f'%{search_query}%')
            ).limit(100).all()
            
            log_activity('search', f'Searched for: {search_query}', 'email', None)
    
    return render_template('email/search.html', results=results, search_query=search_query)
