# Data Connector Configuration

> Complete configuration guide for the ConFuse Data-Connector

## Environment Variables

### Required Variables

```env
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/confuse

# Redis (for job queue)
REDIS_URL=redis://localhost:6379

# Downstream Services
CODE_NORMALIZE_FETCH_URL=http://localhost:8090
CHUNKER_URL=http://localhost:3002
EMBEDDINGS_URL=http://localhost:3005
RELATION_GRAPH_URL=http://localhost:3018

# Auth
AUTH_MIDDLEWARE_URL=http://localhost:3001
```

### Optional Variables

```env
# Server
PORT=8000
HOST=0.0.0.0
DEBUG=false
LOG_LEVEL=info

# Worker Settings
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
WORKER_CONCURRENCY=4

# GitHub
GITHUB_APP_ID=12345
GITHUB_PRIVATE_KEY_PATH=/path/to/private-key.pem
GITHUB_WEBHOOK_SECRET=your-webhook-secret

# GitLab
GITLAB_APP_ID=your-app-id
GITLAB_APP_SECRET=your-app-secret
GITLAB_WEBHOOK_TOKEN=your-webhook-token

# Google
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxx
GOOGLE_SERVICE_ACCOUNT_PATH=/path/to/service-account.json

# Dropbox
DROPBOX_APP_KEY=xxx
DROPBOX_APP_SECRET=xxx

# File Processing
MAX_FILE_SIZE=1048576
MAX_CONCURRENT_DOWNLOADS=10
DOWNLOAD_TIMEOUT=30

# Sync Settings
DEFAULT_SYNC_SCHEDULE=0 */6 * * *
FULL_SYNC_INTERVAL_HOURS=24
WEBHOOK_RETRY_COUNT=3

# Local FS (for local connector)
FS_ALLOWED_PATHS=/home/user/projects,/opt/code
```

## Configuration Details

### Database Configuration

PostgreSQL connection string:
```
postgresql://[user]:[password]@[host]:[port]/[database]?[options]
```

Required tables are created via Alembic migrations:
```bash
alembic upgrade head
```

### GitHub App Configuration

For GitHub integration, you need a GitHub App:

1. Create GitHub App at https://github.com/settings/apps
2. Configure permissions:
   - Repository: Contents (Read)
   - Repository: Metadata (Read)
   - Repository: Pull requests (Read)
   - Repository: Webhooks (Read & Write)
3. Generate and download private key
4. Note the App ID

```env
GITHUB_APP_ID=123456
GITHUB_PRIVATE_KEY_PATH=/etc/confuse/github-private-key.pem
GITHUB_WEBHOOK_SECRET=generated-secret
```

### Google OAuth Configuration

1. Create OAuth credentials in Google Cloud Console
2. Enable Google Drive API
3. Add authorized redirect URIs

```env
GOOGLE_CLIENT_ID=123456789.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxx
```

### Worker Configuration

Celery worker settings:

```env
# Use Redis as broker
CELERY_BROKER_URL=redis://localhost:6379/0

# Store results in Redis
CELERY_RESULT_BACKEND=redis://localhost:6379/1

# Number of concurrent workers
WORKER_CONCURRENCY=4

# Task time limit (seconds)
TASK_TIME_LIMIT=3600

# Soft time limit (warning before hard kill)
TASK_SOFT_TIME_LIMIT=3500
```

### Rate Limiting

```env
# Per-source rate limits
GITHUB_RATE_LIMIT_PER_HOUR=4000
GITLAB_RATE_LIMIT_PER_HOUR=3000
GDRIVE_RATE_LIMIT_PER_MINUTE=100

# Overall limits
WEBHOOK_RATE_LIMIT=1000/minute
API_RATE_LIMIT=100/minute
```

## Configuration Files

### alembic.ini

```ini
[alembic]
script_location = alembic
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =
```

### celeryconfig.py

```python
broker_url = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')
result_backend = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')

task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
enable_utc = True

task_routes = {
    'workers.tasks.sync_source_task': {'queue': 'sync'},
    'workers.tasks.process_file_batch': {'queue': 'process'},
}

task_annotations = {
    'workers.tasks.sync_source_task': {
        'rate_limit': '10/m',
        'time_limit': 3600,
    },
}
```

## Secrets Management

### Development

```bash
cp .env.example .env
# Edit .env with your values
```

### Production

Use environment variables from your orchestrator:

**Docker Compose:**
```yaml
services:
  data-connector:
    environment:
      - DATABASE_URL
      - REDIS_URL
      - GITHUB_PRIVATE_KEY
    secrets:
      - github_private_key
```

**Kubernetes:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: data-connector-secrets
type: Opaque
stringData:
  DATABASE_URL: postgresql://...
  GITHUB_WEBHOOK_SECRET: xxx
```

## Webhook Configuration

### GitHub Webhooks

When connecting a GitHub repository, data-connector automatically:
1. Creates a webhook on the repository
2. Subscribes to: push, pull_request, issues (if enabled)
3. Uses `GITHUB_WEBHOOK_SECRET` to sign payloads

Webhook URL format:
```
https://your-domain.com/webhooks/github
```

### GitLab Webhooks

GitLab webhooks are configured per project:
1. Auto-configured when source is added
2. Uses token authentication
3. Subscribes to: push, merge_request

### Google Drive Push Notifications

Google Drive uses push notifications:
1. Registered via Drive API `watch` method
2. Requires publicly accessible HTTPS endpoint
3. Expires after 1 week (auto-renewed)

## Logging Configuration

```env
LOG_LEVEL=info
LOG_FORMAT=json
LOG_FILE=/var/log/confuse/data-connector.log
```

Python logging config:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            'class': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'format': '%(asctime)s %(levelname)s %(name)s %(message)s'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console']
    }
}
```
