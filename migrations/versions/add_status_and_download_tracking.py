"""Add status and download tracking fields

Revision ID: f1a2b3c4d5e6
Revises: e08bd99be194
Create Date: 2025-12-27 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'e08bd99be194'
branch_labels = None
depends_on = None


def upgrade():
    # ### Add new columns to emails table ###
    
    # Add status column with default 'unverified'
    op.add_column('emails', sa.Column('status', sa.String(length=20), nullable=True))
    
    # Set status based on existing is_validated and is_valid fields
    op.execute("""
        UPDATE emails 
        SET status = CASE 
            WHEN is_validated = true AND is_valid = true THEN 'verified'
            WHEN is_validated = true AND is_valid = false THEN 'rejected'
            WHEN suppressed = true THEN 'suppressed'
            ELSE 'unverified'
        END
    """)
    
    # Make status NOT NULL after setting values
    op.alter_column('emails', 'status', nullable=False)
    
    # Add new tracking columns
    op.add_column('emails', sa.Column('downloaded_at', sa.DateTime(), nullable=True))
    op.add_column('emails', sa.Column('created_at', sa.DateTime(), nullable=True))
    op.add_column('emails', sa.Column('verified_at', sa.DateTime(), nullable=True))
    op.add_column('emails', sa.Column('rejected_reason', sa.String(length=255), nullable=True))
    
    # Set created_at to uploaded_at for existing records
    op.execute("UPDATE emails SET created_at = uploaded_at WHERE created_at IS NULL")
    
    # Make created_at NOT NULL after setting values
    op.alter_column('emails', 'created_at', nullable=False)
    
    # Set verified_at for already verified emails
    op.execute("UPDATE emails SET verified_at = uploaded_at WHERE status = 'verified' AND verified_at IS NULL")
    
    # Add indexes
    op.create_index('ix_emails_status', 'emails', ['status'], unique=False)
    op.create_index('ix_emails_downloaded_at', 'emails', ['downloaded_at'], unique=False)
    op.create_index('idx_status_downloaded', 'emails', ['status', 'downloaded_at'], unique=False)
    
    # Make email column unique (global unique constraint)
    # First, remove duplicates if any exist, keeping the most recent one
    op.execute("""
        DELETE FROM emails
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM emails
            GROUP BY LOWER(email)
        )
    """)
    
    # Create unique index on lowercase email
    op.create_index('idx_emails_email_unique', 'emails', [sa.text('LOWER(email)')], unique=True)
    
    # ### Add new columns to batches table ###
    op.add_column('batches', sa.Column('total_rows', sa.Integer(), nullable=True))
    op.add_column('batches', sa.Column('imported_count', sa.Integer(), nullable=True))
    op.add_column('batches', sa.Column('rejected_file_path', sa.String(length=500), nullable=True))
    
    # Migrate data from old columns to new columns
    op.execute("UPDATE batches SET total_rows = total_count WHERE total_rows IS NULL")
    op.execute("UPDATE batches SET imported_count = total_count WHERE imported_count IS NULL")
    
    # Make new columns NOT NULL after setting values
    op.execute("UPDATE batches SET total_rows = 0 WHERE total_rows IS NULL")
    op.execute("UPDATE batches SET imported_count = 0 WHERE imported_count IS NULL")
    op.alter_column('batches', 'total_rows', nullable=False)
    op.alter_column('batches', 'imported_count', nullable=False)


def downgrade():
    # ### Remove added indexes ###
    op.drop_index('idx_emails_email_unique', table_name='emails')
    op.drop_index('idx_status_downloaded', table_name='emails')
    op.drop_index('ix_emails_downloaded_at', table_name='emails')
    op.drop_index('ix_emails_status', table_name='emails')
    
    # ### Remove columns from emails table ###
    op.drop_column('emails', 'rejected_reason')
    op.drop_column('emails', 'verified_at')
    op.drop_column('emails', 'created_at')
    op.drop_column('emails', 'downloaded_at')
    op.drop_column('emails', 'status')
    
    # ### Remove columns from batches table ###
    op.drop_column('batches', 'rejected_file_path')
    op.drop_column('batches', 'imported_count')
    op.drop_column('batches', 'total_rows')
