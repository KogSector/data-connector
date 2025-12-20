use crate::clients::AuthClient;
use crate::domain::connectors::Connector;
use crate::domain::models::{ConnectorType, DataSource, NormalizedDocument};
use crate::error::{AppError, AppResult};
use async_trait::async_trait;
use std::sync::Arc;
use uuid::Uuid;

/// Dropbox connector (stub implementation).
pub struct DropboxConnector {
    #[allow(dead_code)]
    auth_client: Arc<AuthClient>,
}

impl DropboxConnector {
    pub fn new(auth_client: Arc<AuthClient>) -> Self {
        Self { auth_client }
    }
}

#[async_trait]
impl Connector for DropboxConnector {
    fn connector_type(&self) -> ConnectorType {
        ConnectorType::Dropbox
    }

    async fn validate_access(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<bool> {
        Err(AppError::Internal("Dropbox connector not yet implemented".to_string()))
    }

    async fn fetch_content(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<Vec<NormalizedDocument>> {
        Err(AppError::Internal("Dropbox connector not yet implemented".to_string()))
    }
}
