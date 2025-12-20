use actix_web::{web, HttpRequest, HttpResponse};
use serde::{Deserialize, Serialize};
use crate::error::{AppError, AppResult};
use crate::middleware::extract_user_id_from_http_request;
use crate::domain::models::{ConnectorType, DataSource};
use crate::domain::sync::SyncOrchestrator;
use crate::storage::Storage;
use std::sync::Arc;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct CreateSourceRequest {
    pub name: String,
    #[serde(rename = "type")]
    pub source_type: String,
    pub config: serde_json::Value,
}

#[derive(Debug, Serialize)]
pub struct CreateSourceResponse {
    pub id: Uuid,
    pub name: String,
    #[serde(rename = "type")]
    pub source_type: String,
    pub status: String,
    pub message: String,
}

#[derive(Debug, Serialize)]
pub struct SourceItem {
    pub id: Uuid,
    pub name: String,
    #[serde(rename = "type")]
    pub source_type: String,
    pub status: String,
    pub last_synced_at: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Serialize)]
pub struct ListSourcesResponse {
    pub sources: Vec<SourceItem>,
}

fn parse_connector_type(s: &str) -> Result<ConnectorType, AppError> {
    match s.to_lowercase().as_str() {
        "github" => Ok(ConnectorType::GitHub),
        "gitlab" => Ok(ConnectorType::GitLab),
        "bitbucket" => Ok(ConnectorType::Bitbucket),
        "google_drive" | "googledrive" => Ok(ConnectorType::GoogleDrive),
        "dropbox" => Ok(ConnectorType::Dropbox),
        "slack" => Ok(ConnectorType::Slack),
        "url_scraper" | "urlscraper" | "url" => Ok(ConnectorType::UrlScraper),
        "local_file" | "localfile" | "local" => Ok(ConnectorType::LocalFile),
        _ => Err(AppError::BadRequest(format!("Unknown source type: {}", s))),
    }
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
    
    // If it's a GitHub source, start background sync
    let message = if connector_type == ConnectorType::GitHub {
        let orchestrator = SyncOrchestrator::new(
            Arc::clone(&app_state.storage),
            Arc::clone(&app_state.auth_client),
            Arc::clone(&app_state.chunker_client),
            Arc::clone(&app_state.github_client),
        );
        
        match orchestrator.start_sync(source.clone(), user_id).await {
            Ok(_) => "Source created, sync started".to_string(),
            Err(e) => format!("Source created, but sync failed to start: {}", e),
        }
    } else {
        "Source created".to_string()
    };
    
    Ok(HttpResponse::Created().json(CreateSourceResponse {
        id: source_id,
        name: body.name.clone(),
        source_type: body.source_type.clone(),
        status: "pending".to_string(),
        message,
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
        .map(|s| SourceItem {
            id: s.id,
            name: s.name,
            source_type: s.connector_type.to_string(),
            status: format!("{:?}", s.status).to_lowercase(),
            last_synced_at: s.last_synced_at.map(|t| t.to_rfc3339()),
            created_at: s.created_at.to_rfc3339(),
        })
        .collect();
    
    Ok(HttpResponse::Ok().json(ListSourcesResponse { sources: items }))
}
