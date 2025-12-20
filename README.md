# Data Service

ConHub's data ingestion microservice providing connector-based content fetching from multiple sources.

## Features

- **Connector Framework**: Fetch content from GitHub, GitLab, Bitbucket, Google Drive, Dropbox, Slack, URLs, and local files
- **Sync Orchestration**: Background sync jobs with status tracking
- **OAuth Integration**: Retrieves provider tokens from auth-service
- **Downstream Pipeline**: Triggers chunker service for content processing
- **Document Management**: Upload, search, and manage documents

## Quick Start

### Prerequisites

- Rust 1.70+ (install from https://rustup.rs)

### Running Locally

```powershell
# Clone and navigate to the project
cd data-connector

# Run in development mode
cargo run
```

The server starts on `http://localhost:3013` by default.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3013` | Server port |
| `AUTH_SERVICE_URL` | `http://localhost:3010` | Auth service for OAuth tokens |
| `CHUNKER_SERVICE_URL` | `http://localhost:3012` | Chunker service for processing |
| `DATABASE_URL` | - | Optional PostgreSQL connection |
| `JWT_SECRET` | - | JWT validation secret (optional for dev) |
| `LOCAL_SYNC_PATH_DEFAULT` | - | Default path for local file sync |
| `GITHUB_APP_NAME` | `conhub-data-connector` | GitHub App name |

### Example Requests

#### Health Check
```powershell
curl http://localhost:3013/health
# Response: {"status":"ok"}
```

#### Status
```powershell
curl http://localhost:3013/status
# Response: {"service":"data-service","version":"0.1.0","status":"running","uptime_seconds":123}
```

#### Create GitHub Data Source (OAuth)
```powershell
curl -X POST http://localhost:3013/api/data/sources `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <jwt_token>" `
  -d '{
    "name": "My Repository",
    "type": "github",
    "config": {
      "repository": "owner/repo",
      "branch": "main"
    }
  }'
```

#### List Data Sources
```powershell
curl http://localhost:3013/api/data/sources `
  -H "Authorization: Bearer <jwt_token>"
```

#### Upload Document
```powershell
curl -X POST http://localhost:3013/api/documents/upload `
  -H "Authorization: Bearer <jwt_token>" `
  -F "file=@path/to/document.md"
```

#### Create Document
```powershell
curl -X POST http://localhost:3013/api/documents `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <jwt_token>" `
  -d '{
    "name": "example.md",
    "content": "# Hello World",
    "content_type": "markdown"
  }'
```

#### List Documents
```powershell
curl http://localhost:3013/api/documents `
  -H "Authorization: Bearer <jwt_token>"
```

#### Search Documents
```powershell
curl "http://localhost:3013/api/documents?search=hello" `
  -H "Authorization: Bearer <jwt_token>"
```

#### Local Filesystem Sync
```powershell
curl -X POST http://localhost:3013/api/data/local/sync `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <jwt_token>" `
  -d '{
    "path": "C:/Users/me/projects/mycode",
    "name": "My Local Code"
  }'
```

#### GitHub Sync (OAuth)
```powershell
curl -X POST http://localhost:3013/api/github/sync `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer <jwt_token>" `
  -d '{
    "repository": "owner/repo",
    "branch": "main"
  }'
```

## API Endpoints

### Health & Status
- `GET /health` - Health check
- `GET /status` - Detailed status

### GitHub (Legacy - token in body)
- `POST /api/github/validate-access` - Validate repo access
- `POST /api/github/sync-repository` - Sync repository
- `POST /api/github/branches` - Get branches
- `POST /api/github/languages` - Get languages

### GitHub (OAuth - token from auth-service)
- `POST /api/github/sync` - Sync repository

### Repository Helpers
- `POST /api/repositories/oauth/check` - Check OAuth access
- `GET /api/repositories/oauth/branches` - Get branches
- `GET /api/repositories` - List user repositories

### Data Sources
- `POST /api/data/sources` - Create data source
- `GET /api/data/sources` - List data sources
- `GET /api/data-sources` - Alias

### Documents
- `POST /api/documents` - Create document
- `GET /api/documents` - List/search documents
- `DELETE /api/documents/{id}` - Delete document
- `GET /api/documents/analytics` - Get analytics
- `POST /api/documents/upload` - Upload file
- `POST /api/documents/import` - Cloud import (stub)
- `GET /api/documents/cloud/files` - List cloud files (stub)

### Local Sync
- `POST /api/data/local/sync` - Sync local directory

### GitHub App
- `GET /api/connectors/github/app/install-url` - Get install URL
- `GET /api/connectors/github/app/callback` - OAuth callback
- `GET /api/connectors/github/app/installations` - List installations
- `GET /api/connectors/github/app/{installation_id}/repos` - List repos
- `POST /api/connectors/github/app/{installation_id}/repos` - Configure repos
- `GET /api/connectors/github/app/{installation_id}/repos/selected` - Get selected
- `POST /api/connectors/github/app/repos/{repo_config_id}/sync` - Sync repo
- `GET /api/connectors/github/app/jobs/{job_id}` - Get job status
- `POST /api/connectors/github/app/jobs/{job_id}/execute` - Execute job

## Architecture

```
src/
├── main.rs              # Entry point
├── config.rs            # Environment configuration
├── error.rs             # Error types
├── api/                 # HTTP handlers
├── domain/              # Business logic
│   ├── models.rs        # Data models
│   ├── connectors/      # Connector implementations
│   └── sync.rs          # Sync orchestration
├── clients/             # External service clients
├── storage/             # Persistence layer
└── middleware/          # JWT middleware
```

## Connector Types

| Type | Status | Description |
|------|--------|-------------|
| `github` | ✅ Full | GitHub repositories |
| `local_file` | ✅ Full | Local filesystem |
| `gitlab` | 🔲 Stub | GitLab repositories |
| `bitbucket` | 🔲 Stub | Bitbucket repositories |
| `google_drive` | 🔲 Stub | Google Drive documents |
| `dropbox` | 🔲 Stub | Dropbox files |
| `slack` | 🔲 Stub | Slack messages |
| `url_scraper` | 🔲 Stub | Web page scraping |

## License

MIT