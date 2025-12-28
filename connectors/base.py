"""
ConHub Data Connector - Base Connector Interface

Abstract base class that all connectors must implement.
Ported from Rust domain/connectors/mod.rs Connector trait.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from app.schemas import ConnectorType, ContentType, NormalizedDocument, SourceKind


@dataclass
class Item:
    """Represents an item from a data source."""
    id: str
    name: str
    path: Optional[str] = None
    item_type: str = "file"  # file, folder, message, etc.
    size: Optional[int] = None
    mime_type: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class ItemContent:
    """Content fetched from a data source item."""
    item: Item
    content: str
    content_type: ContentType = ContentType.UNKNOWN
    language: Optional[str] = None
    encoding: str = "utf-8"
    is_binary: bool = False


@dataclass
class ChangeEvent:
    """Represents a change event from delta sync or webhook."""
    item_id: str
    change_type: str  # created, updated, deleted
    item: Optional[Item] = None
    cursor: Optional[str] = None
    timestamp: Optional[datetime] = None


class BaseConnector(ABC):
    """
    Abstract base class for all connectors.
    
    Each connector implementation must provide methods for:
    - OAuth authorization
    - Token refresh
    - Listing items (with pagination)
    - Fetching item content
    - Webhook registration and handling
    - Delta/incremental sync
    """
    
    def __init__(
        self,
        connector_type: ConnectorType,
        config: dict[str, Any],
        tenant_id: str,
        connector_id: Optional[UUID] = None,
    ):
        self.connector_type = connector_type
        self.config = config
        self.tenant_id = tenant_id
        self.connector_id = connector_id
    
    @property
    @abstractmethod
    def source_kind(self) -> SourceKind:
        """Return the source kind for chunker categorization."""
        ...
    
    @abstractmethod
    async def authorize(self) -> str:
        """
        Initiate OAuth flow or confirm API key.
        
        Returns:
            Authorization URL or confirmation message.
        """
        ...
    
    @abstractmethod
    async def refresh_token(self) -> str:
        """
        Refresh OAuth tokens where applicable.
        
        Returns:
            New access token.
        """
        ...
    
    @abstractmethod
    async def validate_access(self) -> bool:
        """
        Validate access to the data source.
        
        Returns:
            True if access is valid.
        """
        ...
    
    @abstractmethod
    async def list_items(
        self,
        cursor: Optional[str] = None,
    ) -> tuple[list[Item], Optional[str]]:
        """
        Paginated listing of items from the data source.
        
        Args:
            cursor: Pagination cursor from previous call.
            
        Returns:
            Tuple of (items, next_cursor). next_cursor is None if no more items.
        """
        ...
    
    @abstractmethod
    async def fetch_item(self, item_id: str) -> ItemContent:
        """
        Fetch content for a specific item.
        
        Args:
            item_id: ID of the item to fetch.
            
        Returns:
            ItemContent with content and metadata.
        """
        ...
    
    async def register_webhook(self, callback_url: str) -> str:
        """
        Register a webhook with the provider.
        
        Args:
            callback_url: URL to receive webhook events.
            
        Returns:
            Webhook ID or confirmation.
            
        Note:
            Optional - not all connectors support webhooks.
        """
        raise NotImplementedError(f"{self.connector_type} does not support webhooks")
    
    async def handle_webhook(self, payload: dict[str, Any]) -> list[ChangeEvent]:
        """
        Parse webhook payload into change events.
        
        Args:
            payload: Raw webhook payload from provider.
            
        Returns:
            List of change events to process.
        """
        raise NotImplementedError(f"{self.connector_type} does not support webhooks")
    
    async def delta_sync(self, cursor: str) -> tuple[list[ChangeEvent], Optional[str]]:
        """
        Get changes since the given cursor.
        
        Args:
            cursor: Previous sync cursor.
            
        Returns:
            Tuple of (changes, new_cursor).
        """
        raise NotImplementedError(f"{self.connector_type} does not support delta sync")
    
    async def fetch_all_content(self) -> list[NormalizedDocument]:
        """
        Convenience method to fetch all content from the source.
        
        Iterates through all items and fetches their content.
        
        Returns:
            List of normalized documents.
        """
        from uuid import uuid4
        from datetime import datetime, timezone
        
        documents = []
        cursor = None
        
        while True:
            items, next_cursor = await self.list_items(cursor)
            
            for item in items:
                try:
                    content = await self.fetch_item(item.id)
                    
                    now = datetime.now(timezone.utc)
                    doc = NormalizedDocument(
                        id=uuid4(),
                        source_id=self.connector_id or uuid4(),
                        connector_type=self.connector_type,
                        external_id=item.id,
                        name=item.name,
                        path=item.path,
                        content=content.content,
                        content_type=content.content_type,
                        metadata=item.metadata,
                        language=content.language,
                        created_at=now,
                        updated_at=now,
                    )
                    documents.append(doc)
                except Exception as e:
                    # Log but continue with other items
                    import structlog
                    logger = structlog.get_logger(__name__)
                    logger.warning(
                        "Failed to fetch item",
                        item_id=item.id,
                        error=str(e),
                    )
            
            if not next_cursor:
                break
            cursor = next_cursor
        
        return documents
