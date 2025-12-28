#!/usr/bin/env python
"""
Verification script for guest isolation feature implementation.
Run this to verify all components are properly installed.
"""

import sys

def verify_imports():
    """Verify all new models and tasks can be imported"""
    try:
        from app.models.email import GuestEmailItem
        from app.models.job import GuestDownloadHistory
        from app.jobs.tasks import export_guest_emails_task
        print("✓ All new models and tasks import successfully")
        return True
    except ImportError as e:
        print(f"✗ Import error: {e}")
        return False

def verify_app_creation():
    """Verify app can be created with new models"""
    try:
        from app import create_app, db
        app = create_app()
        with app.app_context():
            # Check if models are registered
            assert 'guest_email_items' in [t.name for t in db.metadata.tables.values()]
            assert 'guest_download_history' in [t.name for t in db.metadata.tables.values()]
        print("✓ App creates successfully with new models")
        return True
    except Exception as e:
        print(f"✗ App creation error: {e}")
        return False

def verify_migration_file():
    """Verify migration file exists"""
    import os
    migration_path = "migrations/versions/20251227_141019_add_guest_isolation_tables.py"
    if os.path.exists(migration_path):
        print(f"✓ Migration file exists: {migration_path}")
        return True
    else:
        print(f"✗ Migration file not found: {migration_path}")
        return False

def verify_templates():
    """Verify new templates exist"""
    import os
    templates = [
        "app/templates/email/batch_detail_guest.html",
        "app/templates/email/download_history_guest.html"
    ]
    all_exist = True
    for template in templates:
        if os.path.exists(template):
            print(f"✓ Template exists: {template}")
        else:
            print(f"✗ Template missing: {template}")
            all_exist = False
    return all_exist

def verify_tests():
    """Verify test file exists"""
    import os
    test_file = "tests/test_guest_isolation.py"
    if os.path.exists(test_file):
        print(f"✓ Test file exists: {test_file}")
        return True
    else:
        print(f"✗ Test file not found: {test_file}")
        return False

def verify_documentation():
    """Verify documentation files exist"""
    import os
    docs = [
        "GUEST_ISOLATION_IMPLEMENTATION.md",
        "GUEST_ISOLATION_GUIDE.md",
        "FEATURE_SUMMARY.md"
    ]
    all_exist = True
    for doc in docs:
        if os.path.exists(doc):
            print(f"✓ Documentation exists: {doc}")
        else:
            print(f"✗ Documentation missing: {doc}")
            all_exist = False
    return all_exist

def main():
    """Run all verification checks"""
    print("=" * 60)
    print("Guest Isolation Feature Implementation Verification")
    print("=" * 60)
    print()
    
    checks = [
        ("Imports", verify_imports),
        ("App Creation", verify_app_creation),
        ("Migration File", verify_migration_file),
        ("Templates", verify_templates),
        ("Tests", verify_tests),
        ("Documentation", verify_documentation)
    ]
    
    results = []
    for name, check_func in checks:
        print(f"\n{name}:")
        print("-" * 40)
        results.append(check_func())
    
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    
    if all(results):
        print("✓ ALL CHECKS PASSED")
        print("\nImplementation is complete and ready for:")
        print("  1. Database migration (flask db upgrade)")
        print("  2. Manual testing with guest user")
        print("  3. Deployment to staging/production")
        return 0
    else:
        print("✗ SOME CHECKS FAILED")
        print("\nPlease review the errors above and fix before deployment.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
