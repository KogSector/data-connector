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
    /// Database URL (optional, for future Postgres support)
    pub database_url: Option<String>,
    /// Default local sync path
    pub local_sync_path_default: Option<String>,
    /// JWT secret for token validation (optional - when not validating locally)
    pub jwt_secret: Option<String>,
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
                .unwrap_or_else(|_| "http://localhost:3012".to_string()),
            database_url: env::var("DATABASE_URL").ok(),
            local_sync_path_default: env::var("LOCAL_SYNC_PATH_DEFAULT").ok(),
            jwt_secret: env::var("JWT_SECRET").ok(),
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
