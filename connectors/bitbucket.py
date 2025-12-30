"""
ConHub Data Connector - Bitbucket Connector

Bitbucket connector for fetching repository content.
Supports both Bitbucket Cloud (bitbucket.org) and Bitbucket Server.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote
from uuid import UUID

import httpx
import structlog

from app.exceptions import BadRequestError, ExternalServiceError
from app.schemas import ConnectorType, ContentType, SourceKind
from connectors.base import BaseConnector, ChangeEvent, Item, ItemContent

logger = structlog.get_logger(__name__)


@dataclass
class BitbucketSyncOptions:
    """Filtering options for Bitbucket sync."""
    include_languages: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    max_file_size_mb: Optional[float] = None
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "BitbucketSyncOptions":
        """Parse from connector config JSON."""
        return cls(
            include_languages=config.get("include_languages") or config.get("file_extensions") or [],
            exclude_paths=config.get("exclude_paths") or [],
            max_file_size_mb=config.get("max_file_size_mb"),
        )
    
    def should_include(self, path: str, file_size: Optional[int] = None) -> bool:
        """Check if a file path should be included based on filters."""
        if self.max_file_size_mb and file_size:
            max_bytes = int(self.max_file_size_mb * 1024 * 1024)
            if file_size > max_bytes:
                return False
        
        for pattern in self.exclude_paths:
            if pattern in path:
                return False
        
        if self.include_languages:
            ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
            if ext not in [lang.lower().lstrip(".") for lang in self.include_languages]:
                return False
        
        return True


# Binary file extensions to skip
BINARY_EXTENSIONS = frozenset([
    "png", "jpg", "jpeg", "gif", "ico", "svg", "webp", "bmp",
    "woff", "woff2", "ttf", "eot", "otf",
    "pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx",
    "zip", "tar", "gz", "rar", "7z",
    "exe", "dll", "so", "dylib", "bin",
    "mp3", "mp4", "wav", "avi", "mov", "mkv",
    "db", "sqlite", "lock",
])

# Content type mapping
CONTENT_TYPE_MAP = {
    "md": ContentType.MARKDOWN,
    "markdown": ContentType.MARKDOWN,
    "html": ContentType.HTML,
    "htm": ContentType.HTML,
    "json": ContentType.JSON,
    "xml": ContentType.XML,
    "yaml": ContentType.YAML,
    "yml": ContentType.YAML,
    "txt": ContentType.TEXT,
}

CODE_EXTENSIONS = frozenset([
    "rs", "py", "js", "ts", "go", "java", "c", "cpp", "h", "hpp",
    "cs", "rb", "php", "swift", "kt", "scala", "sql", "sh", "bash",
    "ps1", "psm1", "jsx", "tsx", "vue", "svelte", "css", "scss", "sass",
])

LANGUAGE_MAP = {
    "rs": "rust", "py": "python", "js": "javascript", "ts": "typescript",
    "jsx": "javascript", "tsx": "typescript", "go": "go", "java": "java",
    "c": "c", "cpp": "cpp", "h": "c", "hpp": "cpp", "cs": "csharp",
    "rb": "ruby", "php": "php", "swift": "swift", "kt": "kotlin",
    "scala": "scala", "sql": "sql", "sh": "shell", "bash": "shell",
    "vue": "vue", "svelte": "svelte", "md": "markdown",
}


class BitbucketConnector(BaseConnector):
    """Bitbucket connector for fetching repository content."""
    
    # Bitbucket Cloud API URL
    CLOUD_API_URL = "https://api.bitbucket.org/2.0"
    
    def __init__(
        self,
        config: dict[str, Any],
        tenant_id: str,
        connector_id: Optional[UUID] = None,
        access_token: Optional[str] = None,
    ):
        super().__init__(
            connector_type=ConnectorType.BITBUCKET,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
        )
        self.access_token = access_token
        self.sync_options = BitbucketSyncOptions.from_config(config)
        
        # Bitbucket uses workspace/repo format
        self.workspace = config.get("workspace", "")
        self.repo_slug = config.get("repository") or config.get("repo_slug", "")
        self.branch = config.get("branch", "main")
        
        # Support Bitbucket Server
        base_url = config.get("bitbucket_url") or config.get("base_url")
        if base_url:
            self.base_url = base_url.rstrip("/")
            self.is_server = True
        else:
            self.base_url = self.CLOUD_API_URL
            self.is_server = False
        
        # Auth method: app_password or OAuth token
        self.username = config.get("username", "")
        self.app_password = config.get("app_password", "")
        
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.CODE_REPO
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "Accept": "application/json",
                "User-Agent": "ConHub-DataConnector/1.0",
            }
            
            auth = None
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            elif self.username and self.app_password:
                auth = httpx.BasicAuth(self.username, self.app_password)
            
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                auth=auth,
                timeout=30.0,
            )
        return self._client
    
    @staticmethod
    def get_content_type(path: str) -> ContentType:
        """Determine content type from file extension."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        if ext in CONTENT_TYPE_MAP:
            return CONTENT_TYPE_MAP[ext]
        if ext in CODE_EXTENSIONS:
            return ContentType.CODE
        return ContentType.UNKNOWN
    
    @staticmethod
    def get_language(path: str) -> Optional[str]:
        """Detect programming language from file extension."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return LANGUAGE_MAP.get(ext)
    
    @staticmethod
    def is_binary_file(path: str) -> bool:
        """Check if file should be skipped."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return ext in BINARY_EXTENSIONS
    
    async def authorize(self) -> str:
        """Return Bitbucket OAuth URL."""
        return "https://bitbucket.org/site/oauth2/authorize"
    
    async def refresh_token(self) -> str:
        """Refresh OAuth token."""
        return self.access_token or ""
    
    async def validate_access(self) -> bool:
        """Validate access to the repository."""
        if not self.workspace or not self.repo_slug:
            return False
        
        client = await self._get_client()
        try:
            response = await client.get(f"/repositories/{self.workspace}/{self.repo_slug}")
            return response.status_code == 200
        except Exception as e:
            logger.warning("Failed to validate Bitbucket access", error=str(e))
            return False
    
    async def list_items(
        self,
        cursor: Optional[str] = None,
    ) -> tuple[list[Item], Optional[str]]:
        """List all files in the repository using the src endpoint."""
        if not self.workspace or not self.repo_slug:
            raise BadRequestError("Missing workspace or repo_slug in config")
        
        client = await self._get_client()
        
        all_items = []
        url = cursor or f"/repositories/{self.workspace}/{self.repo_slug}/src/{self.branch}/"
        
        # Bitbucket uses path-based navigation for directories
        # We need to recursively fetch all files
        await self._fetch_directory(client, url, "", all_items)
        
        logger.info(
            "Listed Bitbucket repository files",
            workspace=self.workspace,
            repo=self.repo_slug,
            branch=self.branch,
            file_count=len(all_items),
        )
        
        return all_items, None
    
    async def _fetch_directory(
        self,
        client: httpx.AsyncClient,
        url: str,
        base_path: str,
        items: list[Item],
    ) -> None:
        """Recursively fetch files from a directory."""
        response = await client.get(url)
        
        if response.status_code != 200:
            raise ExternalServiceError(
                f"Bitbucket API error: {response.status_code} - {response.text}"
            )
        
        data = response.json()
        
        for entry in data.get("values", []):
            entry_type = entry.get("type", "")
            path = entry.get("path", "")
            
            if entry_type == "commit_directory":
                # Recursively fetch subdirectory
                dir_url = f"/repositories/{self.workspace}/{self.repo_slug}/src/{self.branch}/{path}/"
                await self._fetch_directory(client, dir_url, path, items)
            elif entry_type == "commit_file":
                # Skip binary files
                if self.is_binary_file(path):
                    continue
                
                size = entry.get("size", 0)
                if not self.sync_options.should_include(path, size):
                    continue
                
                items.append(Item(
                    id=entry.get("commit", {}).get("hash", path),
                    name=path.rsplit("/", 1)[-1],
                    path=path,
                    item_type="file",
                    size=size,
                    metadata={
                        "workspace": self.workspace,
                        "repo": self.repo_slug,
                        "branch": self.branch,
                    },
                ))
        
        # Handle pagination
        next_url = data.get("next")
        if next_url:
            await self._fetch_directory(client, next_url, base_path, items)
    
    async def fetch_item(self, item_id: str) -> ItemContent:
        """Fetch content for a specific file."""
        # item_id is the file path for Bitbucket
        return await self.fetch_file_by_path(item_id)
    
    async def fetch_file_by_path(self, path: str) -> ItemContent:
        """Fetch content for a file by path."""
        if not self.workspace or not self.repo_slug:
            raise BadRequestError("Missing workspace or repo_slug in config")
        
        client = await self._get_client()
        
        url = f"/repositories/{self.workspace}/{self.repo_slug}/src/{self.branch}/{path}"
        response = await client.get(url)
        
        if response.status_code != 200:
            raise ExternalServiceError(f"Bitbucket API error: {response.status_code}")
        
        content = response.text
        
        return ItemContent(
            item=Item(
                id=path,
                name=path.rsplit("/", 1)[-1],
                path=path,
            ),
            content=content,
            content_type=self.get_content_type(path),
            language=self.get_language(path),
        )
    
    async def register_webhook(self, callback_url: str) -> str:
        """Register a Bitbucket webhook."""
        if not self.workspace or not self.repo_slug:
            raise BadRequestError("Missing workspace or repo_slug in config")
        
        client = await self._get_client()
        
        response = await client.post(
            f"/repositories/{self.workspace}/{self.repo_slug}/hooks",
            json={
                "description": "ConHub Data Connector",
                "url": callback_url,
                "active": True,
                "events": ["repo:push", "pullrequest:created", "pullrequest:updated"],
            },
        )
        
        if response.status_code not in (200, 201):
            raise ExternalServiceError(f"Failed to register webhook: {response.text}")
        
        data = response.json()
        return str(data.get("uuid", ""))
    
    async def handle_webhook(self, payload: dict[str, Any]) -> list[ChangeEvent]:
        """Parse Bitbucket webhook payload into change events."""
        events = []
        
        # Handle push events
        push_data = payload.get("push", {})
        for change in push_data.get("changes", []):
            for commit in change.get("commits", []):
                commit_hash = commit.get("hash", "")
                # Bitbucket doesn't include file lists in webhook, need to fetch
                events.append(ChangeEvent(
                    item_id=commit_hash,
                    change_type="updated",
                    cursor=commit_hash,
                ))
        
        return events
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
