"""
ConHub Data Connector - Chunker Client

HTTP client for communicating with the chunker service.
Ported from Rust clients/chunker.rs.
"""

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


class ChunkerClient:
    """Client for communicating with the chunker service."""
    
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = base_url or settings.chunker_service_url
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=60.0,
                headers={"Content-Type": "application/json"},
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
