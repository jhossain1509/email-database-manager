import pytest
import os
import csv
import tempfile

# Set test database URL BEFORE importing app
os.environ['DATABASE_URL'] = 'sqlite:///:memory:'

from app import create_app, db
from app.models.user import User
from app.models.email import Email, Batch, GuestEmailItem
from app.models.job import GuestDownloadHistory
from app.jobs.tasks import import_emails_task, export_guest_emails_task

@pytest.fixture
def app():
    """Create application for testing"""
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['CELERY_BROKER_URL'] = 'memory://'
    app.config['CELERY_RESULT_BACKEND'] = 'cache+memory://'
    
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    """Create test client"""
    return app.test_client()

@pytest.fixture
def guest_user(app):
    """Create a guest user"""
    with app.app_context():
        user = User(username='testguest', email='guest@test.com', role='guest')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        return user

@pytest.fixture
def regular_user(app):
    """Create a regular user"""
    with app.app_context():
        user = User(username='testuser', email='user@test.com', role='user')
        user.set_password('password')
        db.session.add(user)
        db.session.commit()
        return user

class TestGuestEmailItemModel:
    """Test GuestEmailItem model"""
    
    def test_guest_item_creation(self, app, guest_user):
        """Test creating guest email items"""
        with app.app_context():
            batch = Batch(
                name='Test Batch',
                filename='test.csv',
                user_id=guest_user.id,
                status='processing'
            )
            db.session.add(batch)
            db.session.commit()
            
            # Create a guest item
            item = GuestEmailItem(
                batch_id=batch.id,
                user_id=guest_user.id,
                email_normalized='test@example.com',
                domain='example.com',
                result='inserted'
            )
            db.session.add(item)
            db.session.commit()
            
            # Verify
            assert item.id is not None
            assert item.email_normalized == 'test@example.com'
            assert item.result == 'inserted'
    
    def test_guest_item_unique_constraint(self, app, guest_user):
        """Test unique constraint on batch_id + email_normalized"""
        with app.app_context():
            batch = Batch(
                name='Test Batch',
                filename='test.csv',
                user_id=guest_user.id,
                status='processing'
            )
            db.session.add(batch)
            db.session.commit()
            
            # Create first item
            item1 = GuestEmailItem(
                batch_id=batch.id,
                user_id=guest_user.id,
                email_normalized='test@example.com',
                domain='example.com',
                result='inserted'
            )
            db.session.add(item1)
            db.session.commit()
            
            # Try to create duplicate in same batch - should raise error
            item2 = GuestEmailItem(
                batch_id=batch.id,
                user_id=guest_user.id,
                email_normalized='test@example.com',
                domain='example.com',
                result='duplicate'
            )
            db.session.add(item2)
            
            with pytest.raises(Exception):
                db.session.commit()

class TestGuestImportIsolation:
    """Test guest import creates GuestEmailItem records"""
    
    def test_guest_import_creates_items(self, app, guest_user):
        """Test that guest import creates GuestEmailItem records"""
        with app.app_context():
            # Create batch
            batch = Batch(
                name='Guest Test Batch',
                filename='test.csv',
                user_id=guest_user.id,
                status='processing'
            )
            db.session.add(batch)
            db.session.commit()
            
            # Create test CSV file
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
                writer = csv.writer(f)
                writer.writerow(['test1@example.com'])
                writer.writerow(['test2@example.com'])
                writer.writerow(['test3@example.com'])
                csv_path = f.name
            
            try:
                # Run import (synchronously for test)
                from unittest.mock import Mock
                mock_task = Mock()
                mock_task.request.id = 'test-job-id'
                
                result = import_emails_task(
                    mock_task,
                    batch.id,
                    csv_path,
                    guest_user.id,
                    consent_granted=True
                )
                
                # Verify GuestEmailItem records were created
                guest_items = GuestEmailItem.query.filter_by(
                    batch_id=batch.id,
                    user_id=guest_user.id
                ).all()
                
                assert len(guest_items) == 3, "Should create 3 guest items"
                assert all(item.result == 'inserted' for item in guest_items), "All should be inserted"
                
                # Verify Email records were created
                emails = Email.query.filter_by(batch_id=batch.id).all()
                assert len(emails) == 3, "Should create 3 email records"
                
            finally:
                os.unlink(csv_path)
    
    def test_guest_import_handles_duplicates(self, app, guest_user):
        """Test that guest import handles duplicates correctly"""
        with app.app_context():
            # Create existing email in main DB
            existing_batch = Batch(
                name='Existing Batch',
                filename='existing.csv',
                user_id=1,  # Different user
                status='uploaded'
            )
            db.session.add(existing_batch)
            db.session.commit()
            
            existing_email = Email(
                email='duplicate@example.com',
                domain='example.com',
                batch_id=existing_batch.id,
                uploaded_by=1,
                is_validated=False
            )
            db.session.add(existing_email)
            db.session.commit()
            
            # Create guest batch
            guest_batch = Batch(
                name='Guest Batch',
                filename='guest.csv',
                user_id=guest_user.id,
                status='processing'
            )
            db.session.add(guest_batch)
            db.session.commit()
            
            # Create test CSV with duplicate email
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
                writer = csv.writer(f)
                writer.writerow(['duplicate@example.com'])
                writer.writerow(['new@example.com'])
                csv_path = f.name
            
            try:
                # Run import
                from unittest.mock import Mock
                mock_task = Mock()
                mock_task.request.id = 'test-job-id-2'
                
                result = import_emails_task(
                    mock_task,
                    guest_batch.id,
                    csv_path,
                    guest_user.id,
                    consent_granted=True
                )
                
                # Verify GuestEmailItem records
                guest_items = GuestEmailItem.query.filter_by(
                    batch_id=guest_batch.id,
                    user_id=guest_user.id
                ).all()
                
                assert len(guest_items) == 2, "Should create 2 guest items"
                
                # Find the duplicate item
                dup_item = next((item for item in guest_items if item.email_normalized == 'duplicate@example.com'), None)
                assert dup_item is not None, "Should have duplicate item"
                assert dup_item.result == 'duplicate', "Should be marked as duplicate"
                assert dup_item.matched_email_id == existing_email.id, "Should link to existing email"
                
                # Find the new item
                new_item = next((item for item in guest_items if item.email_normalized == 'new@example.com'), None)
                assert new_item is not None, "Should have new item"
                assert new_item.result == 'inserted', "Should be marked as inserted"
                
                # Verify no duplicate was inserted into main emails table
                all_emails = Email.query.filter_by(email='duplicate@example.com').all()
                assert len(all_emails) == 1, "Should only have one copy in main DB"
                
            finally:
                os.unlink(csv_path)

