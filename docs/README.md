# Data Connector Documentation

## Overview

The data-connector service is ConFuse's data ingestion layer. It connects to external data sources (GitHub, GitLab, Google Drive, etc.), handles webhooks, and triggers the knowledge processing pipeline.

## Role in ConFuse

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL DATA SOURCES                         │
│  GitHub  │  GitLab  │  Bitbucket  │  G Drive  │  Dropbox  │  Local  │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │ OAuth tokens / API access
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     DATA-CONNECTOR (This Service)                    │
│                            Port: 8000                                │
│                                                                      │
│   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐              │
│   │ Connectors  │   │  Webhooks   │   │   Workers   │              │
│   │             │   │             │   │             │              │
│   │ • GitHub    │   │ • Push      │   │ • Sync      │              │
│   │ • GitLab    │   │ • PR/MR     │   │ • Process   │              │
│   │ • G Drive   │   │ • File chg  │   │ • Queue     │              │
│   │ • Dropbox   │   │             │   │             │              │
│   │ • Local FS  │   │             │   │             │              │
│   └─────────────┘   └─────────────┘   └─────────────┘              │
└───────────────────────────────────┬─────────────────────────────────┘
                                    │ Normalized content
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      KNOWLEDGE PIPELINE                              │
│  code-normalize-fetch → chunker → embeddings → relation-graph       │
└─────────────────────────────────────────────────────────────────────┘
```

## Supported Sources

| Source | Status | Features |
|--------|--------|----------|
| GitHub | ✅ Ready | Repos, PRs, Issues, Wikis |
| GitLab | ✅ Ready | Projects, MRs, Issues |
| Bitbucket | ✅ Ready | Repos, PRs |
| Google Drive | ✅ Ready | Docs, Sheets, PDFs |
| Dropbox | 🚧 WIP | Files, folders |
| OneDrive | 📋 Planned | Files, folders |
| Notion | 📋 Planned | Pages, databases |
| Confluence | 📋 Planned | Spaces, pages |
| Local FS | ✅ Ready | Local directories |
| Slack | 📋 Planned | Channels, threads |
| Jira | 📋 Planned | Issues, projects |

## API Endpoints

### Sources

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/sources` | GET | List connected sources |
| `/sources` | POST | Connect new source |
| `/sources/:id` | GET | Get source details |
| `/sources/:id` | DELETE | Disconnect source |
| `/sources/:id/sync` | POST | Trigger manual sync |
| `/sources/:id/status` | GET | Get sync status |

### Webhooks

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/webhooks/github` | POST | GitHub webhook receiver |
| `/webhooks/gitlab` | POST | GitLab webhook receiver |
| `/webhooks/bitbucket` | POST | Bitbucket webhook receiver |
| `/webhooks/gdrive` | POST | Google Drive push notifications |

### Admin

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/admin/jobs` | GET | List processing jobs |
| `/admin/jobs/:id` | GET | Get job status |
| `/admin/stats` | GET | Service statistics |

## Connection Flow

### 1. GitHub Repository Connection

```
User                    Frontend                Data-Connector           GitHub
 │                         │                         │                      │
 │ Click "Connect GitHub"  │                         │                      │
 │────────────────────────>│                         │                      │
 │                         │ GET /sources/github/auth│                      │
 │                         │────────────────────────>│                      │
 │                         │                         │ OAuth redirect       │
 │ <────────────────────────────────────────────────────────────────────────>
 │                         │                         │                      │
 │ Select repos            │                         │                      │
 │────────────────────────>│                         │                      │
 │                         │ POST /sources           │                      │
 │                         │ {type: github, repos}   │                      │
 │                         │────────────────────────>│                      │
 │                         │                         │ Setup webhooks       │
 │                         │                         │─────────────────────>│
 │                         │                         │<─────────────────────│
 │                         │                         │                      │
 │                         │                         │ Initial sync job     │
 │                         │                         │────────>             │
 │                         │                         │                      │
 │ Source connected!       │                         │                      │
 │<────────────────────────│                         │                      │
```

### 2. Webhook Processing

```
GitHub                  Data-Connector           Code-Normalize-Fetch    Pipeline
  │                          │                           │                  │
  │ POST /webhooks/github    │                           │                  │
  │ {push event}             │                           │                  │
  │─────────────────────────>│                           │                  │
  │                          │ Verify signature          │                  │
  │                          │ Parse changed files       │                  │
  │                          │                           │                  │
  │                          │ POST /process             │                  │
  │                          │ {files, tokens}           │                  │
  │                          │──────────────────────────>│                  │
  │                          │                           │ Fetch, parse     │
  │                          │                           │───────>          │
  │                          │                           │                  │
  │                          │                           │ Normalized files │
  │                          │<──────────────────────────│                  │
  │                          │                           │                  │
  │                          │ Send to chunker           │                  │
  │                          │─────────────────────────────────────────────>│
  │                          │                           │                  │
  │ 200 OK                   │                           │                  │
  │<─────────────────────────│                           │                  │
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PORT` | Server port | `8000` |
| `DATABASE_URL` | PostgreSQL connection | Required |
| `REDIS_URL` | Redis for job queue | Required |
| `CODE_NORMALIZE_FETCH_URL` | Code processing service | `http://localhost:8090` |
| `CHUNKER_URL` | Chunking service | `http://localhost:3002` |
| `GITHUB_APP_ID` | GitHub App ID | - |
| `GITHUB_PRIVATE_KEY` | GitHub App private key | - |
| `GOOGLE_CLIENT_ID` | Google OAuth client | - |
| `GOOGLE_CLIENT_SECRET` | Google OAuth secret | - |

### Source Configuration

```json
{
  "type": "github",
  "config": {
    "owner": "my-org",
    "repo": "my-repo",
    "branch": "main",
    "includePaths": ["src/**", "docs/**"],
    "excludePaths": ["node_modules/**", "*.lock"],
    "languages": ["python", "rust", "typescript"]
  }
}
```

## Job Queue

Data-connector uses a Redis-backed job queue for async processing:

```python
# Job types
JOB_TYPES = {
    "sync.full": "Full repository sync",
    "sync.incremental": "Incremental sync (changed files only)",
    "sync.file": "Single file processing",
    "webhook.push": "Process push webhook",
    "webhook.pr": "Process PR/MR webhook",
}

# Job status
JOB_STATUS = {
    "queued": "Waiting to be processed",
    "running": "Currently processing",
    "completed": "Successfully completed",
    "failed": "Failed with error",
}
```

## Data Flow

```
Source File → data-connector → code-normalize-fetch → chunker → embeddings → relation-graph
     │              │                   │                │           │            │
     │              │                   │                │           │            │
   Raw content   Filter/skip       Parse AST         Segment      Vectorize    Store
                 Check cache      Extract entities   Add context              Link
```

## File Filtering

Files are filtered at multiple stages:

1. **Size limit**: Files > 1MB skipped
2. **Binary detection**: Binary files skipped
3. **Path patterns**: Configurable include/exclude
4. **Language filter**: Only process specified languages
5. **Vendor directories**: node_modules, vendor, etc. excluded

## Retention Policy

See [RETENTION_POLICY.md](../RETENTION_POLICY.md) for data retention details.

## Related Services

| Service | Relationship |
|---------|--------------|
| code-normalize-fetch | Receives files for code processing |
| chunker | Receives normalized content for segmentation |
| auth-middleware | OAuth token management |
| api-backend | Source management API |
