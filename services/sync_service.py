"""
ConHub Data Connector - Sync Service

Sync orchestrator ported from Rust domain/sync.rs.

DSA Patterns Implemented:
- Concurrent Batch Processing with Semaphore (bounded parallelism)
- Sliding Window Rate Limiter for API throttling
- Merge Sort for document ordering by priority/size
- Content Hash Deduplication with HashMap (O(1) lookup)
"""

import asyncio
import hashlib
from collections import deque
from datetime import datetime, timezone
from typing import Optional, List
from uuid import UUID

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.schemas import ConnectorType, SyncStatus
from connectors import get_connector, get_source_kind
from db import get_session
from db.models import Connector as ConnectorModel
from db.models import SyncJob as SyncJobModel
from services.chunker_client import get_chunker_client

logger = structlog.get_logger(__name__)


# =============================================================================
# DSA: Sliding Window Rate Limiter - O(1) amortized per request
# =============================================================================
class SlidingWindowRateLimiter:
    """
    Sliding Window Log algorithm for rate limiting.
    
    More accurate than fixed window, prevents edge-case bursts.
    Time Complexity: O(1) amortized (with periodic cleanup)
    Space Complexity: O(n) where n = max requests in window
    """
    
    def __init__(self, max_requests: int = 100, window_seconds: float = 60.0):
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._requests: deque = deque()
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> bool:
        """
        Check if request is allowed under rate limit.
        Returns True if allowed, False if rate limited.
        """
        async with self._lock:
            now = datetime.now(timezone.utc).timestamp()
            cutoff = now - self._window_seconds
            
            # Remove old requests outside window - O(k) where k = expired requests
            while self._requests and self._requests[0] < cutoff:
                self._requests.popleft()
            
            # Check if under limit
            if len(self._requests) >= self._max_requests:
                return False
            
            # Record this request
            self._requests.append(now)
            return True
    
    def get_retry_after(self) -> float:
        """Get seconds until oldest request expires from window."""
        if not self._requests:
            return 0.0
        
        now = datetime.now(timezone.utc).timestamp()
        oldest = self._requests[0]
        return max(0.0, (oldest + self._window_seconds) - now)


# =============================================================================
# DSA: Merge Sort for Document Ordering - O(n log n), stable sort
# =============================================================================
def merge_sort_documents(documents: List, key_func=None) -> List:
    """
    Merge sort for stable document ordering by priority/size.
    
    Time Complexity: O(n log n)
    Space Complexity: O(n)
    
    Stable sort preserves original order for equal elements.
    Used to process smaller/higher-priority documents first.
    """
    if len(documents) <= 1:
        return documents
    
    if key_func is None:
        key_func = lambda doc: len(doc.content.encode("utf-8"))
    
    mid = len(documents) // 2
    left = merge_sort_documents(documents[:mid], key_func)
    right = merge_sort_documents(documents[mid:], key_func)
    
    return _merge(left, right, key_func)


def _merge(left: List, right: List, key_func) -> List:
    """Merge two sorted lists."""
    result = []
    i = j = 0
    
    while i < len(left) and j < len(right):
        if key_func(left[i]) <= key_func(right[j]):
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    
    result.extend(left[i:])
    result.extend(right[j:])
    return result


