use actix_web::{web, HttpRequest, HttpResponse};
use serde::{Deserialize, Serialize};
use crate::api::response::{success_response, error_response};
use crate::error::{AppError, AppResult};
use crate::middleware::extract_user_id_from_http_request;
use crate::domain::models::{ConnectorType, DataSource};
use crate::domain::sync::SyncOrchestrator;
use crate::storage::Storage;
use std::sync::Arc;
use uuid::Uuid;
use tracing::info;

/// Request format for POST /api/data/sources (original format)
#[derive(Debug, Deserialize)]
pub struct CreateSourceRequest {
    pub name: String,
    #[serde(rename = "type")]
    pub source_type: String,
    pub config: serde_json::Value,
}

/// Request format for POST /api/data-sources/connect (alternative format from API spec)
#[derive(Debug, Deserialize)]
pub struct ConnectSourceRequest {
    #[serde(rename = "type")]
    pub source_type: String,
    pub url: Option<String>,
    pub credentials: Option<serde_json::Value>,
    pub config: Option<serde_json::Value>,
}

#[derive(Debug, Serialize)]
pub struct CreateSourceResponse {
    pub success: bool,
    pub message: String,
    pub data: CreateSourceData,
    #[serde(rename = "syncStarted")]
    pub sync_started: bool,
}

#[derive(Debug, Serialize)]
pub struct CreateSourceData {
    pub id: Uuid,
    pub name: String,
    #[serde(rename = "type")]
    pub source_type: String,
    pub url: Option<String>,
    pub status: String,
    #[serde(rename = "defaultBranch")]
    pub default_branch: Option<String>,
    #[serde(rename = "createdAt")]
    pub created_at: String,
}

#[derive(Debug, Serialize)]
pub struct SourceItem {
    pub id: Uuid,
    pub user_id: Uuid,
    pub name: String,
    pub source_type: String,
    pub url: Option<String>,
    pub status: String,
    pub default_branch: Option<String>,
    pub sync_status: String,
    pub documents_count: u32,
    pub last_synced_at: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Serialize)]
pub struct ListSourcesData {
    #[serde(rename = "dataSources")]
    pub data_sources: Vec<SourceItem>,
}

#[derive(Debug, Serialize)]
pub struct ListSourcesResponse {
    pub success: bool,
    pub message: String,
    pub data: ListSourcesData,
}

#[derive(Debug, Serialize)]
pub struct SyncResponse {
    pub success: bool,
    pub message: String,
    pub data: SyncData,
}

#[derive(Debug, Serialize)]
pub struct SyncData {
    #[serde(rename = "syncId")]
    pub sync_id: String,
    pub status: String,
}

#[derive(Debug, Serialize)]
pub struct DeleteResponse {
    pub success: bool,
    pub message: String,
}

fn parse_connector_type(s: &str) -> Result<ConnectorType, AppError> {
    match s.to_lowercase().as_str() {
        "github" => Ok(ConnectorType::GitHub),
        "gitlab" => Ok(ConnectorType::GitLab),
        "bitbucket" => Ok(ConnectorType::Bitbucket),
        "google_drive" | "googledrive" => Ok(ConnectorType::GoogleDrive),
        "dropbox" => Ok(ConnectorType::Dropbox),
        "slack" => Ok(ConnectorType::Slack),
        "notion" => Ok(ConnectorType::Notion),
        "confluence" => Ok(ConnectorType::Confluence),
        "url_scraper" | "urlscraper" | "url" => Ok(ConnectorType::UrlScraper),
        "local_file" | "localfile" | "local" => Ok(ConnectorType::LocalFile),
        _ => Err(AppError::BadRequest(format!("Unknown source type: {}", s))),
    }
}

/// Extract name from URL (e.g., "https://github.com/owner/repo" -> "owner/repo")
fn extract_name_from_url(url: &str) -> String {
    if url.contains("github.com") || url.contains("gitlab.com") || url.contains("bitbucket.org") {
        // Extract owner/repo from URL
        let parts: Vec<&str> = url.trim_end_matches('/').rsplitn(3, '/').collect();
        if parts.len() >= 2 {
            return format!("{}/{}", parts[1], parts[0]);
        }
    }
    url.to_string()
}

