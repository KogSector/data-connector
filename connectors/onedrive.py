"""
ConHub Data Connector - OneDrive Connector

OneDrive connector for syncing files and documents.
Uses Microsoft Graph API with OAuth 2.0 authentication.
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
class OneDriveSyncOptions:
    """Filtering options for OneDrive sync."""
    include_extensions: list[str] = field(default_factory=list)
    exclude_folders: list[str] = field(default_factory=list)
    max_file_size_mb: Optional[float] = None
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "OneDriveSyncOptions":
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
    "xls": ContentType.SPREADSHEET,
    "xlsx": ContentType.SPREADSHEET,
    "ppt": ContentType.PRESENTATION,
    "pptx": ContentType.PRESENTATION,
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


class OneDriveConnector(BaseConnector):
    """OneDrive connector for fetching file content via Microsoft Graph API."""
    
    GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
    
    def __init__(
        self,
        config: dict[str, Any],
        tenant_id: str,
        connector_id: Optional[UUID] = None,
        access_token: Optional[str] = None,
        refresh_token_value: Optional[str] = None,
    ):
        super().__init__(
            connector_type=ConnectorType.ONEDRIVE,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
        )
        self.access_token = access_token
        self._refresh_token_value = refresh_token_value
        self.sync_options = OneDriveSyncOptions.from_config(config)
        
        # Optional folder path to scope sync (item ID or path)
        self.folder_id = config.get("folder_id") or config.get("root_folder_id")
        self.folder_path = config.get("folder_path", "")
        
        # Drive type: personal, business, or sharepoint
        self.drive_type = config.get("drive_type", "me")  # "me" or specific drive ID
        
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.DOCUMENT
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create API client."""
        if self._client is None:
            headers = {
                "Accept": "application/json",
                "User-Agent": "ConHub-DataConnector/1.0",
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            
            self._client = httpx.AsyncClient(
                base_url=self.GRAPH_API_URL,
                headers=headers,
                timeout=60.0,
            )
        return self._client
    
    def _get_drive_path(self) -> str:
        """Get the drive path prefix based on configuration."""
        if self.drive_type == "me":
            return "/me/drive"
        else:
            return f"/drives/{self.drive_type}"
    
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
        """Return Microsoft OAuth URL."""
        return "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
    
    async def refresh_token(self) -> str:
        """Refresh OAuth token."""
        return self.access_token or ""
    
    async def validate_access(self) -> bool:
        """Validate access to OneDrive."""
        client = await self._get_client()
        try:
            drive_path = self._get_drive_path()
            response = await client.get(drive_path)
            return response.status_code == 200
        except Exception as e:
            logger.warning("Failed to validate OneDrive access", error=str(e))
            return False
    
    async def list_items(
        self,
        cursor: Optional[str] = None,
    ) -> tuple[list[Item], Optional[str]]:
        """List files in OneDrive folder."""
        client = await self._get_client()
        drive_path = self._get_drive_path()
        
        # Build URL
        if cursor:
            url = cursor  # Next page URL
        elif self.folder_id:
            url = f"{drive_path}/items/{self.folder_id}/children"
        elif self.folder_path:
            url = f"{drive_path}/root:/{self.folder_path}:/children"
        else:
            url = f"{drive_path}/root/children"
        
        # Recursively list all files
        all_items = []
        await self._fetch_folder(client, url, "", all_items)
        
        logger.info(
            "Listed OneDrive files",
            drive=self.drive_type,
            folder=self.folder_path or self.folder_id or "root",
            file_count=len(all_items),
        )
        
        return all_items, None
    
    async def _fetch_folder(
        self,
        client: httpx.AsyncClient,
        url: str,
        parent_path: str,
        items: list[Item],
    ) -> None:
        """Recursively fetch files from a folder."""
        params = {
            "$select": "id,name,size,file,folder,parentReference,lastModifiedDateTime,@microsoft.graph.downloadUrl",
        }
        
        response = await client.get(url, params=params)
        
        if response.status_code != 200:
            raise ExternalServiceError(
                f"OneDrive API error: {response.status_code} - {response.text}"
            )
        
        data = response.json()
        
        for entry in data.get("value", []):
            name = entry.get("name", "")
            path = f"{parent_path}/{name}" if parent_path else name
            
            if "folder" in entry:
                # Recursively fetch subfolder
                folder_url = f"{self._get_drive_path()}/items/{entry['id']}/children"
                await self._fetch_folder(client, folder_url, path, items)
            elif "file" in entry:
                # It's a file
                if self.is_binary_file(name):
                    continue
                
                size = entry.get("size", 0)
                if not self.sync_options.should_include(path, size):
                    continue
                
                items.append(Item(
                    id=entry.get("id", ""),
                    name=name,
                    path=path,
                    item_type="file",
                    size=size,
                    metadata={
                        "mime_type": entry.get("file", {}).get("mimeType"),
                        "modified_time": entry.get("lastModifiedDateTime"),
                        "download_url": entry.get("@microsoft.graph.downloadUrl"),
                    },
                ))
        
        # Handle pagination
        next_link = data.get("@odata.nextLink")
        if next_link:
            await self._fetch_folder(client, next_link, parent_path, items)
    
    async def fetch_item(self, item_id: str) -> ItemContent:
        """Fetch content for a specific file by ID."""
        client = await self._get_client()
        drive_path = self._get_drive_path()
        
        # Get file metadata with download URL
        response = await client.get(
            f"{drive_path}/items/{item_id}",
            params={"$select": "id,name,size,file,@microsoft.graph.downloadUrl"}
        )
        
        if response.status_code != 200:
            raise ExternalServiceError(f"OneDrive API error: {response.status_code}")
        
        metadata = response.json()
        name = metadata.get("name", "")
        download_url = metadata.get("@microsoft.graph.downloadUrl")
        
        if not download_url:
            raise ExternalServiceError("No download URL available for file")
        
        # Download content
        async with httpx.AsyncClient(timeout=120.0) as download_client:
            content_response = await download_client.get(download_url)
        
        if content_response.status_code != 200:
            raise ExternalServiceError(f"OneDrive download error: {content_response.status_code}")
        
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
            content_type=self.get_content_type(name),
        )
    
    async def fetch_file_by_path(self, path: str) -> ItemContent:
        """Fetch content for a file by path."""
        client = await self._get_client()
        drive_path = self._get_drive_path()
        
        # Get file by path
        response = await client.get(
            f"{drive_path}/root:/{path}",
            params={"$select": "id,name,size,file,@microsoft.graph.downloadUrl"}
        )
        
        if response.status_code != 200:
            raise ExternalServiceError(f"OneDrive API error: {response.status_code}")
        
        metadata = response.json()
        return await self.fetch_item(metadata.get("id", ""))
    
    async def register_webhook(self, callback_url: str) -> str:
        """
        Register a OneDrive subscription (webhook).
        
        Note: Requires Azure AD app with proper permissions.
        """
        client = await self._get_client()
        
        import datetime
        expiration = datetime.datetime.utcnow() + datetime.timedelta(days=3)
        
        response = await client.post(
            "/subscriptions",
            json={
                "changeType": "updated",
                "notificationUrl": callback_url,
                "resource": f"{self._get_drive_path()}/root",
                "expirationDateTime": expiration.isoformat() + "Z",
                "clientState": "ConHub-DataConnector",
            },
        )
        
        if response.status_code not in (200, 201):
            raise ExternalServiceError(f"Failed to register webhook: {response.text}")
        
        data = response.json()
        return data.get("id", "")
    
    async def handle_webhook(self, payload: dict[str, Any]) -> list[ChangeEvent]:
        """Parse OneDrive webhook payload into change events."""
        events = []
        
        # OneDrive sends notifications with resource data
        for notification in payload.get("value", []):
            resource = notification.get("resource", "")
            change_type = notification.get("changeType", "updated")
            
            events.append(ChangeEvent(
                item_id=resource,
                change_type=change_type,
                cursor=notification.get("subscriptionId"),
            ))
        
        return events
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
