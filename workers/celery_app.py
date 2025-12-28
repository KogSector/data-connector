"""
ConHub Data Connector - Celery Application

Celery configuration with Redis broker.
"""

from celery import Celery

from app.config import settings

# Create Celery app
celery_app = Celery(
    "data_connector",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["workers.sync_tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    
    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=3600,  # 1 hour max per task
    task_soft_time_limit=3300,  # Soft limit at 55 minutes
    
    # Worker settings
    worker_prefetch_multiplier=1,  # One task at a time per worker
    worker_concurrency=4,
    
    # Result settings
    result_expires=3600,  # Results expire after 1 hour
    
    # Retry settings
    task_default_retry_delay=60,  # 1 minute between retries
    task_max_retries=3,
    
    # Beat scheduler (for periodic tasks)
    beat_schedule={
        "cleanup-old-jobs": {
            "task": "workers.sync_tasks.cleanup_old_jobs",
            "schedule": 3600.0,  # Every hour
        },
    },
)


def get_celery_app() -> Celery:
    """Get the Celery application instance."""
    return celery_app
