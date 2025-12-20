use actix_web::{HttpResponse, web};
use serde::Serialize;

#[derive(Serialize)]
struct HealthResponse {
    status: String,
}

#[derive(Serialize)]
struct StatusResponse {
    service: String,
    version: String,
    status: String,
    uptime_seconds: u64,
}

/// Health check endpoint.
/// GET /health
pub async fn health_check() -> HttpResponse {
    HttpResponse::Ok().json(HealthResponse {
        status: "ok".to_string(),
    })
}

/// Status endpoint with detailed information.
/// GET /status
pub async fn status(app_state: web::Data<crate::AppState>) -> HttpResponse {
    let uptime = app_state.started_at.elapsed().as_secs();
    
    HttpResponse::Ok().json(StatusResponse {
        service: "data-service".to_string(),
        version: env!("CARGO_PKG_VERSION").to_string(),
        status: "running".to_string(),
        uptime_seconds: uptime,
    })
}