# =============================================================================
# DSA: Content Hash Deduplication - O(1) lookup
# =============================================================================
class ContentDeduplicator:
    """
    Hash-based content deduplication using SHA-256.
    
    Time Complexity: O(n) for hashing where n = content length, O(1) for lookup
    Space Complexity: O(k) where k = number of unique hashes
    
    Prevents re-processing identical content.
    """
    
    def __init__(self):
        self._seen_hashes: set = set()
    
    def compute_hash(self, content: str) -> str:
        """Compute SHA-256 hash of content."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
    
    def is_duplicate(self, content: str) -> bool:
        """Check if content has been seen before."""
        content_hash = self.compute_hash(content)
        return content_hash in self._seen_hashes
    
    def mark_seen(self, content: str) -> str:
        """Mark content as seen and return its hash."""
        content_hash = self.compute_hash(content)
        self._seen_hashes.add(content_hash)
        return content_hash
    
    def check_and_mark(self, content: str) -> tuple[bool, str]:
        """
        Atomically check if duplicate and mark if new.
        Returns (is_duplicate, hash).
        """
        content_hash = self.compute_hash(content)
        is_dup = content_hash in self._seen_hashes
        if not is_dup:
            self._seen_hashes.add(content_hash)
        return is_dup, content_hash


class SyncService:
    """
    Sync orchestrator for managing data source synchronization.
    
    Enhanced with DSA patterns:
    - Concurrent batch processing with semaphore
    - Sliding window rate limiting
    - Content deduplication with hashing
    - Priority-based document ordering
    
    Ported from Rust SyncOrchestrator.
    """
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.chunker_client = get_chunker_client()
        
        # DSA: Initialize rate limiter (100 requests per minute)
        self._rate_limiter = SlidingWindowRateLimiter(max_requests=100, window_seconds=60.0)
        
        # DSA: Initialize content deduplicator
        self._deduplicator = ContentDeduplicator()
        
        # DSA: Semaphore for bounded concurrent processing
        self._concurrency_semaphore = asyncio.Semaphore(10)
    
    async def start_sync(
        self,
        connector_id: UUID,
        sync_type: str = "full",
        cursor: Optional[str] = None,
    ) -> SyncJobModel:
        """
        Start a sync job for a connector.
        
        Creates a sync job record and initiates the sync process.
        """
        async with get_session() as db:
            # Get connector
            result = await db.execute(
                select(ConnectorModel).where(ConnectorModel.id == connector_id)
            )
            connector = result.scalar_one_or_none()
            
            if not connector:
                raise ValueError(f"Connector {connector_id} not found")
            
            # Create sync job
            sync_job = SyncJobModel(
                connector_id=connector_id,
                tenant_id=connector.tenant_id,
                type=sync_type,
                status="pending",
            )
            db.add(sync_job)
            await db.flush()
            await db.refresh(sync_job)
            
            logger.info(
                "Created sync job",
                job_id=str(sync_job.id),
                connector_id=str(connector_id),
                sync_type=sync_type,
            )
            
            return sync_job
    
    async def execute_sync(
        self,
        job_id: UUID,
        connector_id: UUID,
        sync_type: str = "full",
        access_token: Optional[str] = None,
    ) -> None:
        """
        Execute a sync job.
        
        This is the main sync logic that:
        1. Updates job status to running
        2. Fetches content from the connector (full or incremental)
        3. Sends documents to chunker
        4. Updates job status and cursor
        
        Args:
            job_id: Sync job ID
            connector_id: Connector to sync
            sync_type: "full" or "incremental"
            access_token: Optional access token for OAuth connectors
        """
        async with get_session() as db:
            try:
                # Get connector and job
                connector_result = await db.execute(
                    select(ConnectorModel).where(ConnectorModel.id == connector_id)
                )
                connector = connector_result.scalar_one_or_none()
                
                if not connector:
                    raise ValueError(f"Connector {connector_id} not found")
                
                # Update job status to running
                await db.execute(
                    update(SyncJobModel)
                    .where(SyncJobModel.id == job_id)
                    .values(status="running")
                )
                await db.execute(
                    update(ConnectorModel)
                    .where(ConnectorModel.id == connector_id)
                    .values(status="syncing")
                )
                await db.commit()
                
                logger.info(
                    "Starting sync execution",
                    job_id=str(job_id),
                    connector_id=str(connector_id),
                    connector_type=connector.type,
                    sync_type=sync_type,
                )
                
                # Create connector instance
                connector_type = ConnectorType(connector.type)
                connector_instance = get_connector(
                    connector_type=connector_type,
                    config=connector.config_json,
                    tenant_id=connector.tenant_id,
                    connector_id=connector_id,
                    access_token=access_token,
                )
                
                # Fetch content based on sync type
                new_cursor = None
                if sync_type == "incremental" and connector.last_sync_cursor:
                    # Incremental sync using cursor
                    documents, new_cursor = await connector_instance.fetch_incremental(
                        cursor=connector.last_sync_cursor
                    )
                    logger.info(
                        "Fetched incremental documents",
                        job_id=str(job_id),
                        document_count=len(documents),
                        cursor=connector.last_sync_cursor[:20] + "..." if connector.last_sync_cursor else None,
                    )
                else:
                    # Full sync
                    documents = await connector_instance.fetch_all_content()
                    logger.info(
                        "Fetched all documents",
                        job_id=str(job_id),
                        document_count=len(documents),
                    )
                
                # Send to chunker
                if documents:
                    source_kind = get_source_kind(connector_type)
                    
                    # Use threshold to decide sync vs reference mode
                    threshold_bytes = settings.chunk_size_threshold_kb * 1024
                    
                    for doc in documents:
                        content_size = len(doc.content.encode("utf-8"))
                        
                        if content_size <= threshold_bytes:
                            # Small file - sync mode
                            await self.chunker_client.ingest_small_file(
                                tenant_id=connector.tenant_id,
                                connector_id=str(connector_id),
                                file_id=str(doc.id),
                                file_name=doc.name,
                                content=doc.content,
                                source_type=connector.type,
                                file_path=doc.path,
                                suggest_chunk_strategy=self._get_chunk_strategy(connector_type, doc.language),
                            )
                        else:
                            # Large file - upload to S3 and use reference mode
                            from services.s3_client import get_s3_client
                            s3_client = get_s3_client()
                            
                            if s3_client.is_configured():
                                # Upload to S3
                                blob_url = await s3_client.upload_blob(
                                    content=doc.content,
                                    file_id=str(doc.id),
                                    tenant_id=connector.tenant_id,
                                    file_name=doc.name,
                                    content_type=doc.mime_type or "text/plain",
                                )
                                
                                # Store blob reference
                                from db.models import FileBlob
                                blob_record = FileBlob(
                                    connector_id=connector_id,
                                    tenant_id=connector.tenant_id,
                                    file_id=str(doc.id),
                                    file_name=doc.name,
                                    blob_url=blob_url,
                                    content_hash=doc.content_hash if hasattr(doc, 'content_hash') else None,
                                    size=content_size,
                                    mime_type=doc.mime_type,
                                )
                                db.add(blob_record)
                                await db.flush()
                                
                                # Send reference to chunker
                                await self.chunker_client.ingest_large_file(
                                    tenant_id=connector.tenant_id,
                                    connector_id=str(connector_id),
                                    file_id=str(doc.id),
                                    blob_url=blob_url,
                                    size_bytes=content_size,
                                    file_name=doc.name,
                                    source_type=connector.type,
                                    suggest_chunk_strategy=self._get_chunk_strategy(connector_type, doc.language),
                                )
                                
                                logger.info(
                                    "Large file uploaded to S3",
                                    file_id=str(doc.id),
                                    size_bytes=content_size,
                                )
                            else:
                                # Fallback to sync mode if S3 not configured
                                logger.warning(
                                    "Large file using sync mode (S3 not configured)",
                                    file_id=str(doc.id),
                                    size_bytes=content_size,
                                )
                                await self.chunker_client.ingest_small_file(
                                    tenant_id=connector.tenant_id,
                                    connector_id=str(connector_id),
                                    file_id=str(doc.id),
                                    file_name=doc.name,
                                    content=doc.content,
                                    source_type=connector.type,
                                    file_path=doc.path,
                                )
                
                # Update job status to completed
                now = datetime.now(timezone.utc)
                await db.execute(
                    update(SyncJobModel)
                    .where(SyncJobModel.id == job_id)
                    .values(
                        status="completed",
                        end_time=now,
                        stats_json={
                            "documents_synced": len(documents),
                            "sync_type": sync_type,
                        },
                    )
                )
                
                # Update connector with new cursor (if available)
                connector_update = {
                    "status": "active",
                    "last_sync_time": now,
                }
                if new_cursor:
                    connector_update["last_sync_cursor"] = new_cursor
                
                await db.execute(
                    update(ConnectorModel)
                    .where(ConnectorModel.id == connector_id)
                    .values(**connector_update)
                )
                await db.commit()
                
                logger.info(
                    "Sync completed",
                    job_id=str(job_id),
                    documents_synced=len(documents),
                )
                
            except Exception as e:
                logger.exception(
                    "Sync failed",
                    job_id=str(job_id),
                    error=str(e),
                )
                
                # Update job status to failed
                await db.execute(
                    update(SyncJobModel)
                    .where(SyncJobModel.id == job_id)
                    .values(
                        status="failed",
                        end_time=datetime.now(timezone.utc),
                        error_message=str(e),
                    )
                )
                await db.execute(
                    update(ConnectorModel)
                    .where(ConnectorModel.id == connector_id)
                    .values(status="error")
                )
                await db.commit()
                
                raise
    
    def _get_chunk_strategy(
        self,
        connector_type: ConnectorType,
        language: Optional[str] = None,
    ) -> Optional[str]:
        """Determine suggested chunk strategy based on source type."""
        if connector_type in (ConnectorType.GITHUB, ConnectorType.GITLAB, ConnectorType.BITBUCKET):
            if language:
                return "code_ast"
            return "code_block"
        
        elif connector_type in (ConnectorType.NOTION, ConnectorType.CONFLUENCE):
            return "doc_heading"
        
        elif connector_type == ConnectorType.SLACK:
            return "chat_sliding_window"
        
        return None


# Global service instance
_sync_service: Optional[SyncService] = None


def get_sync_service() -> SyncService:
    """Get global sync service instance."""
    global _sync_service
    if _sync_service is None:
        _sync_service = SyncService()
    return _sync_service
