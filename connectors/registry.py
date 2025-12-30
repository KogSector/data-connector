"""
ConHub Data Connector - Connector Registry

Factory pattern for creating connector instances.
Ported from Rust ConnectorManager.
"""

from typing import Any, Optional
from uuid import UUID

from app.exceptions import BadRequestError
from app.schemas import ConnectorType, SourceKind
from connectors.base import BaseConnector


class StubConnector(BaseConnector):
    """Stub connector for providers not yet implemented."""
    
    _source_kind: SourceKind = SourceKind.OTHER
    
    def __init__(
        self,
        connector_type: ConnectorType,
        config: dict[str, Any],
        tenant_id: str,
        connector_id: Optional[UUID] = None,
        source_kind: SourceKind = SourceKind.OTHER,
    ):
        super().__init__(
            connector_type=connector_type,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
        )
        self._source_kind = source_kind
    
    @property
    def source_kind(self) -> SourceKind:
        return self._source_kind
    
    async def authorize(self) -> str:
        raise NotImplementedError(f"{self.connector_type.value} connector not yet implemented")
    
    async def refresh_token(self) -> str:
        raise NotImplementedError(f"{self.connector_type.value} connector not yet implemented")
    
    async def validate_access(self) -> bool:
        return False
    
    async def list_items(self, cursor=None):
        raise NotImplementedError(f"{self.connector_type.value} connector not yet implemented")
    
    async def fetch_item(self, item_id: str):
        raise NotImplementedError(f"{self.connector_type.value} connector not yet implemented")


# Source kind mapping for each connector type
CONNECTOR_SOURCE_KINDS = {
    ConnectorType.GITHUB: SourceKind.CODE_REPO,
    ConnectorType.GITLAB: SourceKind.CODE_REPO,
    ConnectorType.BITBUCKET: SourceKind.CODE_REPO,
    ConnectorType.LOCAL_FILE: SourceKind.DOCUMENT,
    ConnectorType.GOOGLE_DRIVE: SourceKind.DOCUMENT,
    ConnectorType.DROPBOX: SourceKind.DOCUMENT,
    ConnectorType.ONEDRIVE: SourceKind.DOCUMENT,
    ConnectorType.SLACK: SourceKind.CHAT,
    ConnectorType.NOTION: SourceKind.WIKI,
    ConnectorType.CONFLUENCE: SourceKind.WIKI,
    ConnectorType.URL_SCRAPER: SourceKind.WEB,
}


def get_connector(
    connector_type: ConnectorType,
    config: dict[str, Any],
    tenant_id: str,
    connector_id: Optional[UUID] = None,
    access_token: Optional[str] = None,
) -> BaseConnector:
    """
    Factory function to create the appropriate connector.
    
    Args:
        connector_type: Type of connector to create.
        config: Connector configuration.
        tenant_id: Tenant ID.
        connector_id: Optional connector UUID.
        access_token: Optional OAuth access token.
        
    Returns:
        Configured connector instance.
    """
    if connector_type == ConnectorType.GITHUB:
        from connectors.github import GitHubConnector
        return GitHubConnector(
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
            access_token=access_token,
        )
    
    elif connector_type == ConnectorType.LOCAL_FILE:
        from connectors.local_file import LocalFileConnector
        return LocalFileConnector(
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
        )
    
    elif connector_type == ConnectorType.GITLAB:
        from connectors.gitlab import GitLabConnector
        return GitLabConnector(
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
            access_token=access_token,
        )
    
    elif connector_type == ConnectorType.BITBUCKET:
        # Git repository stub (Bitbucket)
        return StubConnector(
            connector_type=connector_type,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
            source_kind=SourceKind.CODE_REPO,
        )
    
    elif connector_type == ConnectorType.GOOGLE_DRIVE:
        from connectors.google_drive import GoogleDriveConnector
        return GoogleDriveConnector(
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
            access_token=access_token,
        )
    
    elif connector_type in (ConnectorType.DROPBOX, ConnectorType.ONEDRIVE):
        # Cloud storage stubs (Dropbox, OneDrive)
        return StubConnector(
            connector_type=connector_type,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
            source_kind=SourceKind.DOCUMENT,
        )
    
    elif connector_type == ConnectorType.SLACK:
        return StubConnector(
            connector_type=connector_type,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
            source_kind=SourceKind.CHAT,
        )
    
    elif connector_type in (ConnectorType.NOTION, ConnectorType.CONFLUENCE):
        # Wiki stubs
        return StubConnector(
            connector_type=connector_type,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
            source_kind=SourceKind.WIKI,
        )
    
    elif connector_type == ConnectorType.URL_SCRAPER:
        return StubConnector(
            connector_type=connector_type,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
            source_kind=SourceKind.WEB,
        )
    
    else:
        raise BadRequestError(f"Unknown connector type: {connector_type}")


def get_source_kind(connector_type: ConnectorType) -> SourceKind:
    """Get the source kind for a connector type."""
    return CONNECTOR_SOURCE_KINDS.get(connector_type, SourceKind.OTHER)
