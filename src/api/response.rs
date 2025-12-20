use actix_web::HttpResponse;
use serde::Serialize;

/// Standardized API response format.
/// 
/// # Example Success Response
/// ```json
/// {
///     "success": true,
///     "data": { "id": "...", "name": "..." },
///     "error": null,
///     "code": null
/// }
/// ```
/// 
/// # Example Error Response
/// ```json
/// {
///     "success": false,
///     "data": null,
///     "error": "User-friendly error message",
///     "code": "ERROR_CODE"
/// }
/// ```
#[derive(Debug, Serialize)]
pub struct ApiResponse<T: Serialize> {
    pub success: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<T>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub code: Option<String>,
}

impl<T: Serialize> ApiResponse<T> {
    /// Create a success response with data.
    pub fn success(data: T) -> Self {
        Self {
            success: true,
            data: Some(data),
            error: None,
            code: None,
        }
    }

    /// Create an error response.
    pub fn error(message: impl Into<String>, code: Option<String>) -> ApiResponse<()> {
        ApiResponse {
            success: false,
            data: None,
            error: Some(message.into()),
            code,
        }
    }

    /// Convert to HttpResponse with 200 OK.
    pub fn to_http_response(&self) -> HttpResponse 
    where
        T: Serialize,
    {
        HttpResponse::Ok().json(self)
    }
}

/// Helper trait for creating API responses from handlers.
pub trait IntoApiResponse<T: Serialize> {
    fn into_api_response(self) -> HttpResponse;
}

impl<T: Serialize> IntoApiResponse<T> for T {
    fn into_api_response(self) -> HttpResponse {
        HttpResponse::Ok().json(ApiResponse::success(self))
    }
}

/// Create a success HttpResponse with the standard format.
pub fn success_response<T: Serialize>(data: T) -> HttpResponse {
    HttpResponse::Ok().json(ApiResponse::success(data))
}

/// Create an error HttpResponse with the standard format.
pub fn error_response(message: impl Into<String>, code: Option<&str>) -> HttpResponse {
    HttpResponse::Ok().json(ApiResponse::<()>::error(message, code.map(String::from)))
}

/// Create a 201 Created response with the standard format.
pub fn created_response<T: Serialize>(data: T) -> HttpResponse {
    HttpResponse::Created().json(ApiResponse::success(data))
}

/// Create a 202 Accepted response with the standard format.
pub fn accepted_response<T: Serialize>(data: T) -> HttpResponse {
    HttpResponse::Accepted().json(ApiResponse::success(data))
}
