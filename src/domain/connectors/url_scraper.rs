use crate::domain::connectors::Connector;
use crate::domain::models::{ConnectorType, DataSource, NormalizedDocument};
use crate::error::{AppError, AppResult};
use async_trait::async_trait;
use uuid::Uuid;

/// URL scraper connector (stub implementation).
pub struct UrlScraperConnector;

impl UrlScraperConnector {
    pub fn new() -> Self {
        Self
    }
}

impl Default for UrlScraperConnector {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Connector for UrlScraperConnector {
    fn connector_type(&self) -> ConnectorType {
        ConnectorType::UrlScraper
    }

    async fn validate_access(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<bool> {
        Err(AppError::Internal("URL scraper connector not yet implemented".to_string()))
    }

    async fn fetch_content(&self, _source: &DataSource, _user_id: Uuid) -> AppResult<Vec<NormalizedDocument>> {
        Err(AppError::Internal("URL scraper connector not yet implemented".to_string()))
    }
}
