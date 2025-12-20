use crate::clients::{AuthClient, GitHubApiClient};
use crate::domain::connectors::Connector;
use crate::domain::models::{ConnectorType, ContentType, DataSource, NormalizedDocument};
use crate::error::{AppError, AppResult};
use async_trait::async_trait;
use std::sync::Arc;
use tracing::info;
use uuid::Uuid;

/// Filtering options for GitHub sync.
#[derive(Debug, Clone, Default)]
pub struct SyncOptions {
    /// Only include files with these extensions (e.g., ["rs", "md", "py"])
    pub include_languages: Vec<String>,
    /// Exclude files matching these path patterns (regex-like)
    pub exclude_paths: Vec<String>,
    /// Maximum file size in MB to fetch
    pub max_file_size_mb: Option<f64>,
}

impl SyncOptions {
    /// Parse from a DataSource config JSON.
    pub fn from_config(config: &serde_json::Value) -> Self {
        let include_languages = config.get("include_languages")
            .or_else(|| config.get("file_extensions"))
            .and_then(|v| v.as_array())
            .map(|arr| arr.iter().filter_map(|v| v.as_str().map(String::from)).collect())
            .unwrap_or_default();
        
        let exclude_paths = config.get("exclude_paths")
            .and_then(|v| v.as_array())
            .map(|arr| arr.iter().filter_map(|v| v.as_str().map(String::from)).collect())
            .unwrap_or_default();
        
        let max_file_size_mb = config.get("max_file_size_mb")
            .and_then(|v| v.as_f64());
        
        Self {
            include_languages,
            exclude_paths,
            max_file_size_mb,
        }
    }

    /// Check if a file path should be included based on filters.
    pub fn should_include(&self, path: &str, file_size: Option<u64>) -> bool {
        // Check file size limit
        if let (Some(max_mb), Some(size)) = (self.max_file_size_mb, file_size) {
            let max_bytes = (max_mb * 1024.0 * 1024.0) as u64;
            if size > max_bytes {
                return false;
            }
        }
        
        // Check exclude patterns
        for pattern in &self.exclude_paths {
            if path.contains(pattern) {
                return false;
            }
        }
        
        // Check include languages (if specified)
        if !self.include_languages.is_empty() {
            let ext = path.rsplit('.').next().unwrap_or("").to_lowercase();
            if !self.include_languages.iter().any(|lang| lang.to_lowercase() == ext) {
                return false;
            }
        }
        
        true
    }
}

/// GitHub connector for fetching repository content.
pub struct GitHubConnector {
    auth_client: Arc<AuthClient>,
    github_client: Arc<GitHubApiClient>,
}

impl GitHubConnector {
    pub fn new(auth_client: Arc<AuthClient>, github_client: Arc<GitHubApiClient>) -> Self {
        Self {
            auth_client,
            github_client,
        }
    }

    /// Determine content type from file extension.
    fn get_content_type(path: &str) -> ContentType {
        let ext = path.rsplit('.').next().unwrap_or("").to_lowercase();
        match ext.as_str() {
            "md" | "markdown" => ContentType::Markdown,
            "html" | "htm" => ContentType::Html,
            "json" => ContentType::Json,
            "xml" => ContentType::Xml,
            "yaml" | "yml" => ContentType::Yaml,
            "txt" => ContentType::Text,
            "rs" | "py" | "js" | "ts" | "go" | "java" | "c" | "cpp" | "h" | "hpp" 
            | "cs" | "rb" | "php" | "swift" | "kt" | "scala" | "sql" | "sh" | "bash"
            | "ps1" | "psm1" | "jsx" | "tsx" | "vue" | "svelte" => ContentType::Code,
            _ => ContentType::Unknown,
        }
    }

    /// Detect programming language from file extension.
    fn get_language(path: &str) -> Option<String> {
        let ext = path.rsplit('.').next().unwrap_or("").to_lowercase();
        let lang = match ext.as_str() {
            "rs" => "rust",
            "py" => "python",
            "js" => "javascript",
            "ts" => "typescript",
            "jsx" => "javascript",
            "tsx" => "typescript",
            "go" => "go",
            "java" => "java",
            "c" => "c",
            "cpp" | "cc" | "cxx" => "cpp",
            "h" | "hpp" => "c",
            "cs" => "csharp",
            "rb" => "ruby",
            "php" => "php",
            "swift" => "swift",
            "kt" => "kotlin",
            "scala" => "scala",
            "sql" => "sql",
            "sh" | "bash" => "shell",
            "ps1" | "psm1" => "powershell",
            "vue" => "vue",
            "svelte" => "svelte",
            "md" | "markdown" => "markdown",
            "json" => "json",
            "yaml" | "yml" => "yaml",
            "xml" => "xml",
            "html" | "htm" => "html",
            "css" => "css",
            "scss" | "sass" => "scss",
            _ => return None,
        };
        Some(lang.to_string())
    }

