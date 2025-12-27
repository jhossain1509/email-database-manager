# Guest-Isolated Email Tracking Implementation Summary

## Overview
This implementation adds guest-isolated email tracking and export functionality to the Email Database Manager, ensuring that guest users can manage their uploaded email lists without accessing or affecting the main database.

## Key Features Implemented

### 1. New Database Models

#### GuestEmailItem
- **Purpose**: Track individual email items uploaded by guest users
- **Fields**:
  - `batch_id`: Link to the batch
  - `user_id`: Guest user ID
  - `email_normalized`: The email address (case-normalized)
  - `domain`: Email domain
  - `result`: Processing result (inserted, duplicate, rejected)
  - `matched_email_id`: FK to main emails table (null if rejected)
  - `rejected_reason` & `rejected_details`: For rejected emails
  - `created_at`: Timestamp
- **Constraints**: Unique constraint on (batch_id, email_normalized) to prevent duplicates within same batch
- **Purpose**: Allows guests to see their complete uploaded list including duplicates

#### GuestDownloadHistory
- **Purpose**: Track guest export history separately from main DB download tracking
- **Fields**:
  - `user_id`: Guest user ID
  - `batch_id`: Optional batch filter
  - `download_type`: Type of export (verified/unverified/rejected/all)
  - `filename`, `file_path`, `file_size`: File details
  - `record_count`: Number of records exported
  - `filters`: Optional JSON filter data
  - `downloaded_times`: Re-download counter
  - `created_at`, `last_downloaded_at`: Timestamps
- **Purpose**: Enable re-downloads without affecting main DB metrics

### 2. Import Logic Changes (`import_emails_task`)

**For Guest Users:**
- Always creates a `GuestEmailItem` for every uploaded email
- Checks if email exists in main DB (case-insensitive)
- If exists: Creates guest item with `result='duplicate'` and links to existing email
- If new: Inserts into main `emails` table and creates guest item with `result='inserted'`
- For rejected emails: Creates guest item with `result='rejected'`

**For Regular Users:**
- No changes to existing behavior
- No `GuestEmailItem` records created

### 3. Validation Logic Changes (`validate_emails_task`)

**For Guest Users:**
- Gets emails to validate from guest's `GuestEmailItem` scope
- Collects unique emails via `matched_email_id`
- Updates the canonical `Email` rows (not guest items directly)

**For Regular Users:**
- No changes to existing behavior

### 4. Guest Export Task (`export_guest_emails_task`)

**Features:**
- Queries from `GuestEmailItem` table (not `Email`)
- Includes duplicates in export
- Supports filtering by validation status (verified/unverified/invalid/rejected/all)
- Creates `GuestDownloadHistory` record (not `DownloadHistory`)
- **Does NOT modify** `Email.downloaded` or `Email.download_count`
- Supports both CSV and TXT formats

### 5. Route Updates

#### Batch Detail Route (`/email/batch/<id>`)
- Guest users see `batch_detail_guest.html` template
- Shows `GuestEmailItem` data with result column (New/Duplicate/Rejected)
- Displays validation status from linked `Email` records

#### Export Route (`/email/export`)
- Detects guest users and calls `export_guest_emails_task` instead of `export_emails_task`
- Guests don't see main DB domain statistics
- Guests must select a specific batch to export

#### Download History Route (`/email/download-history`)
- Guests see `GuestDownloadHistory` records
- Regular users see `DownloadHistory` records
- Different templates for each user type

#### Download Export Route (`/email/download/<id>`)
- Detects guest vs regular download history
- Updates `downloaded_times` counter for guest downloads
- Enforces access control based on user type

### 6. New Templates

#### `batch_detail_guest.html`
- Shows guest-specific batch view
- Displays all uploaded items including duplicates
- Color-coded result badges (New/Duplicate/Rejected)
- Shows validation status from linked emails

#### `download_history_guest.html`
- Shows guest download history
- Displays download count
- Allows re-downloads without affecting main DB

## Database Migration

**File**: `migrations/versions/20251227_141019_add_guest_isolation_tables.py`

Creates:
- `guest_email_items` table with all necessary indexes and foreign keys
- `guest_download_history` table with indexes
- Unique constraint on (batch_id, email_normalized) in guest_email_items

## Key Benefits

1. **Guest Isolation**: Guests can only see/export their own uploaded lists
2. **Duplicate Visibility**: Guests see all emails they uploaded, even duplicates
3. **No Main DB Pollution**: Guest exports don't affect download metrics
4. **Global Uniqueness**: Main emails table remains globally unique
5. **Validation Integrity**: Validation updates canonical Email records
6. **Re-download Support**: Guests can re-download previous exports without limit
7. **Backward Compatibility**: Regular user and admin flows unchanged

## Acceptance Criteria Met

✅ Guest can see and export their uploaded list even when most emails are duplicates
✅ Main DB remains globally unique; guest uploads never create duplicates in `emails`
✅ Guest export/download does not impact admin/user available/downloaded metrics
✅ Existing admin/user flows remain functional

## Testing

Created comprehensive test suite in `tests/test_guest_isolation.py`:
- Model creation and constraints
- Guest import with duplicates
- Guest export without main DB modification
- Regular user flow verification

## Migration Instructions

1. Install dependencies: `pip install -r requirements.txt`
2. Run migration: `flask db upgrade`
3. Verify tables created: Check for `guest_email_items` and `guest_download_history`
4. Test with guest user account

## Notes

- Guest users identified by `user.role == 'guest'`
- All email comparisons are case-insensitive
- Guest items link to emails via `matched_email_id`
- File exports stored in configured `EXPORT_FOLDER`
