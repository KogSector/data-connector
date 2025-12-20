pub mod health;
pub mod github;
pub mod repositories;
pub mod data_sources;
pub mod documents;
pub mod local_sync;
pub mod github_app;

use actix_web::web;

/// Configure all API routes.
pub fn configure_routes(cfg: &mut web::ServiceConfig) {
    // Health endpoints
    cfg.service(
        web::scope("")
            .route("/health", web::get().to(health::health_check))
            .route("/status", web::get().to(health::status))
    );
    
    // GitHub endpoints (legacy + OAuth)
    cfg.service(
        web::scope("/api/github")
            .route("/validate-access", web::post().to(github::validate_access))
            .route("/sync-repository", web::post().to(github::sync_repository_legacy))
            .route("/branches", web::post().to(github::get_branches_legacy))
            .route("/languages", web::post().to(github::get_languages_legacy))
            .route("/sync", web::post().to(github::sync_oauth))
    );
    
    // Repository helper endpoints
    cfg.service(
        web::scope("/api/repositories")
            .route("/oauth/check", web::post().to(repositories::check_oauth))
            .route("/oauth/branches", web::get().to(repositories::get_branches_oauth))
            .route("", web::get().to(repositories::list_repositories))
    );
    
    // Data sources endpoints
    cfg.service(
        web::scope("/api/data")
            .route("/sources", web::post().to(data_sources::create_source))
            .route("/sources", web::get().to(data_sources::list_sources))
            .route("/local/sync", web::post().to(local_sync::sync_local))
    );
    
    // Alias for data sources
    cfg.route("/api/data-sources", web::get().to(data_sources::list_sources));
    
    // Documents endpoints
    cfg.service(
        web::scope("/api/documents")
            .route("", web::post().to(documents::create_document))
            .route("", web::get().to(documents::list_documents))
            .route("/{id}", web::delete().to(documents::delete_document))
            .route("/analytics", web::get().to(documents::get_analytics))
            .route("/upload", web::post().to(documents::upload_document))
            .route("/import", web::post().to(documents::import_cloud))
            .route("/cloud/files", web::get().to(documents::list_cloud_files))
    );
    
    // GitHub App endpoints
    cfg.service(
        web::scope("/api/connectors/github/app")
            .route("/install-url", web::get().to(github_app::get_install_url))
            .route("/callback", web::get().to(github_app::callback))
            .route("/installations", web::get().to(github_app::list_installations))
            .route("/{installation_id}/repos", web::get().to(github_app::list_repos))
            .route("/{installation_id}/repos", web::post().to(github_app::configure_repos))
            .route("/{installation_id}/repos/selected", web::get().to(github_app::get_selected_repos))
            .route("/repos/{repo_config_id}/sync", web::post().to(github_app::sync_repo))
            .route("/jobs/{job_id}", web::get().to(github_app::get_job))
            .route("/jobs/{job_id}/execute", web::post().to(github_app::execute_job))
    );
}
