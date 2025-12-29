"""add validation_method field

Revision ID: 20251229160000
Revises: 20251229082400
Create Date: 2025-12-29 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251229160000'
down_revision = '20251229082400'
branch_labels = None
depends_on = None


def upgrade():
    # Add validation_method column to emails table
    op.add_column('emails', sa.Column('validation_method', sa.String(20), nullable=True))
    op.create_index('ix_emails_validation_method', 'emails', ['validation_method'])
    
    # Set default validation_method for existing validated emails
    op.execute("""
        UPDATE emails 
        SET validation_method = 'standard'
        WHERE is_validated = TRUE AND validation_method IS NULL
    """)


def downgrade():
    # Remove index and column
    op.drop_index('ix_emails_validation_method', 'emails')
    op.drop_column('emails', 'validation_method')
