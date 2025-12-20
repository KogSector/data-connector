use actix_web::{HttpResponse, ResponseError};
use std::fmt;

/// Application error types.
#[derive(Debug)]
pub enum AppError {
    /// Bad request with message
    BadRequest(String),
    /// Unauthorized access
    Unauthorized(String),
    /// Forbidden access
    Forbidden(String),
    /// Resource not found
    NotFound(String),
    /// Internal server error
    Internal(String),
    /// External service error
    ExternalService(String),
    /// Validation error
    Validation(String),
}

impl fmt::Display for AppError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AppError::BadRequest(msg) => write!(f, "Bad Request: {}", msg),
            AppError::Unauthorized(msg) => write!(f, "Unauthorized: {}", msg),
            AppError::Forbidden(msg) => write!(f, "Forbidden: {}", msg),
            AppError::NotFound(msg) => write!(f, "Not Found: {}", msg),
            AppError::Internal(msg) => write!(f, "Internal Error: {}", msg),
            AppError::ExternalService(msg) => write!(f, "External Service Error: {}", msg),
            AppError::Validation(msg) => write!(f, "Validation Error: {}", msg),
        }
    }
}

impl ResponseError for AppError {
    fn error_response(&self) -> HttpResponse {
        let (status, error_type) = match self {
            AppError::BadRequest(_) => (actix_web::http::StatusCode::BAD_REQUEST, "bad_request"),
            AppError::Unauthorized(_) => (actix_web::http::StatusCode::UNAUTHORIZED, "unauthorized"),
            AppError::Forbidden(_) => (actix_web::http::StatusCode::FORBIDDEN, "forbidden"),
            AppError::NotFound(_) => (actix_web::http::StatusCode::NOT_FOUND, "not_found"),
            AppError::Internal(_) => (actix_web::http::StatusCode::INTERNAL_SERVER_ERROR, "internal_error"),
            AppError::ExternalService(_) => (actix_web::http::StatusCode::BAD_GATEWAY, "external_service_error"),
            AppError::Validation(_) => (actix_web::http::StatusCode::UNPROCESSABLE_ENTITY, "validation_error"),
        };

        HttpResponse::build(status).json(serde_json::json!({
            "error": error_type,
            "message": self.to_string()
        }))
    }
}

impl From<reqwest::Error> for AppError {
    fn from(err: reqwest::Error) -> Self {
        AppError::ExternalService(err.to_string())
    }
}

impl From<serde_json::Error> for AppError {
    fn from(err: serde_json::Error) -> Self {
        AppError::Internal(format!("JSON error: {}", err))
    }
}

impl From<std::io::Error> for AppError {
    fn from(err: std::io::Error) -> Self {
        AppError::Internal(format!("IO error: {}", err))
    }
}

pub type AppResult<T> = Result<T, AppError>;
