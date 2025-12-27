# Database Management System Implementation

This document describes the implementation of the production-grade email database management system according to the requirements specified.

## Overview

The system implements a complete email database management workflow with the following key features:
1. **Import** → Emails are inserted with `status='unverified'`
2. **Validate** → Valid emails become `status='verified'`
3. **Export** → Only emails with `downloaded_at IS NULL` are exported
4. **Download** → Sets `downloaded_at = NOW()` to prevent re-export
5. **Re-download** → Allows downloading same file again without making emails available again

## Core Entities

### 1. Email Table

**Primary Fields:**
- `email` (unique, lowercase, globally unique constraint)
- `domain` (extracted from email)
- `status` (unverified | verified | rejected | suppressed)
- `batch_id` (which batch imported this email)
- `downloaded_at` (nullable, timestamp when downloaded)
- `created_at` (when email was created)
- `verified_at` (when email was verified)
- `rejected_reason` (if status is rejected)

**Key Features:**
- **Global Unique Constraint**: Each email can only exist once in the database (case-insensitive)
- **Status System**: Replaces the old `is_validated` + `is_valid` combination
- **Download Tracking**: `downloaded_at` field tracks when email was downloaded

**Default Behavior:**
- New imports: `status = 'unverified'`
- After validation: `status = 'verified'` (if valid) or `status = 'rejected'` (if invalid)
- Download marks: `downloaded_at = CURRENT_TIMESTAMP`

### 2. Batch Table

**Primary Fields:**
- `id` (batch identifier)
- `filename` (original filename)
- `status` (queued | running | success | failed)
- `total_rows` (total input lines)
- `imported_count` (successfully inserted emails)
- `rejected_count` (rejected emails)
- `duplicate_count` (duplicate emails)
- `rejected_file_path` (path to rejected emails file)

**Legacy Fields** (maintained for backward compatibility):
- `total_count`
- `valid_count`
- `invalid_count`

## Import Logic

### Workflow:
1. Read emails from CSV/TXT file
2. Normalize (lowercase, trim)
3. Check validation rules:
   - **Invalid syntax** → reject
   - **Ignore/blocked domain** → reject
   - **Global duplicate** (check entire database) → reject
   - **In current batch already** → reject
   - **In suppression list** → reject
4. If valid: Insert with `status='unverified'`
5. Update batch statistics

### Code Implementation:
```python
# Check global duplicate (case-insensitive)
existing_email = Email.query.filter(
    db.func.lower(Email.email) == email.lower()
).first()

if existing_email:
    # Mark as duplicate, don't import
    duplicate_count += 1
else:
    # Import with default status
    email_obj = Email(
        email=email,
        domain=domain,
        status='unverified',  # Default status
        batch_id=batch_id,
        uploaded_by=user_id,
        consent_granted=consent_granted
    )
    db.session.add(email_obj)
    imported_count += 1
```

### Batch Statistics Update:
```python
batch.total_rows = len(emails_to_process)  # Total input lines
batch.imported_count = imported_count  # Successfully inserted
batch.rejected_count = rejected_count  # Rejected emails
batch.duplicate_count = duplicate_count  # Duplicate emails
batch.status = 'success'
```

## Status System

### Status Values:
1. **unverified**: Default status after import, not yet validated
2. **verified**: Email passed validation checks
3. **rejected**: Email failed validation
4. **suppressed**: Email is in suppression list (opt-out, bounce, complaint)

### Validation Process:
```python
# During validation task
if is_valid:
    email_obj.status = 'verified'
    email_obj.verified_at = datetime.utcnow()
    email_obj.is_valid = True  # Legacy field
else:
    email_obj.status = 'rejected'
    email_obj.rejected_reason = error_type
    email_obj.is_valid = False  # Legacy field

email_obj.is_validated = True  # Legacy field
```

## Dashboard Metrics

### The 6 Key Numbers:

1. **Total Emails Uploaded**
   ```python
   Email.query.count()
   ```

2. **Total Verified** (status='verified')
   ```python
   Email.query.filter_by(status='verified').count()
   ```

