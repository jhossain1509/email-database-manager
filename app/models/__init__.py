# Import all models for migrations
from app.models.user import User
from app.models.email import Email, Batch, RejectedEmail, IgnoreDomain, SuppressionList, GuestEmailItem
from app.models.job import (
    Job, DownloadHistory, GuestDownloadHistory, ActivityLog, DomainReputation,
    ExportTemplate, ScheduledReport
)

__all__ = [
    'User',
    'Email', 'Batch', 'RejectedEmail', 'IgnoreDomain', 'SuppressionList', 'GuestEmailItem',
    'Job', 'DownloadHistory', 'GuestDownloadHistory', 'ActivityLog', 'DomainReputation',
    'ExportTemplate', 'ScheduledReport'
]
