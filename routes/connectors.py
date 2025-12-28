"""
ConHub Data Connector - Connector CRUD Routes

Connector management endpoints matching OpenAPI spec.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundError
from app.schemas import Connector, ConnectorCreate, ConnectorStatus, ConnectorType
from db import get_db
from db.models import Connector as ConnectorModel

router = APIRouter()


@router.post("", response_model=Connector, status_code=201)
async def create_connector(
    body: ConnectorCreate,
    db: AsyncSession = Depends(get_db),
) -> Connector:
    """
    Create a new connector.
    
    Creates a connector configuration for syncing data from an external source.
    """
    connector = ConnectorModel(
        tenant_id=body.tenant_id,
        type=body.type.value,
        name=body.name,
        config_json=body.config or {},
        metadata_json=body.metadata,
        status="active",
    )
    
    db.add(connector)
    await db.flush()
    await db.refresh(connector)
    
    return Connector(
        id=connector.id,
        tenant_id=connector.tenant_id,
        type=ConnectorType(connector.type),
        name=connector.name,
        config=connector.config_json,
        metadata=connector.metadata_json,
        status=ConnectorStatus(connector.status),
        created_at=connector.created_at,
        last_sync_cursor=connector.last_sync_cursor,
        last_sync_time=connector.last_sync_time,
    )


@router.get("", response_model=list[Connector])
async def list_connectors(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    db: AsyncSession = Depends(get_db),
) -> list[Connector]:
    """
    List all connectors.
    
    Optionally filter by tenant_id.
    """
    query = select(ConnectorModel)
    
    if tenant_id:
        query = query.where(ConnectorModel.tenant_id == tenant_id)
    
    query = query.order_by(ConnectorModel.created_at.desc())
    
    result = await db.execute(query)
    connectors = result.scalars().all()
    
    return [
        Connector(
            id=c.id,
            tenant_id=c.tenant_id,
            type=ConnectorType(c.type),
            name=c.name,
            config=c.config_json,
            metadata=c.metadata_json,
            status=ConnectorStatus(c.status),
            created_at=c.created_at,
            last_sync_cursor=c.last_sync_cursor,
            last_sync_time=c.last_sync_time,
        )
        for c in connectors
    ]


@router.get("/{connector_id}", response_model=Connector)
async def get_connector(
    connector_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> Connector:
    """
    Get connector details by ID.
    """
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Connector {connector_id} not found")
    
    return Connector(
        id=connector.id,
        tenant_id=connector.tenant_id,
        type=ConnectorType(connector.type),
        name=connector.name,
        config=connector.config_json,
        metadata=connector.metadata_json,
        status=ConnectorStatus(connector.status),
        created_at=connector.created_at,
        last_sync_cursor=connector.last_sync_cursor,
        last_sync_time=connector.last_sync_time,
    )


@router.delete("/{connector_id}", status_code=204)
async def delete_connector(
    connector_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Delete a connector.
    
    This will also delete all associated sync jobs, blobs, and webhook events.
    """
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Connector {connector_id} not found")
    
    await db.delete(connector)


@router.post("/{connector_id}/test")
async def test_connector(
    connector_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Test connector connection.
    
    Attempts to connect to the provider and validate access.
    """
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Connector {connector_id} not found")
    
    # TODO: Implement actual connection test via connector adapter
    # For now, return success placeholder
    return {
        "ok": True,
        "details": {
            "connector_type": connector.type,
            "message": "Connection test not yet implemented",
        },
    }
