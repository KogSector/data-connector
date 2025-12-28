"""
ConHub Data Connector - GitHub Connector

GitHub connector implementation ported from Rust domain/connectors/github.rs.
"""

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

import httpx
import structlog

from app.exceptions import BadRequestError, ConnectorError, ExternalServiceError
from app.schemas import ConnectorType, ContentType, SourceKind
from connectors.base import BaseConnector, ChangeEvent, Item, ItemContent

logger = structlog.get_logger(__name__)


@dataclass
class SyncOptions:
    """Filtering options for GitHub sync (ported from Rust)."""
    include_languages: list[str] = field(default_factory=list)
    exclude_paths: list[str] = field(default_factory=list)
    max_file_size_mb: Optional[float] = None
    
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SyncOptions":
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


class GitHubConnector(BaseConnector):
    """GitHub connector for fetching repository content."""
    
    def __init__(
        self,
        config: dict[str, Any],
        tenant_id: str,
        connector_id: Optional[UUID] = None,
        access_token: Optional[str] = None,
    ):
        super().__init__(
            connector_type=ConnectorType.GITHUB,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
        )
        self.access_token = access_token
        self.sync_options = SyncOptions.from_config(config)
        self.repository = config.get("repository", "")
        self.branch = config.get("branch", "main")
        
        # HTTP client
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.CODE_REPO
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "ConHub-DataConnector/1.0",
            }
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            
            self._client = httpx.AsyncClient(
                base_url="https://api.github.com",
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
        """Return GitHub OAuth URL."""
        # OAuth is handled externally via auth service
        return "https://github.com/login/oauth/authorize"
    
    async def refresh_token(self) -> str:
        """Refresh not typically needed for GitHub (tokens don't expire)."""
        return self.access_token or ""
    
    async def validate_access(self) -> bool:
        """Validate access to the repository."""
        if not self.repository:
            return False
        
        client = await self._get_client()
        try:
            response = await client.get(f"/repos/{self.repository}")
            return response.status_code == 200
        except Exception as e:
            logger.warning("Failed to validate GitHub access", error=str(e))
            return False
    
    async def list_items(
        self,
        cursor: Optional[str] = None,
    ) -> tuple[list[Item], Optional[str]]:
        """
        List all files in the repository.
        
        Uses the Git Tree API for efficient listing.
        Returns all items at once (no pagination needed for tree API).
        """
        if not self.repository:
            raise BadRequestError("Missing repository in config")
        
        client = await self._get_client()
        
        # Get repository tree
        url = f"/repos/{self.repository}/git/trees/{self.branch}?recursive=1"
        response = await client.get(url)
        
        if response.status_code != 200:
            raise ExternalServiceError(f"GitHub API error: {response.status_code} - {response.text}")
        
        data = response.json()
        tree = data.get("tree", [])
        
        items = []
        for node in tree:
            # Only process files (blobs), not directories (trees)
            if node.get("type") != "blob":
                continue
            
            path = node.get("path", "")
            size = node.get("size", 0)
            
            # Skip binary files
            if self.is_binary_file(path):
                continue
            
            # Apply sync options filtering
            if not self.sync_options.should_include(path, size):
                continue
            
            items.append(Item(
                id=node.get("sha", ""),
                name=path.rsplit("/", 1)[-1],
                path=path,
                item_type="file",
                size=size,
                metadata={
                    "sha": node.get("sha"),
                    "repository": self.repository,
                    "branch": self.branch,
                },
            ))
        
        logger.info(
            "Listed GitHub repository files",
            repository=self.repository,
            branch=self.branch,
            file_count=len(items),
        )
        
        # Tree API returns all files at once, no pagination
        return items, None
    
    async def fetch_item(self, item_id: str) -> ItemContent:
        """
        Fetch content for a specific file.
        
        Args:
            item_id: The file SHA (blob ID).
            
        Returns:
            ItemContent with file content.
        """
        if not self.repository:
            raise BadRequestError("Missing repository in config")
        
        client = await self._get_client()
        
        # Find the file path from metadata (need to list items first)
        # Alternative: use the blob API directly which accepts SHA
        url = f"/repos/{self.repository}/git/blobs/{item_id}"
        response = await client.get(url)
        
        if response.status_code != 200:
            raise ExternalServiceError(f"GitHub API error: {response.status_code}")
        
        data = response.json()
        
        # Content is base64 encoded
        import base64
        content = data.get("content", "")
        encoding = data.get("encoding", "base64")
        
        if encoding == "base64":
            try:
                content = base64.b64decode(content).decode("utf-8")
            except Exception:
                # Binary file or encoding issue
                content = content
        
        # We don't have the path here, so we can't determine content type
        # In practice, you'd store path in the Item and pass it through
        return ItemContent(
            item=Item(id=item_id, name="", path=""),
            content=content,
            content_type=ContentType.UNKNOWN,
        )
    
    async def fetch_file_by_path(self, path: str) -> ItemContent:
        """
        Fetch content for a file by path.
        
        This is more convenient than fetch_item when you have the path.
        """
        if not self.repository:
            raise BadRequestError("Missing repository in config")
        
        client = await self._get_client()
        
        url = f"/repos/{self.repository}/contents/{path}?ref={self.branch}"
        response = await client.get(url)
        
        if response.status_code != 200:
            raise ExternalServiceError(f"GitHub API error: {response.status_code}")
        
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
                id=data.get("sha", ""),
                name=data.get("name", ""),
                path=path,
                size=data.get("size"),
            ),
            content=content,
            content_type=self.get_content_type(path),
            language=self.get_language(path),
        )
    
    async def register_webhook(self, callback_url: str) -> str:
        """Register a GitHub webhook."""
        if not self.repository:
            raise BadRequestError("Missing repository in config")
        
        client = await self._get_client()
        
        response = await client.post(
            f"/repos/{self.repository}/hooks",
            json={
                "name": "web",
                "active": True,
                "events": ["push", "pull_request"],
                "config": {
                    "url": callback_url,
                    "content_type": "json",
                },
            },
        )
        
        if response.status_code not in (200, 201):
            raise ExternalServiceError(f"Failed to register webhook: {response.text}")
        
        data = response.json()
        return str(data.get("id", ""))
    
    async def handle_webhook(self, payload: dict[str, Any]) -> list[ChangeEvent]:
        """Parse GitHub webhook payload into change events."""
        events = []
        
        # Handle push events
        if "commits" in payload:
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
