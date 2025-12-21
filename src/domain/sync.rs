use crate::clients::{AuthClient, ChunkerClient, GitHubApiClient};
use crate::domain::models::{DataSource, NormalizedDocument, SourceKind, SyncJob, SyncStatus};
use crate::domain::connectors::{Connector, ConnectorManager};
use crate::error::{AppError, AppResult};
use crate::storage::Storage;
use chrono::Utc;
use std::sync::Arc;
use tracing::{error, info};
use uuid::Uuid;

/// Sync orchestrator for managing data source synchronization.
pub struct SyncOrchestrator {
    storage: Arc<dyn Storage>,
    auth_client: Arc<AuthClient>,
    chunker_client: Arc<ChunkerClient>,
    github_client: Arc<GitHubApiClient>,
}

impl SyncOrchestrator {
    pub fn new(
        storage: Arc<dyn Storage>,
        auth_client: Arc<AuthClient>,
        chunker_client: Arc<ChunkerClient>,
        github_client: Arc<GitHubApiClient>,
    ) -> Self {
        Self {
            storage,
            auth_client,
            chunker_client,
            github_client,
        }
    }

    /// Start a sync job for a data source (runs in background).
    pub async fn start_sync(&self, source: DataSource, user_id: Uuid) -> AppResult<SyncJob> {
        let job = SyncJob::new(source.id, user_id);
        self.storage.save_sync_job(job.clone()).await?;

        // Clone what we need for the background task
        let storage = Arc::clone(&self.storage);
        let auth_client = Arc::clone(&self.auth_client);
        let chunker_client = Arc::clone(&self.chunker_client);
        let github_client = Arc::clone(&self.github_client);
        let job_id = job.id;
        let source_clone = source.clone();

        // Spawn background sync task
        tokio::spawn(async move {
            let result = Self::execute_sync(
                storage.clone(),
                auth_client,
                chunker_client,
                github_client,
                source_clone,
                user_id,
                job_id,
            )
            .await;

            if let Err(e) = result {
                error!("Sync job {} failed: {}", job_id, e);
                let _ = storage.update_sync_job_status(job_id, SyncStatus::Failed, Some(e.to_string())).await;
            }
        });

        Ok(job)
    }

    /// Execute the sync operation.
    async fn execute_sync(
        storage: Arc<dyn Storage>,
        auth_client: Arc<AuthClient>,
        chunker_client: Arc<ChunkerClient>,
        github_client: Arc<GitHubApiClient>,
        source: DataSource,
        user_id: Uuid,
        job_id: Uuid,
    ) -> AppResult<()> {
        info!("Starting sync for source {} (job {})", source.id, job_id);
        
        // Update job status to running
        storage.update_sync_job_status(job_id, SyncStatus::Running, None).await?;
        storage.update_source_status(source.id, SyncStatus::Running).await?;

        // Create connector manager and get appropriate connector
        let connector_manager = ConnectorManager::new(
            auth_client,
            github_client,
        );

        let connector = connector_manager.get_connector(source.connector_type);
        
        // Fetch content using the connector
        let documents = connector.fetch_content(&source, user_id).await?;
        
        info!("Fetched {} documents from source {}", documents.len(), source.id);

        // Send documents to chunker
        if !documents.is_empty() {
            Self::send_to_chunker(&chunker_client, &source, &documents).await?;
        }

        // Update job and source status
        storage.update_sync_job_status(job_id, SyncStatus::Completed, None).await?;
        storage.update_source_status(source.id, SyncStatus::Completed).await?;
        storage.update_source_last_synced(source.id, Utc::now()).await?;

        info!("Sync completed for source {} (job {})", source.id, job_id);
        Ok(())
    }

    /// Send normalized documents to the chunker service.
    async fn send_to_chunker(
        chunker_client: &ChunkerClient,
        source: &DataSource,
        documents: &[NormalizedDocument],
    ) -> AppResult<()> {
        let source_kind = match source.connector_type {
            crate::domain::ConnectorType::GitHub 
            | crate::domain::ConnectorType::GitLab 
            | crate::domain::ConnectorType::Bitbucket => SourceKind::CodeRepo,
            crate::domain::ConnectorType::Slack => SourceKind::Chat,
            crate::domain::ConnectorType::Notion 
            | crate::domain::ConnectorType::Confluence => SourceKind::Wiki,
            crate::domain::ConnectorType::UrlScraper => SourceKind::Web,
            crate::domain::ConnectorType::GoogleDrive 
            | crate::domain::ConnectorType::Dropbox 
            | crate::domain::ConnectorType::LocalFile => SourceKind::Document,
        };

        chunker_client.create_chunk_job(source.id, source_kind, documents).await?;
        Ok(())
    }
}
