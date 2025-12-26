import pytest
import os
from app import create_app, db
from app.models.user import User
from app.utils.email_validator import check_us_only_cctld_policy, extract_domain

# Set test database URL before importing app
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

@pytest.fixture
def app():
    """Create application for testing"""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()

class TestUsCcTLDPolicy:
    """Test US-only ccTLD policy"""
    
    def test_generic_tlds_allowed(self, app):
        """Test that generic TLDs are allowed"""
        with app.app_context():
            test_cases = [
                'user@example.com',
                'user@example.net',
                'user@example.org',
                'user@example.info',
                'user@example.biz',
            ]
            
            for email in test_cases:
                allowed, reason = check_us_only_cctld_policy(email)
                assert allowed, f"{email} should be allowed (generic TLD)"
    
    def test_us_cctld_allowed(self, app):
        """Test that .us ccTLD is allowed"""
        with app.app_context():
            test_cases = [
                'user@example.us',
                'user@state.co.us',
            ]
            
            for email in test_cases:
                allowed, reason = check_us_only_cctld_policy(email)
                assert allowed, f"{email} should be allowed (.us ccTLD)"
    
    def test_non_us_cctld_rejected(self, app):
        """Test that non-US ccTLDs are rejected"""
        with app.app_context():
            test_cases = [
                'user@example.uk',
                'user@example.pk',
                'user@example.au',
                'user@example.ca',
                'user@example.in',
                'user@example.de',
                'user@example.fr',
            ]
            
            for email in test_cases:
                allowed, reason = check_us_only_cctld_policy(email)
                assert not allowed, f"{email} should be rejected (non-US ccTLD)"
                assert 'ccTLD' in reason, f"Reason should mention ccTLD for {email}"
    
    def test_multi_level_cctld_rejected(self, app):
        """Test that multi-level ccTLDs are rejected"""
        with app.app_context():
            test_cases = [
                'user@example.co.uk',
                'user@example.com.au',
                'user@example.co.nz',
            ]
            
            for email in test_cases:
                allowed, reason = check_us_only_cctld_policy(email)
                assert not allowed, f"{email} should be rejected (multi-level ccTLD)"
    
    def test_policy_suffixes_blocked(self, app):
        """Test that policy suffixes (.gov, .edu) are blocked"""
        with app.app_context():
            test_cases = [
                'user@example.gov',
                'user@example.edu',
            ]
            
            for email in test_cases:
                allowed, reason = check_us_only_cctld_policy(email)
                assert not allowed, f"{email} should be rejected (policy suffix)"
                assert 'Policy suffix' in reason, f"Reason should mention policy suffix for {email}"
    
    def test_extract_domain(self, app):
        """Test domain extraction"""
        with app.app_context():
            assert extract_domain('user@example.com') == 'example.com'
            assert extract_domain('user@sub.example.com') == 'sub.example.com'
            assert extract_domain('invalid') is None

class TestRBACRoles:
    """Test RBAC role enforcement"""
    
    def test_guest_role_creation_on_registration(self, app, client):
        """Test that self-registration creates guest role"""
        with app.app_context():
            response = client.post('/auth/register', data={
                'username': 'testguest',
                'email': 'guest@test.com',
                'password': 'password123',
                'confirm_password': 'password123'
            }, follow_redirects=True)
            
            user = User.query.filter_by(username='testguest').first()
            assert user is not None
            assert user.role == 'guest', "Self-registered users should have guest role"
    
    def test_guest_is_guest_method(self, app):
        """Test is_guest() method"""
        with app.app_context():
            guest = User(username='guest', email='guest@test.com', role='guest')
            guest.set_password('pass')
            db.session.add(guest)
            
            user = User(username='user', email='user@test.com', role='user')
            user.set_password('pass')
            db.session.add(user)
            
            db.session.commit()
            
            assert guest.is_guest() == True
            assert user.is_guest() == False
    
    def test_guest_cannot_access_main_db(self, app):
        """Test guest users cannot access main DB"""
        with app.app_context():
            guest = User(username='guest', email='guest@test.com', role='guest')
            guest.set_password('pass')
            db.session.add(guest)
            
            user = User(username='user', email='user@test.com', role='user')
            user.set_password('pass')
            db.session.add(user)
            
            db.session.commit()
            
            assert guest.can_access_main_db() == False, "Guest should not access main DB"
            assert user.can_access_main_db() == True, "User should access main DB"
    
    def test_admin_role_check(self, app):
        """Test admin role identification"""
        with app.app_context():
            admin = User(username='admin', email='admin@test.com', role='admin')
            admin.set_password('pass')
            db.session.add(admin)
            
            super_admin = User(username='superadmin', email='sa@test.com', role='super_admin')
            super_admin.set_password('pass')
            db.session.add(super_admin)
            
            user = User(username='user', email='user@test.com', role='user')
            user.set_password('pass')
            db.session.add(user)
            
            db.session.commit()
            
            assert admin.is_admin() == True
            assert super_admin.is_admin() == True
            assert user.is_admin() == False

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