3. **Total Unverified** (status='unverified')
   ```python
   Email.query.filter_by(status='unverified').count()
   ```

4. **Total Downloaded** (downloaded_at IS NOT NULL)
   ```python
   Email.query.filter(Email.downloaded_at.isnot(None)).count()
   ```

5. **Available for Download** (most important)
   ```python
   Email.query.filter(
       Email.status.in_(['verified', 'unverified']),
       Email.downloaded_at.is_(None),
       Email.consent_granted == True,
       Email.suppressed == False
   ).count()
   ```

6. **Domain-wise Count**
   ```python
   db.session.query(
       Email.domain,
       func.count(Email.id).label('count')
   ).group_by(Email.domain).order_by(desc('count')).all()
   ```

## Export / Download Rules

### No Double Download Policy:

**Export Query** (only available emails):
```python
query = Email.query.filter(
    Email.downloaded_at.is_(None),  # Not yet downloaded
    Email.status.in_(['verified', 'unverified']),
    Email.consent_granted == True,
    Email.suppressed == False
)
```

**Mark as Downloaded** (atomic operation):
```python
download_timestamp = datetime.utcnow()
for email_obj in emails_to_export:
    email_obj.downloaded_at = download_timestamp
    email_obj.downloaded = True  # Legacy field
    email_obj.download_count += 1
db.session.commit()
```

**Result:**
- Email is now marked with `downloaded_at` timestamp
- Next export query will skip this email (because `downloaded_at IS NOT NULL`)
- Email will NOT appear in "Available for Download" count

### Re-download Policy:

**Same File Can Be Downloaded Multiple Times:**
```python
@bp.route('/download/<int:history_id>')
def download_export(history_id):
    """Re-download existing export file"""
    history = DownloadHistory.query.get_or_404(history_id)
    
    # File can be downloaded again
    # Emails don't become "available" again
    return send_file(history.file_path, as_attachment=True)
```

