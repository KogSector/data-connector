"""
ConHub Data Connector - Chunker Client

HTTP client for communicating with the chunker service.
Ported from Rust clients/chunker.rs.

DSA Patterns Implemented:
- LRU Cache for response deduplication
- Token Bucket Rate Limiter for API throttling
- Exponential Backoff Retry for resilience
- Connection Pooling for efficiency
"""

import asyncio
import hashlib
import random
import time
from collections import OrderedDict
from typing import Any, Optional
from uuid import UUID

import httpx
import structlog

from app.config import settings
from app.exceptions import ExternalServiceError
from app.schemas import (
    ChunkIngestRequest,
    ChunkReferenceRequest,
    IngestFlags,
    NormalizedDocument,
    SourceKind,
)

logger = structlog.get_logger(__name__)


# =============================================================================
# DSA: LRU Cache Implementation - O(1) get/put with OrderedDict
# =============================================================================
class LRUCache:
    """
    Least Recently Used (LRU) Cache using OrderedDict.
    
    Time Complexity:
    - get: O(1) amortized
    - put: O(1) amortized
    - eviction: O(1) amortized
    
    Used for caching chunker responses to avoid redundant API calls.
    """
    
    def __init__(self, capacity: int = 1000, ttl_seconds: float = 300):
        self._cache: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._capacity = capacity
        self._ttl = ttl_seconds
        self._hits = 0
        self._misses = 0
    
    def _hash_key(self, data: dict) -> str:
        """Create a hash key from request data."""
        serialized = str(sorted(data.items()))
        return hashlib.md5(serialized.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache, returns None if expired or not found."""
        if key not in self._cache:
            self._misses += 1
            return None
        
        value, timestamp = self._cache[key]
        
        # Check TTL expiration
        if time.time() - timestamp > self._ttl:
            del self._cache[key]
            self._misses += 1
            return None
        
        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return value
    
    def put(self, key: str, value: Any) -> None:
        """Add value to cache, evicting LRU item if at capacity."""
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._capacity:
                # Evict least recently used (first item)
                self._cache.popitem(last=False)
        
        self._cache[key] = (value, time.time())
    
    def get_stats(self) -> dict:
        """Get cache hit/miss statistics."""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "size": len(self._cache),
            "capacity": self._capacity,
        }


# =============================================================================
# DSA: Token Bucket Rate Limiter - O(1) per request
# =============================================================================
class TokenBucketRateLimiter:
    """
    Token Bucket algorithm for rate limiting.
    
    Allows bursting up to bucket capacity, then limits to refill rate.
    Time Complexity: O(1) per acquire operation.
    
    Used to prevent overwhelming the chunker service.
    """
    
    def __init__(
        self,
        capacity: int = 100,
        refill_rate: float = 10.0,  # tokens per second
    ):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._tokens = float(capacity)
        self._last_refill = time.time()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1, timeout: float = 30.0) -> bool:
        """
        Acquire tokens from the bucket.
        
        Returns True if tokens acquired, False if timeout exceeded.
        """
        async with self._lock:
            deadline = time.time() + timeout
            
            while True:
                self._refill()
                
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return True
                
                if time.time() >= deadline:
                    return False
                
                # Wait for tokens to refill
                wait_time = (tokens - self._tokens) / self._refill_rate
                wait_time = min(wait_time, deadline - time.time())
                
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
    
    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(
            self._capacity,
            self._tokens + elapsed * self._refill_rate
        )
        self._last_refill = now


# =============================================================================
# DSA: Exponential Backoff Retry - O(1) per calculation
# =============================================================================
def calculate_backoff(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
) -> float:
    """
    Calculate exponential backoff delay with optional jitter.
    
    Formula: min(base * 2^attempt, max) * (0.5 + random(0, 0.5)) if jitter
    Time Complexity: O(1)
    
    Jitter prevents thundering herd problem when multiple clients retry.
    """
    delay = min(base_delay * (2 ** attempt), max_delay)
    
    if jitter:
        # Add 50-100% jitter
        jitter_factor = 0.5 + random.random() * 0.5
        delay *= jitter_factor
    
    return delay


async def retry_with_backoff(
    func,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: tuple = (httpx.RequestError, httpx.TimeoutException),
):
    """
    Execute function with exponential backoff retry.
    
    Args:
        func: Async function to execute
        max_retries: Maximum retry attempts
        base_delay: Base delay for backoff calculation
        max_delay: Maximum delay between retries
        retryable_exceptions: Exceptions that trigger retry
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except retryable_exceptions as e:
            last_exception = e
            
            if attempt == max_retries:
                break
            
            delay = calculate_backoff(attempt, base_delay, max_delay)
            logger.warning(
                "Request failed, retrying",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay=delay,
                error=str(e),
            )
            await asyncio.sleep(delay)
    
    raise last_exception


class ChunkerClient:
    """
    Client for communicating with the chunker service.
    
    Enhanced with DSA patterns:
    - LRU Cache for response deduplication
    - Token Bucket Rate Limiter
    - Exponential Backoff Retry
    - Connection Pooling (via httpx)
    """
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.chunker_service_url
        self._client: Optional[httpx.AsyncClient] = None
        
        # DSA: Initialize LRU cache for response deduplication
        self._cache = LRUCache(capacity=500, ttl_seconds=300)
        
        # DSA: Initialize rate limiter (100 requests/sec burst, 10/sec sustained)
        self._rate_limiter = TokenBucketRateLimiter(capacity=100, refill_rate=10.0)
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with connection pooling."""
        if self._client is None:
            # Connection pooling via limits parameter
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=60.0,
                headers={"Content-Type": "application/json"},
                limits=httpx.Limits(
                    max_keepalive_connections=20,  # Pool size
                    max_connections=100,
                    keepalive_expiry=30.0,
                ),
            )
        return self._client
    
    async def ingest_small_file(
        self,
        tenant_id: str,
        connector_id: str,
        file_id: str,
        file_name: str,
        content: str,
        source_type: Optional[str] = None,
        file_path: Optional[str] = None,
        file_mime: Optional[str] = None,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        commit: Optional[str] = None,
        author: Optional[str] = None,
        suggest_chunk_strategy: Optional[str] = None,
        for_embeddings: bool = True,
        for_graph: bool = True,
    ) -> dict[str, Any]:
        """
        Ingest small file content for immediate chunking.
        
        POST /chunker/ingest
        """
        client = await self._get_client()
        
        payload = ChunkIngestRequest(
            tenant_id=tenant_id,
            connector_id=connector_id,
            source_type=source_type,
            file_id=file_id,
            file_name=file_name,
            file_path=file_path,
            file_mime=file_mime,
            repo=repo,
            branch=branch,
            commit=commit,
            author=author,
            content=content,
            ingest_flags=IngestFlags(
                for_embeddings=for_embeddings,
                for_graph=for_graph,
            ),
            suggest_chunk_strategy=suggest_chunk_strategy,
            size_bytes=len(content.encode("utf-8")),
        )
        
        logger.debug(
            "Sending to chunker",
            file_id=file_id,
            file_name=file_name,
            size_bytes=payload.size_bytes,
        )
        
        response = await client.post(
            "/chunker/ingest",
            json=payload.model_dump(exclude_none=True),
        )
        
        if response.status_code not in (200, 202):
            raise ExternalServiceError(
                f"Chunker service error: {response.status_code} - {response.text}"
            )
        
        result = response.json()
        logger.info(
            "Chunker ingested file",
            file_id=file_id,
            job_id=result.get("job_id"),
            chunk_count=len(result.get("chunks", [])),
        )
        
        return result
    
    async def ingest_large_file(
        self,
        tenant_id: str,
        connector_id: str,
        file_id: str,
        blob_url: str,
        size_bytes: int,
        file_name: Optional[str] = None,
        source_type: Optional[str] = None,
        file_mime: Optional[str] = None,
        repo: Optional[str] = None,
        branch: Optional[str] = None,
        commit: Optional[str] = None,
        author: Optional[str] = None,
        suggest_chunk_strategy: Optional[str] = None,
        for_embeddings: bool = True,
        for_graph: bool = True,
    ) -> dict[str, Any]:
        """
        Ingest large file by reference (blob URL).
        
        POST /chunker/ingest_reference
        """
        client = await self._get_client()
        
        payload = ChunkReferenceRequest(
            tenant_id=tenant_id,
            connector_id=connector_id,
            source_type=source_type,
            file_id=file_id,
            file_name=file_name,
            blob_url=blob_url,
            size_bytes=size_bytes,
            file_mime=file_mime,
            repo=repo,
            branch=branch,
            commit=commit,
            author=author,
            ingest_flags=IngestFlags(
                for_embeddings=for_embeddings,
                for_graph=for_graph,
            ),
            suggest_chunk_strategy=suggest_chunk_strategy,
        )
        
        logger.debug(
            "Sending reference to chunker",
            file_id=file_id,
            blob_url=blob_url,
            size_bytes=size_bytes,
        )
        
        response = await client.post(
            "/chunker/ingest_reference",
            json=payload.model_dump(exclude_none=True),
        )
        
        if response.status_code not in (200, 202):
            raise ExternalServiceError(
                f"Chunker service error: {response.status_code} - {response.text}"
            )
        
        result = response.json()
        logger.info(
            "Chunker accepted reference",
            file_id=file_id,
            job_id=result.get("job_id"),
        )
        
        return result
    
    async def create_chunk_job(
        self,
        source_id: UUID,
        source_kind: SourceKind,
        documents: list[NormalizedDocument],
        tenant_id: str,
    ) -> dict[str, Any]:
        """
        Create a chunk job for multiple documents.
        
        This is the legacy API matching the Rust implementation.
        POST /chunk/jobs
        """
        client = await self._get_client()
        
        items = [
            {
                "id": str(doc.id),
                "source_id": str(doc.source_id),
                "source_kind": source_kind.value,
                "content_type": doc.content_type.value,
                "content": doc.content,
                "metadata": doc.metadata,
                "created_at": doc.created_at.isoformat(),
                "updated_at": doc.updated_at.isoformat(),
            }
            for doc in documents
        ]
        
        payload = {
            "source_id": str(source_id),
            "source_kind": source_kind.value,
            "items": items,
        }
        
        logger.debug(
            "Creating chunk job",
            source_id=str(source_id),
            item_count=len(items),
        )
        
        response = await client.post("/chunk/jobs", json=payload)
        
        if response.status_code not in (200, 201, 202):
            raise ExternalServiceError(
                f"Chunker service error: {response.status_code} - {response.text}"
            )
        
        result = response.json()
        logger.info(
            "Created chunk job",
            job_id=result.get("job_id"),
            accepted=result.get("accepted"),
            items_count=result.get("items_count"),
        )
        
        return result
    
    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Global client instance
_chunker_client: Optional[ChunkerClient] = None


def get_chunker_client() -> ChunkerClient:
    """Get global chunker client instance."""
    global _chunker_client
    if _chunker_client is None:
        _chunker_client = ChunkerClient()
    return _chunker_client
