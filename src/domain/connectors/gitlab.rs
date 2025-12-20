use crate::clients::AuthClient;
use crate::domain::connectors::Connector;
use crate::domain::models::{ConnectorType, DataSource, NormalizedDocument};
use crate::error::{AppError, AppResult};
use async_trait::async_trait;
use std::sync::Arc;
use uuid::Uuid;

/// GitLab connector (stub implementation).
pub struct GitLabConnector {
    #[allow(dead_code)]
    auth_client: Arc<AuthClient>,
}

impl GitLabConnector {
    pub fn new(auth_client: Arc<AuthClient>) -> Self {
        Self { auth_client }
    }
}

#[async_trait]
impl Connector for GitLabConnector {
    fn connector_type(&self) -> ConnectorType {
        ConnectorType::GitLab
    }

    async fn validate_access(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<bool> {
        Err(AppError::Internal("GitLab connector not yet implemented".to_string()))
    }

    async fn fetch_content(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<Vec<NormalizedDocument>> {
        Err(AppError::Internal("GitLab connector not yet implemented".to_string()))
    }
}
