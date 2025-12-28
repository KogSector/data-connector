"""
ConHub Data Connector - Sync Routes

Sync trigger and status endpoints matching OpenAPI spec.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError
from app.schemas import SyncJobResponse, SyncRequest, SyncStatusResponse
from db import get_db
from db.models import Connector as ConnectorModel
from db.models import SyncJob as SyncJobModel

router = APIRouter()


@router.post("/{connector_id}/sync", response_model=SyncJobResponse, status_code=202)
async def trigger_sync(
    connector_id: UUID,
    body: SyncRequest,
    db: AsyncSession = Depends(get_db),
) -> SyncJobResponse:
    """
    Trigger a sync for a connector.
    
    Schedules a background sync job and returns immediately.
    """
    # Verify connector exists
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Connector {connector_id} not found")
    
    # Create sync job record
    sync_job = SyncJobModel(
        connector_id=connector_id,
        tenant_id=connector.tenant_id,
        type=body.type.value,
        status="pending",
    )
    
    db.add(sync_job)
    await db.flush()
    await db.refresh(sync_job)
    
    # TODO: Enqueue Celery task for background sync
    # from workers.sync_tasks import sync_connector_task
    # sync_connector_task.delay(str(sync_job.id), str(connector_id))
    
    return SyncJobResponse(
        job_id=sync_job.id,
        status="scheduled",
    )


@router.get("/{connector_id}/status", response_model=SyncStatusResponse)
async def get_sync_status(
    connector_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SyncStatusResponse:
    """
    Get sync status for a connector.
    
    Returns the latest sync information including last sync time and stats.
    """
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Connector {connector_id} not found")
    
    # Get latest sync job stats
    job_result = await db.execute(
        select(SyncJobModel)
        .where(SyncJobModel.connector_id == connector_id)
        .order_by(SyncJobModel.start_time.desc())
        .limit(1)
    )
    latest_job = job_result.scalar_one_or_none()
    
    return SyncStatusResponse(
        connector_id=connector_id,
        last_sync_time=connector.last_sync_time,
        last_sync_status=latest_job.status if latest_job else None,
        stats=latest_job.stats_json if latest_job else None,
    )