/// Create a new data source.
/// POST /api/data/sources
pub async fn create_source(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    body: web::Json<CreateSourceRequest>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let connector_type = parse_connector_type(&body.source_type)?;
    
    // Create the data source
    let source = DataSource::new(
        user_id,
        body.name.clone(),
        connector_type,
        body.config.clone(),
    );
    
    // Save to storage
    let source = app_state.storage.save_source(source).await?;
    let source_id = source.id;
    let created_at = source.created_at.to_rfc3339();
    
    // If it's a GitHub source, start background sync
    let sync_started = if connector_type == ConnectorType::GitHub {
        let orchestrator = SyncOrchestrator::new(
            Arc::clone(&app_state.storage),
            Arc::clone(&app_state.auth_client),
            Arc::clone(&app_state.chunker_client),
            Arc::clone(&app_state.github_client),
        );
        
        orchestrator.start_sync(source.clone(), user_id).await.is_ok()
    } else {
        false
    };
    
    let url = body.config.get("repository")
        .or_else(|| body.config.get("url"))
        .and_then(|v| v.as_str())
        .map(String::from);
    
    let default_branch = body.config.get("branch")
        .or_else(|| body.config.get("defaultBranch"))
        .and_then(|v| v.as_str())
        .map(String::from);
    
    Ok(HttpResponse::Created().json(CreateSourceResponse {
        success: true,
        message: "Data source created successfully. Sync will be triggered automatically.".to_string(),
        data: CreateSourceData {
            id: source_id,
            name: body.name.clone(),
            source_type: body.source_type.clone(),
            url,
            status: "connected".to_string(),
            default_branch,
            created_at,
        },
        sync_started,
    }))
}

/// Connect a data source (alternative endpoint).
/// POST /api/data-sources/connect
pub async fn connect_source(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    body: web::Json<ConnectSourceRequest>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let connector_type = parse_connector_type(&body.source_type)?;
    
    // Build config from the request
    let mut config = body.config.clone().unwrap_or(serde_json::json!({}));
    if let Some(url) = &body.url {
        config["repository"] = serde_json::json!(extract_name_from_url(url));
        config["url"] = serde_json::json!(url);
    }
    if let Some(creds) = &body.credentials {
        if let Some(token) = creds.get("accessToken").or_else(|| creds.get("token")) {
            config["access_token"] = token.clone();
        }
    }
    
    // Extract name from config or URL
    let name = config.get("name")
        .and_then(|v| v.as_str())
        .map(String::from)
        .unwrap_or_else(|| {
            body.url.as_ref()
                .map(|u| extract_name_from_url(u))
                .unwrap_or_else(|| format!("{} Source", body.source_type))
        });
    
    // Create the data source
    let source = DataSource::new(
        user_id,
        name.clone(),
        connector_type,
        config,
    );
    
    // Save to storage
    let source = app_state.storage.save_source(source).await?;
    let source_id = source.id;
    let created_at = source.created_at.to_rfc3339();
    
    info!("Created data source {} for user {}", source_id, user_id);
    
    // If it's a GitHub source, start background sync
    let sync_started = if connector_type == ConnectorType::GitHub {
        let orchestrator = SyncOrchestrator::new(
            Arc::clone(&app_state.storage),
            Arc::clone(&app_state.auth_client),
            Arc::clone(&app_state.chunker_client),
            Arc::clone(&app_state.github_client),
        );
        
        orchestrator.start_sync(source.clone(), user_id).await.is_ok()
    } else {
        false
    };
    
    Ok(HttpResponse::Created().json(CreateSourceResponse {
        success: true,
        message: "Repository connected successfully".to_string(),
        data: CreateSourceData {
            id: source_id,
            name,
            source_type: body.source_type.clone(),
            url: body.url.clone(),
            status: "connected".to_string(),
            default_branch: source.config.get("defaultBranch")
                .or_else(|| source.config.get("branch"))
                .and_then(|v| v.as_str())
                .map(String::from),
            created_at,
        },
        sync_started,
    }))
}

