"""
ConHub Data Connector - Dropbox Connector

Dropbox connector for syncing files and documents.
Uses Dropbox API v2 with OAuth 2.0 authentication.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

import httpx
import structlog

from app.exceptions import BadRequestError, ExternalServiceError
from app.schemas import ConnectorType, ContentType, SourceKind
from connectors.base import BaseConnector, ChangeEvent, Item, ItemContent

logger = structlog.get_logger(__name__)


@dataclass
class DropboxSyncOptions:
    """Filtering options for Dropbox sync."""
    include_extensions: list[str] = field(default_factory=list)
    exclude_folders: list[str] = field(default_factory=list)
    max_file_size_mb: Optional[float] = None
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "DropboxSyncOptions":
        """Parse from connector config JSON."""
        return cls(
            include_extensions=config.get("include_extensions") or [],
            exclude_folders=config.get("exclude_folders") or [],
            max_file_size_mb=config.get("max_file_size_mb"),
        )
    
    def should_include(self, path: str, file_size: Optional[int] = None) -> bool:
        """Check if a file should be included based on filters."""
        if self.max_file_size_mb and file_size:
            max_bytes = int(self.max_file_size_mb * 1024 * 1024)
            if file_size > max_bytes:
                return False
        
        for folder in self.exclude_folders:
            if folder.lower() in path.lower():
                return False
        
        if self.include_extensions:
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            if ext not in [e.lower().lstrip(".") for e in self.include_extensions]:
                return False
        
        return True


# Content type mapping
CONTENT_TYPE_MAP = {
    "md": ContentType.MARKDOWN,
    "markdown": ContentType.MARKDOWN,
    "txt": ContentType.TEXT,
    "html": ContentType.HTML,
    "htm": ContentType.HTML,
    "json": ContentType.JSON,
    "xml": ContentType.XML,
    "yaml": ContentType.YAML,
    "yml": ContentType.YAML,
    "csv": ContentType.SPREADSHEET,
    "pdf": ContentType.PDF,
    "doc": ContentType.DOCUMENT,
    "docx": ContentType.DOCUMENT,
}

# Binary extensions to skip
BINARY_EXTENSIONS = frozenset([
    "png", "jpg", "jpeg", "gif", "ico", "svg", "webp", "bmp",
    "woff", "woff2", "ttf", "eot", "otf",
    "zip", "tar", "gz", "rar", "7z",
    "exe", "dll", "so", "dylib", "bin",
    "mp3", "mp4", "wav", "avi", "mov", "mkv",
    "db", "sqlite",
])


class DropboxConnector(BaseConnector):
    """Dropbox connector for fetching file content."""
    
    API_URL = "https://api.dropboxapi.com/2"
    CONTENT_URL = "https://content.dropboxapi.com/2"
    
    def __init__(
        self,
        config: dict[str, Any],
        tenant_id: str,
        connector_id: Optional[UUID] = None,
        access_token: Optional[str] = None,
        refresh_token_value: Optional[str] = None,
    ):
        super().__init__(
            connector_type=ConnectorType.DROPBOX,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
        )
        self.access_token = access_token
        self._refresh_token_value = refresh_token_value
        self.sync_options = DropboxSyncOptions.from_config(config)
        
        # Optional folder path to scope sync
        self.folder_path = config.get("folder_path", "")
        
        self._client: Optional[httpx.AsyncClient] = None
        self._content_client: Optional[httpx.AsyncClient] = None
    
    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.DOCUMENT
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create API client."""
        if self._client is None:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "ConHub-DataConnector/1.0",
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            
            self._client = httpx.AsyncClient(
                base_url=self.API_URL,
                headers=headers,
                timeout=60.0,
            )
        return self._client
    
    async def _get_content_client(self) -> httpx.AsyncClient:
        """Get or create content download client."""
        if self._content_client is None:
            headers = {
                "User-Agent": "ConHub-DataConnector/1.0",
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            
            self._content_client = httpx.AsyncClient(
                base_url=self.CONTENT_URL,
                headers=headers,
                timeout=120.0,
            )
        return self._content_client
    
    @staticmethod
    def get_content_type(path: str) -> ContentType:
        """Determine content type from file extension."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return CONTENT_TYPE_MAP.get(ext, ContentType.UNKNOWN)
    
    @staticmethod
    def is_binary_file(path: str) -> bool:
        """Check if file should be skipped."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return ext in BINARY_EXTENSIONS
    
    async def authorize(self) -> str:
        """Return Dropbox OAuth URL."""
        return "https://www.dropbox.com/oauth2/authorize"
    
    async def refresh_token(self) -> str:
        """Refresh OAuth token."""
        return self.access_token or ""
    
    async def validate_access(self) -> bool:
        """Validate access to Dropbox."""
        client = await self._get_client()
        try:
            response = await client.post("/users/get_current_account")
            return response.status_code == 200
        except Exception as e:
            logger.warning("Failed to validate Dropbox access", error=str(e))
            return False
    
    async def list_items(
        self,
        cursor: Optional[str] = None,
    ) -> tuple[list[Item], Optional[str]]:
        """List files in Dropbox folder."""
        client = await self._get_client()
        
        if cursor:
            # Continue from cursor
            response = await client.post(
                "/files/list_folder/continue",
                json={"cursor": cursor}
            )
        else:
            # Start fresh listing
            path = self.folder_path if self.folder_path else ""
            response = await client.post(
                "/files/list_folder",
                json={
                    "path": path,
                    "recursive": True,
                    "include_deleted": False,
                    "include_has_explicit_shared_members": False,
                    "include_mounted_folders": True,
                }
            )
        
        if response.status_code != 200:
            raise ExternalServiceError(
                f"Dropbox API error: {response.status_code} - {response.text}"
            )
        
        data = response.json()
        entries = data.get("entries", [])
        has_more = data.get("has_more", False)
        next_cursor = data.get("cursor") if has_more else None
        
        items = []
        for entry in entries:
            # Skip folders
            if entry.get(".tag") != "file":
                continue
            
            path = entry.get("path_display", "")
            size = entry.get("size", 0)
            
            # Skip binary files
            if self.is_binary_file(path):
                continue
            
            if not self.sync_options.should_include(path, size):
                continue
            
            items.append(Item(
                id=entry.get("id", ""),
                name=entry.get("name", ""),
                path=path,
                item_type="file",
                size=size,
                metadata={
                    "rev": entry.get("rev"),
                    "content_hash": entry.get("content_hash"),
                    "server_modified": entry.get("server_modified"),
                },
            ))
        
        logger.info(
            "Listed Dropbox files",
            folder=self.folder_path,
            file_count=len(items),
            has_more=has_more,
        )
        
        return items, next_cursor
    
    async def fetch_item(self, item_id: str) -> ItemContent:
        """Fetch content for a specific file by ID."""
        # Dropbox uses path for download, need to get metadata first
        client = await self._get_client()
        
        # Get file metadata
        response = await client.post(
            "/files/get_metadata",
            json={"path": item_id}  # item_id can be path or id
        )
        
        if response.status_code != 200:
            raise ExternalServiceError(f"Dropbox API error: {response.status_code}")
        
        metadata = response.json()
        path = metadata.get("path_display", item_id)
        
        return await self.fetch_file_by_path(path)
    
    async def fetch_file_by_path(self, path: str) -> ItemContent:
        """Fetch content for a file by path."""
        content_client = await self._get_content_client()
        
        import json
        response = await content_client.post(
            "/files/download",
            headers={"Dropbox-API-Arg": json.dumps({"path": path})}
        )
        
        if response.status_code != 200:
            raise ExternalServiceError(f"Dropbox download error: {response.status_code}")
        
        # Parse metadata from header
        metadata_header = response.headers.get("dropbox-api-result", "{}")
        try:
            metadata = json.loads(metadata_header)
        except json.JSONDecodeError:
            metadata = {}
        
        # Try to decode as text
        try:
            content = response.text
        except Exception:
            content = ""
        
        return ItemContent(
            item=Item(
                id=metadata.get("id", path),
                name=metadata.get("name", path.rsplit("/", 1)[-1]),
                path=path,
                size=metadata.get("size"),
            ),
            content=content,
            content_type=self.get_content_type(path),
        )
    
    async def register_webhook(self, callback_url: str) -> str:
        """
        Register a Dropbox webhook.
        
        Note: Dropbox webhooks require verification via GET request.
        """
        # Dropbox webhooks are configured in the App Console
        # The callback URL needs to respond to GET with challenge param
        logger.warning("Dropbox webhooks require App Console configuration")
        return "configured-in-app-console"
    
    async def handle_webhook(self, payload: dict[str, Any]) -> list[ChangeEvent]:
        """Parse Dropbox webhook payload into change events."""
        events = []
        
        # Dropbox webhooks contain list_folder info
        # Need to use list_folder delta to get actual changes
        delta = payload.get("delta", {})
        users = delta.get("users", [])
        
        for user_id in users:
            events.append(ChangeEvent(
                item_id=str(user_id),
                change_type="updated",
                cursor=None,
            ))
        
        return events
    
    async def close(self) -> None:
        """Close HTTP clients."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._content_client:
            await self._content_client.aclose()
            self._content_client = None
