# ConFuse Data Connector

Data ingestion service for the ConFuse Knowledge Intelligence Platform. Connects to external data sources and triggers the knowledge processing pipeline.

## Overview

This service is the **data ingestion layer** that:
- Connects to GitHub, GitLab, Google Drive, Dropbox, and more
- Handles OAuth flows and token management
- Receives webhooks for real-time sync
- Triggers the knowledge processing pipeline

## Architecture

See [docs/README.md](docs/README.md) for complete architecture and integration details.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env .env.local

# Run migrations
alembic upgrade head

# Start server
uvicorn app.main:app --reload --port 8000
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sources` | GET | List connected sources |
| `/sources` | POST | Connect new source |
| `/sources/:id/sync` | POST | Trigger sync |
| `/webhooks/github` | POST | GitHub webhook |
| `/webhooks/gitlab` | POST | GitLab webhook |
| `/health` | GET | Health check |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection |
| `CODE_NORMALIZE_FETCH_URL` | Preprocessing service |
| `CHUNKER_URL` | Chunking service |
| `GITHUB_APP_ID` | GitHub App ID |
| `GOOGLE_CLIENT_ID` | Google OAuth client |

## Documentation

See [docs/](docs/) folder for:
- Connector setup guides
- Webhook configuration
- Data flow documentation

## Related Services

| Service | Port | Relationship |
|---------|------|--------------|
| code-normalize-fetch | 8090 | Receives files |
| chunker | 3002 | Receives content |
| auth-middleware | 3001 | Token validation |

## License

MIT - ConFuse Team