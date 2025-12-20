use crate::clients::AuthClient;
use crate::domain::connectors::Connector;
use crate::domain::models::{ConnectorType, DataSource, NormalizedDocument};
use crate::error::{AppError, AppResult};
use async_trait::async_trait;
use std::sync::Arc;
use uuid::Uuid;

/// Slack connector (stub implementation).
pub struct SlackConnector {
    #[allow(dead_code)]
    auth_client: Arc<AuthClient>,
}

impl SlackConnector {
    pub fn new(auth_client: Arc<AuthClient>) -> Self {
        Self { auth_client }
    }
}

#[async_trait]
impl Connector for SlackConnector {
    fn connector_type(&self) -> ConnectorType {
        ConnectorType::Slack
    }

    async fn validate_access(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<bool> {
        Err(AppError::Internal("Slack connector not yet implemented".to_string()))
    }

    async fn fetch_content(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<Vec<NormalizedDocument>> {
        Err(AppError::Internal("Slack connector not yet implemented".to_string()))
    }
}
