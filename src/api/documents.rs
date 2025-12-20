use actix_multipart::Multipart;
use actix_web::{web, HttpRequest, HttpResponse};
use futures::StreamExt;
use serde::{Deserialize, Serialize};
use crate::error::{AppError, AppResult};
use crate::middleware::extract_user_id_from_http_request;
use crate::domain::models::{ContentType, Document};
use crate::storage::Storage;
use uuid::Uuid;

#[derive(Debug, Deserialize)]
pub struct CreateDocumentRequest {
    pub name: String,
    pub content: String,
    #[serde(default)]
    pub content_type: Option<String>,
    #[serde(default)]
    pub metadata: Option<serde_json::Value>,
}

#[derive(Debug, Serialize)]
pub struct DocumentResponse {
    pub id: Uuid,
    pub name: String,
    pub content_type: String,
    pub file_size: Option<u64>,
    pub created_at: String,
}

#[derive(Debug, Serialize)]
pub struct ListDocumentsResponse {
    pub documents: Vec<DocumentResponse>,
}

#[derive(Debug, Deserialize)]
pub struct SearchQuery {
    #[serde(default)]
    pub search: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct ImportCloudRequest {
    pub provider: String,
    pub file_ids: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct ImportCloudResponse {
    pub imported: usize,
    pub message: String,
}

#[derive(Debug, Deserialize)]
pub struct CloudFilesQuery {
    pub provider: String,
}

#[derive(Debug, Serialize)]
pub struct CloudFile {
    pub id: String,
    pub name: String,
    pub mime_type: String,
    pub size: Option<u64>,
}

#[derive(Debug, Serialize)]
pub struct CloudFilesResponse {
    pub files: Vec<CloudFile>,
}

fn parse_content_type(s: &str) -> ContentType {
    match s.to_lowercase().as_str() {
        "text" => ContentType::Text,
        "code" => ContentType::Code,
        "markdown" | "md" => ContentType::Markdown,
        "html" => ContentType::Html,
        "json" => ContentType::Json,
        "xml" => ContentType::Xml,
        "yaml" | "yml" => ContentType::Yaml,
        _ => ContentType::Unknown,
    }
}

/// Create a new document.
/// POST /api/documents
pub async fn create_document(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    body: web::Json<CreateDocumentRequest>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let mut doc = Document::new(user_id, body.name.clone(), body.content.clone());
    
    if let Some(ct) = &body.content_type {
        doc.content_type = parse_content_type(ct);
    }
    
    if let Some(meta) = &body.metadata {
        doc.metadata = meta.clone();
    }
    
    doc.file_size = Some(body.content.len() as u64);
    
    let doc = app_state.storage.save_document(doc).await?;
    
    Ok(HttpResponse::Created().json(DocumentResponse {
        id: doc.id,
        name: doc.name,
        content_type: format!("{:?}", doc.content_type).to_lowercase(),
        file_size: doc.file_size,
        created_at: doc.created_at.to_rfc3339(),
    }))
}

/// List or search documents.
/// GET /api/documents?search=...
pub async fn list_documents(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    query: web::Query<SearchQuery>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let docs = if let Some(search) = &query.search {
        app_state.storage.search_documents(user_id, search).await?
    } else {
        app_state.storage.get_documents_by_user(user_id).await?
    };
    
    let items: Vec<DocumentResponse> = docs
        .into_iter()
        .map(|d| DocumentResponse {
            id: d.id,
            name: d.name,
            content_type: format!("{:?}", d.content_type).to_lowercase(),
            file_size: d.file_size,
            created_at: d.created_at.to_rfc3339(),
        })
        .collect();
    
    Ok(HttpResponse::Ok().json(ListDocumentsResponse { documents: items }))
}

/// Delete a document.
/// DELETE /api/documents/{id}
pub async fn delete_document(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    path: web::Path<Uuid>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let doc_id = path.into_inner();
    
    // Check ownership
    if let Some(doc) = app_state.storage.get_document(doc_id).await? {
        if doc.user_id != user_id {
            return Err(AppError::Forbidden("You don't own this document".to_string()));
        }
    } else {
        return Err(AppError::NotFound("Document not found".to_string()));
    }
    
    app_state.storage.delete_document(doc_id).await?;
    
    Ok(HttpResponse::NoContent().finish())
}

/// Get document analytics.
/// GET /api/documents/analytics
pub async fn get_analytics(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let analytics = app_state.storage.get_document_analytics(user_id).await?;
    
    Ok(HttpResponse::Ok().json(analytics))
}

/// Upload a document (multipart).
/// POST /api/documents/upload
pub async fn upload_document(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    mut payload: Multipart,
) -> AppResult<HttpResponse> {
    let user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    let mut uploaded = Vec::new();
    
    while let Some(item) = payload.next().await {
        let mut field = item.map_err(|e| AppError::BadRequest(format!("Multipart error: {}", e)))?;
        
        let filename = field.content_disposition()
            .and_then(|cd| cd.get_filename())
            .unwrap_or("unknown")
            .to_string();
        
        let mime_type = field.content_type()
            .map(|m| m.to_string())
            .unwrap_or_else(|| "application/octet-stream".to_string());
        
        // Collect file bytes
        let mut bytes = Vec::new();
        while let Some(chunk) = field.next().await {
            let chunk = chunk.map_err(|e| AppError::Internal(format!("Read error: {}", e)))?;
            bytes.extend_from_slice(&chunk);
        }
        
        // Try to convert to string (skip binary files)
        let content = match String::from_utf8(bytes.clone()) {
            Ok(s) => s,
            Err(_) => {
                tracing::warn!("Skipping binary file: {}", filename);
                continue;
            }
        };
        
        let mut doc = Document::new(user_id, filename.clone(), content);
        doc.file_size = Some(bytes.len() as u64);
        doc.mime_type = Some(mime_type);
        
        // Detect content type from filename
        let ext = filename.rsplit('.').next().unwrap_or("");
        doc.content_type = match ext.to_lowercase().as_str() {
            "md" | "markdown" => ContentType::Markdown,
            "html" | "htm" => ContentType::Html,
            "json" => ContentType::Json,
            "xml" => ContentType::Xml,
            "yaml" | "yml" => ContentType::Yaml,
            "txt" => ContentType::Text,
            "rs" | "py" | "js" | "ts" | "go" | "java" | "c" | "cpp" => ContentType::Code,
            _ => ContentType::Text,
        };
        
        let doc = app_state.storage.save_document(doc).await?;
        uploaded.push(DocumentResponse {
            id: doc.id,
            name: doc.name,
            content_type: format!("{:?}", doc.content_type).to_lowercase(),
            file_size: doc.file_size,
            created_at: doc.created_at.to_rfc3339(),
        });
    }
    
    Ok(HttpResponse::Created().json(serde_json::json!({
        "uploaded": uploaded.len(),
        "documents": uploaded,
    })))
}

/// Import documents from cloud provider (stub).
/// POST /api/documents/import
pub async fn import_cloud(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    body: web::Json<ImportCloudRequest>,
) -> AppResult<HttpResponse> {
    let _user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    // TODO: Implement cloud import when Google Drive/Dropbox connectors are ready
    Ok(HttpResponse::Ok().json(ImportCloudResponse {
        imported: 0,
        message: format!(
            "Cloud import from {} not yet implemented. Requested {} files.",
            body.provider,
            body.file_ids.len()
        ),
    }))
}

/// List files from cloud provider (stub).
/// GET /api/documents/cloud/files?provider=...
pub async fn list_cloud_files(
    req: HttpRequest,
    app_state: web::Data<crate::AppState>,
    query: web::Query<CloudFilesQuery>,
) -> AppResult<HttpResponse> {
    let _user_id = extract_user_id_from_http_request(&req, app_state.config.jwt_secret.as_deref())
        .ok_or_else(|| AppError::Unauthorized("Missing or invalid authorization".to_string()))?;
    
    // TODO: Implement when Google Drive/Dropbox connectors are ready
    Ok(HttpResponse::Ok().json(CloudFilesResponse {
        files: vec![],
    }))
}