class TestGuestExportIsolation:
    """Test guest export does not affect main DB"""
    
    def test_guest_export_creates_guest_history(self, app, guest_user):
        """Test that guest export creates GuestDownloadHistory"""
        with app.app_context():
            # Create batch with guest items
            batch = Batch(
                name='Export Test Batch',
                filename='export.csv',
                user_id=guest_user.id,
                status='uploaded'
            )
            db.session.add(batch)
            db.session.commit()
            
            # Create email and guest item
            email = Email(
                email='export@example.com',
                domain='example.com',
                batch_id=batch.id,
                uploaded_by=guest_user.id,
                is_validated=True,
                is_valid=True
            )
            db.session.add(email)
            db.session.flush()
            
            guest_item = GuestEmailItem(
                batch_id=batch.id,
                user_id=guest_user.id,
                email_normalized='export@example.com',
                domain='example.com',
                result='inserted',
                matched_email_id=email.id
            )
            db.session.add(guest_item)
            db.session.commit()
            
            # Run guest export
            from unittest.mock import Mock
            mock_task = Mock()
            mock_task.request.id = 'test-export-job'
            
            result = export_guest_emails_task(
                mock_task,
                guest_user.id,
                batch.id,
                export_type='all',
                export_format='csv'
            )
            
            # Verify GuestDownloadHistory was created
            guest_history = GuestDownloadHistory.query.filter_by(
                user_id=guest_user.id,
                batch_id=batch.id
            ).first()
            
            assert guest_history is not None, "Should create guest download history"
            assert guest_history.record_count == 1, "Should have 1 record"
            
            # Verify main Email record was NOT modified
            email = Email.query.get(email.id)
            assert email.downloaded == False, "Guest export should not set downloaded flag"
            assert email.download_count == 0, "Guest export should not increment download_count"
    
    def test_guest_export_includes_duplicates(self, app, guest_user):
        """Test that guest export includes duplicate items"""
        with app.app_context():
            # Create batch
            batch = Batch(
                name='Duplicate Export Test',
                filename='dup_export.csv',
                user_id=guest_user.id,
                status='uploaded'
            )
            db.session.add(batch)
            db.session.commit()
            
            # Create email (from previous user)
            email = Email(
                email='shared@example.com',
                domain='example.com',
                batch_id=1,  # Different batch
                uploaded_by=1,  # Different user
                is_validated=True,
                is_valid=True
            )
            db.session.add(email)
            db.session.flush()
            
            # Guest uploaded this as duplicate
            guest_item = GuestEmailItem(
                batch_id=batch.id,
                user_id=guest_user.id,
                email_normalized='shared@example.com',
                domain='example.com',
                result='duplicate',
                matched_email_id=email.id
            )
            db.session.add(guest_item)
            db.session.commit()
            
            # Run export
            from unittest.mock import Mock
            mock_task = Mock()
            mock_task.request.id = 'test-dup-export'
            
            result = export_guest_emails_task(
                mock_task,
                guest_user.id,
                batch.id,
                export_type='all',
                export_format='txt'
            )
            
            # Verify export includes the duplicate
            assert result['exported'] == 1, "Should export the duplicate item"
            
            # Verify guest download history
            guest_history = GuestDownloadHistory.query.filter_by(
                user_id=guest_user.id,
                batch_id=batch.id
            ).first()
            
            assert guest_history is not None
            assert guest_history.record_count == 1

class TestRegularUserFlowsUnaffected:
    """Test that regular user flows remain functional"""
    
    def test_regular_user_import_no_guest_items(self, app, regular_user):
        """Test that regular user import does not create guest items"""
        with app.app_context():
            batch = Batch(
                name='Regular User Batch',
                filename='regular.csv',
                user_id=regular_user.id,
                status='processing'
            )
            db.session.add(batch)
            db.session.commit()
            
            # Create test CSV
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.csv') as f:
                writer = csv.writer(f)
                writer.writerow(['regular@example.com'])
                csv_path = f.name
            
            try:
                # Run import
                from unittest.mock import Mock
                mock_task = Mock()
                mock_task.request.id = 'test-regular-job'
                
                result = import_emails_task(
                    mock_task,
                    batch.id,
                    csv_path,
                    regular_user.id,
                    consent_granted=True
                )
                
                # Verify NO GuestEmailItem records were created
                guest_items = GuestEmailItem.query.filter_by(
                    batch_id=batch.id
                ).all()
                
                assert len(guest_items) == 0, "Regular user should not create guest items"
                
                # Verify Email record was created
                emails = Email.query.filter_by(batch_id=batch.id).all()
                assert len(emails) == 1, "Should create email record"
                
            finally:
                os.unlink(csv_path)

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
