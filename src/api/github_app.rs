use actix_web::{web, HttpRequest, HttpResponse};
use serde::{Deserialize, Serialize};
use crate::error::{AppError, AppResult};
use crate::middleware::extract_user_id_from_http_request;
use crate::domain::models::{GitHubInstallation, GitHubRepoConfig, SyncStatus};
use crate::storage::Storage;
use chrono::Utc;
use uuid::Uuid;

// ============================================================================
// Request/Response Types
// ============================================================================

#[derive(Debug, Serialize)]
pub struct InstallUrlResponse {
    pub url: String,
}

#[derive(Debug, Deserialize)]
pub struct CallbackQuery {
    pub installation_id: Option<i64>,
    pub setup_action: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct InstallationInfo {
    pub installation_id: i64,
    pub account_login: String,
    pub account_type: String,
    pub created_at: String,
}

#[derive(Debug, Serialize)]
pub struct InstallationsResponse {
    pub installations: Vec<InstallationInfo>,
}

#[derive(Debug, Serialize)]
pub struct RepoInfo {
    pub id: i64,
    pub name: String,
    pub full_name: String,
    pub private: bool,
}

#[derive(Debug, Serialize)]
pub struct ReposResponse {
    pub repositories: Vec<RepoInfo>,
}

#[derive(Debug, Deserialize)]
pub struct ConfigureReposRequest {
    pub repositories: Vec<ConfigureRepoItem>,
}

#[derive(Debug, Deserialize)]
pub struct ConfigureRepoItem {
    pub full_name: String,
    #[serde(default)]
    pub branch: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ConfigureReposResponse {
    pub configured: usize,
    pub repo_configs: Vec<RepoConfigInfo>,
}

#[derive(Debug, Serialize)]
pub struct RepoConfigInfo {
    pub id: Uuid,
    pub repo_full_name: String,
    pub branch: Option<String>,
    pub sync_enabled: bool,
}

#[derive(Debug, Serialize)]
pub struct SyncRepoResponse {
    pub job_id: Uuid,
    pub status: String,
    pub message: String,
}

#[derive(Debug, Serialize)]
pub struct JobInfo {
    pub id: Uuid,
    pub source_id: Uuid,
    pub status: String,
    pub items_processed: usize,
    pub items_total: Option<usize>,
    pub error: Option<String>,
    pub started_at: String,
    pub completed_at: Option<String>,
}

// ============================================================================
// Endpoints
// ============================================================================

/// Get GitHub App installation URL.
/// GET /api/connectors/github/app/install-url
pub async fn get_install_url() -> AppResult<HttpResponse> {
    // TODO: Configure via environment
    let github_app_name = std::env::var("GITHUB_APP_NAME")
        .unwrap_or_else(|_| "conhub-data-connector".to_string());
    
    let url = format!("https://github.com/apps/{}/installations/new", github_app_name);
    
    Ok(HttpResponse::Ok().json(InstallUrlResponse { url }))
}

/// Handle GitHub App callback.
/// GET /api/connectors/github/app/callback
pub async fn callback(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    query: web::Query<CallbackQuery>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let installation_id = query.installation_id
        .ok_or_else(|| AppError::BadRequest("Missing installation_id".to_string()))?;
    
    // Save installation record
    let installation = GitHubInstallation {
        installation_id,
        user_id,
        account_login: "pending".to_string(), // Would be fetched from GitHub API
        account_type: "User".to_string(),
        created_at: Utc::now(),
    };
    
    app_state.storage.save_github_installation(installation).await?;
    
    Ok(HttpResponse::Ok().json(serde_json::json!({
        "success": true,
        "installation_id": installation_id,
        "message": "GitHub App installed successfully"
    })))
}

/// List GitHub App installations for user.
/// GET /api/connectors/github/app/installations
pub async fn list_installations(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let installations = app_state.storage.get_github_installations(user_id).await?;
    
    let items: Vec<InstallationInfo> = installations
        .into_iter()
        .map(|i| InstallationInfo {
            installation_id: i.installation_id,
            account_login: i.account_login,
            account_type: i.account_type,
            created_at: i.created_at.to_rfc3339(),
        })
        .collect();
    
    Ok(HttpResponse::Ok().json(InstallationsResponse { installations: items }))
}

/// List repositories for an installation.
/// GET /api/connectors/github/app/{installation_id}/repos
pub async fn list_repos(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<i64>,
) -> AppResult<HttpResponse> {
    let _user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let _installation_id = path.into_inner();
    
    // TODO: Fetch repos using GitHub App installation token
    // For now, return empty list
    Ok(HttpResponse::Ok().json(ReposResponse { repositories: vec![] }))
}

/// Configure repositories for sync.
/// POST /api/connectors/github/app/{installation_id}/repos
pub async fn configure_repos(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<i64>,
    body: web::Json<ConfigureReposRequest>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let installation_id = path.into_inner();
    
    let mut configs = Vec::new();
    
    for repo in &body.repositories {
        let mut config = GitHubRepoConfig::new(
            installation_id,
            user_id,
            repo.full_name.clone(),
        );
        config.branch = repo.branch.clone();
        
        let config = app_state.storage.save_github_repo_config(config).await?;
        configs.push(RepoConfigInfo {
            id: config.id,
            repo_full_name: config.repo_full_name,
            branch: config.branch,
            sync_enabled: config.sync_enabled,
        });
    }
    
    Ok(HttpResponse::Created().json(ConfigureReposResponse {
        configured: configs.len(),
        repo_configs: configs,
    }))
}

/// Get selected repositories for an installation.
/// GET /api/connectors/github/app/{installation_id}/repos/selected
pub async fn get_selected_repos(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<i64>,
) -> AppResult<HttpResponse> {
    let _user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let installation_id = path.into_inner();
    
    let configs = app_state.storage.get_github_repo_configs(installation_id).await?;
    
    let items: Vec<RepoConfigInfo> = configs
        .into_iter()
        .map(|c| RepoConfigInfo {
            id: c.id,
            repo_full_name: c.repo_full_name,
            branch: c.branch,
            sync_enabled: c.sync_enabled,
        })
        .collect();
    
    Ok(HttpResponse::Ok().json(serde_json::json!({ "repo_configs": items })))
}

/// Trigger sync for a configured repository.
/// POST /api/connectors/github/app/repos/{repo_config_id}/sync
pub async fn sync_repo(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<Uuid>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let repo_config_id = path.into_inner();
    
    let config = app_state.storage.get_github_repo_config(repo_config_id).await?
        .ok_or_else(|| AppError::NotFound("Repository config not found".to_string()))?;
    
    // Create a sync job
    let job = crate::domain::models::SyncJob::new(repo_config_id, user_id);
    let job = app_state.storage.save_sync_job(job).await?;
    
    Ok(HttpResponse::Accepted().json(SyncRepoResponse {
        job_id: job.id,
        status: "pending".to_string(),
        message: format!("Sync initiated for {}", config.repo_full_name),
    }))
}

/// Get sync job status.
/// GET /api/connectors/github/app/jobs/{job_id}
pub async fn get_job(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<Uuid>,
) -> AppResult<HttpResponse> {
    let _user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let job_id = path.into_inner();
    
    let job = app_state.storage.get_sync_job(job_id).await?
        .ok_or_else(|| AppError::NotFound("Job not found".to_string()))?;
    
    Ok(HttpResponse::Ok().json(JobInfo {
        id: job.id,
        source_id: job.source_id,
        status: format!("{:?}", job.status).to_lowercase(),
        items_processed: job.items_processed,
        items_total: job.items_total,
        error: job.error,
        started_at: job.started_at.to_rfc3339(),
        completed_at: job.completed_at.map(|t| t.to_rfc3339()),
    }))
}

/// Execute a pending sync job.
/// POST /api/connectors/github/app/jobs/{job_id}/execute
pub async fn execute_job(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<Uuid>,
) -> AppResult<HttpResponse> {
    let _user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let job_id = path.into_inner();
    
    // Update job status
    app_state.storage.update_sync_job_status(job_id, SyncStatus::Running, None).await?;
    
    // TODO: Actually execute the sync using installation token
    
    Ok(HttpResponse::Accepted().json(serde_json::json!({
        "job_id": job_id,
        "status": "running",
        "message": "Job execution started"
    })))
}
