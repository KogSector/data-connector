"""
ConHub Data Connector - Webhook Routes

Webhook receiver and chunker callback endpoints.
"""

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequestError, NotFoundError
from app.schemas import ChunkerCallback
from db import get_db
from db.models import Connector as ConnectorModel
from db.models import WebhookEvent as WebhookEventModel

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.post("/webhook/{connector_type}", status_code=202)
async def receive_webhook(
    connector_type: str,
    request: Request,
    x_hub_signature: str = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: str = Header(None, alias="X-GitHub-Event"),
    x_gitlab_event: str = Header(None, alias="X-Gitlab-Event"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Generic webhook receiver for provider events.
    
    Receives webhook events from providers (GitHub, GitLab, etc.),
    validates the signature, and enqueues for processing.
    """
    # Parse raw payload
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw_body": (await request.body()).decode("utf-8", errors="replace")}
    
    logger.info(
        "Received webhook",
        connector_type=connector_type,
        event_type=x_github_event or x_gitlab_event,
        has_signature=bool(x_hub_signature),
    )
    
    # Determine event type from headers
    event_type = x_github_event or x_gitlab_event or payload.get("event_type")
    
    # Find matching connector(s)
    # In production, you'd use webhook secret to identify the connector
    # For now, we'll create a generic webhook event
    
    # Create webhook event record
    webhook_event = WebhookEventModel(
        connector_id=UUID("00000000-0000-0000-0000-000000000000"),  # Placeholder
        provider=connector_type,
        event_type=event_type,
        payload=payload,
        signature=x_hub_signature,
        status="pending",
    )
    
    # TODO: Match webhook to specific connector using webhook secret
    # TODO: Validate signature using HMAC
    # TODO: Enqueue Celery task for processing
    
    db.add(webhook_event)
    await db.flush()
    
    return {
        "status": "accepted",
        "event_id": str(webhook_event.id),
        "message": "Webhook received and queued for processing",
    }


@router.post("/data-connector/chunker-callbacks", status_code=200)
async def chunker_callback(
    body: ChunkerCallback,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Callback endpoint for chunker service.
    
    Receives processed chunks from the chunker and forwards them
    to embeddings and graph services.
    """
    logger.info(
        "Received chunker callback",
        job_id=body.job_id,
        parent_file_id=body.parent_file_id,
        chunk_count=len(body.chunks),
        connector_id=body.connector_id,
    )
    
    # Validate connector exists if provided
    if body.connector_id:
        try:
            connector_uuid = UUID(body.connector_id)
            result = await db.execute(
                select(ConnectorModel).where(ConnectorModel.id == connector_uuid)
            )
            connector = result.scalar_one_or_none()
            
            if not connector:
                logger.warning("Connector not found for callback", connector_id=body.connector_id)
        except ValueError:
            logger.warning("Invalid connector_id format", connector_id=body.connector_id)
    
    # TODO: Forward chunks to embeddings service
    # TODO: Forward chunks to graph service
    # TODO: Update sync job stats
    
    # Log any errors from chunker
    if body.errors:
        for error in body.errors:
            logger.error("Chunker error", error=error)
    
    return {
        "status": "received",
        "chunks_processed": len(body.chunks),
        "job_id": body.job_id,
    }
