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
