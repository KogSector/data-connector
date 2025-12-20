use crate::error::{AppError, AppResult};
use reqwest::Client;
use serde::Deserialize;
use tracing::debug;
use uuid::Uuid;

/// Client for communicating with the auth service.
pub struct AuthClient {
    client: Client,
    base_url: String,
    internal_api_key: Option<String>,
}

#[derive(Debug, Deserialize)]
struct OAuthTokenResponse {
    access_token: String,
    #[allow(dead_code)]
    token_type: Option<String>,
    #[allow(dead_code)]
    expires_at: Option<String>,
}

impl AuthClient {
    pub fn new(base_url: String) -> Self {
        Self {
            client: Client::new(),
            base_url,
            internal_api_key: None,
        }
    }

    /// Create with internal API key for S2S authentication.
    pub fn with_api_key(base_url: String, api_key: Option<String>) -> Self {
        Self {
            client: Client::new(),
            base_url,
            internal_api_key: api_key,
        }
    }

    /// Get OAuth token for a provider and user from the auth service.
    /// Calls: GET {AUTH_SERVICE_URL}/api/auth/internal/tokens/{provider}?user_id={uuid}
    pub async fn get_oauth_token(&self, provider: &str, user_id: Uuid) -> AppResult<String> {
        let url = format!(
            "{}/api/auth/internal/tokens/{}?user_id={}",
            self.base_url, provider, user_id
        );
        
        debug!("Fetching OAuth token from: {}", url);
        
        let mut request = self.client.get(&url);
        
        // Add internal API key if configured
        if let Some(ref api_key) = self.internal_api_key {
            request = request.header("X-Internal-Api-Key", api_key);
        }
        
        let response = request
            .send()
            .await
            .map_err(|e| AppError::ExternalService(format!("Auth service request failed: {}", e)))?;
        
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(AppError::ExternalService(format!(
                "Auth service returned {}: {}",
                status, body
            )));
        }
        
        let token_response: OAuthTokenResponse = response
            .json()
            .await
            .map_err(|e| AppError::ExternalService(format!("Failed to parse auth response: {}", e)))?;
        
        Ok(token_response.access_token)
    }
}

