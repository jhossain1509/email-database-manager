from celery import shared_task
from app import db
from app.models.email import Email, Batch, RejectedEmail, IgnoreDomain, SuppressionList, GuestEmailItem
from app.models.job import Job, DomainReputation, DownloadHistory, GuestDownloadHistory
from app.models.user import User
from app.utils.email_validator import (
    validate_email_full, extract_domain, classify_domain
)
import csv
import os
import zipfile
from datetime import datetime
from flask import current_app
import logging

logger = logging.getLogger(__name__)


def emit_job_progress(job_id, data):
    """Helper function to emit job progress via SocketIO"""
    try:
        from app import socketio
        socketio.emit('job_progress', {
            'job_id': job_id,
            **data
        }, namespace='/jobs', broadcast=True)
    except Exception as e:
        # If SocketIO fails, just continue without real-time updates
        logger.error(f"Failed to emit progress: {str(e)}")


@shared_task(bind=True)
def import_emails_task(self, batch_id, file_path, user_id, consent_granted=False):
    """
    Import emails from file with filtering and rejection tracking.
    Job-driven with progress reporting.
    
    For guest users: Creates GuestEmailItem records for all uploaded emails
    (including duplicates) while only inserting new unique emails into main emails table.
    """
    from app import create_app
    app = create_app()
    
    with app.app_context():
        try:
            # Get or create job record
            job = Job.query.filter_by(job_id=self.request.id).first()
            if not job:
                job = Job(
                    job_id=self.request.id,
                    job_type='import',
                    user_id=user_id,
                    batch_id=batch_id,
                    status='running'
                )
                db.session.add(job)
                db.session.commit()
            
            job.status = 'running'
            job.started_at = datetime.utcnow()
            
            batch = Batch.query.get(batch_id)
            if not batch:
                raise Exception(f'Batch {batch_id} not found')
            
            # Check if user is guest
            user = User.query.get(user_id)
            is_guest = user.is_guest() if user else False
            
            # Get ignore domains
            ignore_domains = [d.domain for d in IgnoreDomain.query.all()]
            
            # Get suppression list
            suppressed_emails = set([s.email for s in SuppressionList.query.all()])
            
            # Read file and count total
            emails_to_process = []
            seen_emails = set()
            
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                reader = csv.reader(f)
                for row in reader:
                    if row and len(row) > 0:
                        email = row[0].strip().lower()
                        if email and '@' in email:
                            emails_to_process.append(email)
            
            job.total = len(emails_to_process)
            db.session.commit()
            
            imported_count = 0
            rejected_count = 0
            duplicate_count = 0
            guest_inserted_count = 0
            guest_duplicate_count = 0
            
            for idx, email in enumerate(emails_to_process):
                try:
                    # Check for duplicates in current batch
                    if email in seen_emails:
                        duplicate_count += 1
                        rejected = RejectedEmail(
                            email=email,
                            domain=extract_domain(email) or 'unknown',
                            reason='duplicate',
                            details='Duplicate in current batch',
                            batch_id=batch_id,
                            job_id=job.id
                        )
                        db.session.add(rejected)
                        
                        # For guest users, still track the duplicate item
                        if is_guest:
                            domain = extract_domain(email)
                            guest_item = GuestEmailItem(
                                batch_id=batch_id,
                                user_id=user_id,
                                email_normalized=email,
                                domain=domain or 'unknown',
                                result='rejected',
                                rejected_reason='duplicate',
                                rejected_details='Duplicate in current batch'
                            )
                            db.session.add(guest_item)
                        continue
                    
                    seen_emails.add(email)
                    
                    # Check if in suppression list
                    if email in suppressed_emails:
                        rejected_count += 1
                        rejected = RejectedEmail(
                            email=email,
                            domain=extract_domain(email) or 'unknown',
                            reason='suppressed',
                            details='Email in suppression list',
                            batch_id=batch_id,
                            job_id=job.id
                        )
                        db.session.add(rejected)
                        
                        # For guest users, track rejected item
                        if is_guest:
                            domain = extract_domain(email)
                            guest_item = GuestEmailItem(
                                batch_id=batch_id,
                                user_id=user_id,
                                email_normalized=email,
                                domain=domain or 'unknown',
                                result='rejected',
                                rejected_reason='suppressed',
                                rejected_details='Email in suppression list'
                            )
                            db.session.add(guest_item)
                        continue
                    
                    # Validate with all filters
                    is_valid, error_type, error_message = validate_email_full(
                        email,
                        check_dns=False,
                        check_role=False,
                        ignore_domains=ignore_domains
                    )
                    
                    domain = extract_domain(email)
                    
                    if not is_valid:
                        # Reject email
                        rejected_count += 1
                        rejected = RejectedEmail(
                            email=email,
                            domain=domain or 'unknown',
                            reason=error_type,
                            details=error_message,
                            batch_id=batch_id,
                            job_id=job.id
                        )
                        db.session.add(rejected)
                        
                        # For guest users, track rejected item
                        if is_guest:
                            guest_item = GuestEmailItem(
                                batch_id=batch_id,
                                user_id=user_id,
                                email_normalized=email,
                                domain=domain or 'unknown',
                                result='rejected',
                                rejected_reason=error_type,
                                rejected_details=error_message
                            )
                            db.session.add(guest_item)
                    else:
                        # For guest users: Check if email already exists in main DB
                        if is_guest:
                            # Check if email already exists globally (case-insensitive)
                            # TODO: Consider adding index on LOWER(email) for better performance
                            existing_email = Email.query.filter(
                                db.func.lower(Email.email) == email.lower()
                            ).first()
                            
                            if existing_email:
                                # Email is a duplicate - don't insert into emails table
                                # But create guest item to track it
                                guest_duplicate_count += 1
                                guest_item = GuestEmailItem(
                                    batch_id=batch_id,
                                    user_id=user_id,
                                    email_normalized=email,
                                    domain=domain,
                                    result='duplicate',
                                    matched_email_id=existing_email.id
                                )
                                db.session.add(guest_item)
                            else:
                                # Email is new - insert into emails table
                                domain_category = classify_domain(domain)
                                
                                email_obj = Email(
                                    email=email,
                                    domain=domain,
                                    domain_category=domain_category,
                                    batch_id=batch_id,
                                    uploaded_by=user_id,
                                    consent_granted=consent_granted,
                                    is_validated=False
                                )
                                db.session.add(email_obj)
                                db.session.flush()  # Get the ID
                                
                                guest_inserted_count += 1
                                
                                # Create guest item linking to new email
                                guest_item = GuestEmailItem(
                                    batch_id=batch_id,
                                    user_id=user_id,
                                    email_normalized=email,
                                    domain=domain,
                                    result='inserted',
                                    matched_email_id=email_obj.id
                                )
                                db.session.add(guest_item)
                        else:
                            # Regular user: Import email normally
                            domain_category = classify_domain(domain)
                            
                            email_obj = Email(
                                email=email,
                                domain=domain,
                                domain_category=domain_category,
                                batch_id=batch_id,
                                uploaded_by=user_id,
                                consent_granted=consent_granted,
                                is_validated=False
                            )
                            db.session.add(email_obj)
                            imported_count += 1
                    
                    # Update progress every 100 emails
                    if (idx + 1) % 100 == 0:
                        job.update_progress(idx + 1)
                        db.session.commit()
                        
                        # Emit real-time progress via SocketIO
                        emit_job_progress(job.job_id, {
                            'status': 'running',
                            'current': idx + 1,
                            'total': job.total,
                            'percent': job.progress_percent,
                            'message': f'Importing emails... {idx + 1}/{job.total}'
                        })
                        
                        # Update Celery task state
                        self.update_state(
                            state='PROGRESS',
                            meta={
                                'current': idx + 1,
                                'total': job.total,
                                'percent': job.progress_percent
                            }
                        )
                
                except Exception as e:
                    job.errors += 1
                    print(f"Error processing email {email}: {str(e)}")
            
            # Final commit
            db.session.commit()
            
            # Update batch statistics
            if is_guest:
                batch.total_count = guest_inserted_count
                batch.rejected_count = rejected_count
                batch.duplicate_count = guest_duplicate_count
            else:
                batch.total_count = imported_count
                batch.rejected_count = rejected_count
                batch.duplicate_count = duplicate_count
            
            batch.status = 'uploaded'
            db.session.commit()
            
            # Complete job
            if is_guest:
                message = f'Imported {guest_inserted_count} new emails, {guest_duplicate_count} duplicates, {rejected_count} rejected'
                result_data = {
                    'imported': guest_inserted_count,
                    'duplicates': guest_duplicate_count,
                    'rejected': rejected_count
                }
            else:
                message = f'Imported {imported_count} emails, rejected {rejected_count}, duplicates {duplicate_count}'
                result_data = {
                    'imported': imported_count,
                    'rejected': rejected_count,
                    'duplicates': duplicate_count
                }
            
            job.complete(message=message, result_data=result_data)
            
            return {
                'status': 'completed',
                'imported': guest_inserted_count if is_guest else imported_count,
                'rejected': rejected_count,
                'duplicates': guest_duplicate_count if is_guest else duplicate_count
            }
            
        except Exception as e:
            if job:
                job.fail(str(e))
            raise

