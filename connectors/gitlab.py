"""
ConHub Data Connector - GitLab Connector

GitLab connector implementation for fetching repository content.
Supports both gitlab.com and self-hosted GitLab instances.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import quote
from uuid import UUID

import httpx
import structlog

from app.exceptions import BadRequestError, ConnectorError, ExternalServiceError
from app.schemas import ConnectorType, ContentType, SourceKind
from connectors.base import BaseConnector, ChangeEvent, Item, ItemContent

logger = structlog.get_logger(__name__)


@dataclass
class GitLabSyncOptions:
    """Filtering options for GitLab sync."""
    include_languages: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    max_file_size_mb: Optional[float] = None
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "GitLabSyncOptions":
        """Parse from connector config JSON."""
        return cls(
            include_languages=config.get("include_languages") or config.get("file_extensions") or [],
            exclude_paths=config.get("exclude_paths") or [],
            max_file_size_mb=config.get("max_file_size_mb"),
        )
    
    def should_include(self, path: str, file_size: Optional[int] = None) -> bool:
        """Check if a file path should be included based on filters."""
        # Check file size limit
        if self.max_file_size_mb and file_size:
            max_bytes = int(self.max_file_size_mb * 1024 * 1024)
            if file_size > max_bytes:
                return False
        
        # Check exclude patterns
        for pattern in self.exclude_paths:
            if pattern in path:
                return False
        
        # Check include languages (if specified)
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


# Content type mapping from file extension
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
    "rs": "rust",
    "py": "python",
    "js": "javascript",
    "ts": "typescript",
    "jsx": "javascript",
    "tsx": "typescript",
    "go": "go",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "cc": "cpp",
    "cxx": "cpp",
    "h": "c",
    "hpp": "c",
    "cs": "csharp",
    "rb": "ruby",
    "php": "php",
    "swift": "swift",
    "kt": "kotlin",
    "scala": "scala",
    "sql": "sql",
    "sh": "shell",
    "bash": "shell",
    "ps1": "powershell",
    "psm1": "powershell",
    "vue": "vue",
    "svelte": "svelte",
    "md": "markdown",
    "markdown": "markdown",
    "json": "json",
    "yaml": "yaml",
    "yml": "yaml",
    "xml": "xml",
    "html": "html",
    "htm": "html",
    "css": "css",
    "scss": "scss",
    "sass": "scss",
}


class GitLabConnector(BaseConnector):
    """GitLab connector for fetching repository content."""
    
    # Default GitLab API URL (can be overridden for self-hosted)
    DEFAULT_BASE_URL = "https://gitlab.com/api/v4"
    
    def __init__(
        self,
        config: dict[str, Any],
        tenant_id: str,
        connector_id: Optional[UUID] = None,
        access_token: Optional[str] = None,
    ):
        super().__init__(
            connector_type=ConnectorType.GITLAB,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
        )
        self.access_token = access_token
        self.sync_options = GitLabSyncOptions.from_config(config)
        
        # GitLab-specific config
        self.project_path = config.get("repository") or config.get("project_path", "")
        self.branch = config.get("branch", "main")
        
        # Support self-hosted GitLab instances
        base_url = config.get("gitlab_url") or config.get("base_url")
        if base_url:
            self.base_url = f"{base_url.rstrip('/')}/api/v4"
        else:
            self.base_url = self.DEFAULT_BASE_URL
        
        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.CODE_REPO
    
    def _encode_project_path(self, path: str) -> str:
        """URL-encode project path for GitLab API."""
        return quote(path, safe="")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "Accept": "application/json",
                "User-Agent": "ConHub-DataConnector/1.0",
            }
            if self.access_token:
                headers["PRIVATE-TOKEN"] = self.access_token
            
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
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
        """Check if file should be skipped (binary files)."""
        ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        return ext in BINARY_EXTENSIONS
    
    async def authorize(self) -> str:
        """Return GitLab OAuth URL."""
        # For gitlab.com, use oauth.authorize path
        # For self-hosted, need to adjust based on config
        if self.base_url == self.DEFAULT_BASE_URL:
            return "https://gitlab.com/oauth/authorize"
        else:
            # Extract base domain from API URL
            domain = self.base_url.replace("/api/v4", "")
            return f"{domain}/oauth/authorize"
    
    async def refresh_token(self) -> str:
        """Refresh OAuth token when expired."""
        # GitLab OAuth tokens can expire, would need refresh_token flow
        # For now, return current token
        return self.access_token or ""
    
    async def validate_access(self) -> bool:
        """Validate access to the project."""
        if not self.project_path:
            return False
        
        client = await self._get_client()
        try:
            encoded_path = self._encode_project_path(self.project_path)
            response = await client.get(f"/projects/{encoded_path}")
            return response.status_code == 200
        except Exception as e:
            logger.warning("Failed to validate GitLab access", error=str(e))
            return False
    
    async def list_items(
        self,
        cursor: Optional[str] = None,
    ) -> tuple[list[Item], Optional[str]]:
        """
        List all files in the repository.
        
        Uses the Repository Tree API for recursive listing.
        """
        if not self.project_path:
            raise BadRequestError("Missing project_path in config")
        
        client = await self._get_client()
        encoded_path = self._encode_project_path(self.project_path)
        
        # GitLab uses pagination, fetch all pages
        all_items = []
        page = 1 if cursor is None else int(cursor)
        per_page = 100
        
        while True:
            url = f"/projects/{encoded_path}/repository/tree"
            params = {
                "ref": self.branch,
                "recursive": "true",
                "per_page": per_page,
                "page": page,
            }
            
            response = await client.get(url, params=params)
            
            if response.status_code != 200:
                raise ExternalServiceError(
                    f"GitLab API error: {response.status_code} - {response.text}"
                )
            
            data = response.json()
            
            if not data:
                break
            
            for node in data:
                # Only process files (blobs), not directories (trees)
                if node.get("type") != "blob":
                    continue
                
                path = node.get("path", "")
                
                # Skip binary files
                if self.is_binary_file(path):
                    continue
                
                # Apply sync options filtering (size not available in tree API)
                if not self.sync_options.should_include(path):
                    continue
                
                all_items.append(Item(
                    id=node.get("id", ""),  # SHA of the blob
                    name=node.get("name", ""),
                    path=path,
                    item_type="file",
                    metadata={
                        "sha": node.get("id"),
                        "project": self.project_path,
                        "branch": self.branch,
                        "mode": node.get("mode"),
                    },
                ))
            
            # Check if there are more pages
            total_pages = int(response.headers.get("x-total-pages", "1"))
            if page >= total_pages:
                break
            
            page += 1
        
        logger.info(
            "Listed GitLab repository files",
            project=self.project_path,
            branch=self.branch,
            file_count=len(all_items),
        )
        
        return all_items, None
    
    async def fetch_item(self, item_id: str) -> ItemContent:
        """
        Fetch content for a specific file by SHA.
        
        Note: GitLab's blob API by SHA requires the project path.
        """
        if not self.project_path:
            raise BadRequestError("Missing project_path in config")
        
        client = await self._get_client()
        encoded_path = self._encode_project_path(self.project_path)
        
        url = f"/projects/{encoded_path}/repository/blobs/{item_id}"
        response = await client.get(url)
        
        if response.status_code != 200:
            raise ExternalServiceError(f"GitLab API error: {response.status_code}")
        
        data = response.json()
        
        # Fetch raw content
        raw_url = f"/projects/{encoded_path}/repository/blobs/{item_id}/raw"
        raw_response = await client.get(raw_url)
        
        if raw_response.status_code != 200:
            raise ExternalServiceError(f"GitLab API error: {raw_response.status_code}")
        
        content = raw_response.text
        
        return ItemContent(
            item=Item(
                id=item_id,
                name=data.get("file_name", ""),
                path=data.get("file_path", ""),
                size=data.get("size"),
            ),
            content=content,
            content_type=self.get_content_type(data.get("file_path", "")),
            language=self.get_language(data.get("file_path", "")),
        )
    
    async def fetch_file_by_path(self, path: str) -> ItemContent:
        """
        Fetch content for a file by path.
        
        This is more convenient than fetch_item when you have the path.
        """
        if not self.project_path:
            raise BadRequestError("Missing project_path in config")
        
        client = await self._get_client()
        encoded_path = self._encode_project_path(self.project_path)
        encoded_file_path = quote(path, safe="")
        
        url = f"/projects/{encoded_path}/repository/files/{encoded_file_path}"
        params = {"ref": self.branch}
        response = await client.get(url, params=params)
        
        if response.status_code != 200:
            raise ExternalServiceError(f"GitLab API error: {response.status_code}")
        
        data = response.json()
        
        # Content is base64 encoded
        import base64
        content = data.get("content", "")
        encoding = data.get("encoding", "base64")
        
        if encoding == "base64":
            try:
                content = base64.b64decode(content).decode("utf-8")
            except Exception:
                content = ""
        
        return ItemContent(
            item=Item(
                id=data.get("blob_id", ""),
                name=data.get("file_name", ""),
                path=path,
                size=data.get("size"),
            ),
            content=content,
            content_type=self.get_content_type(path),
            language=self.get_language(path),
        )
    
    async def register_webhook(self, callback_url: str) -> str:
        """Register a GitLab webhook."""
        if not self.project_path:
            raise BadRequestError("Missing project_path in config")
        
        client = await self._get_client()
        encoded_path = self._encode_project_path(self.project_path)
        
        response = await client.post(
            f"/projects/{encoded_path}/hooks",
            json={
                "url": callback_url,
                "push_events": True,
                "merge_requests_events": True,
                "enable_ssl_verification": True,
            },
        )
        
        if response.status_code not in (200, 201):
            raise ExternalServiceError(f"Failed to register webhook: {response.text}")
        
        data = response.json()
        return str(data.get("id", ""))
    
    async def handle_webhook(self, payload: dict[str, Any]) -> list[ChangeEvent]:
        """Parse GitLab webhook payload into change events."""
        events = []
        
        # Handle push events
        object_kind = payload.get("object_kind", "")
        
        if object_kind == "push":
            for commit in payload.get("commits", []):
                for path in commit.get("added", []):
                    events.append(ChangeEvent(
                        item_id=path,
                        change_type="created",
                        cursor=commit.get("id"),
                    ))
                for path in commit.get("modified", []):
                    events.append(ChangeEvent(
                        item_id=path,
                        change_type="updated",
                        cursor=commit.get("id"),
                    ))
                for path in commit.get("removed", []):
                    events.append(ChangeEvent(
                        item_id=path,
                        change_type="deleted",
                        cursor=commit.get("id"),
                    ))
        
        return events
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
