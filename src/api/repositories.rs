use actix_web::{web, HttpRequest, HttpResponse};
use serde::{Deserialize, Serialize};
use crate::error::{AppError, AppResult};
use crate::middleware::extract_user_id_from_http_request;
use crate::clients::GitHubApiClient;
use std::sync::Arc;

#[derive(Debug, Deserialize)]
pub struct CheckOAuthRequest {
    pub provider: String,
    pub repository: String,
}

#[derive(Debug, Serialize)]
pub struct CheckOAuthResponse {
    pub valid: bool,
    pub provider: String,
}

#[derive(Debug, Deserialize)]
pub struct BranchesQuery {
    pub provider: String,
    pub repo: String,
}

#[derive(Debug, Serialize)]
pub struct BranchInfo {
    pub name: String,
    pub is_default: bool,
}

#[derive(Debug, Serialize)]
pub struct BranchesResponse {
    pub branches: Vec<BranchInfo>,
}

#[derive(Debug, Serialize)]
pub struct RepositoryListResponse {
    pub repositories: Vec<RepositoryItem>,
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

/// Check OAuth access for a repository.
/// POST /api/repositories/oauth/check
pub async fn check_oauth(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    body: web::Json<CheckOAuthRequest>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    // Get OAuth token from auth service
    let token = app_state.auth_client.get_oauth_token(&body.provider, user_id).await?;
    
    // Validate access based on provider
    let valid = match body.provider.as_str() {
        "github" => {
            app_state.github_client.validate_repo_access(&token, &body.repository).await?
        }
        _ => {
            return Err(AppError::BadRequest(format!("Unsupported provider: {}", body.provider)));
        }
    };
    
    Ok(HttpResponse::Ok().json(CheckOAuthResponse {
        valid,
        provider: body.provider.clone(),
    }))
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
            
            let branch_infos: Vec<BranchInfo> = branches
                .into_iter()
                .map(|b| BranchInfo {
                    is_default: b.name == repo_info.default_branch,
                    name: b.name,
                })
                .collect();
            
            Ok(HttpResponse::Ok().json(BranchesResponse { branches: branch_infos }))
        }
        _ => {
            Err(AppError::BadRequest(format!("Unsupported provider: {}", query.provider)))
        }
    }
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
    
    Ok(HttpResponse::Ok().json(RepositoryListResponse { repositories: all_repos }))
}
