use actix_web::{web, HttpRequest, HttpResponse};
use serde::{Deserialize, Serialize};
use crate::error::{AppError, AppResult};
use crate::middleware::extract_user_id_from_http_request;
use crate::domain::models::{ConnectorType, DataSource, SyncStatus};
use crate::domain::sync::SyncOrchestrator;
use crate::clients::{AuthClient, ChunkerClient, GitHubApiClient};
use crate::storage::Storage;
use std::sync::Arc;
use uuid::Uuid;

// ============================================================================
// Request/Response Types
// ============================================================================

#[derive(Debug, Deserialize)]
pub struct ValidateAccessRequest {
    pub access_token: String,
    pub repository: String,
}

#[derive(Debug, Serialize)]
pub struct ValidateAccessResponse {
    pub valid: bool,
    pub repository: Option<RepositoryInfo>,
}

#[derive(Debug, Serialize)]
pub struct RepositoryInfo {
    pub name: String,
    pub full_name: String,
    pub private: bool,
    pub default_branch: String,
}

#[derive(Debug, Deserialize)]
pub struct SyncRepositoryRequest {
    pub access_token: String,
    pub repository: String,
    #[serde(default)]
    pub branch: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct SyncResponse {
    pub success: bool,
    pub job_id: Option<Uuid>,
    pub message: String,
}

#[derive(Debug, Deserialize)]
pub struct BranchesRequest {
    pub access_token: String,
    pub repository: String,
}

#[derive(Debug, Serialize)]
pub struct BranchesResponse {
    pub branches: Vec<String>,
}

#[derive(Debug, Deserialize)]
pub struct LanguagesRequest {
    pub access_token: String,
    pub repository: String,
}

#[derive(Debug, Serialize)]
pub struct LanguagesResponse {
    pub languages: std::collections::HashMap<String, u64>,
}

#[derive(Debug, Deserialize)]
pub struct SyncOAuthRequest {
    pub repository: String,
    #[serde(default)]
    pub branch: Option<String>,
}

// ============================================================================
// Legacy Endpoints (token in body)
// ============================================================================

/// Validate GitHub repository access.
/// POST /api/github/validate-access
pub async fn validate_access(
    github_client: web::Data<Arc<GitHubApiClient>>,
    body: web::Json<ValidateAccessRequest>,
) -> AppResult<HttpResponse> {
    let valid = github_client.validate_repo_access(&body.access_token, &body.repository).await?;
    
    let repository = if valid {
        let repo = github_client.get_repository(&body.access_token, &body.repository).await?;
        Some(RepositoryInfo {
            name: repo.name,
            full_name: repo.full_name,
            private: repo.private,
            default_branch: repo.default_branch,
        })
    } else {
        None
    };
    
    Ok(HttpResponse::Ok().json(ValidateAccessResponse { valid, repository }))
}

/// Sync repository (legacy - token in body).
/// POST /api/github/sync-repository
pub async fn sync_repository_legacy(
    app_state: web::Data<crate::AppState>,
    body: web::Json<SyncRepositoryRequest>,
) -> AppResult<HttpResponse> {
    // For legacy endpoint, we create a temporary source and sync it
    // In production, you'd want to associate this with a user
    let temp_user_id = Uuid::nil(); // Placeholder for anonymous sync
    
    let source = DataSource::new(
        temp_user_id,
        body.repository.clone(),
        ConnectorType::GitHub,
        serde_json::json!({
            "repository": body.repository,
            "branch": body.branch.clone().unwrap_or_else(|| "main".to_string()),
            "access_token": body.access_token,  // Legacy: token stored in config
        }),
    );
    
    // Save source
    let source = app_state.storage.save_source(source).await?;
    
    Ok(HttpResponse::Ok().json(SyncResponse {
        success: true,
        job_id: Some(source.id),
        message: "Sync initiated (legacy mode)".to_string(),
    }))
}

/// Get repository branches (legacy).
/// POST /api/github/branches
pub async fn get_branches_legacy(
    github_client: web::Data<Arc<GitHubApiClient>>,
    body: web::Json<BranchesRequest>,
) -> AppResult<HttpResponse> {
    let branches = github_client.get_branches(&body.access_token, &body.repository).await?;
    
    Ok(HttpResponse::Ok().json(BranchesResponse {
        branches: branches.into_iter().map(|b| b.name).collect(),
    }))
}

/// Get repository languages (legacy).
/// POST /api/github/languages
pub async fn get_languages_legacy(
    github_client: web::Data<Arc<GitHubApiClient>>,
    body: web::Json<LanguagesRequest>,
) -> AppResult<HttpResponse> {
    let languages = github_client.get_languages(&body.access_token, &body.repository).await?;
    
    Ok(HttpResponse::Ok().json(LanguagesResponse {
        languages: languages.0,
    }))
}

// ============================================================================
// OAuth-based Endpoints
// ============================================================================

/// Sync repository using OAuth (token from auth-service).
/// POST /api/github/sync
pub async fn sync_oauth(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    body: web::Json<SyncOAuthRequest>,
) -> AppResult<HttpResponse> {
    // Extract user ID from JWT
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    // Create data source
    let source = DataSource::new(
        user_id,
        body.repository.clone(),
        ConnectorType::GitHub,
        serde_json::json!({
            "repository": body.repository,
            "branch": body.branch.clone().unwrap_or_else(|| "main".to_string()),
        }),
    );
    
    // Save source
    let source = app_state.storage.save_source(source).await?;
    
    // Create sync orchestrator and start background sync
    let orchestrator = SyncOrchestrator::new(
        Arc::clone(&app_state.storage),
        Arc::clone(&app_state.auth_client),
        Arc::clone(&app_state.chunker_client),
        Arc::clone(&app_state.github_client),
    );
    
    let job = orchestrator.start_sync(source, user_id).await?;
    
    Ok(HttpResponse::Accepted().json(SyncResponse {
        success: true,
        job_id: Some(job.id),
        message: "Sync started".to_string(),
    }))
}
