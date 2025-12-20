use crate::error::{AppError, AppResult};
use base64::Engine;
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::debug;

/// Client for GitHub API operations.
pub struct GitHubApiClient {
    client: Client,
}

/// GitHub tree entry.
#[derive(Debug, Clone, Deserialize)]
pub struct TreeEntry {
    pub path: String,
    #[serde(rename = "type")]
    pub file_type: String,
    pub sha: String,
    #[serde(default)]
    pub size: Option<u64>,
}

#[derive(Debug, Deserialize)]
struct TreeResponse {
    tree: Vec<TreeEntry>,
    #[allow(dead_code)]
    truncated: bool,
}

#[derive(Debug, Deserialize)]
struct ContentResponse {
    content: Option<String>,
    encoding: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct Branch {
    pub name: String,
    #[allow(dead_code)]
    pub commit: BranchCommit,
}

#[derive(Debug, Deserialize)]
pub struct BranchCommit {
    #[allow(dead_code)]
    pub sha: String,
}

#[derive(Debug, Deserialize)]
pub struct RepoLanguages(pub std::collections::HashMap<String, u64>);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Repository {
    pub id: i64,
    pub name: String,
    pub full_name: String,
    pub private: bool,
    pub description: Option<String>,
    pub default_branch: String,
    pub html_url: String,
}

impl GitHubApiClient {
    pub fn new() -> Self {
        Self {
            client: Client::new(),
        }
    }

    /// Validate access to a repository.
    pub async fn validate_repo_access(&self, token: &str, repo: &str) -> AppResult<bool> {
        let url = format!("https://api.github.com/repos/{}", repo);
        
        let response = self.client
            .get(&url)
            .header("Authorization", format!("Bearer {}", token))
            .header("User-Agent", "data-service")
            .header("Accept", "application/vnd.github+json")
            .send()
            .await?;
        
        Ok(response.status().is_success())
    }

    /// Get repository details.
    pub async fn get_repository(&self, token: &str, repo: &str) -> AppResult<Repository> {
        let url = format!("https://api.github.com/repos/{}", repo);
        
        debug!("Fetching repository: {}", url);
        
        let response = self.client
            .get(&url)
            .header("Authorization", format!("Bearer {}", token))
            .header("User-Agent", "data-service")
            .header("Accept", "application/vnd.github+json")
            .send()
            .await?;
        
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(AppError::ExternalService(format!(
                "GitHub API returned {}: {}",
                status, body
            )));
        }
        
        let repo: Repository = response.json().await?;
        Ok(repo)
    }

    /// Get repository tree (list of all files).
    pub async fn get_repo_tree(&self, token: &str, repo: &str, branch: &str) -> AppResult<Vec<TreeEntry>> {
        let url = format!(
            "https://api.github.com/repos/{}/git/trees/{}?recursive=1",
            repo, branch
        );
        
        debug!("Fetching tree: {}", url);
        
        let response = self.client
            .get(&url)
            .header("Authorization", format!("Bearer {}", token))
            .header("User-Agent", "data-service")
            .header("Accept", "application/vnd.github+json")
            .send()
            .await?;
        
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(AppError::ExternalService(format!(
                "GitHub API returned {}: {}",
                status, body
            )));
        }
        
        let tree_response: TreeResponse = response.json().await?;
        Ok(tree_response.tree)
    }

    /// Get file content from a repository.
    pub async fn get_file_content(&self, token: &str, repo: &str, path: &str, branch: &str) -> AppResult<String> {
        let url = format!(
            "https://api.github.com/repos/{}/contents/{}?ref={}",
            repo, path, branch
        );
        
        let response = self.client
            .get(&url)
            .header("Authorization", format!("Bearer {}", token))
            .header("User-Agent", "data-service")
            .header("Accept", "application/vnd.github+json")
            .send()
            .await?;
        
        if !response.status().is_success() {
            let status = response.status();
            return Err(AppError::ExternalService(format!(
                "Failed to fetch file {}: {}",
                path, status
            )));
        }
        
        let content_response: ContentResponse = response.json().await?;
        
        match (content_response.content, content_response.encoding) {
            (Some(content), Some(encoding)) if encoding == "base64" => {
                // Remove newlines from base64 content and decode
                let cleaned = content.replace('\n', "");
                let decoded = base64::engine::general_purpose::STANDARD
                    .decode(&cleaned)
                    .map_err(|e| AppError::Internal(format!("Failed to decode base64: {}", e)))?;
                
                String::from_utf8(decoded)
                    .map_err(|e| AppError::Internal(format!("File is not valid UTF-8: {}", e)))
            }
            _ => Err(AppError::Internal("Unexpected content format".to_string())),
        }
    }

    /// Get repository branches.
    pub async fn get_branches(&self, token: &str, repo: &str) -> AppResult<Vec<Branch>> {
        let url = format!("https://api.github.com/repos/{}/branches", repo);
        
        let response = self.client
            .get(&url)
            .header("Authorization", format!("Bearer {}", token))
            .header("User-Agent", "data-service")
            .header("Accept", "application/vnd.github+json")
            .send()
            .await?;
        
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(AppError::ExternalService(format!(
                "GitHub API returned {}: {}",
                status, body
            )));
        }
        
        let branches: Vec<Branch> = response.json().await?;
        Ok(branches)
    }

    /// Get repository languages.
    pub async fn get_languages(&self, token: &str, repo: &str) -> AppResult<RepoLanguages> {
        let url = format!("https://api.github.com/repos/{}/languages", repo);
        
        let response = self.client
            .get(&url)
            .header("Authorization", format!("Bearer {}", token))
            .header("User-Agent", "data-service")
            .header("Accept", "application/vnd.github+json")
            .send()
            .await?;
        
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(AppError::ExternalService(format!(
                "GitHub API returned {}: {}",
                status, body
            )));
        }
        
        let languages: RepoLanguages = response.json().await?;
        Ok(languages)
    }

    /// List user repositories.
    pub async fn list_user_repos(&self, token: &str) -> AppResult<Vec<Repository>> {
        let url = "https://api.github.com/user/repos?per_page=100&sort=updated";
        
        let response = self.client
            .get(url)
            .header("Authorization", format!("Bearer {}", token))
            .header("User-Agent", "data-service")
            .header("Accept", "application/vnd.github+json")
            .send()
            .await?;
        
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(AppError::ExternalService(format!(
                "GitHub API returned {}: {}",
                status, body
            )));
        }
        
        let repos: Vec<Repository> = response.json().await?;
        Ok(repos)
    }
}

impl Default for GitHubApiClient {
    fn default() -> Self {
        Self::new()
    }
}
