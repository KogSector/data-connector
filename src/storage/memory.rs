use crate::domain::models::{DataSource, Document, GitHubInstallation, GitHubRepoConfig, SyncJob, SyncStatus};
use crate::error::{AppError, AppResult};
use crate::storage::{DocumentAnalytics, Storage};
use async_trait::async_trait;
use chrono::{DateTime, Utc};
use std::collections::HashMap;
use std::sync::RwLock;
use uuid::Uuid;

/// In-memory storage implementation for development.
pub struct InMemoryStorage {
    sources: RwLock<HashMap<Uuid, DataSource>>,
    documents: RwLock<HashMap<Uuid, Document>>,
    sync_jobs: RwLock<HashMap<Uuid, SyncJob>>,
    github_installations: RwLock<HashMap<i64, GitHubInstallation>>,
    github_repo_configs: RwLock<HashMap<Uuid, GitHubRepoConfig>>,
}

impl InMemoryStorage {
    pub fn new() -> Self {
        Self {
            sources: RwLock::new(HashMap::new()),
            documents: RwLock::new(HashMap::new()),
            sync_jobs: RwLock::new(HashMap::new()),
            github_installations: RwLock::new(HashMap::new()),
            github_repo_configs: RwLock::new(HashMap::new()),
        }
    }
}

impl Default for InMemoryStorage {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Storage for InMemoryStorage {
    // Data Sources
    async fn save_source(&self, source: DataSource) -> AppResult<DataSource> {
        let mut sources = self.sources.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        sources.insert(source.id, source.clone());
        Ok(source)
    }

    async fn get_source(&self, id: Uuid) -> AppResult<Option<DataSource>> {
        let sources = self.sources.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(sources.get(&id).cloned())
    }

    async fn get_sources_by_user(&self, user_id: Uuid) -> AppResult<Vec<DataSource>> {
        let sources = self.sources.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(sources.values()
            .filter(|s| s.user_id == user_id)
            .cloned()
            .collect())
    }

    async fn update_source_status(&self, id: Uuid, status: SyncStatus) -> AppResult<()> {
        let mut sources = self.sources.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        if let Some(source) = sources.get_mut(&id) {
            source.status = status;
            source.updated_at = Utc::now();
        }
        Ok(())
    }

    async fn update_source_last_synced(&self, id: Uuid, last_synced: DateTime<Utc>) -> AppResult<()> {
        let mut sources = self.sources.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        if let Some(source) = sources.get_mut(&id) {
            source.last_synced_at = Some(last_synced);
            source.updated_at = Utc::now();
        }
        Ok(())
    }

    async fn delete_source(&self, id: Uuid) -> AppResult<bool> {
        let mut sources = self.sources.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(sources.remove(&id).is_some())
    }

    // Documents
    async fn save_document(&self, document: Document) -> AppResult<Document> {
        let mut documents = self.documents.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        documents.insert(document.id, document.clone());
        Ok(document)
    }

    async fn get_document(&self, id: Uuid) -> AppResult<Option<Document>> {
        let documents = self.documents.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(documents.get(&id).cloned())
    }

    async fn get_documents_by_user(&self, user_id: Uuid) -> AppResult<Vec<Document>> {
        let documents = self.documents.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(documents.values()
            .filter(|d| d.user_id == user_id)
            .cloned()
            .collect())
    }

    async fn search_documents(&self, user_id: Uuid, query: &str) -> AppResult<Vec<Document>> {
        let documents = self.documents.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        let query_lower = query.to_lowercase();
        Ok(documents.values()
            .filter(|d| {
                d.user_id == user_id && 
                (d.name.to_lowercase().contains(&query_lower) ||
                 d.content.to_lowercase().contains(&query_lower))
            })
            .cloned()
            .collect())
    }

    async fn delete_document(&self, id: Uuid) -> AppResult<bool> {
        let mut documents = self.documents.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(documents.remove(&id).is_some())
    }

    async fn get_document_analytics(&self, user_id: Uuid) -> AppResult<DocumentAnalytics> {
        let documents = self.documents.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        
        let user_docs: Vec<_> = documents.values()
            .filter(|d| d.user_id == user_id)
            .collect();
        
        let total_documents = user_docs.len();
        let total_size_bytes = user_docs.iter()
            .filter_map(|d| d.file_size)
            .sum();
        
        let mut by_content_type = HashMap::new();
        let mut by_source = HashMap::new();
        
        for doc in &user_docs {
            let content_type = format!("{:?}", doc.content_type).to_lowercase();
            *by_content_type.entry(content_type).or_insert(0) += 1;
            
            if let Some(source_id) = doc.source_id {
                *by_source.entry(source_id.to_string()).or_insert(0) += 1;
            } else {
                *by_source.entry("direct_upload".to_string()).or_insert(0) += 1;
            }
        }
        
        Ok(DocumentAnalytics {
            total_documents,
            total_size_bytes,
            by_content_type,
            by_source,
        })
    }

    // Sync Jobs
    async fn save_sync_job(&self, job: SyncJob) -> AppResult<SyncJob> {
        let mut jobs = self.sync_jobs.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        jobs.insert(job.id, job.clone());
        Ok(job)
    }

    async fn get_sync_job(&self, id: Uuid) -> AppResult<Option<SyncJob>> {
        let jobs = self.sync_jobs.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(jobs.get(&id).cloned())
    }

    async fn update_sync_job_status(&self, id: Uuid, status: SyncStatus, error: Option<String>) -> AppResult<()> {
        let mut jobs = self.sync_jobs.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        if let Some(job) = jobs.get_mut(&id) {
            job.status = status;
            job.error = error;
            if matches!(status, SyncStatus::Completed | SyncStatus::Failed) {
                job.completed_at = Some(Utc::now());
            }
        }
        Ok(())
    }

    // GitHub App
    async fn save_github_installation(&self, installation: GitHubInstallation) -> AppResult<GitHubInstallation> {
        let mut installations = self.github_installations.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        installations.insert(installation.installation_id, installation.clone());
        Ok(installation)
    }

    async fn get_github_installations(&self, user_id: Uuid) -> AppResult<Vec<GitHubInstallation>> {
        let installations = self.github_installations.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(installations.values()
            .filter(|i| i.user_id == user_id)
            .cloned()
            .collect())
    }

    async fn save_github_repo_config(&self, config: GitHubRepoConfig) -> AppResult<GitHubRepoConfig> {
        let mut configs = self.github_repo_configs.write()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        configs.insert(config.id, config.clone());
        Ok(config)
    }

    async fn get_github_repo_configs(&self, installation_id: i64) -> AppResult<Vec<GitHubRepoConfig>> {
        let configs = self.github_repo_configs.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(configs.values()
            .filter(|c| c.installation_id == installation_id)
            .cloned()
            .collect())
    }

    async fn get_github_repo_config(&self, id: Uuid) -> AppResult<Option<GitHubRepoConfig>> {
        let configs = self.github_repo_configs.read()
            .map_err(|_| AppError::Internal("Lock poisoned".to_string()))?;
        Ok(configs.get(&id).cloned())
    }
}
