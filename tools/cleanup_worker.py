"""
ConHub Data Connector - Cleanup Worker

Background worker for chunk storage maintenance.
Handles:
- Stale MongoDB document cleanup (backup for TTL index)
- Tenant retirement bulk deletion
- Orphaned chunk cleanup (missing Neo4j references)
"""

import asyncio
from datetime import datetime, timedelta
from typing import Optional

import structlog
from sqlalchemy import delete, select

from app.config import settings
from db import get_session
from db.mongodb import cleanup_expired_chunks, delete_tenant_chunks, get_chunk_stats
from services.chunk_service import Chunk

logger = structlog.get_logger(__name__)


async def cleanup_stale_chunks() -> dict:
    """
    Run cleanup for stale and orphaned chunks.
    
    Returns:
        Stats about what was cleaned up
    """
    stats = {
        "mongodb_expired": 0,
        "orphaned_chunks": 0,
        "start_time": datetime.utcnow().isoformat(),
    }
    
    # 1. Cleanup expired MongoDB documents (backup for TTL index)
    if settings.chunk_store_mode == "mongo-ttl":
        try:
            stats["mongodb_expired"] = await cleanup_expired_chunks()
        except Exception as e:
            logger.error("MongoDB cleanup failed", error=str(e))
    
    # 2. Cleanup orphaned Postgres chunks (no Neo4j reference after 24h)
    try:
        async with get_session() as session:
            cutoff = datetime.utcnow() - timedelta(hours=24)
            
            # Find chunks that are still pending after 24 hours
            # These likely failed to embed and can be retried or removed
            stmt = select(Chunk).where(
                Chunk.embedding_state == "pending",
                Chunk.created_at < cutoff,
            )
            result = await session.execute(stmt)
            stale_chunks = result.scalars().all()
            
            if stale_chunks:
                logger.warning(
                    "Found stale pending chunks",
                    count=len(stale_chunks),
                )
                # Mark for retry or delete based on policy
                # For now, just log them
                stats["stale_pending"] = len(stale_chunks)
    except Exception as e:
        logger.error("Orphan cleanup failed", error=str(e))
    
    stats["end_time"] = datetime.utcnow().isoformat()
    return stats


async def retire_tenant(tenant_id: str) -> dict:
    """
    Remove all data for a tenant.
    Used during tenant offboarding.
    
    Args:
        tenant_id: Tenant to retire
        
    Returns:
        Deletion stats
    """
    logger.info("Starting tenant retirement", tenant_id=tenant_id)
    
    stats = {
        "tenant_id": tenant_id,
        "mongodb_deleted": 0,
        "postgres_deleted": 0,
    }
    
    # 1. Delete from MongoDB
    if settings.chunk_store_mode == "mongo-ttl":
        try:
            stats["mongodb_deleted"] = await delete_tenant_chunks(tenant_id)
        except Exception as e:
            logger.error("MongoDB tenant deletion failed", tenant_id=tenant_id, error=str(e))
    
    # 2. Delete from Postgres
    try:
        async with get_session() as session:
            stmt = delete(Chunk).where(Chunk.tenant_id == tenant_id)
            result = await session.execute(stmt)
            await session.commit()
            stats["postgres_deleted"] = result.rowcount
    except Exception as e:
        logger.error("Postgres tenant deletion failed", tenant_id=tenant_id, error=str(e))
    
    logger.info("Tenant retirement complete", **stats)
    return stats


async def get_storage_stats(tenant_id: Optional[str] = None) -> dict:
    """
    Get storage statistics.
    
    Args:
        tenant_id: Optional tenant filter
        
    Returns:
        Storage stats
    """
    stats = {"tenant_id": tenant_id}
    
    # MongoDB stats
    if settings.chunk_store_mode == "mongo-ttl":
        try:
            mongo_stats = await get_chunk_stats(tenant_id)
            stats["mongodb"] = mongo_stats
        except Exception as e:
            stats["mongodb_error"] = str(e)
    
    # Postgres stats
    try:
        async with get_session() as session:
            from sqlalchemy import func
            
            stmt = select(func.count(Chunk.id))
            if tenant_id:
                stmt = stmt.where(Chunk.tenant_id == tenant_id)
            result = await session.execute(stmt)
            stats["postgres_chunks"] = result.scalar()
            
            # Count by embedding state
            stmt = select(
                Chunk.embedding_state,
                func.count(Chunk.id)
            ).group_by(Chunk.embedding_state)
            if tenant_id:
                stmt = stmt.where(Chunk.tenant_id == tenant_id)
            result = await session.execute(stmt)
            stats["by_state"] = dict(result.all())
    except Exception as e:
        stats["postgres_error"] = str(e)
    
    return stats


async def run_worker_loop(interval_minutes: int = 60) -> None:
    """
    Run cleanup worker in a loop.
    
    Args:
        interval_minutes: Minutes between cleanup runs
    """
    logger.info("Starting cleanup worker", interval=interval_minutes)
    
    while True:
        try:
            stats = await cleanup_stale_chunks()
            logger.info("Cleanup cycle complete", **stats)
        except Exception as e:
            logger.error("Cleanup cycle failed", error=str(e))
        
        await asyncio.sleep(interval_minutes * 60)


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    """Run cleanup as CLI command."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Chunk storage cleanup worker")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=60, help="Interval in minutes")
    parser.add_argument("--retire-tenant", type=str, help="Retire a specific tenant")
    parser.add_argument("--stats", action="store_true", help="Show storage stats")
    
    args = parser.parse_args()
    
    async def run():
        if args.retire_tenant:
            result = await retire_tenant(args.retire_tenant)
            print(f"Retired tenant: {result}")
        elif args.stats:
            result = await get_storage_stats()
            print(f"Storage stats: {result}")
        elif args.once:
            result = await cleanup_stale_chunks()
            print(f"Cleanup result: {result}")
        else:
            await run_worker_loop(args.interval)
    
    asyncio.run(run())


if __name__ == "__main__":
    main()
