# Email Database Manager - Setup Guide

## Quick Setup for Testing (Without Docker)

This guide helps you set up and test the application locally without Docker.

### Prerequisites
- Python 3.11+
- SQLite (comes with Python)
- Basic understanding of command line

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Set Environment Variables
```bash
export DATABASE_URL='sqlite:///email_manager.db'
export REDIS_URL='redis://localhost:6379/0'
export SECRET_KEY='test-secret-key-change-in-production'
export FLASK_APP=run.py
```

### Step 3: Initialize Database
```bash
# Create the database tables
python -c "from app import create_app, db; app = create_app(); app.app_context().push(); db.create_all(); print('Database created!')"
```

### Step 4: Create Admin User
```bash
python create_admin.py
# Follow prompts to create admin user
# Example: username=admin, email=admin@test.com, password=admin123
```

### Step 5: Run the Application
```bash
python run.py
```

The application will be available at `http://localhost:5000`

### Step 6: Run Tests
```bash
# Run all tests
DATABASE_URL='sqlite:///:memory:' pytest -v

# Run specific test suite
DATABASE_URL='sqlite:///:memory:' pytest tests/test_cctld_policy.py -v
```

## Testing the Features

### 1. Login
- Go to `http://localhost:5000/auth/login`
- Use admin credentials created in Step 4

### 2. Test Guest Registration
- Go to `http://localhost:5000/auth/register`
- Create a guest account
- Notice guest users are limited to their own uploads

### 3. Test Email Upload
- Navigate to Dashboard → Upload
- Upload the provided `sample_emails.csv`
- Notice import job processing
- Check rejected emails (will include .uk, .gov, .edu domains)

### 4. Test Validation
- Go to Dashboard → Validate
- Select uploaded batch
- Enable DNS check (optional)
- Start validation job

### 5. Test Export
- Go to Dashboard → Export
- Select export type (verified/unverified)
- Download results

### 6. Test Admin Features (admin account only)
- Go to Admin → Users: Create/edit users
- Go to Admin → Ignore Domains: Add domains to ignore
- Go to Admin → Download History: View all downloads
- Go to Admin → Activity Logs: View audit trail

## Docker Setup (Production-Ready)

### Step 1: Create .env file
```bash
cp .env.example .env
# Edit .env with production values
```

### Step 2: Build and Start
```bash
docker compose up -d --build
```

### Step 3: Initialize
```bash
docker compose exec web flask db upgrade
docker compose exec web python create_admin.py
```

### Step 4: Access
Open `http://localhost:5000`

## Troubleshooting

### Issue: ModuleNotFoundError
Solution: Make sure all dependencies are installed
```bash
pip install -r requirements.txt
```

### Issue: Database connection error
Solution: Check DATABASE_URL environment variable

### Issue: Import not working
Solution: Make sure upload folder exists and is writable
```bash
mkdir -p uploads exports
chmod 755 uploads exports
```

## Testing Acceptance Criteria

### US-only ccTLD Policy
Run the tests:
```bash
DATABASE_URL='sqlite:///:memory:' pytest tests/test_cctld_policy.py::TestUsCcTLDPolicy -v
```

Should show:
- ✓ user@example.com allowed (generic TLD)
- ✓ user@example.us allowed (US ccTLD)
- ✓ user@example.uk rejected (non-US ccTLD)
- ✓ user@example.co.uk rejected (multi-level ccTLD)
- ✓ user@example.gov rejected (policy suffix)
- ✓ user@example.edu rejected (policy suffix)

### RBAC Tests
```bash
DATABASE_URL='sqlite:///:memory:' pytest tests/test_cctld_policy.py::TestRBACRoles -v
```

Should verify:
- ✓ Self-registration creates guest role
- ✓ Guest users cannot access main DB
- ✓ Admin users have system-wide access
- ✓ Role enforcement works correctly

## Sample Test Scenarios

### Scenario 1: Guest User Flow
1. Register new account (becomes guest)
2. Upload sample_emails.csv
3. View own dashboard (only own uploads)
4. Validate batch
5. Export own data
6. Try accessing /admin (should be denied)

### Scenario 2: Admin Flow
1. Login as admin
2. View system-wide dashboard
3. Create new user with "user" role
4. Add ignore domain (e.g., spam.com)
5. View all batches from all users
6. View download history
7. Re-download any export

### Scenario 3: Import with Rejections
1. Upload sample_emails.csv
2. Wait for import to complete
3. Check batch details
4. Download rejected emails
5. Verify rejections:
   - ✗ rejected@example.uk (non-US ccTLD)
   - ✗ blocked@example.co.uk (multi-level ccTLD)
   - ✗ invalid@example.gov (policy suffix)
   - ✗ forbidden@example.edu (policy suffix)

## Performance Notes

- Import/validation are asynchronous (no Celery = sync processing)
- For production, use Redis + Celery workers
- SQLite is fine for testing, use PostgreSQL for production
- Large files (>10k emails) should use chunked processing

## Next Steps

1. Review the code structure in `/app`
2. Check models in `/app/models`
3. Review routes in `/app/routes`
4. Examine templates in `/app/templates`
5. Run comprehensive tests
6. Deploy to VPS following main README instructions
