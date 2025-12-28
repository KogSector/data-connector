"""
ConHub Data Connector - Sync Tasks

Celery tasks for background sync operations.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from celery import shared_task
from sqlalchemy import delete, select

from db import get_session
from db.models import SyncJob as SyncJobModel
from services.sync_service import get_sync_service

logger = structlog.get_logger(__name__)


def run_async(coro):
    """Run an async coroutine in a sync context."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_kwargs={"max_retries": 3},
)
def sync_connector_task(
    self,
    job_id: str,
    connector_id: str,
    access_token: Optional[str] = None,
) -> dict:
    """
    Background task to sync a connector.
    
    Args:
        job_id: UUID of the sync job.
        connector_id: UUID of the connector to sync.
        access_token: Optional OAuth access token.
        
    Returns:
        Dict with sync results.
    """
    logger.info(
        "Starting sync task",
        job_id=job_id,
        connector_id=connector_id,
        task_id=self.request.id,
    )
    
    try:
        from uuid import UUID
        
        sync_service = get_sync_service()
        run_async(
            sync_service.execute_sync(
                job_id=UUID(job_id),
                connector_id=UUID(connector_id),
                access_token=access_token,
            )
        )
        
        return {
            "status": "completed",
            "job_id": job_id,
            "connector_id": connector_id,
        }
        
    except Exception as e:
        logger.exception(
            "Sync task failed",
            job_id=job_id,
            connector_id=connector_id,
            error=str(e),
        )
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def process_webhook_task(
    self,
    webhook_event_id: str,
    connector_id: str,
) -> dict:
    """
    Background task to process a webhook event.
    
    Args:
        webhook_event_id: UUID of the webhook event.
        connector_id: UUID of the connector.
        
    Returns:
        Dict with processing results.
    """
    logger.info(
        "Processing webhook event",
        webhook_event_id=webhook_event_id,
        connector_id=connector_id,
        task_id=self.request.id,
    )
    
    # TODO: Implement webhook processing
    # 1. Load webhook event from DB
    # 2. Parse event and determine changes
    # 3. Create incremental sync job
    # 4. Execute delta sync
    
    return {
        "status": "processed",
        "webhook_event_id": webhook_event_id,
        "connector_id": connector_id,
    }


@shared_task
def cleanup_old_jobs() -> dict:
    """
    Periodic task to clean up old sync jobs and webhook events.
    
    Removes completed jobs older than 7 days.
    """
    logger.info("Running cleanup task")
    
    async def do_cleanup():
        async with get_session() as db:
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            
            # Delete old completed sync jobs
            result = await db.execute(
                delete(SyncJobModel)
                .where(SyncJobModel.status.in_(["completed", "failed"]))
                .where(SyncJobModel.end_time < cutoff)
            )
            deleted_count = result.rowcount
            
            await db.commit()
            return deleted_count
    
    deleted = run_async(do_cleanup())
    
    logger.info("Cleanup completed", deleted_jobs=deleted)
    
    return {
        "status": "completed",
        "deleted_jobs": deleted,
    }
