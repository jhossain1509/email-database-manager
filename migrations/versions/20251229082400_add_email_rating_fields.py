"""add email rating fields

Revision ID: 20251229082400
Revises: 20251228115507
Create Date: 2025-12-29 08:24:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '20251229082400'
down_revision = '20251228115507'
branch_labels = None
depends_on = None


def upgrade():
    # Add rating column to emails table
    op.add_column('emails', sa.Column('rating', sa.String(1), nullable=True))
    op.create_index('ix_emails_rating', 'emails', ['rating'])
    
    # Add rating column to domain_reputation table
    op.add_column('domain_reputation', sa.Column('rating', sa.String(1), nullable=True))
    op.create_index('ix_domain_reputation_rating', 'domain_reputation', ['rating'])
    
    # Update existing ratings based on quality_score and reputation_score
    # For emails: A >= 80, B >= 60, C >= 40, D < 40
    op.execute("""
        UPDATE emails 
        SET rating = CASE 
            WHEN quality_score >= 80 THEN 'A'
            WHEN quality_score >= 60 THEN 'B'
            WHEN quality_score >= 40 THEN 'C'
            WHEN quality_score < 40 THEN 'D'
            ELSE NULL
        END
        WHERE quality_score IS NOT NULL
    """)
    
    # For domain_reputation: A >= 80, B >= 60, C >= 40, D < 40
    op.execute("""
        UPDATE domain_reputation 
        SET rating = CASE 
            WHEN reputation_score >= 80 THEN 'A'
            WHEN reputation_score >= 60 THEN 'B'
            WHEN reputation_score >= 40 THEN 'C'
            WHEN reputation_score < 40 THEN 'D'
            ELSE NULL
        END
        WHERE reputation_score IS NOT NULL
    """)


def downgrade():
    # Remove indexes
    op.drop_index('ix_domain_reputation_rating', 'domain_reputation')
    op.drop_index('ix_emails_rating', 'emails')
    
    # Remove rating columns
    op.drop_column('domain_reputation', 'rating')
    op.drop_column('emails', 'rating')