/// List data sources for the current user.
/// GET /api/data/sources
/// GET /api/data-sources
pub async fn list_sources(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let sources = app_state.storage.get_sources_by_user(user_id).await?;
    
    let items: Vec<SourceItem> = sources
        .into_iter()
        .map(|s| {
            let url = s.config.get("url")
                .or_else(|| s.config.get("repository"))
                .and_then(|v| v.as_str())
                .map(String::from);
            
            let default_branch = s.config.get("branch")
                .or_else(|| s.config.get("defaultBranch"))
                .and_then(|v| v.as_str())
                .map(String::from);
            
            SourceItem {
                id: s.id,
                user_id: s.user_id,
                name: s.name,
                source_type: s.connector_type.to_string(),
                url,
                status: format!("{:?}", s.status).to_lowercase(),
                default_branch,
                sync_status: format!("{:?}", s.sync_status).to_lowercase(),
                documents_count: s.documents_count, // Will be 0 if not tracked
                last_synced_at: s.last_synced_at.map(|t| t.to_rfc3339()),
                created_at: s.created_at.to_rfc3339(),
            }
        })
        .collect();
    
    let count = items.len();
    
    Ok(HttpResponse::Ok().json(ListSourcesResponse {
        success: true,
        message: format!("Retrieved {} data sources", count),
        data: ListSourcesData { data_sources: items },
    }))
}

/// Get a single data source by ID.
/// GET /api/data-sources/{id}
pub async fn get_source(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<Uuid>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let source_id = path.into_inner();
    
    let source = app_state.storage.get_source(source_id).await?
        .ok_or_else(|| AppError::NotFound(format!("Data source {} not found", source_id)))?;
    
    // Verify ownership
    if source.user_id != user_id {
        return Err(AppError::Forbidden("You don't have access to this data source".to_string()));
    }
    
    let url = source.config.get("url")
        .or_else(|| source.config.get("repository"))
        .and_then(|v| v.as_str())
        .map(String::from);
    
    let default_branch = source.config.get("branch")
        .or_else(|| source.config.get("defaultBranch"))
        .and_then(|v| v.as_str())
        .map(String::from);
    
    let item = SourceItem {
        id: source.id,
        user_id: source.user_id,
        name: source.name,
        source_type: source.connector_type.to_string(),
        url,
        status: format!("{:?}", source.status).to_lowercase(),
        default_branch,
        sync_status: format!("{:?}", source.sync_status).to_lowercase(),
        documents_count: source.documents_count,
        last_synced_at: source.last_synced_at.map(|t| t.to_rfc3339()),
        created_at: source.created_at.to_rfc3339(),
    };
    
    Ok(success_response(item))
}

/// Delete a data source.
/// DELETE /api/data-sources/{id}
pub async fn delete_source(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<Uuid>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let source_id = path.into_inner();
    
    // Verify source exists and belongs to user
    let source = app_state.storage.get_source(source_id).await?
        .ok_or_else(|| AppError::NotFound(format!("Data source {} not found", source_id)))?;
    
    if source.user_id != user_id {
        return Err(AppError::Forbidden("You don't have access to this data source".to_string()));
    }
    
    // Delete from storage
    app_state.storage.delete_source(source_id).await?;
    
    info!("Deleted data source {} for user {}", source_id, user_id);
    
    Ok(HttpResponse::Ok().json(DeleteResponse {
        success: true,
        message: format!("Data source {} deleted successfully", source_id),
    }))
}

/// Trigger sync for a data source.
/// POST /api/data/sources/{id}/sync
pub async fn sync_source(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<Uuid>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let source_id = path.into_inner();
    
    // Verify source exists and belongs to user
    let source = app_state.storage.get_source(source_id).await?
        .ok_or_else(|| AppError::NotFound(format!("Data source {} not found", source_id)))?;
    
    if source.user_id != user_id {
        return Err(AppError::Forbidden("You don't have access to this data source".to_string()));
    }
    
    // Start sync
    let orchestrator = SyncOrchestrator::new(
        Arc::clone(&app_state.storage),
        Arc::clone(&app_state.auth_client),
        Arc::clone(&app_state.chunker_client),
        Arc::clone(&app_state.github_client),
    );
    
    match orchestrator.start_sync(source.clone(), user_id).await {
        Ok(job) => {
            info!("Started sync job {} for source {}", job.id, source_id);
            Ok(HttpResponse::Ok().json(SyncResponse {
                success: true,
                message: "Sync started successfully".to_string(),
                data: SyncData {
                    sync_id: job.id.to_string(),
                    status: "in-progress".to_string(),
                },
            }))
        }
        Err(e) => {
            Ok(error_response(format!("Failed to start sync: {}", e), Some("SYNC_FAILED")))
        }
    }
}

