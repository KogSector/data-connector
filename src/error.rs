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
        let (status, error_code) = match self {
            AppError::BadRequest(_) => (actix_web::http::StatusCode::BAD_REQUEST, "BAD_REQUEST"),
            AppError::Unauthorized(_) => (actix_web::http::StatusCode::UNAUTHORIZED, "UNAUTHORIZED"),
            AppError::Forbidden(_) => (actix_web::http::StatusCode::FORBIDDEN, "FORBIDDEN"),
            AppError::NotFound(_) => (actix_web::http::StatusCode::NOT_FOUND, "NOT_FOUND"),
            AppError::Internal(_) => (actix_web::http::StatusCode::INTERNAL_SERVER_ERROR, "INTERNAL_ERROR"),
            AppError::ExternalService(_) => (actix_web::http::StatusCode::BAD_GATEWAY, "EXTERNAL_SERVICE_ERROR"),
            AppError::Validation(_) => (actix_web::http::StatusCode::UNPROCESSABLE_ENTITY, "VALIDATION_ERROR"),
        };

        // Use standardized response format: {success, data, error, code}
        HttpResponse::build(status).json(serde_json::json!({
            "success": false,
            "data": null,
            "error": self.to_string(),
            "code": error_code
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
