from app import celery_app
from app.jobs.tasks import *

# Celery worker entry point
if __name__ == '__main__':
    celery_app.start()
