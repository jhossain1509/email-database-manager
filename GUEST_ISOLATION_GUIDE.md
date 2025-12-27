# Guest Isolation Feature - Quick Start Guide

## Overview
The Guest Isolation feature allows guest users to upload and manage email lists while maintaining complete separation from the main database. This ensures guest users can see their full uploaded lists (including duplicates) and export them without affecting admin/user metrics.

## Key Concepts

### 1. Guest vs Regular Users
- **Guest Users**: Have `role='guest'`, self-registered users
- **Regular Users**: Have `role='user'`, `role='admin'`, or other non-guest roles

### 2. Main Database (emails table)
- Stores **globally unique** email addresses
- Tracks download metrics for admin/regular users
- Modified by both guest and regular user uploads, but only for NEW emails

### 3. Guest Email Items (guest_email_items table)
- Stores **all emails uploaded by guests**, including duplicates
- Links to main emails table via `matched_email_id`
- Tracks result: `inserted` (new), `duplicate` (already in DB), or `rejected` (invalid)

### 4. Guest Download History (guest_download_history table)
- Tracks guest exports separately
- Allows unlimited re-downloads
- Does NOT affect main database download counters

## User Flows

### Guest User Upload Flow
1. Guest uploads CSV file with emails
2. System processes each email:
   - **New email**: Inserted into main `emails` table + creates GuestEmailItem with `result='inserted'`
   - **Duplicate**: NOT inserted into `emails` table + creates GuestEmailItem with `result='duplicate'` linking to existing email
   - **Rejected**: Creates GuestEmailItem with `result='rejected'` and reason
3. Guest sees ALL their uploaded emails in batch detail view

### Guest User Export Flow
1. Guest selects batch to export
2. System queries `guest_email_items` for that guest/batch
3. Exports all items (including duplicates)
4. Creates `GuestDownloadHistory` record
5. **Does NOT** modify `emails.downloaded` or `emails.download_count`

### Guest User Validation Flow
1. Guest initiates validation on their batch
2. System finds unique emails via GuestEmailItem → Email links
3. Runs validation on those emails
4. Updates canonical `Email` records with validation results
5. Guest sees updated status in batch detail view

## Database Schema

### GuestEmailItem
```sql
CREATE TABLE guest_email_items (
    id INTEGER PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id),
    user_id INTEGER NOT NULL REFERENCES users(id),
    email_normalized VARCHAR(255) NOT NULL,
    domain VARCHAR(255) NOT NULL,
    result VARCHAR(50) NOT NULL,  -- 'inserted', 'duplicate', 'rejected'
    matched_email_id INTEGER REFERENCES emails(id),
    rejected_reason VARCHAR(100),
    rejected_details TEXT,
    created_at TIMESTAMP NOT NULL,
    UNIQUE (batch_id, email_normalized)  -- No duplicates within same batch
)
```

### GuestDownloadHistory
```sql
CREATE TABLE guest_download_history (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    batch_id INTEGER REFERENCES batches(id),
    download_type VARCHAR(50) NOT NULL,  -- 'verified', 'unverified', 'rejected', 'all'
    filename VARCHAR(255) NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    file_size BIGINT,
    record_count INTEGER NOT NULL,
    filters TEXT,
    downloaded_times INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL,
    last_downloaded_at TIMESTAMP NOT NULL
)
```

## API/Route Changes

### Modified Routes
- **GET /email/batch/<id>**: Returns different template for guests (`batch_detail_guest.html`)
- **POST /email/export**: Routes guests to `export_guest_emails_task`
- **GET /email/download-history**: Shows `GuestDownloadHistory` for guests
- **GET /email/download/<id>**: Handles both guest and regular history types

### New Celery Task
- **`export_guest_emails_task(user_id, batch_id, export_type, export_format, custom_fields)`**
  - Queries from `guest_email_items` table
  - Does not modify main `emails` table
  - Creates `GuestDownloadHistory` record

## Migration Guide

### Step 1: Backup Database
```bash
pg_dump -U postgres email_manager > backup_before_guest_isolation.sql
```

### Step 2: Run Migration
```bash
flask db upgrade
```

### Step 3: Verify Tables Created
```bash
flask shell
>>> from app import db
>>> db.engine.table_names()
# Should include 'guest_email_items' and 'guest_download_history'
```

### Step 4: Test with Guest User
1. Create or login as guest user
2. Upload a CSV with some duplicate emails
3. Check batch detail - should see all emails with result column
4. Export the batch - should create guest download history
5. Re-download - should increment download counter without affecting main DB

## Backward Compatibility

### ✅ Unchanged Behavior
- Regular user and admin workflows remain identical
- Main `emails` table still globally unique
- Regular user exports still update `emails.downloaded`
- Admin metrics and reporting unchanged

### ⚠️ Breaking Changes
None - this is an additive feature

## Performance Considerations

### Potential Bottlenecks
1. **Guest Import**: Case-insensitive email lookup for duplicates runs per-email
   - **Recommendation**: Add database index on `LOWER(email)` for production
   - **Alternative**: Batch lookup approach for large imports

2. **Guest Export**: Joins GuestEmailItem with Email for status
   - **Optimization**: Uses `joinedload` for eager loading
   - **Scale**: Should handle 100k+ guest items per batch

### Monitoring Metrics
- Number of GuestEmailItem records per batch
- Average export time for guest batches
- Guest download history growth rate

## Troubleshooting

### Issue: Guest sees wrong item count
**Cause**: Guest items include duplicates and rejected
**Solution**: Check `GuestEmailItem.result` field - only `result='inserted'` are new to DB

### Issue: Guest export is slow
**Cause**: Large batch with many items
**Solution**: 
1. Add index on `guest_email_items(user_id, batch_id)`
2. Consider pagination for very large batches
3. Use TXT format instead of CSV for faster exports

### Issue: Validation not showing for guest items
**Cause**: Validation runs on `Email` table, not `GuestEmailItem`
**Solution**: Ensure `matched_email_id` is set correctly and join is working

## Testing

### Unit Tests
Run guest isolation tests:
```bash
pytest tests/test_guest_isolation.py -v
```

### Manual Testing Checklist
- [ ] Guest user can upload CSV
- [ ] Guest sees all uploaded emails including duplicates
- [ ] Guest export includes duplicates
- [ ] Guest re-download works
- [ ] Main DB download metrics unchanged after guest export
- [ ] Regular user upload still works
- [ ] Admin can see all batches
- [ ] Validation updates guest item status

## Security Notes

- Guest users can only see/export their own batches
- Guest cannot access main DB download metrics
- Guest cannot see other guests' uploads
- Guest exports are isolated to their own history
- Access control enforced at route level and in queries

## Future Enhancements

1. **Bulk duplicate detection**: Pre-check entire guest batch against main DB
2. **Guest analytics**: Track duplicate rates, validation rates per guest
3. **Guest limits**: Set max uploads/exports per guest per time period
4. **Guest batch merging**: Allow guests to combine multiple batches
5. **Guest email deduplication**: UI to show guests which emails are duplicates

## Support

For issues or questions:
1. Check `GUEST_ISOLATION_IMPLEMENTATION.md` for technical details
2. Review test cases in `tests/test_guest_isolation.py`
3. Check application logs for task errors
4. Verify database migration completed successfully
