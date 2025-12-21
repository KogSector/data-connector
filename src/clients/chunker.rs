use crate::domain::models::{NormalizedDocument, SourceKind};
use crate::error::{AppError, AppResult};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tracing::{debug, info};
use uuid::Uuid;

/// Client for communicating with the chunker service.
pub struct ChunkerClient {
    client: Client,
    base_url: String,
}

/// Item to send to the chunker.
#[derive(Debug, Serialize)]
struct ChunkItem {
    id: Uuid,
    source_id: Uuid,
    source_kind: SourceKind,
    content_type: String,
    content: String,
    metadata: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    created_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    updated_at: Option<String>,
}

/// Request payload for creating a chunk job.
#[derive(Debug, Serialize)]
struct CreateChunkJobRequest {
    source_id: Uuid,
    source_kind: SourceKind,
    items: Vec<ChunkItem>,
}

/// Response from creating a chunk job.
/// Matches chunker's StartChunkJobResponse format.
#[derive(Debug, Deserialize)]
pub struct ChunkJobResponse {
    pub job_id: Uuid,
    pub accepted: bool,
    pub items_count: usize,
    #[serde(default)]
    pub message: Option<String>,
}

impl ChunkerClient {
    pub fn new(base_url: String) -> Self {
        Self {
            client: Client::new(),
            base_url,
        }
    }

    /// Create a chunk job for the given documents.
    /// Calls: POST {CHUNKER_SERVICE_URL}/chunk/jobs
    pub async fn create_chunk_job(
        &self,
        source_id: Uuid,
        source_kind: SourceKind,
        documents: &[NormalizedDocument],
    ) -> AppResult<ChunkJobResponse> {
        let url = format!("{}/chunk/jobs", self.base_url);
        
        debug!("Creating chunk job at: {} with {} items", url, documents.len());
        
        let items: Vec<ChunkItem> = documents
            .iter()
            .map(|doc| ChunkItem {
                id: doc.id,
                source_id: doc.source_id,
                source_kind,
                content_type: format!("{:?}", doc.content_type).to_lowercase(),
                content: doc.content.clone(),
                metadata: doc.metadata.clone(),
                created_at: Some(doc.created_at.to_rfc3339()),
                updated_at: Some(doc.updated_at.to_rfc3339()),
            })
            .collect();
        
        let request = CreateChunkJobRequest {
            source_id,
            source_kind,
            items,
        };
        
        let response = self.client
            .post(&url)
            .json(&request)
            .send()
            .await
            .map_err(|e| AppError::ExternalService(format!("Chunker service request failed: {}", e)))?;
        
        if !response.status().is_success() {
            let status = response.status();
            let body = response.text().await.unwrap_or_default();
            return Err(AppError::ExternalService(format!(
                "Chunker service returned {}: {}",
                status, body
            )));
        }
        
        let job_response: ChunkJobResponse = response
            .json()
            .await
            .map_err(|e| AppError::ExternalService(format!("Failed to parse chunker response: {}", e)))?;
        
        info!(
            "Created chunk job {} (accepted: {}, items: {})", 
            job_response.job_id, 
            job_response.accepted,
            job_response.items_count
        );
        Ok(job_response)
    }
}
