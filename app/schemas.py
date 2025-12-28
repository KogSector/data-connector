"""
ConHub Data Connector - Pydantic Schemas

Data models and schemas matching the OpenAPI spec and Rust domain models.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# =============================================================================
# Enums (ported from Rust domain/models.rs)
# =============================================================================

class ConnectorType(str, Enum):
    """Types of connectors supported by the system."""
    LOCAL_FILE = "local_file"
    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    GOOGLE_DRIVE = "google_drive"
    DROPBOX = "dropbox"
    ONEDRIVE = "onedrive"
    SLACK = "slack"
    NOTION = "notion"
    CONFLUENCE = "confluence"
    URL_SCRAPER = "url_scraper"


class ContentType(str, Enum):
    """Content types for documents."""
    TEXT = "text"
    CODE = "code"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    XML = "xml"
    YAML = "yaml"
    BINARY = "binary"
    UNKNOWN = "unknown"


class SourceKind(str, Enum):
    """Source kinds for the chunker service."""
    CODE_REPO = "code_repo"
    DOCUMENT = "document"
    CHAT = "chat"
    TICKETING = "ticketing"
    WIKI = "wiki"
    EMAIL = "email"
    WEB = "web"
    OTHER = "other"


class SyncType(str, Enum):
    """Types of sync operations."""
    FULL = "full"
    INCREMENTAL = "incremental"
    WEBHOOK = "webhook"


class SyncStatus(str, Enum):
    """Status of a sync job or connector."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ConnectorStatus(str, Enum):
    """Status of a connector."""
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class Priority(str, Enum):
    """Priority levels for sync and ingestion."""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


# =============================================================================
# Connector Schemas (matching OpenAPI spec)
# =============================================================================

class ConnectorConfig(BaseModel):
    """Provider-specific configuration stored encrypted."""
    class Config:
        extra = "allow"


class ConnectorCreate(BaseModel):
    """Request body for creating a connector."""
    tenant_id: str
    type: ConnectorType
    name: str
    config: Optional[dict[str, Any]] = Field(default_factory=dict)
    metadata: Optional[dict[str, Any]] = None


class Connector(BaseModel):
    """Connector response model."""
    id: UUID
    tenant_id: str
    type: ConnectorType
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: Optional[dict[str, Any]] = None
    status: ConnectorStatus = ConnectorStatus.ACTIVE
    created_at: datetime
    last_sync_cursor: Optional[str] = None
    last_sync_time: Optional[datetime] = None


# =============================================================================
# Sync Schemas
# =============================================================================

class SyncRequest(BaseModel):
    """Request body for triggering a sync."""
    type: SyncType
    force: bool = False
    priority: Priority = Priority.NORMAL
    cursor: Optional[str] = None
    params: Optional[dict[str, Any]] = None


class SyncStatusResponse(BaseModel):
    """Response for sync status."""
    connector_id: UUID
    last_sync_time: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    stats: Optional[dict[str, Any]] = None


class SyncJobResponse(BaseModel):
    """Response when sync job is scheduled."""
    job_id: UUID
    status: str


# =============================================================================
# Webhook Schemas
# =============================================================================

class WebhookEvent(BaseModel):
    """Incoming webhook event from provider."""
    connector_type: Optional[str] = None
    provider: Optional[str] = None
    raw: Optional[dict[str, Any]] = None
    signature: Optional[str] = None
    received_at: Optional[datetime] = None


# =============================================================================
# Chunker Schemas (matching OpenAPI spec)
# =============================================================================

class IngestFlags(BaseModel):
    """Flags for ingestion behavior."""
    for_embeddings: bool = True
    for_graph: bool = True
    priority: Priority = Priority.NORMAL


class ChunkIngestRequest(BaseModel):
    """Request to ingest small file contents for immediate chunking."""
    tenant_id: str
    connector_id: str
    source_type: Optional[str] = None
    file_id: str
    file_name: str
    file_path: Optional[str] = None
    file_mime: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    author: Optional[str] = None
    original_timestamp: Optional[datetime] = None
    content: str
    content_hash: Optional[str] = None
    ingest_flags: Optional[IngestFlags] = None
    suggest_chunk_strategy: Optional[str] = None
    size_bytes: Optional[int] = None