    /// Check if file should be skipped (binary files).
    fn is_binary_file(path: &str) -> bool {
        let ext = path.rsplit('.').next().unwrap_or("").to_lowercase();
        matches!(ext.as_str(), 
            "png" | "jpg" | "jpeg" | "gif" | "ico" | "svg" | "webp" | "bmp" |
            "woff" | "woff2" | "ttf" | "eot" | "otf" |
            "pdf" | "doc" | "docx" | "xls" | "xlsx" | "ppt" | "pptx" |
            "zip" | "tar" | "gz" | "rar" | "7z" |
            "exe" | "dll" | "so" | "dylib" | "bin" |
            "mp3" | "mp4" | "wav" | "avi" | "mov" | "mkv" |
            "db" | "sqlite" | "lock"
        )
    }
}

#[async_trait]
impl Connector for GitHubConnector {
    fn connector_type(&self) -> ConnectorType {
        ConnectorType::GitHub
    }

    async fn validate_access(&self, source: &DataSource, user_id: Uuid) -> AppResult<bool> {
        // Get OAuth token from auth service
        let token = self.auth_client.get_oauth_token("github", user_id).await?;
        
        // Extract repo from config
        let repo = source.config.get("repository")
            .and_then(|v| v.as_str())
            .ok_or_else(|| AppError::BadRequest("Missing repository in config".to_string()))?;
        
        // Validate access via GitHub API
        self.github_client.validate_repo_access(&token, repo).await
    }

    async fn fetch_content(&self, source: &DataSource, user_id: Uuid) -> AppResult<Vec<NormalizedDocument>> {
        info!("Fetching content from GitHub for source {}", source.id);
        
        // Parse filtering options from config
        let options = SyncOptions::from_config(&source.config);
        info!("Sync options: include_languages={:?}, exclude_paths={:?}, max_file_size_mb={:?}",
            options.include_languages, options.exclude_paths, options.max_file_size_mb);
        
        // Get OAuth token from auth service
        let token = self.auth_client.get_oauth_token("github", user_id).await?;
        
        // Extract repo and branch from config
        let repo = source.config.get("repository")
            .and_then(|v| v.as_str())
            .ok_or_else(|| AppError::BadRequest("Missing repository in config".to_string()))?;
        
        let branch = source.config.get("branch")
            .and_then(|v| v.as_str())
            .unwrap_or("main");
        
        // Fetch repository tree
        let files = self.github_client.get_repo_tree(&token, repo, branch).await?;
        
        let mut documents = Vec::new();
        let mut skipped_count = 0;
        
        for file in files {
            // Skip non-blob entries
            if file.file_type != "blob" {
                continue;
            }
            
            // Skip binary files
            if Self::is_binary_file(&file.path) {
                continue;
            }
            
            // Apply sync options filtering
            if !options.should_include(&file.path, file.size) {
                skipped_count += 1;
                continue;
            }
            
            // Fetch file content
            match self.github_client.get_file_content(&token, repo, &file.path, branch).await {
                Ok(content) => {
                    let mut doc = NormalizedDocument::new(
                        source.id,
                        ConnectorType::GitHub,
                        file.sha.clone(),
                        file.path.rsplit('/').next().unwrap_or(&file.path).to_string(),
                        content,
                    );
                    doc.path = Some(file.path.clone());
                    doc.content_type = Self::get_content_type(&file.path);
                    doc.language = Self::get_language(&file.path);
                    doc.metadata = serde_json::json!({
                        "repository": repo,
                        "branch": branch,
                        "sha": file.sha,
                        "size": file.size,
                    });
                    
                    documents.push(doc);
                }
                Err(e) => {
                    // Log but continue with other files
                    tracing::warn!("Failed to fetch {}: {}", file.path, e);
                }
            }
        }
        
        info!("Fetched {} documents from GitHub repository {} (skipped {} due to filters)", 
            documents.len(), repo, skipped_count);
        Ok(documents)
    }
}

