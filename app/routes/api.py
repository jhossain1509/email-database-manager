from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from app import db
from app.models.email import Email, Batch
from app.models.job import Job
from sqlalchemy import func

bp = Blueprint('api', __name__, url_prefix='/api')

@bp.route('/stats')
@login_required
def stats():
    """Get dashboard statistics"""
    if current_user.is_guest():
        # Guest stats
        total_uploaded = Email.query.filter_by(uploaded_by=current_user.id).count()
        total_verified = Email.query.filter(
            Email.uploaded_by == current_user.id,
            Email.is_validated == True,
            Email.is_valid == True
        ).count()
    else:
        # Main DB stats
        total_uploaded = Email.query.count()
        total_verified = Email.query.filter_by(is_validated=True, is_valid=True).count()
    
    return jsonify({
        'total_uploaded': total_uploaded,
        'total_verified': total_verified
    })

@bp.route('/batch/<int:batch_id>/stats')
@login_required
def batch_stats(batch_id):
    """Get batch statistics"""
    batch = Batch.query.get_or_404(batch_id)
    
    # Check access
    if current_user.is_guest() and batch.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    return jsonify({
        'id': batch.id,
        'name': batch.name,
        'status': batch.status,
        'total_count': batch.total_count,
        'valid_count': batch.valid_count,
        'invalid_count': batch.invalid_count,
        'rejected_count': batch.rejected_count,
        'duplicate_count': batch.duplicate_count
    })

@bp.route('/check-file/<int:batch_id>')
@login_required
def check_file(batch_id):
    """Check if batch is ready for download"""
    batch = Batch.query.get_or_404(batch_id)
    
    # Check access
    if current_user.is_guest() and batch.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    # Check if validation is complete
    is_ready = batch.status == 'validated'
    
    return jsonify({
        'ready': is_ready,
        'status': batch.status,
        'valid_count': batch.valid_count,
        'total_count': batch.total_count
    })

@bp.route('/export/domain-stats')
@login_required
def export_domain_stats():
    """Get domain statistics for export based on batch and export type"""
    batch_id = request.args.get('batch_id', type=int)
    export_type = request.args.get('export_type', 'all')
    
    # Guests should not access this endpoint
    if current_user.is_guest():
        return jsonify({'error': 'Access denied'}), 403
    
    # Build base query
    if current_user.is_admin():
        base_query = Email.query
    else:
        base_query = Email.query.filter_by(uploaded_by=current_user.id)
    
    # Filter by batch if specified
    if batch_id:
        batch = Batch.query.get(batch_id)
        if not batch:
            return jsonify({'error': 'Batch not found'}), 404
        
        # Check access
        if not current_user.is_admin() and batch.user_id != current_user.id:
            return jsonify({'error': 'Access denied'}), 403
        
        base_query = base_query.filter_by(batch_id=batch_id)
    
    # Get top domains from config
    from flask import current_app
    TOP_DOMAINS = current_app.config.get('TOP_DOMAINS', [
        'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
        'aol.com', 'icloud.com', 'protonmail.com', 'mail.com',
        'zoho.com', 'gmx.com'
    ])
    
    domain_stats = []
    
    # Calculate stats for each domain
    for domain in TOP_DOMAINS:
        domain_query = base_query.filter_by(domain=domain)
        
        # Apply export type filter
        if export_type == 'verified':
            count = domain_query.filter_by(is_validated=True, is_valid=True, downloaded=False).count()
        elif export_type == 'unverified':
            count = domain_query.filter_by(is_validated=False, downloaded=False).count()
        elif export_type == 'invalid':
            count = domain_query.filter_by(is_validated=True, is_valid=False, downloaded=False).count()
        else:  # 'all'
            count = domain_query.filter_by(downloaded=False).count()
        
        if count > 0:
            total = domain_query.count()
            domain_stats.append({
                'domain': domain,
                'count': count,
                'total': total
            })
    
    # Calculate mixed domain stats
    mixed_query = base_query.filter_by(domain_category='mixed')
    
    if export_type == 'verified':
        mixed_count = mixed_query.filter_by(is_validated=True, is_valid=True, downloaded=False).count()
    elif export_type == 'unverified':
        mixed_count = mixed_query.filter_by(is_validated=False, downloaded=False).count()
    elif export_type == 'invalid':
        mixed_count = mixed_query.filter_by(is_validated=True, is_valid=False, downloaded=False).count()
    else:  # 'all'
        mixed_count = mixed_query.filter_by(downloaded=False).count()
    
    if mixed_count > 0:
        mixed_total = mixed_query.count()
        domain_stats.append({
            'domain': 'mixed',
            'count': mixed_count,
            'total': mixed_total
        })
    
    return jsonify({
        'domain_stats': domain_stats,
        'batch_id': batch_id,
        'export_type': export_type
    })
