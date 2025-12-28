"""
ConHub Data Connector - Legacy Routes

Backward compatibility routes matching the existing Rust API structure.
"""

from typing import Any, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequestError, NotFoundError
from app.schemas import ConnectorType
from db import get_db
from db.models import Connector as ConnectorModel
from db.models import SyncJob as SyncJobModel

logger = structlog.get_logger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models for Legacy API
# =============================================================================

class LegacySyncRequest(BaseModel):
    """Legacy sync request matching Rust API."""
    repository: str
    branch: Optional[str] = "main"
    include_languages: Optional[list[str]] = None
    file_extensions: Optional[list[str]] = None
    exclude_paths: Optional[list[str]] = None
    max_file_size_mb: Optional[float] = None


class LegacyDataSourceCreate(BaseModel):
    """Legacy data source creation matching Rust API."""
    name: str
    connector_type: str
    config: dict[str, Any] = {}


class LegacyDataSourceResponse(BaseModel):
    """Legacy data source response."""
    id: UUID
    user_id: Optional[UUID] = None
    name: str
    connector_type: str
    config: dict[str, Any]
    status: str
    sync_status: str
    documents_count: int = 0
    last_synced_at: Optional[str] = None
    created_at: str


# =============================================================================
# GitHub Endpoints (matching Rust /api/github/*)
# =============================================================================

@router.post("/github/validate-access")
async def validate_github_access(
    body: dict[str, Any],
) -> dict[str, Any]:
    """Validate GitHub access (legacy endpoint)."""
    # TODO: Implement actual validation
    return {"valid": True}


@router.post("/github/sync-repository")
async def sync_repository_legacy(
    body: LegacySyncRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Sync a GitHub repository (legacy endpoint)."""
    logger.info("Legacy sync request", repository=body.repository, branch=body.branch)
    
    # Create a temporary connector and sync job
    connector = ConnectorModel(
        tenant_id="legacy",
        type="github",
        name=f"GitHub: {body.repository}",
        config_json={
            "repository": body.repository,
            "branch": body.branch,
            "include_languages": body.include_languages or body.file_extensions,
            "exclude_paths": body.exclude_paths,
            "max_file_size_mb": body.max_file_size_mb,
        },
        status="active",
    )
    db.add(connector)
    await db.flush()
    
    sync_job = SyncJobModel(
        connector_id=connector.id,
        tenant_id="legacy",
        type="full",
        status="pending",
    )
    db.add(sync_job)
    await db.flush()
    
    return {
        "job_id": str(sync_job.id),
        "status": "scheduled",
        "message": f"Sync scheduled for {body.repository}",
    }


@router.post("/github/branches")
async def get_branches_legacy(
    body: dict[str, Any],
) -> list[str]:
    """Get branches for a repository (legacy endpoint)."""
    # TODO: Implement via GitHub API
    return ["main", "develop"]


@router.post("/github/languages")
async def get_languages_legacy(
    body: dict[str, Any],
) -> dict[str, int]:
    """Get language breakdown for a repository (legacy endpoint)."""
    # TODO: Implement via GitHub API
    return {"Python": 60, "TypeScript": 30, "Rust": 10}


@router.post("/github/sync")
async def sync_oauth(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Sync using OAuth (legacy endpoint)."""
    return {"status": "scheduled", "message": "Sync initiated"}


# =============================================================================
# Data Sources Endpoints (matching Rust /api/data/* and /api/data-sources/*)
# =============================================================================

@router.post("/data/sources", response_model=LegacyDataSourceResponse)
async def create_source(
    body: LegacyDataSourceCreate,
    db: AsyncSession = Depends(get_db),
) -> LegacyDataSourceResponse:
    """Create a data source (legacy endpoint)."""
    connector = ConnectorModel(
        tenant_id="legacy",
        type=body.connector_type,
        name=body.name,
        config_json=body.config,
        status="active",
    )
    db.add(connector)
    await db.flush()
    await db.refresh(connector)
    
    return LegacyDataSourceResponse(
        id=connector.id,
        name=connector.name,
        connector_type=connector.type,
        config=connector.config_json,
        status=connector.status,
        sync_status="pending",
        created_at=connector.created_at.isoformat(),
    )


@router.get("/data/sources")
async def list_sources(
    db: AsyncSession = Depends(get_db),
) -> list[LegacyDataSourceResponse]:
    """List data sources (legacy endpoint)."""
    result = await db.execute(
        select(ConnectorModel).order_by(ConnectorModel.created_at.desc())
    )
    connectors = result.scalars().all()
    
    return [
        LegacyDataSourceResponse(
            id=c.id,
            name=c.name,
            connector_type=c.type,
            config=c.config_json,
            status=c.status,
            sync_status="pending",
            last_synced_at=c.last_sync_time.isoformat() if c.last_sync_time else None,
            created_at=c.created_at.isoformat(),
        )
        for c in connectors
    ]


@router.post("/data/sources/{source_id}/sync")
async def sync_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Trigger sync for a data source (legacy endpoint)."""
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == source_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Source {source_id} not found")
    
    sync_job = SyncJobModel(
        connector_id=source_id,
        tenant_id=connector.tenant_id,
        type="full",
        status="pending",
    )
    db.add(sync_job)
    await db.flush()
    
    return {"job_id": str(sync_job.id), "status": "scheduled"}


@router.post("/data/local/sync")
async def sync_local(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Sync local files (legacy endpoint)."""
    path = body.get("path")
    if not path:
        raise BadRequestError("Missing path in request body")
    
    connector = ConnectorModel(
        tenant_id="legacy",
        type="local_file",
        name=f"Local: {path}",
        config_json={"path": path},
        status="active",
    )
    db.add(connector)
    await db.flush()
    
    sync_job = SyncJobModel(
        connector_id=connector.id,
        tenant_id="legacy",
        type="full",
        status="pending",
    )
    db.add(sync_job)
    await db.flush()
    
    return {"job_id": str(sync_job.id), "status": "scheduled"}


# Alternative data-sources prefix
@router.get("/data-sources")
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
) -> list[LegacyDataSourceResponse]:
    """List data sources (alternative endpoint)."""
    return await list_sources(db)


@router.post("/data-sources/connect")
async def connect_source(
    body: LegacyDataSourceCreate,
    db: AsyncSession = Depends(get_db),
) -> LegacyDataSourceResponse:
    """Connect a data source (alternative endpoint)."""
    return await create_source(body, db)


@router.get("/data-sources/{source_id}")
async def get_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> LegacyDataSourceResponse:
    """Get data source details (alternative endpoint)."""
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == source_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Source {source_id} not found")
    
    return LegacyDataSourceResponse(
        id=connector.id,
        name=connector.name,
        connector_type=connector.type,
        config=connector.config_json,
        status=connector.status,
        sync_status="pending",
        last_synced_at=connector.last_sync_time.isoformat() if connector.last_sync_time else None,
        created_at=connector.created_at.isoformat(),
    )


@router.delete("/data-sources/{source_id}", status_code=204)
async def delete_source(
    source_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a data source (alternative endpoint)."""
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == source_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Source {source_id} not found")
    
    await db.delete(connector)
