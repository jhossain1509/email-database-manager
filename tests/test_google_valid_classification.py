import pytest
import sys
import os

# Set test database URL BEFORE importing anything else
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

# Now we can safely import
from app.utils.email_validator import (
    is_google_email, 
    classify_domain,
    extract_domain
)

class TestGoogleValidClassificationUnit:
    """Unit tests for Google_Valid email classification utilities"""
    
    def test_is_google_email_gmail(self):
        """Test that Gmail emails are identified as Google emails"""
        test_cases = [
            'user@gmail.com',
            'test.user@gmail.com',
            'user123@gmail.com',
        ]
        
        for email in test_cases:
            assert is_google_email(email), f"{email} should be identified as Google email"
    
    def test_is_google_email_googlemail(self):
        """Test that Googlemail emails are identified as Google emails"""
        test_cases = [
            'user@googlemail.com',
            'test.user@googlemail.com',
        ]
        
        for email in test_cases:
            assert is_google_email(email), f"{email} should be identified as Google email"
    
    def test_is_not_google_email(self):
        """Test that non-Google emails are not identified as Google emails"""
        test_cases = [
            'user@yahoo.com',
            'user@outlook.com',
            'user@hotmail.com',
            'user@example.com',
        ]
        
        for email in test_cases:
            assert not is_google_email(email), f"{email} should NOT be identified as Google email"
    
    def test_extract_domain_from_gmail(self):
        """Test domain extraction from Gmail addresses"""
        assert extract_domain('user@gmail.com') == 'gmail.com'
        assert extract_domain('test.user@gmail.com') == 'gmail.com'
        assert extract_domain('user+tag@gmail.com') == 'gmail.com'
    
    def test_extract_domain_from_various_emails(self):
        """Test domain extraction from various email addresses"""
        assert extract_domain('user@yahoo.com') == 'yahoo.com'
        assert extract_domain('user@outlook.com') == 'outlook.com'
        assert extract_domain('invalid') is None

# Integration tests with app context
@pytest.fixture
def app():
    """Create application for testing"""
    # Ensure DATABASE_URL is set before import
    os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
    
    from app import create_app, db
    
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

class TestGoogleValidClassificationIntegration:
    """Integration tests for Google_Valid email classification with app context"""
    
    def test_classify_domain_with_google_valid_when_valid(self, app):
        """Test that valid Gmail emails are classified as Google_Valid"""
        from app.utils.email_validator import classify_domain_with_google_valid
        
        with app.app_context():
            # Gmail domain when valid
            assert classify_domain_with_google_valid('gmail.com', is_valid=True) == 'Google_Valid'
            
            # Googlemail domain when valid
            assert classify_domain_with_google_valid('googlemail.com', is_valid=True) == 'Google_Valid'
    
    def test_classify_domain_with_google_valid_when_invalid(self, app):
        """Test that invalid Gmail emails are not classified as Google_Valid"""
        from app.utils.email_validator import classify_domain_with_google_valid
        
        with app.app_context():
            # Gmail domain when invalid should use standard classification
            result = classify_domain_with_google_valid('gmail.com', is_valid=False)
            assert result == 'gmail.com', f"Invalid Gmail should be classified as 'gmail.com', got {result}"
    
    def test_classify_domain_with_google_valid_other_domains(self, app):
        """Test that non-Google domains use standard classification"""
        from app.utils.email_validator import classify_domain_with_google_valid
        
        with app.app_context():
            # Yahoo when valid
            assert classify_domain_with_google_valid('yahoo.com', is_valid=True) == 'yahoo.com'
            
            # Random domain when valid
            assert classify_domain_with_google_valid('example.com', is_valid=True) == 'mixed'
    
    def test_google_valid_integration(self, app):
        """Test the full integration of Google_Valid classification"""
        from app import db
        from app.models.email import Email, Batch
        from app.models.user import User
        from app.utils.email_validator import classify_domain_with_google_valid
        
        with app.app_context():
            # Create a test user
            user = User(username='testuser', email='test@gmail.com', role='user')
            user.set_password('password')
            db.session.add(user)
            db.session.flush()
            
            # Create a test batch
            batch = Batch(
                name='Test Batch',
                filename='test.csv',
                user_id=user.id,
                status='uploaded'
            )
            db.session.add(batch)
            db.session.flush()
            
            # Create test emails
            gmail_email = Email(
                email='user@gmail.com',
                domain='gmail.com',
                domain_category='gmail.com',  # Initial category
                batch_id=batch.id,
                uploaded_by=user.id,
                is_validated=False
            )
            
            yahoo_email = Email(
                email='user@yahoo.com',
                domain='yahoo.com',
                domain_category='yahoo.com',
                batch_id=batch.id,
                uploaded_by=user.id,
                is_validated=False
            )
            
            db.session.add_all([gmail_email, yahoo_email])
            db.session.commit()
            
            # Simulate validation - update Gmail email with Google_Valid category
            gmail_email.is_validated = True
            gmail_email.is_valid = True
            gmail_email.domain_category = classify_domain_with_google_valid(
                gmail_email.domain, 
                is_valid=True
            )
            
            # Validate Yahoo email normally
            yahoo_email.is_validated = True
            yahoo_email.is_valid = True
            yahoo_email.domain_category = classify_domain_with_google_valid(
                yahoo_email.domain, 
                is_valid=True
            )
            
            db.session.commit()
            
            # Verify the classifications
            assert gmail_email.domain_category == 'Google_Valid', \
                f"Gmail should be classified as Google_Valid, got {gmail_email.domain_category}"
            assert yahoo_email.domain_category == 'yahoo.com', \
                f"Yahoo should keep its domain category, got {yahoo_email.domain_category}"
            
            # Test querying by Google_Valid category
            google_valid_emails = Email.query.filter_by(domain_category='Google_Valid').all()
            assert len(google_valid_emails) == 1
            assert google_valid_emails[0].email == 'user@gmail.com'

if __name__ == '__main__':
    pytest.main([__file__, '-v'])

