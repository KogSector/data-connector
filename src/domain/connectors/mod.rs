pub mod github;
pub mod gitlab;
pub mod bitbucket;
pub mod google_drive;
pub mod dropbox;
pub mod slack;
pub mod url_scraper;
pub mod local_file;

use crate::clients::{AuthClient, GitHubApiClient};
use crate::domain::models::{ConnectorType, DataSource, NormalizedDocument};
use crate::error::AppResult;
use async_trait::async_trait;
use std::sync::Arc;
use uuid::Uuid;

/// Trait for content connectors.
#[async_trait]
pub trait Connector: Send + Sync {
    /// Fetch content from the data source.
    async fn fetch_content(&self, source: &DataSource, user_id: Uuid) -> AppResult<Vec<NormalizedDocument>>;
    
    /// Get the connector type.
    fn connector_type(&self) -> ConnectorType;
    
    /// Validate access to the source.
    async fn validate_access(&self, source: &DataSource, user_id: Uuid) -> AppResult<bool>;
}

/// Manager for creating and orchestrating connectors.
pub struct ConnectorManager {
    auth_client: Arc<AuthClient>,
    github_client: Arc<GitHubApiClient>,
}

impl ConnectorManager {
    pub fn new(
        auth_client: Arc<AuthClient>,
        github_client: Arc<GitHubApiClient>,
    ) -> Self {
        Self {
            auth_client,
            github_client,
        }
    }

    /// Get a connector for the given type.
    pub fn get_connector(&self, connector_type: ConnectorType) -> Box<dyn Connector> {
        match connector_type {
            ConnectorType::GitHub => Box::new(github::GitHubConnector::new(
                Arc::clone(&self.auth_client),
                Arc::clone(&self.github_client),
            )),
            ConnectorType::GitLab => Box::new(gitlab::GitLabConnector::new(
                Arc::clone(&self.auth_client),
            )),
            ConnectorType::Bitbucket => Box::new(bitbucket::BitbucketConnector::new(
                Arc::clone(&self.auth_client),
            )),
            ConnectorType::GoogleDrive => Box::new(google_drive::GoogleDriveConnector::new(
                Arc::clone(&self.auth_client),
            )),
            ConnectorType::Dropbox => Box::new(dropbox::DropboxConnector::new(
                Arc::clone(&self.auth_client),
            )),
            ConnectorType::Slack => Box::new(slack::SlackConnector::new(
                Arc::clone(&self.auth_client),
            )),
            ConnectorType::UrlScraper => Box::new(url_scraper::UrlScraperConnector::new()),
            ConnectorType::LocalFile => Box::new(local_file::LocalFileConnector::new()),
            // Notion and Confluence - use placeholder connectors for now
            ConnectorType::Notion => Box::new(url_scraper::UrlScraperConnector::new()),
            ConnectorType::Confluence => Box::new(url_scraper::UrlScraperConnector::new()),
        }
    }
}
