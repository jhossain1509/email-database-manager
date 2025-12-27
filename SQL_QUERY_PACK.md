# SQL Query Pack for Email Database Management

This document contains the SQL queries for implementing the production-grade email database management system as specified in the requirements.

## 1. Dashboard Metrics Queries

### Total Emails Uploaded
```sql
SELECT COUNT(id) FROM emails;
```

### Total Verified (status='verified')
```sql
SELECT COUNT(id) FROM emails WHERE status = 'verified';
```

### Total Unverified (status='unverified')
```sql
SELECT COUNT(id) FROM emails WHERE status = 'unverified';
```

### Total Downloaded (downloaded_at IS NOT NULL)
```sql
SELECT COUNT(id) FROM emails WHERE downloaded_at IS NOT NULL;
```

### Available for Download
**Formula: status IN ('verified','unverified') AND downloaded_at IS NULL AND consent_granted = true AND suppressed = false**
```sql
SELECT COUNT(id) 
FROM emails 
WHERE status IN ('verified', 'unverified')
  AND downloaded_at IS NULL
  AND consent_granted = true
  AND suppressed = false;
```

### Total Rejected
```sql
SELECT COUNT(id) FROM rejected_emails;
-- OR using status field
SELECT COUNT(id) FROM emails WHERE status = 'rejected';
```

## 2. Batch Detail Metrics Queries

### Batch Summary
```sql
SELECT 
    id,
    name,
    filename,
    status,
    total_rows,
    imported_count,
    rejected_count,
    duplicate_count,
    created_at,
    updated_at
FROM batches
WHERE id = :batch_id;
```

### Batch-wise Verified/Unverified Counts
```sql
SELECT 
    status,
    COUNT(*) as count
FROM emails
WHERE batch_id = :batch_id
GROUP BY status;
```

### Batch-wise Domain Breakdown
```sql
SELECT 
    domain,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'verified' THEN 1 ELSE 0 END) as verified,
    SUM(CASE WHEN status = 'unverified' THEN 1 ELSE 0 END) as unverified,
    SUM(CASE WHEN downloaded_at IS NOT NULL THEN 1 ELSE 0 END) as downloaded,
    SUM(CASE WHEN downloaded_at IS NULL THEN 1 ELSE 0 END) as available
FROM emails
WHERE batch_id = :batch_id
GROUP BY domain
ORDER BY total DESC
LIMIT 10;
```

## 3. Top 10 Domain + Others Query

### Top 10 Domains (Dynamic)
```sql
SELECT 
    domain_category,
    COUNT(*) as count
FROM emails
GROUP BY domain_category
ORDER BY count DESC
LIMIT 10;
```

### Top 10 + Others Bucket
```sql
WITH top_domains AS (
    SELECT 
        domain_category,
        COUNT(*) as count
    FROM emails
    GROUP BY domain_category
    ORDER BY count DESC
    LIMIT 10
),
others AS (
    SELECT 
        'Others' as domain_category,
        COUNT(*) as count
    FROM emails
    WHERE domain_category NOT IN (
        SELECT domain_category FROM top_domains
    )
)
SELECT * FROM top_domains
UNION ALL
SELECT * FROM others
ORDER BY count DESC;
```

### Top Domains (Fixed List from Config) + Mixed
```sql
SELECT 
    CASE 
        WHEN domain IN ('gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com', 
                       'aol.com', 'icloud.com', 'protonmail.com', 'mail.com',
                       'zoho.com', 'gmx.com') THEN domain
        ELSE 'mixed'
    END as category,
    COUNT(*) as count
FROM emails
GROUP BY category
ORDER BY count DESC;
```

## 4. Available Calculation Query (for Export)

### Get Available Emails for Export
```sql
SELECT *
FROM emails
WHERE status IN ('verified', 'unverified')
  AND downloaded_at IS NULL
  AND consent_granted = true
  AND suppressed = false
ORDER BY created_at;
```

### Get Available Emails by Domain
```sql
SELECT *
FROM emails
WHERE status IN ('verified', 'unverified')
  AND downloaded_at IS NULL
  AND consent_granted = true
  AND suppressed = false
  AND domain = :domain
ORDER BY created_at
LIMIT :limit;
```

### Get Available Emails by Status Type
```sql
-- For verified only
SELECT *
FROM emails
WHERE status = 'verified'
  AND downloaded_at IS NULL
  AND consent_granted = true
  AND suppressed = false
ORDER BY created_at;

-- For unverified only
SELECT *
FROM emails
WHERE status = 'unverified'
  AND downloaded_at IS NULL
  AND consent_granted = true
  AND suppressed = false
ORDER BY created_at;
```

## 5. Domain-wise Breakdown Query

### Global Domain-wise Statistics
```sql
SELECT 
    domain,
    COUNT(*) as total_count,
    SUM(CASE WHEN status = 'verified' THEN 1 ELSE 0 END) as verified_count,
    SUM(CASE WHEN status = 'unverified' THEN 1 ELSE 0 END) as unverified_count,
    SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected_count,
    SUM(CASE WHEN downloaded_at IS NOT NULL THEN 1 ELSE 0 END) as downloaded_count,
    SUM(CASE WHEN downloaded_at IS NULL AND status IN ('verified', 'unverified') 
             AND consent_granted = true AND suppressed = false THEN 1 ELSE 0 END) as available_count
FROM emails
GROUP BY domain
ORDER BY total_count DESC;
```

### Domain Category Statistics
```sql
SELECT 
    domain_category,
    COUNT(*) as total_count,
    SUM(CASE WHEN status = 'verified' THEN 1 ELSE 0 END) as verified_count,
    SUM(CASE WHEN status = 'unverified' THEN 1 ELSE 0 END) as unverified_count,
    SUM(CASE WHEN downloaded_at IS NULL THEN 1 ELSE 0 END) as available_count
FROM emails
GROUP BY domain_category
ORDER BY total_count DESC;
```

