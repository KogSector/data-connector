"""
ConHub Data Connector - Sync Service

Sync orchestrator ported from Rust domain/sync.rs.
"""

from datetime import datetime, timezone
from typing import Optional
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


class SyncService:
    """
    Sync orchestrator for managing data source synchronization.
    
    Ported from Rust SyncOrchestrator.
    """
    
    def __init__(self, db: Optional[AsyncSession] = None):
        self.db = db
        self.chunker_client = get_chunker_client()
    
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
