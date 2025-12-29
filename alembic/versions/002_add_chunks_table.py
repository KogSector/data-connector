"""Add chunks table for minimal metadata storage

Revision ID: 002_add_chunks_table
Revises: 001_initial_schema
Create Date: 2024-12-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "002_add_chunks_table"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Chunks table - minimal metadata only
    # Full body stored in MongoDB (TTL mode) or streamed (ephemeral mode)
    op.create_table(
        "chunks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", sa.String(255), nullable=False),
        sa.Column("source_id", UUID(as_uuid=True), nullable=False),  # Connector or file reference
        sa.Column("source_type", sa.String(50), nullable=False),  # connector, file, url
        sa.Column("content_hash", sa.String(64), nullable=False),  # SHA-256 for deduplication
        sa.Column("neo4j_id", sa.String(255), nullable=True),  # Neo4j node ID (contains vector)
        sa.Column("embedding_state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("content_summary", sa.Text, nullable=True),  # Optional LLM-generated summary
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),  # Position in source
        sa.Column("token_count", sa.Integer, nullable=True),  # Estimated token count
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )
    
    # Indexes for common queries
    op.create_index("ix_chunks_tenant_id", "chunks", ["tenant_id"])
    op.create_index("ix_chunks_source_id", "chunks", ["source_id"])
    op.create_index("ix_chunks_embedding_state", "chunks", ["embedding_state"])
    op.create_index("ix_chunks_content_hash", "chunks", ["content_hash"])
    
    # Composite index for deduplication check
    op.create_index("ix_chunks_tenant_source_hash", "chunks", ["tenant_id", "source_id", "content_hash"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_chunks_tenant_source_hash")
    op.drop_index("ix_chunks_content_hash")
    op.drop_index("ix_chunks_embedding_state")
    op.drop_index("ix_chunks_source_id")
    op.drop_index("ix_chunks_tenant_id")
    op.drop_table("chunks")
