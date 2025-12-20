use crate::clients::{AuthClient, GitHubApiClient};
use crate::domain::connectors::Connector;
use crate::domain::models::{ConnectorType, ContentType, DataSource, NormalizedDocument};
use crate::error::{AppError, AppResult};
use async_trait::async_trait;
use std::sync::Arc;
use tracing::info;
use uuid::Uuid;

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
        
        for file in files {
            // Skip non-blob entries and binary files
            if file.file_type != "blob" {
                continue;
            }
            
            // Skip likely binary files
            let ext = file.path.rsplit('.').next().unwrap_or("");
            if matches!(ext, "png" | "jpg" | "jpeg" | "gif" | "ico" | "svg" | "woff" | "woff2" | "ttf" | "eot" | "pdf" | "zip" | "tar" | "gz" | "exe" | "dll" | "so" | "dylib") {
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
        
        info!("Fetched {} documents from GitHub repository {}", documents.len(), repo);
        Ok(documents)
    }
}
