# ConHub Data Connector Service

Python FastAPI implementation of the data connector service for syncing content from various sources (GitHub, local files, cloud storage, etc.) to the ConHub knowledge platform.

## Features

- **Multi-source connectors**: GitHub, GitLab, Google Drive, Dropbox, OneDrive, Slack, Notion, Confluence, local files
- **Background sync**: Celery workers for async sync operations
- **PostgreSQL persistence**: Full state management with SQLAlchemy ORM
- **Webhook support**: Real-time updates from provider webhooks
- **Chunker integration**: Automatic chunking of synced content
- **OAuth flows**: Built-in OAuth handling for providers

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 15+
- Redis 7+

### Local Development

1. **Install dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

2. **Start services with Docker:**
   ```bash
   docker-compose -f docker-compose.dev.yml up -d db redis minio
   ```

3. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

4. **Start the API server:**
   ```bash
   uvicorn app.main:app --reload --port 3013
   ```

5. **Start Celery worker (in another terminal):**
   ```bash
   celery -A workers.celery_app worker --loglevel=info
   ```

### Using Docker Compose

```bash
# Start all services
docker-compose -f docker-compose.dev.yml up -d

# View logs
docker-compose -f docker-compose.dev.yml logs -f api

# Stop services
docker-compose -f docker-compose.dev.yml down
```

## API Endpoints

### Health
- `GET /health` - Health check
- `GET /status` - Extended status

### Connectors
- `POST /connectors` - Create connector
- `GET /connectors` - List connectors
- `GET /connectors/{id}` - Get connector details
- `DELETE /connectors/{id}` - Delete connector
- `POST /connectors/{id}/test` - Test connection

### OAuth
- `GET /connectors/{id}/oauth/start` - Initiate OAuth
- `GET /connectors/{id}/oauth/callback` - OAuth callback

### Sync
- `POST /connectors/{id}/sync` - Trigger sync
- `GET /connectors/{id}/status` - Get sync status

### Webhooks
- `POST /webhook/{connector}` - Receive provider webhooks
- `POST /data-connector/chunker-callbacks` - Chunker callbacks

### Legacy (Backward Compatibility)
- `/api/github/*` - Legacy GitHub endpoints
- `/api/data/*` - Legacy data source endpoints
- `/api/data-sources/*` - Alternative data source endpoints

## Configuration

Environment variables (see `.env` for defaults):

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | 3013 |
| `DATABASE_URL` | PostgreSQL connection | postgresql://... |
| `REDIS_URL` | Redis connection | redis://localhost:6379 |
| `AUTH_SERVICE_URL` | Auth service URL | http://localhost:3010 |
| `CHUNKER_SERVICE_URL` | Chunker service URL | http://localhost:3017 |
| `EMBEDDING_ENABLED` | Enable embeddings | true |
| `GRAPH_RAG_ENABLED` | Enable graph RAG | true |

## Project Structure

```
data-connector/
├── app/                    # FastAPI application
│   ├── main.py            # App factory
│   ├── config.py          # Settings
│   ├── schemas.py         # Pydantic models
│   └── exceptions.py      # Custom exceptions
├── connectors/            # Connector implementations
│   ├── base.py           # Abstract base class
│   ├── github.py         # GitHub connector
│   ├── local_file.py     # Local file connector
│   └── registry.py       # Connector factory
├── db/                    # Database layer
│   ├── models.py         # SQLAlchemy models
│   └── session.py        # Session management
├── routes/                # API routes
│   ├── connectors.py     # CRUD endpoints
│   ├── sync.py           # Sync endpoints
│   ├── oauth.py          # OAuth endpoints
│   ├── webhooks.py       # Webhook endpoints
│   └── legacy.py         # Backward compatibility
├── services/              # Business logic
│   ├── chunker_client.py # Chunker HTTP client
│   └── sync_service.py   # Sync orchestrator
├── workers/               # Celery tasks
│   ├── celery_app.py     # Celery configuration
│   └── sync_tasks.py     # Background tasks
├── tests/                 # Test suite
├── pyproject.toml        # Project config
├── requirements.txt      # Dependencies
├── Dockerfile            # Container image
└── docker-compose.dev.yml # Local dev stack
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov=connectors --cov=services

# Run specific tests
pytest tests/test_connectors/ -v
```

## Development

### Adding a New Connector

1. Create `connectors/<provider>.py` extending `BaseConnector`
2. Implement required methods: `authorize`, `list_items`, `fetch_item`
3. Register in `connectors/registry.py`
4. Add OAuth URLs if applicable in `routes/oauth.py`

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Migration from Rust

This service is a Python port of the original Rust data-connector. Key differences:

- **Framework**: Actix-web → FastAPI
- **Storage**: In-memory → PostgreSQL
- **Background tasks**: tokio::spawn → Celery
- **HTTP client**: reqwest → httpx

The API endpoints are backward compatible with the Rust implementation.

## License

MIT