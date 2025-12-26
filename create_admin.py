#!/usr/bin/env python3
"""
Script to create an admin user and initialize the database
"""
import sys
from app import create_app, db
from app.models.user import User

def create_admin():
    app = create_app()
    
    with app.app_context():
        # Create tables
        print("Creating database tables...")
        db.create_all()
        print("✓ Database tables created")
        
        # Check if admin exists
        admin = User.query.filter_by(username='admin').first()
        
        if admin:
            print("⚠ Admin user already exists")
            response = input("Do you want to reset the admin password? (yes/no): ")
            if response.lower() == 'yes':
                password = input("Enter new admin password: ")
                admin.set_password(password)
                admin.role = 'super_admin'
                admin.is_active = True
                db.session.commit()
                print("✓ Admin password updated")
            return
        
        # Create admin user
        print("\nCreating admin user...")
        username = input("Admin username (default: admin): ").strip() or 'admin'
        email = input("Admin email (default: admin@example.com): ").strip() or 'admin@example.com'
        password = input("Admin password: ").strip()
        
        if not password:
            print("✗ Password is required")
            sys.exit(1)
        
        admin = User(
            username=username,
            email=email,
            role='super_admin',
            is_active=True
        )
        admin.set_password(password)
        
        db.session.add(admin)
        db.session.commit()
        
        print(f"✓ Admin user '{username}' created successfully with super_admin role")
        print(f"  Email: {email}")
        print(f"  Role: super_admin")

if __name__ == '__main__':
    create_admin()
