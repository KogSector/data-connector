"""
ConHub Data Connector - OAuth Routes

OAuth flow endpoints for connector authorization.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import BadRequestError, NotFoundError
from app.schemas import Connector, ConnectorStatus, ConnectorType
from db import get_db
from db.models import Connector as ConnectorModel

router = APIRouter()


@router.get("/{connector_id}/oauth/start")
async def oauth_start(
    connector_id: UUID,
    redirect_url: str = Query(None, description="URL to redirect after OAuth"),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """
    Initiate OAuth flow for a connector.
    
    Redirects the user to the provider's OAuth authorization page.
    """
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Connector {connector_id} not found")
    
    connector_type = ConnectorType(connector.type)
    
    # Build OAuth URL based on connector type
    # TODO: Implement actual OAuth URLs for each provider
    oauth_urls = {
        ConnectorType.GITHUB: "https://github.com/login/oauth/authorize",
        ConnectorType.GITLAB: "https://gitlab.com/oauth/authorize",
        ConnectorType.GOOGLE_DRIVE: "https://accounts.google.com/o/oauth2/v2/auth",
        ConnectorType.DROPBOX: "https://www.dropbox.com/oauth2/authorize",
        ConnectorType.ONEDRIVE: "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        ConnectorType.SLACK: "https://slack.com/oauth/v2/authorize",
        ConnectorType.NOTION: "https://api.notion.com/v1/oauth/authorize",
    }
    
    if connector_type not in oauth_urls:
        raise BadRequestError(f"OAuth not supported for {connector_type}")
    
    # Build callback URL
    callback_url = f"{settings.auth_service_url}/connectors/{connector_id}/oauth/callback"
    
    # Store redirect URL in connector metadata for later
    connector.metadata_json = connector.metadata_json or {}
    connector.metadata_json["oauth_redirect_url"] = redirect_url
    await db.flush()
    
    # TODO: Build proper OAuth URL with client_id, scope, state, etc.
    # For now, return placeholder
    oauth_url = f"{oauth_urls[connector_type]}?redirect_uri={callback_url}&state={connector_id}"
    
    return RedirectResponse(url=oauth_url, status_code=302)


@router.get("/{connector_id}/oauth/callback", response_model=Connector)
async def oauth_callback(
    connector_id: UUID,
    code: str = Query(None, description="Authorization code from provider"),
    state: str = Query(None, description="State parameter"),
    error: str = Query(None, description="Error from provider"),
    db: AsyncSession = Depends(get_db),
) -> Connector:
    """
    OAuth callback endpoint.
    
    Receives the authorization code from the provider, exchanges it for tokens,
    and stores them encrypted in the database.
    """
    if error:
        raise BadRequestError(f"OAuth error: {error}")
    
    if not code:
        raise BadRequestError("Missing authorization code")
    
    result = await db.execute(
        select(ConnectorModel).where(ConnectorModel.id == connector_id)
    )
    connector = result.scalar_one_or_none()
    
    if not connector:
        raise NotFoundError(f"Connector {connector_id} not found")
    
    # TODO: Exchange code for tokens with provider
    # TODO: Store tokens encrypted in config_json or secret manager
    
    # Update connector status to active
    connector.status = "active"
    connector.config_json = connector.config_json or {}
    connector.config_json["oauth_connected"] = True
    # In production: connector.config_json["access_token"] = encrypted_token
    
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
