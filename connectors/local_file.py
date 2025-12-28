"""
ConHub Data Connector - Local File Connector

Local file system connector ported from Rust domain/connectors/local_file.rs.
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

import structlog

from app.exceptions import BadRequestError, NotFoundError
from app.schemas import ConnectorType, ContentType, SourceKind
from connectors.base import BaseConnector, Item, ItemContent

logger = structlog.get_logger(__name__)


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
}


class LocalFileConnector(BaseConnector):
    """Local file system connector for syncing local directories."""
    
    def __init__(
        self,
        config: dict[str, Any],
        tenant_id: str,
        connector_id: Optional[UUID] = None,
    ):
        super().__init__(
            connector_type=ConnectorType.LOCAL_FILE,
            config=config,
            tenant_id=tenant_id,
            connector_id=connector_id,
        )
        self.base_path = Path(config.get("path", "."))
        self.include_extensions = config.get("include_extensions", [])
        self.exclude_patterns = config.get("exclude_patterns", [])
    
    @property
    def source_kind(self) -> SourceKind:
        return SourceKind.DOCUMENT
    
    @staticmethod
    def get_content_type(path: Path) -> ContentType:
        """Determine content type from file extension."""
        ext = path.suffix.lstrip(".").lower()
        if ext in CONTENT_TYPE_MAP:
            return CONTENT_TYPE_MAP[ext]
        if ext in CODE_EXTENSIONS:
            return ContentType.CODE
        return ContentType.UNKNOWN
    
    @staticmethod
    def get_language(path: Path) -> Optional[str]:
        """Detect programming language from file extension."""
        ext = path.suffix.lstrip(".").lower()
        return LANGUAGE_MAP.get(ext)
    
    @staticmethod
    def should_skip(path: Path) -> bool:
        """Check if file should be skipped (binary files, etc.)."""
        ext = path.suffix.lstrip(".").lower()
        return ext in BINARY_EXTENSIONS
    
    def _is_hidden(self, path: Path) -> bool:
        """Check if any component of the path is hidden (starts with .)."""
        for part in path.parts:
            if part.startswith("."):
                return True
        return False
    
    async def authorize(self) -> str:
        """Local files don't require authorization."""
        return "local"
    
    async def refresh_token(self) -> str:
        """Local files don't require tokens."""
        return ""
    
    async def validate_access(self) -> bool:
        """Validate access to the local path."""
        return self.base_path.exists() and self.base_path.is_dir()
    
    async def list_items(
        self,
        cursor: Optional[str] = None,
    ) -> tuple[list[Item], Optional[str]]:
        """
        List all files in the local directory.
        
        Recursively walks the directory tree and returns all files.
        """
        if not self.base_path.exists():
            raise NotFoundError(f"Path does not exist: {self.base_path}")
        
        items = []
        
        for root, dirs, files in os.walk(self.base_path, followlinks=True):
            root_path = Path(root)
            
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            
            for filename in files:
                file_path = root_path / filename
                
                # Skip hidden files
                if filename.startswith("."):
                    continue
                
                # Skip binary files
                if self.should_skip(file_path):
                    continue
                
                # Get relative path
                try:
                    relative_path = file_path.relative_to(self.base_path)
                except ValueError:
                    relative_path = file_path
                
                # Get file stats
                try:
                    stat = file_path.stat()
                    size = stat.st_size
                    modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
                except OSError:
                    size = 0
                    modified_at = None
                
                items.append(Item(
                    id=str(file_path.absolute()),
                    name=filename,
                    path=str(relative_path),
                    item_type="file",
                    size=size,
                    metadata={
                        "base_path": str(self.base_path),
                        "relative_path": str(relative_path),
                        "absolute_path": str(file_path.absolute()),
                    },
                    updated_at=modified_at,
                ))
        
        logger.info(
            "Listed local files",
            base_path=str(self.base_path),
            file_count=len(items),
        )
        
        # Local file listing returns all files at once
        return items, None
    
    async def fetch_item(self, item_id: str) -> ItemContent:
        """
        Fetch content for a specific file.
        
        Args:
            item_id: The absolute file path.
            
        Returns:
            ItemContent with file content.
        """
        file_path = Path(item_id)
        
        if not file_path.exists():
            raise NotFoundError(f"File not found: {item_id}")
        
        if not file_path.is_file():
            raise BadRequestError(f"Not a file: {item_id}")
        
        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Try with different encoding or skip
            try:
                content = file_path.read_text(encoding="latin-1")
            except Exception:
                content = ""
        except Exception as e:
            logger.warning("Failed to read file", path=item_id, error=str(e))
            content = ""
        
        # Get relative path
        try:
            relative_path = file_path.relative_to(self.base_path)
        except ValueError:
            relative_path = file_path
        
        return ItemContent(
            item=Item(
                id=item_id,
                name=file_path.name,
                path=str(relative_path),
                size=len(content.encode("utf-8")),
            ),
            content=content,
            content_type=self.get_content_type(file_path),
            language=self.get_language(file_path),
        )
