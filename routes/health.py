"""
ConHub Data Connector - Health Routes

Health check endpoints ported from Rust api/health.rs.
"""

import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from app.config import settings

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, str]:
    """
    Simple health check endpoint.
    
    Returns:
        {"status": "ok"}
    """
    return {"status": "ok"}


@router.get("/status")
async def status() -> dict[str, Any]:
    """
    Extended status endpoint with service information.
    
    Returns service status including uptime, version, and configuration.
    """
    from app.main import APP_START_TIME
    
    uptime_seconds = time.time() - APP_START_TIME if APP_START_TIME > 0 else 0
    
    return {
        "status": "ok",
        "service": "data-connector",
        "version": "1.0.0",
        "uptime_seconds": round(uptime_seconds, 2),
        "started_at": datetime.fromtimestamp(APP_START_TIME, tz=timezone.utc).isoformat() 
            if APP_START_TIME > 0 else None,
        "config": {
            "port": settings.port,
            "debug": settings.debug,
            "embedding_enabled": settings.embedding_enabled,
            "graph_rag_enabled": settings.graph_rag_enabled,
        },
        "services": {
            "auth_service_url": settings.auth_service_url,
            "chunker_service_url": settings.chunker_service_url,
            "embedding_service_url": settings.embedding_service_url,
            "graph_service_url": settings.relation_graph_service_url,
        },
    }
