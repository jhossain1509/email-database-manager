from celery import shared_task
from app import db
from app.models.email import Email, Batch, RejectedEmail, IgnoreDomain, SuppressionList
from app.models.job import Job, DomainReputation, DownloadHistory
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
                    else:
                        # Import email
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
            batch.total_count = imported_count
            batch.rejected_count = rejected_count
            batch.duplicate_count = duplicate_count
            batch.status = 'uploaded'
            db.session.commit()
            
            # Complete job
            job.complete(
                message=f'Imported {imported_count} emails, rejected {rejected_count}, duplicates {duplicate_count}',
                result_data={
                    'imported': imported_count,
                    'rejected': rejected_count,
                    'duplicates': duplicate_count
                }
            )
            
            return {
                'status': 'completed',
                'imported': imported_count,
                'rejected': rejected_count,
                'duplicates': duplicate_count
            }
            
        except Exception as e:
            if job:
                job.fail(str(e))
            raise

@shared_task(bind=True)
def validate_emails_task(self, batch_id, user_id, check_dns=False, check_role=False):
    """
    Validate emails in a batch.
    Job-driven with progress reporting.
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
            
            batch = Batch.query.get(batch_id)
            if not batch:
                raise Exception(f'Batch {batch_id} not found')
            
            # Get emails to validate
            emails = Email.query.filter_by(batch_id=batch_id).all()
            job.total = len(emails)
            db.session.commit()
            
            # Get ignore domains
            ignore_domains = [d.domain for d in IgnoreDomain.query.all()]
            
            valid_count = 0
            invalid_count = 0
            
            for idx, email_obj in enumerate(emails):
                try:
                    # Validate
                    is_valid, error_type, error_message = validate_email_full(
                        email_obj.email,
                        check_dns=check_dns,
                        check_role=check_role,
                        ignore_domains=ignore_domains
                    )
                    
                    email_obj.is_validated = True
                    email_obj.is_valid = is_valid
                    
                    if not is_valid:
                        email_obj.validation_error = error_message
                        invalid_count += 1
                    else:
                        valid_count += 1
                        # Calculate quality score (simple heuristic)
                        score = 70
                        if check_dns and email_obj.domain:
                            from app.utils.email_validator import check_dns_mx
                            if check_dns_mx(email_obj.domain):
                                score += 20
                        email_obj.quality_score = min(100, score)
                    
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
def export_emails_task(self, user_id, export_type='verified', batch_id=None, filter_domains=None):
    """
    Export emails with filtering.
    Job-driven with progress reporting.
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
            
            # Build query
            query = Email.query
            
            if batch_id:
                query = query.filter_by(batch_id=batch_id)
            
            if export_type == 'verified':
                query = query.filter_by(is_validated=True, is_valid=True)
            elif export_type == 'unverified':
                query = query.filter_by(is_validated=False)
            elif export_type == 'invalid':
                query = query.filter_by(is_validated=True, is_valid=False)
            
            if filter_domains:
                query = query.filter(Email.domain.in_(filter_domains))
            
            # Get suppression list
            suppressed = set([s.email for s in SuppressionList.query.all()])
            
            emails = query.all()
            job.total = len(emails)
            db.session.commit()
            
            # Create export file
            export_folder = app.config['EXPORT_FOLDER']
            os.makedirs(export_folder, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"export_{export_type}_{user_id}_{timestamp}.csv"
            file_path = os.path.join(export_folder, filename)
            
            exported_count = 0
            
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['Email', 'Domain', 'Quality Score', 'Uploaded At'])
                
                for idx, email_obj in enumerate(emails):
                    # Skip suppressed emails
                    if email_obj.email in suppressed:
                        continue
                    
                    writer.writerow([
                        email_obj.email,
                        email_obj.domain,
                        email_obj.quality_score or '',
                        email_obj.uploaded_at.strftime('%Y-%m-%d %H:%M:%S')
                    ])
                    
                    # Mark as downloaded
                    email_obj.downloaded = True
                    email_obj.download_count += 1
                    exported_count += 1
                    
                    if (idx + 1) % 100 == 0:
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
            
            db.session.commit()
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Create download history
            history = DownloadHistory(
                user_id=user_id,
                batch_id=batch_id,
                download_type=export_type,
                filter_domains=','.join(filter_domains) if filter_domains else None,
                filename=filename,
                file_path=file_path,
                file_size=file_size,
                record_count=exported_count
            )
            db.session.add(history)
            db.session.commit()
            
            # Complete job
            job.complete(
                message=f'Exported {exported_count} emails',
                result_data={
                    'exported': exported_count,
                    'filename': filename,
                    'file_path': file_path,
                    'history_id': history.id
                }
            )
            
            return {
                'status': 'completed',
                'exported': exported_count,
                'filename': filename,
                'file_path': file_path,
                'history_id': history.id
            }
            
        except Exception as e:
            if job:
                job.fail(str(e))
            raise
