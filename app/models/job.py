from app import db
from datetime import datetime

class Job(db.Model):
    __tablename__ = 'jobs'
    
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(255), unique=True, nullable=False, index=True)  # Celery task ID
    job_type = db.Column(db.String(50), nullable=False, index=True)
    # Types: import, validate, export
    
    # Status tracking
    status = db.Column(db.String(50), default='pending', nullable=False, index=True)
    # Status: pending, running, completed, failed
    
    # Progress
    total = db.Column(db.Integer, default=0, nullable=False)
    processed = db.Column(db.Integer, default=0, nullable=False)
    errors = db.Column(db.Integer, default=0, nullable=False)
    progress_percent = db.Column(db.Float, default=0.0, nullable=False)
    
    # Details
    result_message = db.Column(db.Text)
    error_message = db.Column(db.Text)
    result_data = db.Column(db.JSON)  # Store additional result data
    
    # References
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), index=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    
    def update_progress(self, processed, errors=None):
        """Update job progress"""
        self.processed = processed
        if errors is not None:
            self.errors = errors
        if self.total > 0:
            self.progress_percent = (self.processed / self.total) * 100
        db.session.commit()
    
    def complete(self, message=None, result_data=None):
        """Mark job as completed"""
        self.status = 'completed'
        self.completed_at = datetime.utcnow()
        if message:
            self.result_message = message
        if result_data:
            self.result_data = result_data
        db.session.commit()
    
    def fail(self, error_message):
        """Mark job as failed"""
        self.status = 'failed'
        self.completed_at = datetime.utcnow()
        self.error_message = error_message
        db.session.commit()
    
    def __repr__(self):
        return f'<Job {self.job_type} - {self.status}>'

class DownloadHistory(db.Model):
    __tablename__ = 'download_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), index=True)
    
    # Download details
    download_type = db.Column(db.String(50), nullable=False)  # verified, unverified, rejected, all
    filter_domains = db.Column(db.Text)  # Comma-separated domains if filtered
    
    # File info
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.BigInteger)
    
    # Counts
    record_count = db.Column(db.Integer, nullable=False)
    
    # Timestamps
    downloaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<DownloadHistory {self.filename}>'

class GuestDownloadHistory(db.Model):
    """
    Tracks guest export/download history separately from main DB downloads.
    Allows guests to re-download their previous exports without affecting main DB metrics.
    """
    __tablename__ = 'guest_download_history'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    batch_id = db.Column(db.Integer, db.ForeignKey('batches.id'), index=True)
    
    # Download details
    download_type = db.Column(db.String(50), nullable=False)  # verified, unverified, rejected, all
    
    # File info
    filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_size = db.Column(db.BigInteger)
    
    # Counts
    record_count = db.Column(db.Integer, nullable=False)
    
    # Optional filters (JSON string)
    filters = db.Column(db.Text)
    
    # Download tracking
    downloaded_times = db.Column(db.Integer, default=1, nullable=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_downloaded_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationships
    user = db.relationship('User', backref='guest_downloads', lazy='joined')
    batch = db.relationship('Batch', backref='guest_downloads', lazy='joined')
    
    def __repr__(self):
        return f'<GuestDownloadHistory {self.filename}>'

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    action = db.Column(db.String(100), nullable=False, index=True)
    # Actions: login, logout, upload, validate, download, admin_action
    
    description = db.Column(db.Text)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(500))
    
    # Additional context
    resource_type = db.Column(db.String(50))  # batch, job, user, etc.
    resource_id = db.Column(db.Integer)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)
    
    def __repr__(self):
        return f'<ActivityLog {self.action} by user {self.user_id}>'

class DomainReputation(db.Model):
    __tablename__ = 'domain_reputation'
    
    id = db.Column(db.Integer, primary_key=True)
    domain = db.Column(db.String(255), unique=True, nullable=False, index=True)
    
    # Reputation score (0-100)
    reputation_score = db.Column(db.Integer, default=50, nullable=False)
    
    # Metrics
    total_emails = db.Column(db.Integer, default=0, nullable=False)
    valid_emails = db.Column(db.Integer, default=0, nullable=False)
    bounced_emails = db.Column(db.Integer, default=0, nullable=False)
    
    # Manual override
    manual_score = db.Column(db.Integer)
    notes = db.Column(db.Text)
    
    # Timestamps
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def compute_score(self):
        """Compute reputation score based on metrics"""
        if self.manual_score is not None:
            return self.manual_score
        
        if self.total_emails == 0:
            return 50
        
        valid_rate = self.valid_emails / self.total_emails
        bounce_rate = self.bounced_emails / self.total_emails
        
        score = int((valid_rate * 70) + ((1 - bounce_rate) * 30))
        return max(0, min(100, score))
    
    def __repr__(self):
        return f'<DomainReputation {self.domain}: {self.reputation_score}>'

class ExportTemplate(db.Model):
    __tablename__ = 'export_templates'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Filter settings (JSON)
    filter_settings = db.Column(db.JSON, nullable=False)
    # Example: {"verified": true, "domains": ["gmail.com"], "quality_min": 50}
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<ExportTemplate {self.name}>'

class ScheduledReport(db.Model):
    __tablename__ = 'scheduled_reports'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    
    # Schedule
    frequency = db.Column(db.String(50), nullable=False)  # daily, weekly, monthly
    next_run = db.Column(db.DateTime, nullable=False)
    
    # Report settings
    report_type = db.Column(db.String(50), nullable=False)  # summary, detailed
    include_charts = db.Column(db.Boolean, default=True, nullable=False)
    
    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    last_run = db.Column(db.DateTime)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f'<ScheduledReport {self.name}>'


class SMTPConfig(db.Model):
    """SMTP Configuration for email validation"""
    __tablename__ = 'smtp_configs'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)  # Config name/label
    
    # SMTP Server settings
    smtp_host = db.Column(db.String(255), nullable=False)
    smtp_port = db.Column(db.Integer, default=25, nullable=False)
    smtp_username = db.Column(db.String(255))
    smtp_password = db.Column(db.String(255))  # Encrypted in production
    use_tls = db.Column(db.Boolean, default=False, nullable=False)
    use_ssl = db.Column(db.Boolean, default=False, nullable=False)
    
    # Validation settings
    from_email = db.Column(db.String(255), nullable=False)  # MAIL FROM address
    timeout = db.Column(db.Integer, default=10, nullable=False)  # seconds
    
    # Status
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_default = db.Column(db.Boolean, default=False, nullable=False)
    last_tested = db.Column(db.DateTime)
    test_status = db.Column(db.String(50))  # success, failed, pending
    test_message = db.Column(db.Text)
    
    # Rotation and threading
    thread_count = db.Column(db.Integer, default=5, nullable=False)  # Concurrent threads
    enable_rotation = db.Column(db.Boolean, default=True, nullable=False)  # Rotate SMTP servers
    last_used_at = db.Column(db.DateTime)  # Last time this server was used
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    def __repr__(self):
        return f'<SMTPConfig {self.name}>'