**Key Points:**
- User can re-download the same file from history
- Email records are NOT updated on re-download
- `downloaded_at` remains set (emails don't become available again)
- Only the file is served again

## Domain-wise Export / Download

### Export by Domain:
```python
# Query for specific domain
query = Email.query.filter(
    Email.downloaded_at.is_(None),
    Email.domain == 'gmail.com',
    Email.status == 'verified'
)

# Multiple files by domain
for domain in domains:
    domain_emails = query.filter_by(domain=domain).all()
    filename = f"verified_{domain}_part1.txt"
    _write_export_file(domain_emails, filename)
```

### Domain Statistics:
```python
domain_stats = db.session.query(
    Email.domain,
    func.count(Email.id).label('total'),
    func.sum(db.case((Email.status == 'verified', 1), else_=0)).label('verified'),
    func.sum(db.case((Email.status == 'unverified', 1), else_=0)).label('unverified'),
    func.sum(db.case((Email.downloaded_at.isnot(None), 1), else_=0)).label('downloaded'),
    func.sum(db.case((Email.downloaded_at.is_(None), 1), else_=0)).label('available')
).group_by(Email.domain).order_by(desc('total')).limit(10).all()
```

## Database Migration

### Migration File: `add_status_and_download_tracking.py`

**Key Changes:**
1. Add `status` column with default 'unverified'
2. Migrate existing data based on `is_validated` and `is_valid` fields
3. Add `downloaded_at`, `created_at`, `verified_at`, `rejected_reason` columns
4. Add unique constraint on `LOWER(email)` for global uniqueness
5. Add indexes for performance
6. Add `total_rows`, `imported_count`, `rejected_file_path` to batches table

**Migration Logic:**
```sql
-- Add status column
ALTER TABLE emails ADD COLUMN status VARCHAR(20);

-- Migrate existing data
UPDATE emails 
SET status = CASE 
    WHEN is_validated = true AND is_valid = true THEN 'verified'
    WHEN is_validated = true AND is_valid = false THEN 'rejected'
    WHEN suppressed = true THEN 'suppressed'
    ELSE 'unverified'
END;

-- Make status NOT NULL after setting values
ALTER TABLE emails ALTER COLUMN status SET NOT NULL;

-- Add unique index on lowercase email
CREATE UNIQUE INDEX idx_emails_email_unique ON emails(LOWER(email));
```

## Top 10 Domains + Mixed

### Top 10 Dynamic:
```python
top_domains = db.session.query(
    Email.domain_category,
    func.count(Email.id).label('count')
).group_by(
    Email.domain_category
).order_by(
    desc('count')
).limit(10).all()
```

### Top Domains Fixed + Mixed:
```python
# From config.py
TOP_DOMAINS = [
    'gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com',
    'aol.com', 'icloud.com', 'protonmail.com', 'mail.com',
    'zoho.com', 'gmx.com'
]

# Classify domain
def classify_domain(domain):
    if domain in TOP_DOMAINS:
        return domain
    else:
        return 'mixed'
```

## Consistency Rules

### Server Error Prevention:

1. **Email Unique Constraint**: Enforced at database level with unique index on `LOWER(email)`
2. **Field Name Consistency**: Use `total_rows`, `imported_count` consistently across all code
3. **Status Field**: Always use `status` field in new queries, keep legacy fields for compatibility
4. **Downloaded Tracking**: Always use `downloaded_at` for checking if email was downloaded
5. **Atomic Transactions**: Wrap download marking in transactions

### Code Example:
```python
# GOOD - Consistent field names
batch.total_rows = len(emails)
batch.imported_count = imported_count

# GOOD - Use status field
query.filter_by(status='verified')

# GOOD - Use downloaded_at
query.filter(Email.downloaded_at.is_(None))

# GOOD - Check global unique
existing = Email.query.filter(
    db.func.lower(Email.email) == email.lower()
).first()
```

## Testing

### Key Test Scenarios:

1. **Import with Global Duplicate**
   - Import email A in batch 1
   - Try to import email A in batch 2
   - Should be rejected as duplicate

2. **Status Transitions**
   - Import: `status='unverified'`
   - Validate (pass): `status='verified'`, `verified_at` set
   - Validate (fail): `status='rejected'`, `rejected_reason` set

3. **Download Once**
   - Export available emails
   - Mark `downloaded_at = NOW()`
   - Try to export again
   - Previously downloaded emails should NOT appear

4. **Re-download File**
   - Download export file (history_id=1)
   - Download same file again
   - Both downloads should succeed
   - Email availability should not change

5. **Dashboard Metrics Consistency**
   - Total Uploaded = Verified + Unverified + Rejected + Suppressed
   - Available = Unverified (not downloaded) + Verified (not downloaded)
   - Downloaded = Emails with `downloaded_at IS NOT NULL`

## Benefits

### Compared to Old System:

1. **Simpler Status Logic**: One `status` field instead of `is_validated` + `is_valid` combination
2. **Clear Download Tracking**: `downloaded_at` timestamp instead of boolean flag
3. **Global Uniqueness**: Enforced at database level, prevents duplicates across all batches
4. **Accurate Metrics**: "Available for Download" count is always accurate
5. **No Double Download**: Prevents exporting same email twice
6. **Re-download Support**: Users can re-download files without affecting email availability
7. **Better Statistics**: Easy to query by status, domain, and download state

## Database Schema Summary

### Email Table:
```
id (PK)
email (unique, lowercase) ✅
domain ✅
status (unverified/verified/rejected/suppressed) ✅
batch_id (FK) ✅
downloaded_at (nullable timestamp) ✅
created_at ✅
verified_at (nullable) ✅
rejected_reason (nullable) ✅
uploaded_by (FK)
consent_granted
suppressed
```

### Batch Table:
```
id (PK)
filename ✅
status (queued/running/success/failed) ✅
total_rows ✅
imported_count ✅
rejected_count ✅
duplicate_count ✅
rejected_file_path ✅
user_id (FK)
created_at
updated_at
```

## Conclusion

This implementation provides a robust, production-ready email database management system with:
- Clear status tracking
- Accurate download management
- Global email uniqueness
- Consistent metrics
- Domain-wise statistics
- Re-download capability

All queries and logic are designed to prevent bugs and ensure data consistency.
