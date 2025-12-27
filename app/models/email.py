from app import db
from datetime import datetime

class Email(db.Model):
    __tablename__ = 'emails'
    
    id = db.Column(db.Integer, primary_key=True)
    # Note: unique constraint is handled by index on LOWER(email) in migration
    email = db.Column(db.String(255), nullable=False, index=True)
    domain = db.Column(db.String(255), nullable=False, index=True)
    domain_category = db.Column(db.String(50), index=True)  # top_domain name or 'mixed'
    
    # Status field: unverified | verified | rejected | suppressed
    status = db.Column(db.String(20), default='unverified', nullable=False, index=True)
    
    # Legacy validation fields (keep for backward compatibility during transition)
    is_validated = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_valid = db.Column(db.Boolean, default=None)
    validation_error = db.Column(db.Text)
    
    # Quality metrics
    quality_score = db.Column(db.Integer)  # 0-100
    
    # Tracking
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    verified_at = db.Column(db.DateTime, nullable=True)
    
    # Compliance
    consent_granted = db.Column(db.Boolean, default=False, nullable=False)
    suppressed = db.Column(db.Boolean, default=False, nullable=False, index=True)
    
    # Download tracking - downloaded_at replaces downloaded boolean
    downloaded_at = db.Column(db.DateTime, nullable=True, index=True)
    downloaded = db.Column(db.Boolean, default=False, nullable=False, index=True)  # Keep for backward compat
    download_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Additional metadata
    engagement_prediction = db.Column(db.String(20))  # high, medium, low
    rejected_reason = db.Column(db.String(255), nullable=True)  # If status is rejected
    
    __table_args__ = (
        db.Index('idx_email_domain', 'email', 'domain'),
        db.Index('idx_batch_valid', 'batch_id', 'is_valid'),
        db.Index('idx_status_downloaded', 'status', 'downloaded_at'),
    )
    
    def __repr__(self):
        return f'<Email {self.email}>'

class Batch(db.Model):
    __tablename__ = 'batches'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=False)  # original_filename
    
    # Owner
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Status
    status = db.Column(db.String(50), default='queued', nullable=False, index=True)
    # Status: queued, running, success, failed
    
    # Statistics - aligned with problem requirements
    total_rows = db.Column(db.Integer, default=0, nullable=False)  # Total input lines
    imported_count = db.Column(db.Integer, default=0, nullable=False)  # Successfully inserted
    rejected_count = db.Column(db.Integer, default=0, nullable=False)  # Rejected emails
    duplicate_count = db.Column(db.Integer, default=0, nullable=False)  # Duplicate emails
    
    # Legacy fields (keep for backward compatibility)
    total_count = db.Column(db.Integer, default=0, nullable=False)
    valid_count = db.Column(db.Integer, default=0, nullable=False)
    invalid_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Rejected file storage
    rejected_file_path = db.Column(db.String(500), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Organization
    tags = db.Column(db.Text)  # Comma-separated tags
    notes = db.Column(db.Text)
    
    # Relationships
    emails = db.relationship('Email', backref='batch', lazy='dynamic', cascade='all, delete-orphan')
    rejected_emails = db.relationship('RejectedEmail', backref='batch', lazy='dynamic', cascade='all, delete-orphan')
    jobs = db.relationship('Job', backref='batch', lazy='dynamic')
    
    def __repr__(self):
        return f'<Batch {self.name}>'

class RejectedEmail(db.Model):
    __tablename__ = 'rejected_emails'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    domain = db.Column(db.String(255), nullable=False, index=True)
    reason = db.Column(db.String(100), nullable=False, index=True)
    # Reasons: ignore_domain, cctld_policy, policy_suffix, duplicate, invalid_syntax
    details = db.Column(db.Text)
    
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), nullable=False, index=True)
    job_id = db.Column(db.Integer, db.ForeignKey('jobs.id'), index=True)
    
    rejected_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<RejectedEmail {self.email} - {self.reason}>'

class IgnoreDomain(db.Model):
    __tablename__ = 'ignore_domains'
    
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(255), unique=True, nullable=False, index=True)
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    reason = db.Column(db.Text)
    
    def __repr__(self):
        return f'<IgnoreDomain {self.domain}>'

class SuppressionList(db.Model):
    __tablename__ = 'suppression_list'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    reason = db.Column(db.String(100))  # opt_out, bounce, complaint
    added_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    added_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    def __repr__(self):
        return f'<SuppressionList {self.email}>'
