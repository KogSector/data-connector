use std::env;

/// Application configuration loaded from environment variables.
#[derive(Debug, Clone)]
pub struct Config {
    /// Server port (default: 3013)
    pub port: u16,
    /// Auth service URL for OAuth token retrieval
    pub auth_service_url: String,
    /// Chunker service URL for triggering downstream processing
    pub chunker_service_url: String,
    /// Embedding service URL for vector embeddings
    pub embedding_service_url: String,
    /// Graph RAG service URL for knowledge graph construction
    pub graph_service_url: String,
    /// Whether embedding is enabled
    pub embedding_enabled: bool,
    /// Whether graph RAG is enabled
    pub graph_rag_enabled: bool,
    /// Database URL (optional, for future Postgres support)
    pub database_url: Option<String>,
    /// Redis URL for caching
    pub redis_url: Option<String>,
    /// Default local sync path
    pub local_sync_path_default: Option<String>,
    /// JWT secret for token validation (HS256 - development mode)
    pub jwt_secret: Option<String>,
    /// Path to JWT public key PEM file (RS256 - production mode)
    pub jwt_public_key_path: Option<String>,
    /// Internal API key for S2S authentication with auth-service
    pub internal_api_key: Option<String>,
    /// Auth0 domain for JWT validation
    pub auth0_domain: Option<String>,
    /// Auth0 audience for JWT validation
    pub auth0_audience: Option<String>,
}

impl Config {
    /// Load configuration from environment variables.
    pub fn from_env() -> Self {
        Self {
            port: env::var("PORT")
                .ok()
                .and_then(|p| p.parse().ok())
                .unwrap_or(3013),
            auth_service_url: env::var("AUTH_SERVICE_URL")
                .unwrap_or_else(|_| "http://localhost:3010".to_string()),
            chunker_service_url: env::var("CHUNKER_SERVICE_URL")
                .unwrap_or_else(|_| "http://localhost:3017".to_string()),
            embedding_service_url: env::var("EMBEDDING_SERVICE_URL")
                .unwrap_or_else(|_| "http://localhost:8082".to_string()),
            graph_service_url: env::var("RELATION_GRAPH_SERVICE_URL")
                .unwrap_or_else(|_| "http://localhost:3018".to_string()),
            embedding_enabled: env::var("EMBEDDING_ENABLED")
                .map(|v| v.to_lowercase() == "true")
                .unwrap_or(true),
            graph_rag_enabled: env::var("GRAPH_RAG_ENABLED")
                .map(|v| v.to_lowercase() == "true")
                .unwrap_or(true),
            database_url: env::var("DATABASE_URL").ok(),
            redis_url: env::var("REDIS_URL").ok(),
            local_sync_path_default: env::var("LOCAL_SYNC_PATH_DEFAULT").ok(),
            jwt_secret: env::var("JWT_SECRET").ok(),
            jwt_public_key_path: env::var("JWT_PUBLIC_KEY_PATH").ok(),
            internal_api_key: env::var("INTERNAL_API_KEY").ok(),
            auth0_domain: env::var("AUTH0_DOMAIN").ok(),
            auth0_audience: env::var("AUTH0_AUDIENCE").ok(),
        }
    }

    /// Get local sync path for a specific profile.
    pub fn get_local_sync_path(&self, profile: Option<&str>) -> Option<String> {
        match profile {
            Some(name) => {
                let var_name = format!("LOCAL_SYNC_PATH_{}", name.to_uppercase());
                env::var(&var_name).ok()
            }
            None => self.local_sync_path_default.clone(),
        }
    }
}

impl Default for Config {
    fn default() -> Self {
        Self::from_env()
    }
}
