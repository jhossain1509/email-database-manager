# Quick Reference Guide - Database Management System

## Essential Changes at a Glance

### 1. Email Status Field (Most Important Change)

**Old Way:**
```python
# Checking if email is verified
email.is_validated == True and email.is_valid == True
```

**New Way:**
```python
# Much simpler!
email.status == 'verified'
```

**Status Values:**
- `unverified` - Default after import
- `verified` - Passed validation
- `rejected` - Failed validation
- `suppressed` - In suppression list

### 2. Download Tracking

**Old Way:**
```python
# Boolean flag
email.downloaded = True
```

**New Way:**
```python
# Timestamp tracking
email.downloaded_at = datetime.utcnow()
```

**Why?** Knowing WHEN email was downloaded is more useful than just knowing IF it was downloaded.

### 3. Global Email Uniqueness

**Before:** Email could be imported multiple times in different batches

**Now:** Each email address can only exist ONCE in the entire database (case-insensitive)

```python
# Automatic check during import
existing = Email.query.filter(
    db.func.lower(Email.email) == email.lower()
).first()

if existing:
    # Reject as duplicate
```

### 4. Dashboard Metrics - The 6 Key Numbers

```python
# 1. Total Emails Uploaded
Email.query.count()

# 2. Total Verified
Email.query.filter_by(status='verified').count()

# 3. Total Unverified
Email.query.filter_by(status='unverified').count()

# 4. Total Downloaded
Email.query.filter(Email.downloaded_at.isnot(None)).count()

# 5. Available for Download (MOST IMPORTANT)
Email.query.filter(
    Email.status.in_(['verified', 'unverified']),
    Email.downloaded_at.is_(None),
    Email.consent_granted == True,
    Email.suppressed == False
).count()

# 6. Total Rejected
RejectedEmail.query.count()
```

### 5. Export Logic - No Double Download

**Before:** Might export same email multiple times

**Now:** Only exports emails that haven't been downloaded yet

```python
# Export query
emails = Email.query.filter(
    Email.downloaded_at.is_(None),  # KEY: Only not-yet-downloaded
    Email.status.in_(['verified', 'unverified']),
    Email.consent_granted == True,
    Email.suppressed == False
).all()

# After export, mark them
for email in emails:
    email.downloaded_at = datetime.utcnow()
db.session.commit()
```

### 6. Re-download Support

**User can download same file multiple times, but emails don't become "available" again**

```python
# Route allows re-downloading
@bp.route('/download/<int:history_id>')
def download_export(history_id):
    history = DownloadHistory.query.get_or_404(history_id)
    return send_file(history.file_path)  # File served again
    # Email records NOT updated - downloaded_at stays set
```

### 7. Import Workflow

```
1. Read email from file
2. Normalize (lowercase, trim)
3. Check if already exists globally → reject if yes
4. Validate syntax, domain rules → reject if invalid
5. Import with status='unverified'
6. Update batch statistics
```

### 8. Validation Workflow

```
1. Get unverified emails
2. Run validation checks
3. If valid:   status='verified', verified_at=NOW()
4. If invalid: status='rejected', rejected_reason=error_type
5. Update batch statistics
```

### 9. Batch Statistics - New Fields

```python
batch.total_rows        # Total lines in uploaded file
batch.imported_count    # Successfully imported emails
batch.rejected_count    # Rejected during import
batch.duplicate_count   # Duplicates found
```

### 10. Common Queries

**Get all available emails:**
```sql
SELECT * FROM emails
WHERE status IN ('verified', 'unverified')
  AND downloaded_at IS NULL
  AND consent_granted = true
  AND suppressed = false;
```

**Check if email exists:**
```sql
SELECT * FROM emails
WHERE LOWER(email) = LOWER('user@example.com');
```

**Get domain statistics:**
```sql
SELECT 
    domain,
    COUNT(*) as total,
    SUM(CASE WHEN status='verified' THEN 1 ELSE 0 END) as verified,
    SUM(CASE WHEN status='unverified' THEN 1 ELSE 0 END) as unverified,
    SUM(CASE WHEN downloaded_at IS NOT NULL THEN 1 ELSE 0 END) as downloaded
FROM emails
GROUP BY domain
ORDER BY total DESC;
```

## Migration Command

```bash
# Run migration to apply all changes
flask db upgrade

# Or with Docker
docker compose exec web flask db upgrade
```

## Key Files Changed

1. **app/models/email.py** - Email and Batch models updated
2. **app/jobs/tasks.py** - Import, validation, export tasks updated
3. **app/routes/dashboard.py** - Dashboard metrics updated
4. **app/routes/api.py** - API endpoints updated
5. **app/templates/** - Template displays updated
6. **migrations/versions/add_status_and_download_tracking.py** - Migration file

## Backward Compatibility

✅ All legacy fields maintained:
- `is_validated`, `is_valid` (still updated)
- `downloaded` boolean (still updated)
- `total_count`, `valid_count`, `invalid_count` (still updated)

You can use either old or new fields during transition period.

## Testing Quick Checklist

```bash
# 1. Test import with duplicate
python -c "from app import create_app; app = create_app(); ..."

# 2. Check dashboard metrics
curl http://localhost:5000/api/stats

# 3. Test export
# Export, then export again - second should return 0 emails

# 4. Test re-download
# Download file twice - both should succeed
```

## Common Issues & Solutions

**Issue:** Email can't be imported
**Solution:** Check if it already exists globally (case-insensitive)

**Issue:** Available count seems wrong
**Solution:** Verify all 4 conditions: status, downloaded_at, consent_granted, suppressed

**Issue:** Can't re-download file
**Solution:** Check DownloadHistory table for file_path

**Issue:** Migration fails
**Solution:** Check for duplicate emails first, migration will keep most recent

## Need More Details?

- **SQL Queries:** See SQL_QUERY_PACK.md
- **Implementation Details:** See DATABASE_MANAGEMENT_IMPLEMENTATION.md
- **Full Summary:** See IMPLEMENTATION_SUMMARY.md

---

**Remember:** The most important change is using `status` field and `downloaded_at` timestamp for cleaner, more reliable code!