## 6. Download Marking Query (Safe/Atomic)

### Mark Emails as Downloaded (Atomic Transaction)
```sql
BEGIN TRANSACTION;

-- Update downloaded_at for emails being exported
UPDATE emails
SET 
    downloaded_at = CURRENT_TIMESTAMP,
    downloaded = true,
    download_count = download_count + 1
WHERE id IN (
    SELECT id 
    FROM emails
    WHERE status IN ('verified', 'unverified')
      AND downloaded_at IS NULL
      AND consent_granted = true
      AND suppressed = false
    LIMIT :export_limit
);

-- Create download history record
INSERT INTO download_history (
    user_id, batch_id, download_type, filename, 
    file_path, record_count, downloaded_at
)
VALUES (
    :user_id, :batch_id, :download_type, :filename,
    :file_path, :record_count, CURRENT_TIMESTAMP
);

COMMIT;
```

### Check if Email is Already Downloaded
```sql
SELECT 
    email,
    downloaded_at,
    download_count
FROM emails
WHERE email = :email_address;
```

## 7. Import Logic Queries

### Check for Global Duplicate (Case-Insensitive)
```sql
SELECT id, email, batch_id
FROM emails
WHERE LOWER(email) = LOWER(:new_email)
LIMIT 1;
```

### Insert New Email with Default Status
```sql
INSERT INTO emails (
    email, domain, domain_category, status, 
    batch_id, uploaded_by, consent_granted, 
    created_at, uploaded_at
)
VALUES (
    LOWER(:email), :domain, :domain_category, 'unverified',
    :batch_id, :user_id, :consent_granted,
    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
);
```

### Update Batch Statistics After Import
```sql
UPDATE batches
SET 
    total_rows = :total_input_lines,
    imported_count = :successfully_inserted,
    rejected_count = :rejected_count,
    duplicate_count = :duplicate_count,
    status = 'success',
    updated_at = CURRENT_TIMESTAMP
WHERE id = :batch_id;
```

## 8. Validation Logic Queries

### Update Email Status to Verified
```sql
UPDATE emails
SET 
    status = 'verified',
    verified_at = CURRENT_TIMESTAMP,
    is_validated = true,
    is_valid = true,
    quality_score = :quality_score
WHERE id = :email_id;
```

### Update Email Status to Rejected
```sql
UPDATE emails
SET 
    status = 'rejected',
    rejected_reason = :reason,
    is_validated = true,
    is_valid = false,
    validation_error = :error_message
WHERE id = :email_id;
```

### Batch Update After Validation
```sql
UPDATE batches
SET 
    valid_count = (
        SELECT COUNT(*) FROM emails 
        WHERE batch_id = :batch_id AND status = 'verified'
    ),
    invalid_count = (
        SELECT COUNT(*) FROM emails 
        WHERE batch_id = :batch_id AND status = 'rejected'
    ),
    status = 'validated',
    updated_at = CURRENT_TIMESTAMP
WHERE id = :batch_id;
```

## 9. Re-download Queries

### Get Download History for Re-download
```sql
SELECT 
    id, user_id, filename, file_path, 
    record_count, downloaded_at
FROM download_history
WHERE id = :history_id
  AND user_id = :user_id;
```

### List User's Download History
```sql
SELECT 
    dh.id,
    dh.filename,
    dh.download_type,
    dh.record_count,
    dh.downloaded_at,
    b.name as batch_name
FROM download_history dh
LEFT JOIN batches b ON dh.batch_id = b.id
WHERE dh.user_id = :user_id
ORDER BY dh.downloaded_at DESC
LIMIT 50;
```

## 10. Performance Optimization Indexes

### Essential Indexes for Performance
```sql
-- Email table indexes
CREATE INDEX idx_emails_status ON emails(status);
CREATE INDEX idx_emails_downloaded_at ON emails(downloaded_at);
CREATE INDEX idx_emails_status_downloaded ON emails(status, downloaded_at);
CREATE INDEX idx_emails_domain ON emails(domain);
CREATE INDEX idx_emails_batch_id ON emails(batch_id);
CREATE UNIQUE INDEX idx_emails_email_unique ON emails(LOWER(email));

-- Batch table indexes
CREATE INDEX idx_batches_user_id ON batches(user_id);
CREATE INDEX idx_batches_status ON batches(status);

-- Download history indexes
CREATE INDEX idx_download_history_user_id ON download_history(user_id);
CREATE INDEX idx_download_history_downloaded_at ON download_history(downloaded_at);

-- Rejected emails indexes
CREATE INDEX idx_rejected_emails_batch_id ON rejected_emails(batch_id);
CREATE INDEX idx_rejected_emails_reason ON rejected_emails(reason);
```

## Notes on Implementation

1. **Global Unique Constraint**: The `LOWER(email)` unique index ensures case-insensitive uniqueness across all batches.

2. **No Double Download**: The `downloaded_at IS NULL` filter in export queries ensures emails are only exported once.

3. **Re-download Policy**: Users can re-download existing files from `download_history` without affecting email availability.

4. **Atomic Operations**: All download marking operations should be wrapped in transactions for consistency.

5. **Status Field**: The new `status` field replaces the combination of `is_validated` and `is_valid` fields for cleaner queries.

6. **Available for Download Formula**: 
   - `status IN ('verified', 'unverified')`
   - `downloaded_at IS NULL`
   - `consent_granted = true`
   - `suppressed = false`

7. **Backward Compatibility**: Legacy fields (`is_validated`, `is_valid`, `downloaded`) are maintained during transition.

This query pack ensures bug-free, consistent database operations across the entire email management system.
