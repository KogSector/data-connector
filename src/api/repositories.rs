use actix_web::{web, HttpRequest, HttpResponse};
use serde::{Deserialize, Serialize};
use crate::api::response::success_response;
use crate::error::{AppError, AppResult};
use crate::middleware::extract_user_id_from_http_request;
use crate::clients::GitHubApiClient;
use std::sync::Arc;

/// Request format for POST /api/repositories/oauth/check
/// Supports both `repo_url` (full URL) and `repository` (owner/repo format)
#[derive(Debug, Deserialize)]
pub struct CheckOAuthRequest {
    pub provider: String,
    /// Repository in owner/repo format (also accepts repo_url alias)
    #[serde(alias = "repository")]
    pub repo_url: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct CheckOAuthResponse {
    pub success: bool,
    pub provider: String,
    pub name: Option<String>,
    pub full_name: Option<String>,
    pub default_branch: Option<String>,
    pub private: Option<bool>,
    pub has_read_access: bool,
    pub languages: Option<Vec<String>>,
    pub code: Option<String>,
    pub error: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct BranchesQuery {
    pub provider: String,
    pub repo: String,
}

/// Request format for POST /api/repositories/fetch-branches
#[derive(Debug, Deserialize)]
pub struct FetchBranchesRequest {
    /// Repository URL (also accepts repo_url alias)
    #[serde(alias = "repo_url")]
    #[serde(alias = "repoUrl")]
    pub repo_url: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct BranchInfo {
    pub name: String,
    pub is_default: bool,
}

#[derive(Debug, Serialize)]
pub struct BranchesResponseData {
    pub branches: Vec<String>,
    pub default_branch: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct BranchesResponse {
    pub success: bool,
    pub data: BranchesResponseData,
}

#[derive(Debug, Serialize)]
pub struct FetchBranchesResponse {
    pub branches: Vec<String>,
    #[serde(rename = "defaultBranch")]
    pub default_branch: String,
    pub provider: String,
    #[serde(rename = "repoInfo")]
    pub repo_info: RepoInfo,
}

#[derive(Debug, Serialize)]
pub struct RepoInfo {
    pub owner: String,
    pub repo: String,
}

#[derive(Debug, Serialize)]
pub struct RepositoryListData {
    pub repositories: Vec<RepositoryItem>,
}

#[derive(Debug, Serialize)]
pub struct RepositoryListResponse {
    pub success: bool,
    pub data: RepositoryListData,
}

#[derive(Debug, Serialize)]
pub struct RepositoryItem {
    pub id: i64,
    pub name: String,
    pub full_name: String,
    pub private: bool,
    pub description: Option<String>,
    pub default_branch: String,
    pub html_url: String,
    pub provider: String,
}

/// Extract owner/repo from various URL formats
fn extract_repo_from_url(url: &str) -> Option<(String, String)> {
    // Handle GitHub URLs: https://github.com/owner/repo or github.com/owner/repo
    let clean = url.trim_end_matches('/').trim_end_matches(".git");
    
    if clean.contains("github.com") || clean.contains("gitlab.com") || clean.contains("bitbucket.org") {
        let parts: Vec<&str> = clean.rsplitn(3, '/').collect();
        if parts.len() >= 2 {
            return Some((parts[1].to_string(), parts[0].to_string()));
        }
    }
    
    // Try owner/repo format directly
    if let Some((owner, repo)) = clean.split_once('/') {
        return Some((owner.to_string(), repo.to_string()));
    }
    
    None
}

/// Check OAuth access for a repository.
/// POST /api/repositories/oauth/check
pub async fn check_oauth(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    body: web::Json<CheckOAuthRequest>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    // Extract repository from repo_url field
    let repo_input = body.repo_url.as_ref()
        .ok_or_else(|| AppError::BadRequest("Missing repository or repo_url field".to_string()))?;
    
    let (owner, repo_name) = extract_repo_from_url(repo_input)
        .ok_or_else(|| AppError::BadRequest("Invalid repository URL format".to_string()))?;
    
    let full_repo = format!("{}/{}", owner, repo_name);
    
    // Get OAuth token from auth service
    let token = app_state.auth_client.get_oauth_token(&body.provider, user_id).await?;
    
    // Validate access based on provider
    match body.provider.as_str() {
        "github" => {
            match app_state.github_client.get_repository(&token, &full_repo).await {
                Ok(repo_info) => {
                    // Get languages - convert HashMap keys to Vec
                    let languages = app_state.github_client.get_languages(&token, &full_repo).await
                        .ok()
                        .map(|langs| langs.0.keys().cloned().collect::<Vec<String>>());
                    
                    Ok(HttpResponse::Ok().json(CheckOAuthResponse {
                        success: true,
                        provider: body.provider.clone(),
                        name: Some(repo_info.name),
                        full_name: Some(repo_info.full_name),
                        default_branch: Some(repo_info.default_branch),
                        private: Some(repo_info.private),
                        has_read_access: true,
                        languages,
                        code: None,
                        error: None,
                    }))
                }
                Err(e) => {
                    Ok(HttpResponse::Ok().json(CheckOAuthResponse {
                        success: false,
                        provider: body.provider.clone(),
                        name: None,
                        full_name: None,
                        default_branch: None,
                        private: None,
                        has_read_access: false,
                        languages: None,
                        code: Some("ACCESS_DENIED".to_string()),
                        error: Some(e.to_string()),
                    }))
                }
            }
        }
        _ => {
            Err(AppError::BadRequest(format!("Unsupported provider: {}", body.provider)))
        }
    }
}

/// Get repository branches via OAuth.
/// GET /api/repositories/oauth/branches?provider=...&repo=owner/repo
pub async fn get_branches_oauth(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    query: web::Query<BranchesQuery>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    // Get OAuth token from auth service
    let token = app_state.auth_client.get_oauth_token(&query.provider, user_id).await?;
    
    match query.provider.as_str() {
        "github" => {
            // Get repo info for default branch
            let repo_info = app_state.github_client.get_repository(&token, &query.repo).await?;
            let branches = app_state.github_client.get_branches(&token, &query.repo).await?;
            
            let branch_names: Vec<String> = branches.into_iter().map(|b| b.name).collect();
            
            Ok(HttpResponse::Ok().json(BranchesResponse {
                success: true,
                data: BranchesResponseData {
                    branches: branch_names,
                    default_branch: Some(repo_info.default_branch),
                },
            }))
        }
        _ => {
            Err(AppError::BadRequest(format!("Unsupported provider: {}", query.provider)))
        }
    }
}

/// Fetch branches for a repository URL.
/// POST /api/repositories/fetch-branches
pub async fn fetch_branches(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    body: web::Json<FetchBranchesRequest>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let repo_url = body.repo_url.as_ref()
        .ok_or_else(|| AppError::BadRequest("Missing repoUrl field".to_string()))?;
    
    let (owner, repo_name) = extract_repo_from_url(repo_url)
        .ok_or_else(|| AppError::BadRequest("Invalid repository URL format".to_string()))?;
    
    let full_repo = format!("{}/{}", owner, repo_name);
    
    // Determine provider from URL
    let provider = if repo_url.contains("github.com") {
        "github"
    } else if repo_url.contains("gitlab.com") {
        "gitlab"
    } else if repo_url.contains("bitbucket") {
        "bitbucket"
    } else {
        "github" // Default to GitHub
    };
    
    // Get OAuth token from auth service
    let token = app_state.auth_client.get_oauth_token(provider, user_id).await?;
    
    // Get branches
    let repo_info = app_state.github_client.get_repository(&token, &full_repo).await?;
    let branches = app_state.github_client.get_branches(&token, &full_repo).await?;
    
    let branch_names: Vec<String> = branches.into_iter().map(|b| b.name).collect();
    
    Ok(HttpResponse::Ok().json(FetchBranchesResponse {
        branches: branch_names,
        default_branch: repo_info.default_branch,
        provider: provider.to_string(),
        repo_info: RepoInfo {
            owner,
            repo: repo_name,
        },
    }))
}

/// List user repositories.
/// GET /api/repositories
pub async fn list_repositories(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let mut all_repos = Vec::new();
    
    // Try to get GitHub repos
    if let Ok(token) = app_state.auth_client.get_oauth_token("github", user_id).await {
        if let Ok(repos) = app_state.github_client.list_user_repos(&token).await {
            for repo in repos {
                all_repos.push(RepositoryItem {
                    id: repo.id,
                    name: repo.name,
                    full_name: repo.full_name,
                    private: repo.private,
                    description: repo.description,
                    default_branch: repo.default_branch,
                    html_url: repo.html_url,
                    provider: "github".to_string(),
                });
            }
        }
    }
    
    // TODO: Add other providers (GitLab, Bitbucket) when implemented
    
    Ok(HttpResponse::Ok().json(RepositoryListResponse {
        success: true,
        data: RepositoryListData { repositories: all_repos },
    }))
}

