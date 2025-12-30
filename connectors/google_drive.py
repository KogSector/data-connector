"""
ConHub Data Connector - Google Drive Connector

Google Drive connector for syncing documents, spreadsheets, and other files.
Uses Google Drive API v3 with OAuth 2.0 authentication.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID
import mimetypes

import httpx
import structlog

from app.exceptions import BadRequestError, ExternalServiceError
from app.schemas import ConnectorType, ContentType, SourceKind
from connectors.base import BaseConnector, ChangeEvent, Item, ItemContent

logger = structlog.get_logger(__name__)


@dataclass
class GoogleDriveSyncOptions:
    """Filtering options for Google Drive sync."""
    include_mime_types: list[str] = field(default_factory=list)
    exclude_folders: list[str] = field(default_factory=list)
    max_file_size_mb: Optional[float] = None
    include_shared: bool = True
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "GoogleDriveSyncOptions":
        """Parse from connector config JSON."""
        return cls(
            include_mime_types=config.get("include_mime_types") or [],
            exclude_folders=config.get("exclude_folders") or [],
            max_file_size_mb=config.get("max_file_size_mb"),
            include_shared=config.get("include_shared", True),
        )
    
    def should_include(self, mime_type: str, file_size: Optional[int] = None) -> bool:
        """Check if a file should be included based on filters."""
        # Check file size limit
        if self.max_file_size_mb and file_size:
            max_bytes = int(self.max_file_size_mb * 1024 * 1024)
            if file_size > max_bytes:
                return False
        
        # Check MIME type filter
        if self.include_mime_types:
            if not any(mime_type.startswith(mt) for mt in self.include_mime_types):
                return False
        
        return True


# Google Drive MIME types to ConHub content types
MIME_TYPE_MAP = {
    # Google Docs native formats
    "application/vnd.google-apps.document": ContentType.DOCUMENT,
    "application/vnd.google-apps.spreadsheet": ContentType.SPREADSHEET,
    "application/vnd.google-apps.presentation": ContentType.PRESENTATION,
    
    # Standard formats
    "text/plain": ContentType.TEXT,
    "text/markdown": ContentType.MARKDOWN,
    "text/html": ContentType.HTML,
    "application/json": ContentType.JSON,
    "application/xml": ContentType.XML,
    "text/xml": ContentType.XML,
    "application/pdf": ContentType.PDF,
    
    # Code files
    "text/x-python": ContentType.CODE,
    "text/javascript": ContentType.CODE,
    "application/x-javascript": ContentType.CODE,
    "text/x-java-source": ContentType.CODE,
}

# MIME types to export format for Google Docs
GOOGLE_EXPORT_MIMES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

# MIME types to skip (binary files)
SKIP_MIME_TYPES = frozenset([
    "image/",
    "video/",
    "audio/",
    "application/zip",
    "application/x-rar-compressed",
    "application/x-7z-compressed",
    "application/octet-stream",
])


class GoogleDriveConnector(BaseConnector):
    """Google Drive connector for fetching document content."""
    
    # Google Drive API endpoints
    DRIVE_API_URL = "https://www.googleapis.com/drive/v3"
    
    def __init__(
        self,
        config: dict[str, Any],
        tenant_id: str,
        connector_id: Optional[UUID] = None,
        access_token: Optional[str] = None,
        refresh_token_value: Optional[str] = None,
    ):
        super().__init__(
            connector_type=ConnectorType.GOOGLE_DRIVE,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
        )
        self.access_token = access_token
        self._refresh_token_value = refresh_token_value
        self.sync_options = GoogleDriveSyncOptions.from_config(config)
        
        # Optional folder ID to scope sync
        self.folder_id = config.get("folder_id") or config.get("root_folder_id")
        
        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.DOCUMENT
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "Accept": "application/json",
                "User-Agent": "ConHub-DataConnector/1.0",
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            
            self._client = httpx.AsyncClient(
                base_url=self.DRIVE_API_URL,
                headers=headers,
                timeout=60.0,
            )
        return self._client
    
    @staticmethod
    def get_content_type(mime_type: str) -> ContentType:
        """Determine content type from MIME type."""
        if mime_type in MIME_TYPE_MAP:
            return MIME_TYPE_MAP[mime_type]
        
        # Check prefix matches
        for prefix in ["text/x-", "application/x-"]:
            if mime_type.startswith(prefix):
                return ContentType.CODE
        
        if mime_type.startswith("text/"):
            return ContentType.TEXT
        
        return ContentType.UNKNOWN
    
    @staticmethod
    def should_skip_mime_type(mime_type: str) -> bool:
        """Check if MIME type should be skipped."""
        for skip in SKIP_MIME_TYPES:
            if mime_type.startswith(skip):
                return True
        return False
    
    async def authorize(self) -> str:
        """Return Google OAuth URL."""
        # Standard Google OAuth 2.0 authorization URL
        return "https://accounts.google.com/o/oauth2/v2/auth"
    
    async def refresh_token(self) -> str:
        """Refresh OAuth token when expired."""
        # Would need client_id/client_secret and refresh_token to refresh
        # For now, return current token
        return self.access_token or ""
    
    async def validate_access(self) -> bool:
        """Validate access to Google Drive."""
        client = await self._get_client()
        try:
            response = await client.get("/about", params={"fields": "user"})
            return response.status_code == 200
        except Exception as e:
            logger.warning("Failed to validate Google Drive access", error=str(e))
            return False
    
    async def list_items(
        self,
        cursor: Optional[str] = None,
    ) -> tuple[list[Item], Optional[str]]:
        """
        List files in Google Drive.
        
        Uses the files.list endpoint with pagination.
        """
        client = await self._get_client()
        
        # Build query
        query_parts = ["trashed = false"]
        
        # Only get files, not folders
        query_parts.append("mimeType != 'application/vnd.google-apps.folder'")
        
        # Scope to folder if specified
        if self.folder_id:
            query_parts.append(f"'{self.folder_id}' in parents")
        
        # Include shared files if configured
        if not self.sync_options.include_shared:
            query_parts.append("'me' in owners")
        
        query = " and ".join(query_parts)
        
        params = {
            "q": query,
            "fields": "nextPageToken,files(id,name,mimeType,size,modifiedTime,parents,webViewLink)",
            "pageSize": 100,
            "orderBy": "modifiedTime desc",
        }
        
        if cursor:
            params["pageToken"] = cursor
        
        response = await client.get("/files", params=params)
        
        if response.status_code != 200:
            raise ExternalServiceError(
                f"Google Drive API error: {response.status_code} - {response.text}"
            )
        
        data = response.json()
        files = data.get("files", [])
        next_cursor = data.get("nextPageToken")
        
        items = []
        for file in files:
            mime_type = file.get("mimeType", "")
            size = int(file.get("size", 0)) if file.get("size") else None
            
            # Skip binary files
            if self.should_skip_mime_type(mime_type):
                continue
            
            # Apply sync options filtering
            if not self.sync_options.should_include(mime_type, size):
                continue
            
            items.append(Item(
                id=file.get("id", ""),
                name=file.get("name", ""),
                path=file.get("name", ""),  # Drive doesn't have paths, use name
                item_type="file",
                size=size,
                metadata={
                    "mime_type": mime_type,
                    "modified_time": file.get("modifiedTime"),
                    "parents": file.get("parents", []),
                    "web_link": file.get("webViewLink"),
                },
            ))
        
        logger.info(
            "Listed Google Drive files",
            file_count=len(items),
            has_more=next_cursor is not None,
        )
        
        return items, next_cursor
    
    async def fetch_item(self, item_id: str) -> ItemContent:
        """
        Fetch content for a specific file.
        
        Handles both regular files and Google Docs (which need export).
        """
        client = await self._get_client()
        
        # First, get file metadata
        meta_response = await client.get(
            f"/files/{item_id}",
            params={"fields": "id,name,mimeType,size"}
        )
        
        if meta_response.status_code != 200:
            raise ExternalServiceError(f"Google Drive API error: {meta_response.status_code}")
        
        metadata = meta_response.json()
        mime_type = metadata.get("mimeType", "")
        name = metadata.get("name", "")
        
        # Handle Google Docs native formats (need export)
        if mime_type in GOOGLE_EXPORT_MIMES:
            export_mime = GOOGLE_EXPORT_MIMES[mime_type]
            content_response = await client.get(
                f"/files/{item_id}/export",
                params={"mimeType": export_mime}
            )
        else:
            # Regular file download
            content_response = await client.get(
                f"/files/{item_id}",
                params={"alt": "media"}
            )
        
        if content_response.status_code != 200:
            raise ExternalServiceError(
                f"Google Drive download error: {content_response.status_code}"
            )
        
        # Try to decode as text
        try:
            content = content_response.text
        except Exception:
            content = ""
        
        return ItemContent(
            item=Item(
                id=item_id,
                name=name,
                path=name,
                size=metadata.get("size"),
            ),
            content=content,
            content_type=self.get_content_type(mime_type),
        )
    
    async def register_webhook(self, callback_url: str) -> str:
        """
        Register a Google Drive webhook (watch).
        
        Note: Google Drive webhooks require a verified domain.
        """
        client = await self._get_client()
        
        import uuid
        channel_id = str(uuid.uuid4())
        
        # Watch changes to the drive
        response = await client.post(
            "/changes/watch",
            params={"pageToken": "1"},  # Need actual page token in production
            json={
                "id": channel_id,
                "type": "web_hook",
                "address": callback_url,
            },
        )
        
        if response.status_code not in (200, 201):
            raise ExternalServiceError(f"Failed to register webhook: {response.text}")
        
        data = response.json()
        return data.get("resourceId", channel_id)
    
    async def handle_webhook(self, payload: dict[str, Any]) -> list[ChangeEvent]:
        """Parse Google Drive webhook payload into change events."""
        events = []
        
        # Google Drive webhooks are notifications, need to fetch changes
        # The payload contains headers like X-Goog-Resource-ID
        # Would need to call changes.list to get actual changes
        
        resource_id = payload.get("resourceId") or payload.get("resource_id")
        if resource_id:
            events.append(ChangeEvent(
                item_id=resource_id,
                change_type="updated",
                cursor=None,
            ))
        
        return events
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
