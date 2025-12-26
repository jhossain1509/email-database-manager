# Migration Path Error Fix

## Problem
When running `docker compose exec web flask db upgrade`, the application was failing with:
```
Error: Path doesn't exist: migrations. Please use the 'init' command to create a new scripts folder.
```

## Root Cause
The Flask-Migrate migrations directory was not initialized and committed to the repository. Flask-Migrate requires a `migrations/` folder to be present before running `flask db upgrade`.

## Solution
Initialized Flask-Migrate and created the initial database migration:

1. **Initialized Flask-Migrate**: Ran `flask db init` to create the migrations directory structure
2. **Created Initial Migration**: Ran `flask db migrate` to generate the initial migration with all database models
3. **Committed migrations to repository**: Added the migrations folder to git so it's available when the application is deployed

## Files Added
- `migrations/README` - Migration directory documentation
- `migrations/alembic.ini` - Alembic configuration
- `migrations/env.py` - Migration environment configuration
- `migrations/script.py.mako` - Migration script template
- `migrations/versions/e08bd99be194_initial_migration_with_all_models.py` - Initial migration script

## Database Tables Created
The initial migration creates 12 application tables:
1. `users` - User authentication and roles
2. `emails` - Email records
3. `batches` - Upload batches
4. `jobs` - Background job tracking
5. `rejected_emails` - Rejected email records with reasons
6. `activity_logs` - Audit trail
7. `download_history` - Export tracking
8. `ignore_domains` - Domain filtering
9. `suppression_list` - Opt-out management
10. `domain_reputation` - Domain quality scores
11. `export_templates` - Export configuration
12. `scheduled_reports` - Report scheduling

Plus the `alembic_version` table for migration tracking.

## Testing
Verified the migrations work correctly:
- ✓ Migrations directory exists
- ✓ Initial migration script generated
- ✓ `flask db upgrade` runs successfully
- ✓ All 13 tables created correctly
- ✓ Migration is idempotent (can run multiple times safely)

## Docker Compose Workflow
The corrected workflow is now:

```bash
# 1. Start services
docker compose up -d --build

# 2. Run migrations (this now works!)
docker compose exec web flask db upgrade

# 3. Create admin user
docker compose exec web python create_admin.py

# 4. Access application
open http://localhost:5000
```

## Technical Details
- **Migration Tool**: Flask-Migrate 4.0.5 (based on Alembic)
- **Database Support**: PostgreSQL (production) and SQLite (development/testing)
- **Migration ID**: e08bd99be194
- **Migration Message**: "Initial migration with all models"

## No Breaking Changes
This fix is backward compatible and doesn't require any changes to:
- Application code
- Docker configuration
- Environment variables
- Existing documentation (README.md, SETUP.md)

The documentation was already correct; we just needed to create the migrations folder that it referenced.
