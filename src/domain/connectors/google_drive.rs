use crate::clients::AuthClient;
use crate::domain::connectors::Connector;
use crate::domain::models::{ConnectorType, DataSource, NormalizedDocument};
use crate::error::{AppError, AppResult};
use async_trait::async_trait;
use std::sync::Arc;
use uuid::Uuid;

/// Google Drive connector (stub implementation).
pub struct GoogleDriveConnector {
    #[allow(dead_code)]
    auth_client: Arc<AuthClient>,
}

impl GoogleDriveConnector {
    pub fn new(auth_client: Arc<AuthClient>) -> Self {
        Self { auth_client }
    }
}

#[async_trait]
impl Connector for GoogleDriveConnector {
    fn connector_type(&self) -> ConnectorType {
        ConnectorType::GoogleDrive
    }

    async fn validate_access(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<bool> {
        Err(AppError::Internal("Google Drive connector not yet implemented".to_string()))
    }

    async fn fetch_content(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<Vec<NormalizedDocument>> {
        Err(AppError::Internal("Google Drive connector not yet implemented".to_string()))
    }
}
