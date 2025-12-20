use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// Types of connectors supported by the system.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ConnectorType {
    LocalFile,
    GitHub,
    GitLab,
    Bitbucket,
    GoogleDrive,
    Dropbox,
    Slack,
    Notion,
    Confluence,
    UrlScraper,
}

impl std::fmt::Display for ConnectorType {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ConnectorType::LocalFile => write!(f, "local_file"),
            ConnectorType::GitHub => write!(f, "github"),
            ConnectorType::GitLab => write!(f, "gitlab"),
            ConnectorType::Bitbucket => write!(f, "bitbucket"),
            ConnectorType::GoogleDrive => write!(f, "google_drive"),
            ConnectorType::Dropbox => write!(f, "dropbox"),
            ConnectorType::Slack => write!(f, "slack"),
            ConnectorType::Notion => write!(f, "notion"),
            ConnectorType::Confluence => write!(f, "confluence"),
            ConnectorType::UrlScraper => write!(f, "url_scraper"),
        }
    }
}

/// Content types for documents.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ContentType {
    Text,
    Code,
    Markdown,
    Html,
    Json,
    Xml,
    Yaml,
    Binary,
    Unknown,
}

impl Default for ContentType {
    fn default() -> Self {
        ContentType::Unknown
    }
}

/// Source kinds for the chunker service.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceKind {
    CodeRepo,
    Document,
    Chat,
}

/// A chunk of a document (optional, chunker owns real chunking).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DocumentChunk {
    pub id: Uuid,
    pub document_id: Uuid,
    pub content: String,
    pub chunk_index: usize,
    pub start_offset: usize,
    pub end_offset: usize,
    pub metadata: serde_json::Value,
}

/// Normalized document model for content from any source.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NormalizedDocument {
    pub id: Uuid,
    pub source_id: Uuid,
    pub connector_type: ConnectorType,
    pub external_id: String,
    pub name: String,
    pub path: Option<String>,
    pub content: String,
    pub content_type: ContentType,
    pub metadata: serde_json::Value,
    pub chunks: Option<Vec<DocumentChunk>>,
    pub block_type: Option<String>,
    pub language: Option<String>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl NormalizedDocument {
    pub fn new(
        source_id: Uuid,
        connector_type: ConnectorType,
        external_id: String,
        name: String,
        content: String,
    ) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            source_id,
            connector_type,
            external_id,
            name,
            path: None,
            content,
            content_type: ContentType::default(),
            metadata: serde_json::json!({}),
            chunks: None,
            block_type: None,
            language: None,
            created_at: now,
            updated_at: now,
        }
    }
}

/// Status of a sync job.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SyncStatus {
    Pending,
    Running,
    Completed,
    Failed,
}

/// A connected data source.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DataSource {
    pub id: Uuid,
    pub user_id: Uuid,
    pub name: String,
    pub connector_type: ConnectorType,
    pub config: serde_json::Value,
    pub status: SyncStatus,
    pub sync_status: SyncStatus,
    pub documents_count: u32,
    pub last_synced_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl DataSource {
    pub fn new(user_id: Uuid, name: String, connector_type: ConnectorType, config: serde_json::Value) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            user_id,
            name,
            connector_type,
            config,
            status: SyncStatus::Pending,
            sync_status: SyncStatus::Pending,
            documents_count: 0,
            last_synced_at: None,
            created_at: now,
            updated_at: now,
        }
    }
}

/// A sync job for tracking background sync operations.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyncJob {
    pub id: Uuid,
    pub source_id: Uuid,
    pub user_id: Uuid,
    pub status: SyncStatus,
    pub items_processed: usize,
    pub items_total: Option<usize>,
    pub error: Option<String>,
    pub started_at: DateTime<Utc>,
    pub completed_at: Option<DateTime<Utc>>,
}

impl SyncJob {
    pub fn new(source_id: Uuid, user_id: Uuid) -> Self {
        Self {
            id: Uuid::new_v4(),
            source_id,
            user_id,
            status: SyncStatus::Pending,
            items_processed: 0,
            items_total: None,
            error: None,
            started_at: Utc::now(),
            completed_at: None,
        }
    }
}

/// A stored document in the system.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Document {
    pub id: Uuid,
    pub user_id: Uuid,
    pub source_id: Option<Uuid>,
    pub name: String,
    pub content: String,
    pub content_type: ContentType,
    pub file_path: Option<String>,
    pub file_size: Option<u64>,
    pub mime_type: Option<String>,
    pub metadata: serde_json::Value,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

impl Document {
    pub fn new(user_id: Uuid, name: String, content: String) -> Self {
        let now = Utc::now();
        Self {
            id: Uuid::new_v4(),
            user_id,
            source_id: None,
            name,
            content,
            content_type: ContentType::Text,
            file_path: None,
            file_size: None,
            mime_type: None,
            metadata: serde_json::json!({}),
            created_at: now,
            updated_at: now,
        }
    }
}

/// GitHub App installation record.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitHubInstallation {
    pub installation_id: i64,
    pub user_id: Uuid,
    pub account_login: String,
    pub account_type: String,
    pub created_at: DateTime<Utc>,
}

/// GitHub repository configuration.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitHubRepoConfig {
    pub id: Uuid,
    pub installation_id: i64,
    pub user_id: Uuid,
    pub repo_full_name: String,
    pub branch: Option<String>,
    pub sync_enabled: bool,
    pub last_synced_at: Option<DateTime<Utc>>,
    pub created_at: DateTime<Utc>,
}

impl GitHubRepoConfig {
    pub fn new(installation_id: i64, user_id: Uuid, repo_full_name: String) -> Self {
        Self {
            id: Uuid::new_v4(),
            installation_id,
            user_id,
            repo_full_name,
            branch: None,
            sync_enabled: true,
            last_synced_at: None,
            created_at: Utc::now(),
        }
    }
}
