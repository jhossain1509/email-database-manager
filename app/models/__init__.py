# Import all models for migrations
from app.models.user import User
from app.models.email import Email, Batch, RejectedEmail, IgnoreDomain, SuppressionList
from app.models.job import (
    Job, DownloadHistory, ActivityLog, DomainReputation,
    ExportTemplate, ScheduledReport
)

__all__ = [
    'User',
    'Email', 'Batch', 'RejectedEmail', 'IgnoreDomain', 'SuppressionList',
    'Job', 'DownloadHistory', 'ActivityLog', 'DomainReputation',
    'ExportTemplate', 'ScheduledReport'
]
