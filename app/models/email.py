from app import db
from datetime import datetime

class Email(db.Model):
    __tablename__ = 'emails'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    domain = db.Column(db.String(255), nullable=False, index=True)
    domain_category = db.Column(db.String(50), index=True)  # top_domain name or 'mixed'
    
    # Validation status
    is_validated = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_valid = db.Column(db.Boolean, default=None)
    validation_error = db.Column(db.Text)
    
    # Quality metrics
    quality_score = db.Column(db.Integer)  # 0-100
    rating = db.Column(db.String(1), index=True)  # A, B, C, D rating based on quality
    
    # Tracking
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), nullable=False, index=True)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Compliance
    consent_granted = db.Column(db.Boolean, default=False, nullable=False)
    suppressed = db.Column(db.Boolean, default=False, nullable=False, index=True)
    
    # Download tracking
    downloaded = db.Column(db.Boolean, default=False, nullable=False, index=True)
    download_count = db.Column(db.Integer, default=0, nullable=False)
    
    # Additional metadata
    engagement_prediction = db.Column(db.String(20))  # high, medium, low
    
    __table_args__ = (
        db.Index('idx_email_domain', 'email', 'domain'),
        db.Index('idx_batch_valid', 'batch_id', 'is_valid'),
    )
    
    def calculate_rating(self):
        """
        Calculate email rating (A, B, C, D) based on quality_score and domain reputation.
        A: 80-100 (Excellent quality)
        B: 60-79 (Good quality)
        C: 40-59 (Fair quality)
        D: 0-39 (Poor quality)
        """
        if self.quality_score is None:
            return None
        
        if self.quality_score >= 80:
            return 'A'
        elif self.quality_score >= 60:
            return 'B'
        elif self.quality_score >= 40:
            return 'C'
        else:
            return 'D'
    
    def update_rating(self):
        """Update the rating field based on current quality_score"""
        self.rating = self.calculate_rating()
    
    def __repr__(self):
        return f'<Email {self.email}>'

class Batch(db.Model):
    __tablename__ = 'batches'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    
    # Owner
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Status
    status = db.Column(db.String(50), default='uploaded', nullable=False, index=True)
    # Status: uploaded, processing, validated, failed
    
    # Statistics
    total_count = db.Column(db.Integer, default=0, nullable=False)
    valid_count = db.Column(db.Integer, default=0, nullable=False)
    invalid_count = db.Column(db.Integer, default=0, nullable=False)
    rejected_count = db.Column(db.Integer, default=0, nullable=False)
    duplicate_count = db.Column(db.Integer, default=0, nullable=False)
    
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

class GuestEmailItem(db.Model):
    """
    Tracks individual email items uploaded by guests.
    Allows guests to see their complete uploaded list including duplicates.
    """
    __tablename__ = 'guest_email_items'
    
    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Email details (denormalized for quick access)
    email_normalized = db.Column(db.String(255), nullable=False, index=True)
    domain = db.Column(db.String(255), nullable=False, index=True)
    
    # Processing result
    result = db.Column(db.String(50), nullable=False, index=True)
    # Results: inserted, duplicate, rejected
    
    # Link to main emails table (null if rejected)
    matched_email_id = db.Column(db.Integer, db.ForeignKey('emails.id'), index=True)
    
    # Rejection details (if result=rejected)
    rejected_reason = db.Column(db.String(100))
    rejected_details = db.Column(db.Text)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    matched_email = db.relationship('Email', backref='guest_items', lazy='joined')
    
    __table_args__ = (
        # Prevent duplicate items within same batch
        # (Allows same email in different batches, e.g., if uploaded by different guests)
        db.UniqueConstraint('batch_id', 'email_normalized', name='uq_guest_batch_email'),
        db.Index('idx_guest_user_batch', 'user_id', 'batch_id'),
    )
    
    def __repr__(self):
        return f'<GuestEmailItem {self.email_normalized} - {self.result}>'
