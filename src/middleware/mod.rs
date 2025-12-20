use actix_web::{dev::ServiceRequest, HttpMessage};
use jsonwebtoken::{decode, DecodingKey, Validation, Algorithm};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// JWT claims structure.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Claims {
    pub sub: String,
    pub exp: usize,
    #[serde(default)]
    pub iat: Option<usize>,
    #[serde(default)]
    pub email: Option<String>,
}

/// Extract user ID from a service request.
/// Parses the JWT from the Authorization header (if present).
pub fn extract_user_id_from_request(req: &ServiceRequest, jwt_secret: Option<&str>) -> Option<Uuid> {
    // Try to get from already-parsed extensions first
    if let Some(user_id) = req.extensions().get::<Uuid>() {
        return Some(*user_id);
    }
    
    // Try to parse from Authorization header
    let auth_header = req.headers().get("Authorization")?;
    let auth_str = auth_header.to_str().ok()?;
    
    if !auth_str.starts_with("Bearer ") {
        return None;
    }
    
    let token = &auth_str[7..];
    parse_user_id_from_token(token, jwt_secret)
}

/// Extract user ID from an HTTP request (for handlers).
pub fn extract_user_id_from_http_request(
    req: &actix_web::HttpRequest,
    jwt_secret: Option<&str>,
) -> Option<Uuid> {
    // Try to get from already-parsed extensions first
    if let Some(user_id) = req.extensions().get::<Uuid>() {
        return Some(*user_id);
    }
    
    // Try to parse from Authorization header
    let auth_header = req.headers().get("Authorization")?;
    let auth_str = auth_header.to_str().ok()?;
    
    if !auth_str.starts_with("Bearer ") {
        return None;
    }
    
    let token = &auth_str[7..];
    parse_user_id_from_token(token, jwt_secret)
}

/// Parse user ID from JWT token.
fn parse_user_id_from_token(token: &str, jwt_secret: Option<&str>) -> Option<Uuid> {
    // If we have a secret, validate the token
    if let Some(secret) = jwt_secret {
        let key = DecodingKey::from_secret(secret.as_bytes());
        let mut validation = Validation::new(Algorithm::HS256);
        validation.validate_exp = true;
        
        match decode::<Claims>(token, &key, &validation) {
            Ok(token_data) => {
                return Uuid::parse_str(&token_data.claims.sub).ok();
            }
            Err(e) => {
                tracing::warn!("JWT validation failed: {}", e);
                return None;
            }
        }
    }
    
    // If no secret, just decode without validation (development mode)
    // This allows testing without a properly signed token
    let parts: Vec<&str> = token.split('.').collect();
    if parts.len() != 3 {
        return None;
    }
    
    // Decode the payload (second part)
    let payload = base64::engine::general_purpose::URL_SAFE_NO_PAD
        .decode(parts[1])
        .ok()?;
    
    let claims: Claims = serde_json::from_slice(&payload).ok()?;
    Uuid::parse_str(&claims.sub).ok()
}

use base64::Engine;
