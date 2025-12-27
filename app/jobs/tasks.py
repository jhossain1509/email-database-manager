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
def validate_emails_task(self, batch_id, user_id, check_dns=False, check_role=False, check_disposable=True):
    """
    Validate emails in a batch with enhanced validation.
    Job-driven with progress reporting.
    
    For guest users: Validates emails from their GuestEmailItem scope,
    but updates the canonical Email rows.
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
            
            batch = Batch.query.get(batch_id)
            if not batch:
                raise Exception(f'Batch {batch_id} not found')
            
            # Check if user is guest
            user = User.query.get(user_id)
            is_guest = user.is_guest() if user else False
            
            # Get ignore domains
            ignore_domains = [d.domain for d in IgnoreDomain.query.all()]
            
            # For guest users, get emails via their guest items
            # For regular users, get emails directly
            if is_guest:
                # Get guest items that were inserted or are duplicates (have matched_email_id)
                guest_items = GuestEmailItem.query.filter_by(
                    batch_id=batch_id,
                    user_id=user_id
                ).filter(
                    GuestEmailItem.matched_email_id.isnot(None)
                ).all()
                
                # Get unique emails to validate
                emails_to_validate = []
                seen_email_ids = set()
                
                for item in guest_items:
                    if item.matched_email_id and item.matched_email_id not in seen_email_ids:
                        seen_email_ids.add(item.matched_email_id)
                        if item.matched_email:
                            emails_to_validate.append(item.matched_email)
                
                emails = emails_to_validate
            else:
                # Regular user: get emails from batch
                emails = Email.query.filter_by(batch_id=batch_id).all()
            
            job.total = len(emails)
            db.session.commit()
            
            valid_count = 0
            invalid_count = 0
            
            from app.utils.email_validator import validate_email_enhanced
            
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
                    
                    if not is_valid:
                        email_obj.validation_error = f'{error_type}: {error_message}'
                        invalid_count += 1
                    else:
                        valid_count += 1
                    
                    # Update progress every 50 emails
                    if (idx + 1) % 50 == 0:
                        job.update_progress(idx + 1)
                        db.session.commit()
                        
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
                    invalid_count += 1
            
            # Final commit
            db.session.commit()
            
            # Update batch statistics
            batch.valid_count = valid_count
            batch.invalid_count = invalid_count
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
                       export_format='csv', custom_fields=None):
    """
    Export emails with advanced filtering and options.
    Job-driven with progress reporting.
    
    Args:
        user_id: User performing export
        export_type: 'verified', 'unverified', 'invalid', or 'all'
        batch_id: Optional batch filter
        filter_domains: List of domains to filter
        domain_limits: Dict of domain: max_count limits
        split_files: Whether to split into multiple files
        split_size: Number of records per split file
        export_format: 'csv' or 'txt'
        custom_fields: List of fields to export (for CSV)
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
            elif export_type == 'unverified':
                query = query.filter_by(is_validated=False)
            elif export_type == 'invalid':
                query = query.filter_by(is_validated=True, is_valid=False)
            # 'all' exports everything
            
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
            
            # Create download history entries
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
def export_guest_emails_task(self, user_id, batch_id, export_type='all', export_format='csv', custom_fields=None):
    """
    Export emails for guest users from their GuestEmailItem scope.
    Does NOT update emails.downloaded or emails.download_count.
    Creates GuestDownloadHistory instead of DownloadHistory.
    
    Args:
        user_id: Guest user ID
        batch_id: Batch ID to export
        export_type: 'verified', 'unverified', 'invalid', 'rejected', or 'all'
        export_format: 'csv' or 'txt'
        custom_fields: List of fields to export (for CSV)
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
