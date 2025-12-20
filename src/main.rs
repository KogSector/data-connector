mod api;
mod clients;
mod config;
mod domain;
mod error;
mod middleware;
mod storage;

use actix_cors::Cors;
use actix_web::{web, App, HttpServer};
use clients::{AuthClient, ChunkerClient, GitHubApiClient};
use config::Config;
use storage::memory::InMemoryStorage;
use storage::Storage;
use std::sync::Arc;
use std::time::Instant;
use tracing::info;
use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt};

/// Application state shared across handlers.
pub struct AppState {
    pub config: Config,
    pub storage: Arc<dyn Storage>,
    pub auth_client: Arc<AuthClient>,
    pub chunker_client: Arc<ChunkerClient>,
    pub github_client: Arc<GitHubApiClient>,
    pub started_at: Instant,
}

#[tokio::main]
async fn main() -> std::io::Result<()> {
    // Initialize tracing
    tracing_subscriber::registry()
        .with(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "data_service=debug,actix_web=info".into()),
        )
        .with(tracing_subscriber::fmt::layer())
        .init();

    // Load configuration
    let config = Config::from_env();
    let port = config.port;

    info!("Starting data-service on port {}", port);
    info!("Auth service URL: {}", config.auth_service_url);
    info!("Chunker service URL: {}", config.chunker_service_url);

    // Initialize clients
    let auth_client = Arc::new(AuthClient::with_api_key(
        config.auth_service_url.clone(),
        config.internal_api_key.clone(),
    ));
    let chunker_client = Arc::new(ChunkerClient::new(config.chunker_service_url.clone()));
    let github_client = Arc::new(GitHubApiClient::new());

    // Initialize storage
    let storage: Arc<dyn Storage> = Arc::new(InMemoryStorage::new());

    // Create app state
    let app_state = web::Data::new(AppState {
        config: config.clone(),
        storage: Arc::clone(&storage),
        auth_client: Arc::clone(&auth_client),
        chunker_client: Arc::clone(&chunker_client),
        github_client: Arc::clone(&github_client),
        started_at: Instant::now(),
    });

    let github_client_data = web::Data::new(Arc::clone(&github_client));

    // Start HTTP server
    HttpServer::new(move || {
        // Configure CORS for local development and production
        let cors = Cors::default()
            .allowed_origin("http://localhost:3000")
            .allowed_origin("http://localhost:3001")
            .allowed_origin("http://localhost:5173")
            .allowed_origin("http://127.0.0.1:3000")
            .allowed_origin("http://127.0.0.1:3001")
            .allowed_origin("http://127.0.0.1:5173")
            .allowed_methods(vec!["GET", "POST", "PUT", "DELETE", "OPTIONS"])
            .allowed_headers(vec![
                actix_web::http::header::AUTHORIZATION,
                actix_web::http::header::ACCEPT,
                actix_web::http::header::CONTENT_TYPE,
                actix_web::http::header::HeaderName::from_static("x-correlation-id"),
            ])
            .supports_credentials()  // Enable Access-Control-Allow-Credentials: true
            .max_age(3600);

        App::new()
            .wrap(cors)
            .app_data(app_state.clone())
            .app_data(github_client_data.clone())
            .configure(api::configure_routes)
    })
    .bind(("0.0.0.0", port))?
    .run()
    .await
}
