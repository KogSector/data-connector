"""Initial schema - connectors, sync_jobs, file_blobs, webhook_events

Revision ID: 001_initial_schema
Revises: 
Create Date: 2024-12-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Connectors table
    op.create_table(
        "connectors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("config_json", JSONB, nullable=False, server_default="{}"),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("last_sync_cursor", sa.Text, nullable=True),
        sa.Column("last_sync_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    # Sync jobs table
    op.create_table(
        "sync_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("connector_id", UUID(as_uuid=True), sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("stats_json", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
    )
    
    # File blobs table
    op.create_table(
        "file_blobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("connector_id", UUID(as_uuid=True), sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(255), nullable=False, index=True),
        sa.Column("file_id", sa.String(255), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("blob_url", sa.Text, nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    # Webhook events table
    op.create_table(
        "webhook_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("connector_id", UUID(as_uuid=True), sa.ForeignKey("connectors.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=True),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("signature", sa.String(255), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("webhook_events")
    op.drop_table("file_blobs")
    op.drop_table("sync_jobs")
    op.drop_table("connectors")