@shared_task(bind=True)
def validate_emails_task(self, batch_id, user_id, check_dns=False, check_role=False, check_disposable=True, 
                        validate_all_unverified=False, filter_domains='', use_smtp=False):
    """
    Validate emails in a batch with enhanced validation.
    Job-driven with progress reporting.
    
    For guest users: Validates emails from their GuestEmailItem scope,
    but updates the canonical Email rows.
    
    Args:
        batch_id: Batch ID to validate (None if validate_all_unverified is True)
        user_id: User ID performing validation
        check_dns: Whether to check DNS/MX records
        check_role: Whether to filter role-based emails
        check_disposable: Whether to check for disposable emails
        validate_all_unverified: Whether to validate all unverified emails
        filter_domains: Comma-separated list of domains to filter
        use_smtp: Whether to use SMTP verification (requires SMTP servers configured)
    """
    from app import create_app
    from app.models.job import SMTPConfig
    from app.utils.email_validator import verify_email_smtp
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import datetime as dt
    
    app = create_app()
    
    with app.app_context():
        try:
            # Get or create job record
            job = Job.query.filter_by(job_id=self.request.id).first()
            if not job:
                job = Job(
                    job_id=self.request.id,
                    job_type='validate',
                    user_id=user_id,
                    batch_id=batch_id,
                    status='running'
                )
                db.session.add(job)
                db.session.commit()
            
            job.status = 'running'
            job.started_at = datetime.utcnow()
            db.session.commit()
            
            # Check if user is guest
            user = User.query.get(user_id)
            is_guest = user.is_guest() if user else False
            
            # Check SMTP permission for guests
            if use_smtp and is_guest and not (user and user.smtp_verification_allowed):
                raise Exception('Guest user does not have SMTP verification permission')
            
            # Get SMTP servers if use_smtp is enabled
            smtp_servers = []
            if use_smtp:
                smtp_configs = SMTPConfig.query.filter_by(is_active=True).order_by(
                    SMTPConfig.last_used_at.asc().nullsfirst()
                ).all()
                
                if not smtp_configs:
                    # Fallback to DNS validation if no SMTP servers
                    print(f"[SMTP] WARNING: No active SMTP servers configured. Falling back to DNS validation.")
                    use_smtp = False
                    check_dns = True
                else:
                    smtp_servers = smtp_configs
                    # Get thread count from first config (they should all have same setting)
                    thread_count = smtp_configs[0].thread_count if smtp_configs else 5
                    print(f"[SMTP] Found {len(smtp_servers)} active SMTP server(s), thread_count={thread_count}")
            
            # Get ignore domains
            ignore_domains = [d.domain for d in IgnoreDomain.query.all()]
            
            # Build filter for domains if provided
            domain_filter = None
            if filter_domains:
                domain_filter = [d.strip() for d in filter_domains.split(',') if d.strip()]
            
            # For guest users, get emails via their guest items
            # For regular users, get emails directly
            if is_guest:
                if validate_all_unverified:
                    # Get all unverified emails for guest
                    guest_items = GuestEmailItem.query.filter_by(
                        user_id=user_id
                    ).filter(
                        GuestEmailItem.matched_email_id.isnot(None)
                    ).all()
                elif batch_id:
                    # Get guest items from specific batch
                    guest_items = GuestEmailItem.query.filter_by(
                        batch_id=batch_id,
                        user_id=user_id
                    ).filter(
                        GuestEmailItem.matched_email_id.isnot(None)
                    ).all()
                else:
                    raise Exception('Either batch_id or validate_all_unverified must be specified')
                
                # Get unique emails to validate
                emails_to_validate = []
                seen_email_ids = set()
                
                for item in guest_items:
                    if item.matched_email_id and item.matched_email_id not in seen_email_ids:
                        email_obj = item.matched_email
                        if email_obj and not email_obj.is_validated:
                            # Apply domain filter if specified
                            if domain_filter:
                                if email_obj.domain in domain_filter or (email_obj.domain_category == 'mixed' and 'mixed' in domain_filter):
                                    seen_email_ids.add(item.matched_email_id)
                                    emails_to_validate.append(email_obj)
                            else:
                                seen_email_ids.add(item.matched_email_id)
                                emails_to_validate.append(email_obj)
                
                emails = emails_to_validate
            else:
                # Regular user
                if validate_all_unverified:
                    # Get all unverified emails for user
                    query = Email.query.filter_by(uploaded_by=user_id, is_validated=False)
                elif batch_id:
                    batch = Batch.query.get(batch_id)
                    if not batch:
                        raise Exception(f'Batch {batch_id} not found')
                    # Get unverified emails from batch
                    query = Email.query.filter_by(batch_id=batch_id, is_validated=False)
                else:
                    raise Exception('Either batch_id or validate_all_unverified must be specified')
                
                # Apply domain filter if specified
                if domain_filter:
                    # Filter by specific domains or mixed category
                    domain_conditions = []
                    for domain in domain_filter:
                        if domain == 'mixed':
                            domain_conditions.append(Email.domain_category == 'mixed')
                        else:
                            domain_conditions.append(Email.domain == domain)
                    
                    if domain_conditions:
                        from sqlalchemy import or_
                        query = query.filter(or_(*domain_conditions))
                
                emails = query.all()
            
            job.total = len(emails)
            db.session.commit()
            
            valid_count = 0
            invalid_count = 0
            
            from app.utils.email_validator import validate_email_enhanced
            
            if use_smtp and smtp_servers:
                # Log SMTP validation start
                print(f"[SMTP] Using SMTP verification with {len(smtp_servers)} server(s), {thread_count} thread(s)")
                print(f"[SMTP] Server list: {[f'{s.smtp_host}:{s.smtp_port}' for s in smtp_servers]}")
                
                # SMTP validation with threading and rotation
                def validate_with_smtp(email_obj, smtp_server_idx):
                    """Validate single email using SMTP"""
                    smtp_server = smtp_servers[smtp_server_idx % len(smtp_servers)]
                    server_name = f"{smtp_server.smtp_host}:{smtp_server.smtp_port}"
                    
                    print(f"[SMTP] Validating {email_obj.email} using {server_name}")
                    
                    is_valid, error_code, error_message = verify_email_smtp(
                        email_obj.email,
                        smtp_server.smtp_host,
                        smtp_server.smtp_port,
                        smtp_server.smtp_username,
                        smtp_server.smtp_password,
                        use_tls=smtp_server.use_tls,
                        use_ssl=smtp_server.use_ssl,
                        timeout=smtp_server.timeout or 30,
                        from_email=smtp_server.from_email
                    )
                    
                    # Log result
                    result_str = "VALID" if is_valid else f"INVALID ({error_message})"
                    print(f"[SMTP] Email validated: {email_obj.email} - Result: {result_str}")
                    
                    # Update last used timestamp for rotation
                    smtp_server.last_used_at = dt.utcnow()
                    
                    return email_obj, is_valid, error_code, error_message
                
                # Use ThreadPoolExecutor for concurrent SMTP validation
                print(f"[SMTP] Starting concurrent validation with thread pool (max_workers={thread_count})")
                with ThreadPoolExecutor(max_workers=thread_count) as executor:
                    futures = []
                    for idx, email_obj in enumerate(emails):
                        # Round-robin server selection
                        future = executor.submit(validate_with_smtp, email_obj, idx)
                        futures.append(future)
                    
                    # Process results as they complete
                    completed = 0
                    for future in as_completed(futures):
                        try:
                            email_obj, is_valid, error_code, error_message = future.result()
                            
                            email_obj.is_validated = True
                            email_obj.is_valid = is_valid
                            email_obj.quality_score = 100 if is_valid else 0
                            email_obj.update_rating()  # Calculate and set rating
                            email_obj.validation_method = 'smtp'  # Mark as SMTP validated
                            
                            if not is_valid:
                                email_obj.validation_error = f'SMTP: {error_message}' if error_message else 'Invalid'
                                invalid_count += 1
                            else:
                                valid_count += 1
                            
                            completed += 1
                            
                            # Update progress every 50 emails
                            if completed % 50 == 0:
                                print(f"[SMTP] Progress: {completed}/{job.total} emails validated ({valid_count} valid, {invalid_count} invalid)")
                                job.update_progress(completed)
                                db.session.commit()
                                
                                self.update_state(
                                    state='PROGRESS',
                                    meta={
                                        'current': completed,
                                        'total': job.total,
                                        'percent': job.progress_percent
                                    }
                                )
                        except Exception as e:
                            job.errors += 1
                            print(f"[SMTP] ERROR: Validation error - {str(e)}")
                
                # Update SMTP server timestamps
                db.session.commit()
                print(f"[SMTP] SMTP validation completed: {valid_count} valid, {invalid_count} invalid out of {len(emails)} total")
            else:
                # Standard validation (DNS/MX)
                for idx, email_obj in enumerate(emails):
                    try:
                        # Enhanced validation with quality scoring
                        is_valid, error_type, error_message, quality_score, details = validate_email_enhanced(
                            email_obj.email,
                            check_dns=check_dns,
                            check_smtp=False,  # SMTP check is slow, keep disabled
                            check_role=check_role,
                            check_disposable=check_disposable,
                            ignore_domains=ignore_domains
                        )
                        
                        email_obj.is_validated = True
                        email_obj.is_valid = is_valid
                        email_obj.quality_score = quality_score
                        email_obj.update_rating()  # Calculate and set rating
                        
                        if not is_valid:
                            email_obj.validation_error = f'{error_type}: {error_message}'
                            invalid_count += 1
                        else:
                            valid_count += 1
                        
                        # Update progress every 50 emails
                        if (idx + 1) % 50 == 0:
                            job.update_progress(idx + 1)
                            db.session.commit()
                            
                            # Emit real-time progress via SocketIO
                            emit_job_progress(job.job_id, {
                                'status': 'running',
                                'current': idx + 1,
                                'total': job.total,
                                'percent': job.progress_percent,
                                'message': f'Validating emails... {idx + 1}/{job.total}'
                            })
                            
                            self.update_state(
                                state='PROGRESS',
                                meta={
                                    'current': idx + 1,
                                    'total': job.total,
                                    'percent': job.progress_percent
                                }
                            )
                    
                    except Exception as e:
                        job.errors += 1
                        email_obj.is_validated = True
                        email_obj.is_valid = False
                        email_obj.validation_error = f'Validation error: {str(e)}'
                        email_obj.quality_score = 0
                        email_obj.update_rating()  # Calculate and set rating
                        invalid_count += 1
            
            # Final commit
            db.session.commit()
            
            # Update batch statistics if batch_id provided
            if batch_id:
                batch = Batch.query.get(batch_id)
                if batch:
                    batch.valid_count = Email.query.filter_by(batch_id=batch_id, is_validated=True, is_valid=True).count()
                    batch.invalid_count = Email.query.filter_by(batch_id=batch_id, is_validated=True, is_valid=False).count()
                    batch.status = 'validated'
                    db.session.commit()
            
            # Complete job
            job.complete(
                message=f'Validated {valid_count} valid, {invalid_count} invalid emails',
                result_data={
                    'valid': valid_count,
                    'invalid': invalid_count
                }
            )
            
            return {
                'status': 'completed',
                'valid': valid_count,
                'invalid': invalid_count
            }
            
        except Exception as e:
            if job:
                job.fail(str(e))
            raise

