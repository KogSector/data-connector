# Data Connector API Reference

> Complete API documentation for the ConFuse Data-Connector

## Base URL

```
Development: http://localhost:8000
Production: https://data.confuse.io
```

## Authentication

All endpoints require authentication via:
- **Bearer Token**: `Authorization: Bearer <jwt_token>`
- **API Key**: `X-API-Key: <api_key>` (for webhooks only)

Internal service calls use:
- **Service Token**: `X-Service-Token: <internal_token>`

---

## Endpoints

### Sources

#### GET /sources

List all connected data sources for the current user.

**Headers:**
```
Authorization: Bearer <token>
```

**Response (200):**
```json
{
  "sources": [
    {
      "id": "uuid",
      "type": "github",
      "name": "confuse/api-backend",
      "status": "synced",
      "config": {
        "owner": "confuse",
        "repo": "api-backend",
        "branch": "main"
      },
      "stats": {
        "filesIndexed": 150,
        "chunksCreated": 1200,
        "lastSyncDuration": 45
      },
      "lastSyncAt": "2026-01-01T12:00:00Z",
      "createdAt": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 1
}
```

---

#### POST /sources

Connect a new data source.

**Headers:**
```
Authorization: Bearer <token>
```

**Request (GitHub):**
```json
{
  "type": "github",
  "config": {
    "owner": "confuse",
    "repo": "api-backend",
    "branch": "main",
    "includePaths": ["src/**", "docs/**"],
    "excludePaths": ["node_modules/**", "*.lock"]
  }
}
```

**Request (Google Drive):**
```json
{
  "type": "gdrive",
  "config": {
    "folderId": "1abc...",
    "includeShared": true,
    "fileTypes": ["document", "spreadsheet", "pdf"]
  }
}
```

**Response (201):**
```json
{
  "source": {
    "id": "uuid",
    "type": "github",
    "name": "confuse/api-backend",
    "status": "pending"
  },
  "syncJob": {
    "id": "job-uuid",
    "status": "queued"
  }
}
```

---

#### GET /sources/:id

Get details for a specific source.

**Response (200):**
```json
{
  "id": "uuid",
  "type": "github",
  "name": "confuse/api-backend",
  "status": "synced",
  "config": {
    "owner": "confuse",
    "repo": "api-backend",
    "branch": "main"
  },
  "stats": {
    "filesIndexed": 150,
    "totalSize": 2456789,
    "languages": {
      "typescript": 80,
      "python": 45,
      "markdown": 25
    }
  },
  "lastSyncAt": "2026-01-01T12:00:00Z"
}
```

---

#### DELETE /sources/:id

Disconnect and remove a source.

**Response (200):**
```json
{
  "message": "Source deleted",
  "filesRemoved": 150,
  "chunksRemoved": 1200
}
```

---

#### POST /sources/:id/sync

Trigger a manual sync for a source.

**Request (optional):**
```json
{
  "type": "full"  // or "incremental"
}
```

**Response (202):**
```json
{
  "job": {
    "id": "job-uuid",
    "status": "queued",
    "type": "full",
    "estimatedDuration": 120
  }
}
```

---

### Sync Jobs

#### GET /jobs/:id

Get status of a sync job.

**Response (200):**
```json
{
  "id": "job-uuid",
  "sourceId": "source-uuid",
  "type": "full",
  "status": "running",
  "progress": 45,
  "stats": {
    "filesTotal": 150,
    "filesProcessed": 67,
    "chunksCreated": 540,
    "errors": 0
  },
  "startedAt": "2026-01-01T12:00:00Z",
  "estimatedCompletion": "2026-01-01T12:02:00Z"
}
```

---

#### GET /jobs

List recent sync jobs.

**Query Parameters:**
- `sourceId` - Filter by source
- `status` - Filter by status (queued, running, completed, failed)
- `limit` - Number of results (default: 20)

**Response (200):**
```json
{
  "jobs": [
    {
      "id": "job-uuid",
      "sourceId": "source-uuid",
      "type": "incremental",
      "status": "completed",
      "progress": 100,
      "completedAt": "2026-01-01T12:02:00Z"
    }
  ],
  "total": 15
}
```

---

### Webhooks

#### POST /webhooks/github

Receive GitHub webhook events.

**Headers:**
```
X-GitHub-Event: push
X-Hub-Signature-256: sha256=...
X-GitHub-Delivery: uuid
```

**Request Body:** GitHub webhook payload

**Response (200):**
```json
{
  "received": true,
  "jobId": "job-uuid"
}
```

---

#### POST /webhooks/gitlab

Receive GitLab webhook events.

**Headers:**
```
X-Gitlab-Event: Push Hook
X-Gitlab-Token: secret-token
```

---

#### POST /webhooks/bitbucket

Receive Bitbucket webhook events.

---

#### POST /webhooks/gdrive

Receive Google Drive push notifications.

---

### OAuth

#### GET /oauth/:provider

Start OAuth flow for connecting a source.

**Providers:** `github`, `gitlab`, `google`, `dropbox`

**Query Parameters:**
- `redirect_uri` - Where to redirect after auth

**Response:** Redirect to provider's OAuth page

---

#### GET /oauth/:provider/callback

OAuth callback handler.

---

#### GET /oauth/tokens/:provider

Get stored OAuth token for a provider (internal use).

**Headers:**
```
X-Service-Token: <internal_token>
X-User-Id: <user_id>
```

**Response (200):**
```json
{
  "accessToken": "gho_xxx",
  "refreshToken": "ghr_xxx",
  "expiresAt": "2026-01-02T12:00:00Z",
  "scopes": ["repo", "read:user"]
}
```

---

### Files

#### GET /sources/:id/files

List indexed files for a source.

**Query Parameters:**
- `path` - Filter by path prefix
- `language` - Filter by language
- `limit` - Number of results

**Response (200):**
```json
{
  "files": [
    {
      "id": "file-uuid",
      "path": "src/auth/handler.ts",
      "language": "typescript",
      "size": 2456,
      "lastModified": "2026-01-01T10:00:00Z",
      "indexedAt": "2026-01-01T12:00:00Z"
    }
  ],
  "total": 150
}
```

---

### Health

#### GET /health

Service health check.

**Response (200):**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database": "connected",
  "redis": "connected",
  "services": {
    "code-normalize-fetch": "healthy",
    "chunker": "healthy",
    "embeddings": "healthy"
  }
}
```

---

## Error Responses

```json
{
  "error": {
    "code": "SOURCE_NOT_FOUND",
    "message": "Source with ID xxx not found",
    "details": {}
  }
}
```

### Error Codes

| Code | HTTP | Description |
|------|------|-------------|
| `VALIDATION_ERROR` | 400 | Invalid request |
| `UNAUTHORIZED` | 401 | No/invalid auth |
| `FORBIDDEN` | 403 | No access to source |
| `SOURCE_NOT_FOUND` | 404 | Source not found |
| `JOB_NOT_FOUND` | 404 | Job not found |
| `PROVIDER_ERROR` | 502 | External API error |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Server error |

---

## Webhook Signatures

### GitHub

```python
import hmac
import hashlib

def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    expected = 'sha256=' + hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### GitLab

GitLab uses a simple secret token comparison via `X-Gitlab-Token` header.

---

## Rate Limits

| Endpoint | Limit | Window |
|----------|-------|--------|
| POST /sources | 10 | 1 hour |
| POST /sources/:id/sync | 5 | 15 min |
| Webhooks | 1000 | 1 min |
| Others | 100 | 1 min |
