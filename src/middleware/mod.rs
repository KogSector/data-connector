use actix_web::{dev::ServiceRequest, HttpMessage};
use jsonwebtoken::{decode, DecodingKey, Validation, Algorithm};
use serde::{Deserialize, Serialize};
use uuid::Uuid;
use std::sync::OnceLock;

/// Cached RSA public key for RS256 validation.
static RSA_PUBLIC_KEY: OnceLock<Option<DecodingKey>> = OnceLock::new();

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

/// Load RSA public key from file path (cached).
fn get_rsa_public_key(path: &str) -> Option<&'static DecodingKey> {
    RSA_PUBLIC_KEY.get_or_init(|| {
        match std::fs::read(path) {
            Ok(pem_bytes) => {
                match DecodingKey::from_rsa_pem(&pem_bytes) {
                    Ok(key) => {
                        tracing::info!("Loaded RSA public key from {}", path);
                        Some(key)
                    }
                    Err(e) => {
                        tracing::error!("Failed to parse RSA public key from {}: {}", path, e);
                        None
                    }
                }
            }
            Err(e) => {
                tracing::error!("Failed to read RSA public key file {}: {}", path, e);
                None
            }
        }
    }).as_ref()
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
    parse_user_id_from_token(token, jwt_secret, None)
}

/// Extract user ID from an HTTP request (for handlers).
pub fn extract_user_id_from_http_request(
    req: &actix_web::HttpRequest,
    jwt_secret: Option<&str>,
) -> Option<Uuid> {
    extract_user_id_from_http_request_with_key(req, jwt_secret, None)
}

/// Extract user ID from an HTTP request with optional RSA public key path.
pub fn extract_user_id_from_http_request_with_key(
    req: &actix_web::HttpRequest,
    jwt_secret: Option<&str>,
    jwt_public_key_path: Option<&str>,
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
    parse_user_id_from_token(token, jwt_secret, jwt_public_key_path)
}

/// Parse user ID from JWT token.
/// Priority: RS256 (if public key path provided) > HS256 (if secret provided) > Decode only (dev mode)
fn parse_user_id_from_token(
    token: &str,
    jwt_secret: Option<&str>,
    jwt_public_key_path: Option<&str>,
) -> Option<Uuid> {
    // Try RS256 first if public key path is available
    if let Some(key_path) = jwt_public_key_path {
        if let Some(key) = get_rsa_public_key(key_path) {
            let mut validation = Validation::new(Algorithm::RS256);
            validation.validate_exp = true;
            
            match decode::<Claims>(token, key, &validation) {
                Ok(token_data) => {
                    return Uuid::parse_str(&token_data.claims.sub).ok();
                }
                Err(e) => {
                    tracing::warn!("RS256 JWT validation failed: {}", e);
                    // Fall through to try HS256 or dev mode
                }
            }
        }
    }
    
    // Try HS256 if secret is provided
    if let Some(secret) = jwt_secret {
        let key = DecodingKey::from_secret(secret.as_bytes());
        let mut validation = Validation::new(Algorithm::HS256);
        validation.validate_exp = true;
        
        match decode::<Claims>(token, &key, &validation) {
            Ok(token_data) => {
                return Uuid::parse_str(&token_data.claims.sub).ok();
            }
            Err(e) => {
                tracing::warn!("HS256 JWT validation failed: {}", e);
                return None;
            }
        }
    }
    
    // Development mode: decode without validation
    // This allows testing without a properly signed token
    tracing::debug!("No JWT validation configured, decoding without signature verification");
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