@shared_task(bind=True)
def export_emails_task(self, user_id, export_type='verified', batch_id=None, filter_domains=None, 
                       domain_limits=None, split_files=False, split_size=10000, 
                       export_format='csv', custom_fields=None, random_limit=None, rating_filter=None):
    """
    Export emails with advanced filtering and options.
    Job-driven with progress reporting.
    
    Args:
        user_id: User performing export
        export_type: 'verified', 'smtp_verified', 'unverified', 'invalid', or 'all'
        batch_id: Optional batch filter
        filter_domains: List of domains to filter
        domain_limits: Dict of domain: max_count limits
        split_files: Whether to split into multiple files
        split_size: Number of records per split file
        export_format: 'csv' or 'txt'
        custom_fields: List of fields to export (for CSV)
        random_limit: Optional limit to random sample of N emails
        rating_filter: Optional list of ratings to filter (e.g., ['A', 'B'])
    """
    from app import create_app
    app = create_app()
    
    with app.app_context():
        try:
            # Get or create job record
            job = Job.query.filter_by(job_id=self.request.id).first()
            if not job:
                job = Job(
                    job_id=self.request.id,
                    job_type='export',
                    user_id=user_id,
                    batch_id=batch_id,
                    status='running'
                )
                db.session.add(job)
                db.session.commit()
            
            job.status = 'running'
            job.started_at = datetime.utcnow()
            db.session.commit()
            
            # Build base query
            query = Email.query
            
            if batch_id:
                query = query.filter_by(batch_id=batch_id)
            
            if export_type == 'verified':
                query = query.filter_by(is_validated=True, is_valid=True)
            elif export_type == 'smtp_verified':
                query = query.filter_by(is_validated=True, is_valid=True, validation_method='smtp')
            elif export_type == 'unverified':
                query = query.filter_by(is_validated=False)
            elif export_type == 'invalid':
                query = query.filter_by(is_validated=True, is_valid=False)
            # 'all' exports everything
            
            # Apply rating filter if specified
            if rating_filter and len(rating_filter) > 0:
                query = query.filter(Email.rating.in_(rating_filter))
            
            # Get suppression list
            suppressed = set([s.email for s in SuppressionList.query.all()])
            
            # Collect emails by domain if domain_limits specified
            emails_to_export = []
            
            if domain_limits:
                # Export specific domains with limits
                for domain, limit in domain_limits.items():
                    domain_query = query.filter_by(domain=domain)
                    domain_emails = domain_query.limit(limit).all()
                    emails_to_export.extend(domain_emails)
            elif filter_domains:
                # Export all from specified domains (backward compatibility)
                query = query.filter(Email.domain.in_(filter_domains))
                emails_to_export = query.all()
            else:
                # Export all matching query
                # If random_limit is specified, use random sampling
                if random_limit and random_limit > 0:
                    from sqlalchemy import func
                    total_count = query.count()
                    if total_count > random_limit:
                        # Use ORDER BY RANDOM() with LIMIT for random sampling
                        emails_to_export = query.order_by(func.random()).limit(random_limit).all()
                    else:
                        emails_to_export = query.all()
                else:
                    emails_to_export = query.all()
            
            job.total = len(emails_to_export)
            db.session.commit()
            
            # Create export folder
            export_folder = app.config['EXPORT_FOLDER']
            os.makedirs(export_folder, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            
            # Determine fields to export
            if custom_fields:
                fields = custom_fields
            else:
                if export_format == 'txt':
                    fields = ['email']
                else:
                    fields = ['email', 'domain', 'quality_score', 'uploaded_at']
            
            # Export emails
            exported_count = 0
            file_paths = []
            file_number = 1
            file_counts = []  # Track count per file
            
            if split_files and len(emails_to_export) > split_size:
                # Split into multiple files
                for i in range(0, len(emails_to_export), split_size):
                    chunk = emails_to_export[i:i + split_size]
                    ext = 'txt' if export_format == 'txt' else 'csv'
                    filename = f"export_{export_type}_{user_id}_{timestamp}_part{file_number}.{ext}"
                    file_path = os.path.join(export_folder, filename)
                    file_paths.append((filename, file_path))
                    
                    chunk_count = _write_export_file(chunk, file_path, fields, export_format, suppressed)
                    file_counts.append(chunk_count)
                    exported_count += chunk_count
                    file_number += 1
                    
                    # Update progress
                    job.update_progress(min(i + split_size, len(emails_to_export)))
                    db.session.commit()
            else:
                # Single file export
                ext = 'txt' if export_format == 'txt' else 'csv'
                filename = f"export_{export_type}_{user_id}_{timestamp}.{ext}"
                file_path = os.path.join(export_folder, filename)
                file_paths.append((filename, file_path))
                
                exported_count = _write_export_file(
                    emails_to_export, file_path, fields, export_format, suppressed, job, self
                )
                file_counts.append(exported_count)
            
            # Mark emails as downloaded
            for email_obj in emails_to_export:
                if email_obj.email not in suppressed:
                    email_obj.downloaded = True
                    email_obj.download_count += 1
            db.session.commit()
            
            # If split files, create ZIP archive
            final_file_path = None
            final_filename = None
            final_file_size = 0
            
            if split_files and len(file_paths) > 1:
                # Create ZIP file containing all parts
                zip_filename = f"export_{export_type}_{user_id}_{timestamp}.zip"
                zip_path = os.path.join(export_folder, zip_filename)
                
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for filename, file_path in file_paths:
                        zipf.write(file_path, filename)
                        # Delete individual files after adding to ZIP
                        try:
                            os.remove(file_path)
                        except:
                            pass
                
                final_file_path = zip_path
                final_filename = zip_filename
                final_file_size = os.path.getsize(zip_path)
                
                # Create single download history entry for ZIP
                history = DownloadHistory(
                    user_id=user_id,
                    batch_id=batch_id,
                    download_type=export_type,
                    filter_domains=','.join(filter_domains) if filter_domains else None,
                    filename=final_filename,
                    file_path=final_file_path,
                    file_size=final_file_size,
                    record_count=exported_count
                )
                db.session.add(history)
                db.session.flush()
                history_ids = [history.id]
            else:
                # Create download history entries for single or non-split files
                history_ids = []
                for idx, (filename, file_path) in enumerate(file_paths):
                    file_size = os.path.getsize(file_path)
                    history = DownloadHistory(
                        user_id=user_id,
                        batch_id=batch_id,
                        download_type=export_type,
                        filter_domains=','.join(filter_domains) if filter_domains else None,
                        filename=filename,
                        file_path=file_path,
                        file_size=file_size,
                        record_count=file_counts[idx]
                    )
                    db.session.add(history)
                    db.session.flush()
                    history_ids.append(history.id)
            
            db.session.commit()
            
            # Complete job
            job.complete(
                message=f'Exported {exported_count} emails in {len(file_paths)} file(s)',
                result_data={
                    'exported': exported_count,
                    'files': len(file_paths),
                    'history_id': history_ids[0] if history_ids else None,
                    'history_ids': history_ids
                }
            )
            
            return {
                'status': 'completed',
                'exported': exported_count,
                'files': len(file_paths),
                'history_ids': history_ids
            }
            
        except Exception as e:
            if job:
                job.fail(str(e))
            raise


def _write_export_file(emails, file_path, fields, export_format, suppressed, job=None, task=None):
    """Helper function to write export file"""
    exported_count = 0
    
    if export_format == 'txt':
        # TXT format - email list only
        with open(file_path, 'w', encoding='utf-8') as f:
            for idx, email_obj in enumerate(emails):
                if email_obj.email in suppressed:
                    continue
                f.write(email_obj.email + '\n')
                exported_count += 1
                
                if job and task and (idx + 1) % 100 == 0:
                    job.update_progress(idx + 1)
                    task.update_state(
                        state='PROGRESS',
                        meta={
                            'current': idx + 1,
                            'total': len(emails),
                            'percent': (idx + 1) / len(emails) * 100
                        }
                    )
    else:
        # CSV format
        with open(file_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write header
            header = []
            for field in fields:
                if field == 'email':
                    header.append('Email')
                elif field == 'domain':
                    header.append('Domain')
                elif field == 'quality_score':
                    header.append('Quality Score')
                elif field == 'uploaded_at':
                    header.append('Uploaded At')
                elif field == 'domain_category':
                    header.append('Domain Category')
                elif field == 'is_valid':
                    header.append('Is Valid')
                else:
                    header.append(field.replace('_', ' ').title())
            writer.writerow(header)
            
            # Write data
            for idx, email_obj in enumerate(emails):
                if email_obj.email in suppressed:
                    continue
                
                row = []
                for field in fields:
                    if field == 'email':
                        row.append(email_obj.email)
                    elif field == 'domain':
                        row.append(email_obj.domain)
                    elif field == 'quality_score':
                        row.append(email_obj.quality_score or '')
                    elif field == 'uploaded_at':
                        row.append(email_obj.uploaded_at.strftime('%Y-%m-%d %H:%M:%S'))
                    elif field == 'domain_category':
                        row.append(email_obj.domain_category or '')
                    elif field == 'is_valid':
                        row.append('Yes' if email_obj.is_valid else 'No' if email_obj.is_valid is False else '')
                    else:
                        row.append(getattr(email_obj, field, ''))
                writer.writerow(row)
                exported_count += 1
                
                if job and task and (idx + 1) % 100 == 0:
                    job.update_progress(idx + 1)
                    task.update_state(
                        state='PROGRESS',
                        meta={
                            'current': idx + 1,
                            'total': len(emails),
                            'percent': (idx + 1) / len(emails) * 100
                        }
                    )
    
    return exported_count


@shared_task(bind=True)
def export_guest_emails_task(self, user_id, batch_id, export_type='all', export_format='csv', custom_fields=None, random_limit=None, rating_filter=None):
    """
    Export emails for guest users from their GuestEmailItem scope.
    Does NOT update emails.downloaded or emails.download_count.
    Creates GuestDownloadHistory instead of DownloadHistory.
    
    Args:
        user_id: Guest user ID
        batch_id: Batch ID to export
        export_type: 'verified', 'smtp_verified', 'unverified', 'invalid', 'rejected', or 'all'
        export_format: 'csv' or 'txt'
        custom_fields: List of fields to export (for CSV)
        random_limit: Optional limit to random sample of N emails
        rating_filter: Optional list of ratings to filter (e.g., ['A', 'B'])
    """
    from app import create_app
    app = create_app()
    
    with app.app_context():
        try:
            # Get or create job record
            job = Job.query.filter_by(job_id=self.request.id).first()
            if not job:
                job = Job(
                    job_id=self.request.id,
                    job_type='export',
                    user_id=user_id,
                    batch_id=batch_id,
                    status='running'
                )
                db.session.add(job)
                db.session.commit()
            
            job.status = 'running'
            job.started_at = datetime.utcnow()
            db.session.commit()
            
            # Verify user is guest
            user = User.query.get(user_id)
            if not user or not user.is_guest():
                raise Exception('This export function is only for guest users')
            
            # Build query for guest email items
            query = GuestEmailItem.query.filter_by(
                user_id=user_id,
                batch_id=batch_id
            )
            
            # Apply filters based on export_type
            if export_type == 'verified':
                # Only items that link to validated & valid emails
                query = query.join(Email, GuestEmailItem.matched_email_id == Email.id)\
                    .filter(Email.is_validated.is_(True), Email.is_valid.is_(True))
            elif export_type == 'smtp_verified':
                # Only items linked to SMTP validated & valid emails
                query = query.join(Email, GuestEmailItem.matched_email_id == Email.id)\
                    .filter(Email.is_validated.is_(True), Email.is_valid.is_(True), Email.validation_method == 'smtp')
            elif export_type == 'unverified':
                # Items linked to unvalidated emails
                query = query.join(Email, GuestEmailItem.matched_email_id == Email.id)\
                    .filter(Email.is_validated.is_(False))
            elif export_type == 'invalid':
                # Items linked to validated but invalid emails
                query = query.join(Email, GuestEmailItem.matched_email_id == Email.id)\
                    .filter(Email.is_validated.is_(True), Email.is_valid.is_(False))
            elif export_type == 'rejected':
                # Items with result=rejected
                query = query.filter(GuestEmailItem.result == 'rejected')
            # 'all' exports everything
            
            # Apply rating filter if specified
            if rating_filter and len(rating_filter) > 0:
                if export_type != 'rejected':  # Rejected emails don't have ratings
                    query = query.join(Email, GuestEmailItem.matched_email_id == Email.id)\
                        .filter(Email.rating.in_(rating_filter))
            
            # Apply random limit if specified
            if random_limit and random_limit > 0:
                from sqlalchemy import func
                total_count = query.count()
                if total_count > random_limit:
                    # Use ORDER BY RANDOM() with LIMIT for random sampling
                    query = query.order_by(func.random()).limit(random_limit)
            
            # Get items to export (eager load matched_email for efficiency)
            from sqlalchemy.orm import joinedload
            guest_items = query.options(joinedload(GuestEmailItem.matched_email)).all()
            
            job.total = len(guest_items)
            db.session.commit()
            
            # Create export folder
            export_folder = app.config['EXPORT_FOLDER']
            os.makedirs(export_folder, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            
            # Determine fields to export
            if custom_fields:
                fields = custom_fields
            else:
                if export_format == 'txt':
                    fields = ['email']
                else:
                    fields = ['email', 'domain', 'result', 'status', 'quality_score']
            
            # Create filename
            ext = 'txt' if export_format == 'txt' else 'csv'
            filename = f"guest_export_{export_type}_{user_id}_batch{batch_id}_{timestamp}.{ext}"
            file_path = os.path.join(export_folder, filename)
            
            # Write export file
            exported_count = 0
            
            if export_format == 'txt':
                # TXT format - email list only
                with open(file_path, 'w', encoding='utf-8') as f:
                    for idx, item in enumerate(guest_items):
                        f.write(item.email_normalized + '\n')
                        exported_count += 1
                        
                        if (idx + 1) % 100 == 0:
                            job.update_progress(idx + 1)
                            self.update_state(
                                state='PROGRESS',
                                meta={
                                    'current': idx + 1,
                                    'total': len(guest_items),
                                    'percent': (idx + 1) / len(guest_items) * 100
                                }
                            )
            else:
                # CSV format
                with open(file_path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    
                    # Write header
                    header = []
                    for field in fields:
                        if field == 'email':
                            header.append('Email')
                        elif field == 'domain':
                            header.append('Domain')
                        elif field == 'result':
                            header.append('Result')
                        elif field == 'status':
                            header.append('Status')
                        elif field == 'quality_score':
                            header.append('Quality Score')
                        elif field == 'rejected_reason':
                            header.append('Rejected Reason')
                        else:
                            header.append(field.replace('_', ' ').title())
                    writer.writerow(header)
                    
                    # Write data
                    for idx, item in enumerate(guest_items):
                        row = []
                        for field in fields:
                            if field == 'email':
                                row.append(item.email_normalized)
                            elif field == 'domain':
                                row.append(item.domain)
                            elif field == 'result':
                                row.append(item.result)
                            elif field == 'status':
                                # Get status from matched email
                                if item.matched_email:
                                    if item.matched_email.is_validated:
                                        status = 'Valid' if item.matched_email.is_valid else 'Invalid'
                                    else:
                                        status = 'Unverified'
                                elif item.result == 'rejected':
                                    status = 'Rejected'
                                else:
                                    status = 'Unknown'
                                row.append(status)
                            elif field == 'quality_score':
                                if item.matched_email:
                                    row.append(item.matched_email.quality_score or '')
                                else:
                                    row.append('')
                            elif field == 'rejected_reason':
                                row.append(item.rejected_reason or '')
                            else:
                                row.append(getattr(item, field, ''))
                        writer.writerow(row)
                        exported_count += 1
                        
                        if (idx + 1) % 100 == 0:
                            job.update_progress(idx + 1)
                            self.update_state(
                                state='PROGRESS',
                                meta={
                                    'current': idx + 1,
                                    'total': len(guest_items),
                                    'percent': (idx + 1) / len(guest_items) * 100
                                }
                            )
            
            # Create guest download history record
            file_size = os.path.getsize(file_path)
            guest_history = GuestDownloadHistory(
                user_id=user_id,
                batch_id=batch_id,
                download_type=export_type,
                filename=filename,
                file_path=file_path,
                file_size=file_size,
                record_count=exported_count,
                filters=export_format,
                downloaded_times=1
            )
            db.session.add(guest_history)
            db.session.commit()
            
            # Complete job
            job.complete(
                message=f'Exported {exported_count} guest email items',
                result_data={
                    'exported': exported_count,
                    'history_id': guest_history.id
                }
            )
            
            return {
                'status': 'completed',
                'exported': exported_count,
                'history_id': guest_history.id
            }
            
        except Exception as e:
            if job:
                job.fail(str(e))
            raise
