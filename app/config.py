"""
ConHub Data Connector - Configuration Module

Loads configuration from environment variables with Pydantic settings.
Ported from Rust config.rs.
"""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # Server Configuration
    port: int = 3013
    debug: bool = False
    log_level: str = "INFO"
    
    # Database
    database_url: str = "postgresql+asyncpg://localhost:5432/data_connector"
    
    # Redis
    redis_url: str = "redis://localhost:6379/0"
    
    # Service Integration URLs
    auth_service_url: str = "http://localhost:3010"
    chunker_service_url: str = "http://localhost:3017"
    embedding_service_url: str = "http://localhost:8082"
    relation_graph_service_url: str = "http://localhost:3018"
    
    # Feature Flags
    embedding_enabled: bool = True
    graph_rag_enabled: bool = True
    
    # Auth0 Configuration
    auth0_domain: Optional[str] = None
    auth0_issuer: Optional[str] = None
    auth0_audience: Optional[str] = None
    auth0_jwks_uri: Optional[str] = None
    
    # JWT Configuration
    jwt_secret: Optional[str] = None
    jwt_public_key_path: Optional[str] = None
    internal_api_key: Optional[str] = None
    conhub_auth_public_key: Optional[str] = None  # For ConHub internal token verification
    
    # Chunk Storage Configuration (Ephemeral-First)
    chunk_store_mode: str = "ephemeral"  # ephemeral | mongo-ttl | postgres
    chunk_ttl_days: int = 7
    mongodb_uri: Optional[str] = None
    
    # Neo4j Configuration (Unified Vector + Graph Storage)
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: Optional[str] = None
    neo4j_vector_dimension: int = 1024  # Jina embeddings v3 dimension
    
    # S3/MinIO Configuration
    s3_endpoint_url: Optional[str] = None
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_bucket_name: str = "data-connector-blobs"
    s3_region: str = "us-east-1"
    
    # Chunker Configuration
    chunk_size_threshold_kb: int = 256  # Files larger than this use reference mode
    
    # Local File Sync
    local_sync_path_default: Optional[str] = None
    
    # GitHub App Configuration
    github_app_name: Optional[str] = None
    github_app_id: Optional[str] = None
    github_app_private_key_path: Optional[str] = None
    
    # CORS Origins
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001", 
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:5173",
    ]
    
    @property
    def async_database_url(self) -> str:
        """Return async-compatible database URL."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    
    def get_local_sync_path(self, profile: Optional[str] = None) -> Optional[str]:
        """Get local sync path for a specific profile."""
        import os
        if profile:
            var_name = f"LOCAL_SYNC_PATH_{profile.upper()}"
            return os.getenv(var_name)
        return self.local_sync_path_default


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience exports
settings = get_settings()
