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
pub struct LocalSyncRequest {
    pub path: String,
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub profile: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct LocalSyncResponse {
    pub source_id: Uuid,
    pub job_id: Uuid,
    pub path: String,
    pub message: String,
}

/// Sync local filesystem directory.
/// POST /api/data/local/sync
pub async fn sync_local(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    body: web::Json<LocalSyncRequest>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    // Determine the path to sync
    let sync_path = if body.path.is_empty() {
        // Use profile or default path from config
        app_state.config.get_local_sync_path(body.profile.as_deref())
            .ok_or_else(|| AppError::BadRequest(
                "No path provided and no default configured".to_string()
            ))?
    } else {
        body.path.clone()
    };
    
    // Validate path exists
    let path = std::path::Path::new(&sync_path);
    if !path.exists() {
        return Err(AppError::NotFound(format!("Path does not exist: {}", sync_path)));
    }
    if !path.is_dir() {
        return Err(AppError::BadRequest(format!("Path is not a directory: {}", sync_path)));
    }
    
    // Create data source
    let source_name = body.name.clone().unwrap_or_else(|| {
        path.file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("Local Files")
            .to_string()
    });
    
    let source = DataSource::new(
        user_id,
        source_name,
        ConnectorType::LocalFile,
        serde_json::json!({
            "path": sync_path,
            "profile": body.profile,
        }),
    );
    
    // Save source
    let source = app_state.storage.save_source(source).await?;
    let source_id = source.id;
    
    // Start sync
    let orchestrator = SyncOrchestrator::new(
        Arc::clone(&app_state.storage),
        Arc::clone(&app_state.auth_client),
        Arc::clone(&app_state.chunker_client),
        Arc::clone(&app_state.github_client),
    );
    
    let job = orchestrator.start_sync(source, user_id).await?;
    
    Ok(HttpResponse::Accepted().json(LocalSyncResponse {
        source_id,
        job_id: job.id,
        path: sync_path,
        message: "Local sync started".to_string(),
    }))
}