class ChunkReferenceRequest(BaseModel):
    """Request to ingest large file by reference (blob URL)."""
    tenant_id: str
    connector_id: str
    source_type: Optional[str] = None
    file_id: str
    file_name: Optional[str] = None
    blob_url: str
    size_bytes: int
    file_mime: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None
    author: Optional[str] = None
    original_timestamp: Optional[datetime] = None
    ingest_flags: Optional[IngestFlags] = None
    suggest_chunk_strategy: Optional[str] = None


class EntityMention(BaseModel):
    """Entity mention in a chunk."""
    name: str
    type: str
    confidence: float = 1.0


class Chunk(BaseModel):
    """A chunk returned by the chunker."""
    chunk_id: str
    parent_file_id: str
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    content: str
    length_tokens: Optional[int] = None
    language: Optional[str] = None
    chunk_strategy: Optional[str] = None
    source_meta: Optional[dict[str, Any]] = None
    ingest_flags: Optional[dict[str, Any]] = None
    entities: Optional[list[EntityMention]] = None
    code_signatures: Optional[list[str]] = None


class ChunkerCallback(BaseModel):
    """Callback from chunker with processed chunks."""
    job_id: str
    parent_file_id: str
    connector_id: Optional[str] = None
    tenant_id: Optional[str] = None
    chunks: list[Chunk]
    stats: Optional[dict[str, Any]] = None
    errors: Optional[list[dict[str, Any]]] = None


# =============================================================================
# Embeddings Schemas
# =============================================================================

class EmbeddingChunk(BaseModel):
    """Chunk to be embedded."""
    id: str
    content: str
    source_meta: Optional[dict[str, Any]] = None
    embedding_profile: Optional[str] = None
    embedding_version: Optional[str] = None


class EmbeddingsBatchRequest(BaseModel):
    """Request for batch embedding."""
    chunks: list[EmbeddingChunk]
    tenant_id: Optional[str] = None
    model_hint: Optional[str] = None
    batch_id: Optional[str] = None


class EmbeddingResponseItem(BaseModel):
    """Single embedding response."""
    id: str
    vector: list[float]
    dimension: int
    model: str
    timestamp: Optional[datetime] = None


class EmbeddingsBatchResponse(BaseModel):
    """Response from batch embedding."""
    embeddings: list[EmbeddingResponseItem]
    stats: Optional[dict[str, Any]] = None


# =============================================================================
# Graph Schemas
# =============================================================================

class GraphChunk(BaseModel):
    """Chunk for graph ingestion."""
    chunk_id: str
    content: str
    source_meta: Optional[dict[str, Any]] = None
    graph_hints: Optional[dict[str, Any]] = None
    provenance: Optional[dict[str, Any]] = None


class GraphIngestRequest(BaseModel):
    """Request for graph chunk ingestion."""
    chunks: list[GraphChunk]
    tenant_id: Optional[str] = None
    batch_id: Optional[str] = None


# =============================================================================
# Internal Models (ported from Rust)
# =============================================================================

class NormalizedDocument(BaseModel):
    """Normalized document model for content from any source."""
    id: UUID
    source_id: UUID
    connector_type: ConnectorType
    external_id: str
    name: str
    path: Optional[str] = None
    content: str
    content_type: ContentType = ContentType.UNKNOWN
    metadata: dict[str, Any] = Field(default_factory=dict)
    block_type: Optional[str] = None
    language: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class SyncJob(BaseModel):
    """A sync job for tracking background sync operations."""
    id: UUID
    source_id: UUID
    user_id: UUID
    status: SyncStatus = SyncStatus.PENDING
    items_processed: int = 0
    items_total: Optional[int] = None
    error: Optional[str] = None
    started_at: datetime
    completed_at: Optional[datetime] = None


# =============================================================================
# Error Schemas
# =============================================================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    code: int
    message: str
    details: Optional[dict[str, Any]] = None
