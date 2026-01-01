# ConFuse Data Connector

> Data Ingestion Service for the ConFuse Knowledge Intelligence Platform

## What is this service?

The **data-connector** is ConFuse's data ingestion layer. It connects to external data sources (GitHub, GitLab, Google Drive, etc.), manages OAuth tokens, handles webhooks for real-time updates, and orchestrates the knowledge processing pipeline.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/confuse/data-connector.git
cd data-connector

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env

# Run database migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --port 8000
```

The server starts at `http://localhost:8000`.

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | System design and data flows |
| [API Reference](api-reference.md) | Complete endpoint documentation |
| [Configuration](configuration.md) | Environment variables |
| [Connectors](connectors.md) | Supported data sources |
| [Integration](integration.md) | How it connects to other services |
| [Webhooks](webhooks.md) | Webhook handling guide |
| [Development](development.md) | Local development setup |
| [Troubleshooting](troubleshooting.md) | Common issues |

## How It Fits in ConFuse

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXTERNAL DATA SOURCES                                │
│   GitHub  │  GitLab  │  Bitbucket  │  G Drive  │  Dropbox  │  Local FS     │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ OAuth / API / Webhooks
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DATA-CONNECTOR (This Service)                           │
│                              Port: 8000                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                 │
│   │  Connectors  │    │   Webhooks   │    │   Workers    │                 │
│   │              │    │              │    │              │                 │
│   │ • GitHub     │    │ • Push       │    │ • Sync       │                 │
│   │ • GitLab     │    │ • PR/MR      │    │ • Process    │                 │
│   │ • Bitbucket  │    │ • File chg   │    │ • Embed      │                 │
│   │ • G Drive    │    │ • Comment    │    │ • Index      │                 │
│   │ • Dropbox    │    │              │    │              │                 │
│   │ • Local FS   │    │              │    │              │                 │
│   └──────────────┘    └──────────────┘    └──────────────┘                 │
│                                                                              │
│   ┌──────────────────────────────────────────────────────────────────────┐  │
│   │                         Job Queue (Redis)                             │  │
│   │   Manages async processing of sync and indexing jobs                  │  │
│   └──────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ Normalized content
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         KNOWLEDGE PIPELINE                                   │
│   code-normalize-fetch → chunker → embeddings → relation-graph              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Multi-Source Connectivity
- GitHub repositories, PRs, issues, wikis
- GitLab projects, merge requests
- Bitbucket repositories
- Google Drive documents, sheets, presentations
- Dropbox files and folders
- Local filesystem directories

### 2. Real-Time Sync via Webhooks
- Receive push events from Git providers
- Incremental updates (only changed files)
- PR/MR tracking and indexing
- Automatic re-indexing on changes

### 3. OAuth Token Management
- Secure token storage (encrypted)
- Automatic token refresh
- Multi-provider support
- Scoped access

### 4. Async Job Processing
- Redis-backed job queue
- Retry with exponential backoff
- Job status tracking
- Failure notifications

## Technology Stack

| Technology | Purpose |
|------------|---------|
| Python 3.11+ | Runtime |
| FastAPI | Web framework |
| SQLAlchemy | ORM |
| Alembic | Migrations |
| PostgreSQL | Data storage |
| Redis | Job queue |
| httpx | Async HTTP client |
| Celery | Background workers |

## Database Schema

Key tables:

```sql
sources          -- Connected data sources
files            -- Indexed files
sync_jobs        -- Sync job history
webhook_events   -- Received webhooks
oauth_tokens     -- Provider access tokens
```

## Related Services

| Service | Port | Relationship |
|---------|------|--------------|
| auth-middleware | 3001 | OAuth token management, API key validation |
| code-normalize-fetch | 8090 | Sends code files for preprocessing |
| chunker | 3002 | Sends normalized content for chunking |
| api-backend | 3003 | Source management API |
| relation-graph | 3018 | Sends entities for graph storage |

## License

MIT - ConFuse Team
