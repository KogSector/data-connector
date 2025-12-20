pub mod memory;

use crate::domain::models::{DataSource, Document, GitHubInstallation, GitHubRepoConfig, SyncJob, SyncStatus};
use crate::error::AppResult;
use async_trait::async_trait;
use chrono::{DateTime, Utc};
use uuid::Uuid;

/// Storage trait for persistence operations.
#[async_trait]
pub trait Storage: Send + Sync {
    // Data Sources
    async fn save_source(&self, source: DataSource) -> AppResult<DataSource>;
    async fn get_source(&self, id: Uuid) -> AppResult<Option<DataSource>>;
    async fn get_sources_by_user(&self, user_id: Uuid) -> AppResult<Vec<DataSource>>;
    async fn update_source_status(&self, id: Uuid, status: SyncStatus) -> AppResult<()>;
    async fn update_source_last_synced(&self, id: Uuid, last_synced: DateTime<Utc>) -> AppResult<()>;
    async fn delete_source(&self, id: Uuid) -> AppResult<bool>;

    // Documents
    async fn save_document(&self, document: Document) -> AppResult<Document>;
    async fn get_document(&self, id: Uuid) -> AppResult<Option<Document>>;
    async fn get_documents_by_user(&self, user_id: Uuid) -> AppResult<Vec<Document>>;
    async fn search_documents(&self, user_id: Uuid, query: &str) -> AppResult<Vec<Document>>;
    async fn delete_document(&self, id: Uuid) -> AppResult<bool>;
    async fn get_document_analytics(&self, user_id: Uuid) -> AppResult<DocumentAnalytics>;

    // Sync Jobs
    async fn save_sync_job(&self, job: SyncJob) -> AppResult<SyncJob>;
    async fn get_sync_job(&self, id: Uuid) -> AppResult<Option<SyncJob>>;
    async fn update_sync_job_status(&self, id: Uuid, status: SyncStatus, error: Option<String>) -> AppResult<()>;

    // GitHub App
    async fn save_github_installation(&self, installation: GitHubInstallation) -> AppResult<GitHubInstallation>;
    async fn get_github_installations(&self, user_id: Uuid) -> AppResult<Vec<GitHubInstallation>>;
    async fn save_github_repo_config(&self, config: GitHubRepoConfig) -> AppResult<GitHubRepoConfig>;
    async fn get_github_repo_configs(&self, installation_id: i64) -> AppResult<Vec<GitHubRepoConfig>>;
    async fn get_github_repo_config(&self, id: Uuid) -> AppResult<Option<GitHubRepoConfig>>;
}

/// Document analytics summary.
#[derive(Debug, Clone, serde::Serialize)]
pub struct DocumentAnalytics {
    pub total_documents: usize,
    pub total_size_bytes: u64,
    pub by_content_type: std::collections::HashMap<String, usize>,
    pub by_source: std::collections::HashMap<String, usize>,
}
