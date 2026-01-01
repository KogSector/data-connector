# Data Connector Architecture

> Internal architecture and data flow documentation

## System Architecture

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                              DATA-CONNECTOR                                    │
├───────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌───────────────────────────────────────────────────────────────────────┐    │
│  │                          API Layer (FastAPI)                           │    │
│  ├───────────────────────────────────────────────────────────────────────┤    │
│  │                                                                        │    │
│  │   /sources/*         /webhooks/*        /oauth/*         /jobs/*      │    │
│  │        │                  │                 │                │        │    │
│  │        ▼                  ▼                 ▼                ▼        │    │
│  │   SourceRouter      WebhookRouter      OAuthRouter      JobRouter     │    │
│  │                                                                        │    │
│  └───────────────────────────────────────────────────────────────────────┘    │
│                                      │                                         │
│                                      ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐    │
│  │                         Service Layer                                  │    │
│  ├───────────────────────────────────────────────────────────────────────┤    │
│  │                                                                        │    │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │    │
│  │  │ SourceSvc   │  │  SyncSvc    │  │ WebhookSvc  │  │  TokenSvc   │   │    │
│  │  │             │  │             │  │             │  │             │   │    │
│  │  │• Create     │  │• Full sync  │  │• Validate   │  │• Store      │   │    │
│  │  │• List       │  │• Incremental│  │• Parse      │  │• Refresh    │   │    │
│  │  │• Delete     │  │• Status     │  │• Dispatch   │  │• Encrypt    │   │    │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │    │
│  │                                                                        │    │
│  └───────────────────────────────────────────────────────────────────────┘    │
│                                      │                                         │
│                                      ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐    │
│  │                        Connector Layer                                 │    │
│  ├───────────────────────────────────────────────────────────────────────┤    │
│  │                                                                        │    │
│  │   ┌─────────────────────────────────────────────────────────────────┐ │    │
│  │   │                    BaseConnector (Abstract)                      │ │    │
│  │   │                                                                  │ │    │
│  │   │   • list_files()                                                │ │    │
│  │   │   • get_file_content()                                          │ │    │
│  │   │   • setup_webhook()                                             │ │    │
│  │   │   • validate_webhook()                                          │ │    │
│  │   └─────────────────────────────────────────────────────────────────┘ │    │
│  │        ▲            ▲            ▲            ▲            ▲          │    │
│  │        │            │            │            │            │          │    │
│  │   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐     │    │
│  │   │ GitHub │   │ GitLab │   │Bitbuckt│   │G Drive │   │Dropbox │     │    │
│  │   │Connectr│   │Connectr│   │Connectr│   │Connectr│   │Connectr│     │    │
│  │   └────────┘   └────────┘   └────────┘   └────────┘   └────────┘     │    │
│  │                                                                        │    │
│  └───────────────────────────────────────────────────────────────────────┘    │
│                                      │                                         │
│                                      ▼                                         │
│  ┌───────────────────────────────────────────────────────────────────────┐    │
│  │                        Worker Layer (Celery)                           │    │
│  ├───────────────────────────────────────────────────────────────────────┤    │
│  │                                                                        │    │
│  │   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                   │    │
│  │   │  sync_repo  │  │process_file │  │ send_to_    │                   │    │
│  │   │   _task     │  │   _task     │  │ pipeline    │                   │    │
│  │   └─────────────┘  └─────────────┘  └─────────────┘                   │    │
│  │                                                                        │    │
│  └───────────────────────────────────────────────────────────────────────┘    │
│                                                                                │
└─────────────────────────────────────┬─────────────────────────────────────────┘
                                      │
                 ┌────────────────────┼────────────────────┐
                 ▼                    ▼                    ▼
         ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
         │  PostgreSQL   │   │     Redis     │   │  External     │
         │               │   │               │   │  Services     │
         │ • sources     │   │ • job queue   │   │               │
         │ • files       │   │ • cache       │   │ • GitHub API  │
         │ • sync_jobs   │   │ • rate limits │   │ • GitLab API  │
         │ • tokens      │   │               │   │ • Drive API   │
         └───────────────┘   └───────────────┘   └───────────────┘
```

## Data Flows

### 1. Source Connection Flow

```
User: "Connect my GitHub repo"

┌──────────┐     ┌──────────────────┐     ┌────────────────┐
│ Frontend │     │  Data-Connector  │     │    GitHub      │
└────┬─────┘     └────────┬─────────┘     └───────┬────────┘
     │                    │                       │
     │ POST /sources      │                       │
     │ {type: github,     │                       │
     │  repo: "owner/rpo"}│                       │
     │───────────────────>│                       │
     │                    │                       │
     │                    │ GET /repos/:repo      │
     │                    │ (validate access)     │
     │                    │──────────────────────>│
     │                    │                       │
     │                    │ 200 OK                │
     │                    │<──────────────────────│
     │                    │                       │
     │                    │ POST /repos/:repo/    │
     │                    │ hooks (setup webhook) │
     │                    │──────────────────────>│
     │                    │                       │
     │                    │ 201 Created           │
     │                    │<──────────────────────│
     │                    │                       │
     │                    │ Store source in DB    │
     │                    │ Queue initial sync    │
     │                    │                       │
     │ {source: {...},    │                       │
     │  jobId: "..."}     │                       │
     │<───────────────────│                       │
```

### 2. Webhook Processing Flow

```
GitHub: Push event (files changed)

┌──────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────┐
│  GitHub  │     │ Data-Connector  │     │ Code-Normalize  │     │   Chunker   │
└────┬─────┘     └───────┬─────────┘     └───────┬─────────┘     └──────┬──────┘
     │                   │                       │                      │
     │ POST /webhooks/   │                       │                      │
     │ github            │                       │                      │
     │ {event: push,     │                       │                      │
     │  commits: [...]}  │                       │                      │
     │──────────────────>│                       │                      │
     │                   │                       │                      │
     │                   │ Verify signature      │                      │
     │                   │ Parse changed files   │                      │
     │                   │                       │                      │
     │ 200 OK            │                       │                      │
     │<──────────────────│                       │                      │
     │                   │                       │                      │
     │                   │ Queue sync job        │                      │
     │                   │                       │                      │
     │                   │ ═══════════════════════════════════════════════
     │                   │        (Async worker process)
     │                   │ ═══════════════════════════════════════════════
     │                   │                       │                      │
     │                   │ POST /process         │                      │
     │                   │ {files: [...]}        │                      │
     │                   │──────────────────────>│                      │
     │                   │                       │                      │
     │                   │ {normalized_files}    │                      │
     │                   │<──────────────────────│                      │
     │                   │                       │                      │
     │                   │ POST /chunk           │                      │
     │                   │ {content: [...]}      │                      │
     │                   │─────────────────────────────────────────────>│
     │                   │                       │                      │
     │                   │                       │     {chunks: [...]}  │
     │                   │<─────────────────────────────────────────────│
     │                   │                       │                      │
     │                   │ Send to embeddings... │                      │
```

### 3. Full Sync Flow

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              FULL SYNC PROCESS                                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│   1. Fetch Repository Tree                                                    │
│      ├── GET /repos/:repo/git/trees?recursive=1                              │
│      └── Returns all files with SHA hashes                                   │
│                                                                               │
│   2. Filter Files                                                            │
│      ├── Skip binary files                                                   │
│      ├── Skip large files (>1MB)                                             │
│      ├── Skip excluded paths (node_modules, .git, etc.)                      │
│      └── Apply language filter if configured                                 │
│                                                                               │
│   3. Batch Processing (concurrency: 10)                                      │
│      ├── For each file batch:                                                │
│      │   ├── Fetch file content                                              │
│      │   ├── Send to code-normalize-fetch                                    │
│      │   ├── Receive entities                                                │
│      │   ├── Send to chunker                                                 │
│      │   ├── Receive chunks                                                  │
│      │   ├── Send to embeddings                                              │
│      │   └── Send to relation-graph                                          │
│      └── Update progress                                                     │
│                                                                               │
│   4. Cleanup                                                                  │
│      ├── Remove orphaned files (deleted in repo)                             │
│      └── Update source sync timestamp                                        │
│                                                                               │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Connector Architecture

### Base Connector Interface

```python
from abc import ABC, abstractmethod
from typing import List, Optional

class BaseConnector(ABC):
    """Abstract base class for all data source connectors."""
    
    @abstractmethod
    async def validate_connection(self) -> bool:
        """Verify the connection with provided credentials."""
        pass
    
    @abstractmethod
    async def list_files(
        self, 
        path: Optional[str] = None,
        recursive: bool = True
    ) -> List[FileInfo]:
        """List all files in the source."""
        pass
    
    @abstractmethod
    async def get_file_content(self, path: str) -> bytes:
        """Get the content of a specific file."""
        pass
    
    @abstractmethod
    async def get_file_metadata(self, path: str) -> FileMetadata:
        """Get metadata for a file."""
        pass
    
    @abstractmethod
    async def setup_webhook(self, callback_url: str) -> str:
        """Setup a webhook and return the webhook ID."""
        pass
    
    @abstractmethod
    async def validate_webhook(self, request: WebhookRequest) -> bool:
        """Validate an incoming webhook request."""
        pass
    
    @abstractmethod
    async def parse_webhook(self, request: WebhookRequest) -> List[FileChange]:
        """Parse a webhook into file changes."""
        pass
```

### Connector Registration

```python
# connectors/__init__.py
from .github import GitHubConnector
from .gitlab import GitLabConnector
from .gdrive import GoogleDriveConnector
from .dropbox import DropboxConnector
from .local import LocalFSConnector

CONNECTORS = {
    "github": GitHubConnector,
    "gitlab": GitLabConnector,
    "bitbucket": BitbucketConnector,
    "gdrive": GoogleDriveConnector,
    "dropbox": DropboxConnector,
    "local": LocalFSConnector,
}

def get_connector(source_type: str, config: dict) -> BaseConnector:
    connector_class = CONNECTORS.get(source_type)
    if not connector_class:
        raise ValueError(f"Unknown source type: {source_type}")
    return connector_class(**config)
```

## Database Schema

```sql
-- Sources: Connected data sources
CREATE TABLE sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id),
    type VARCHAR(50) NOT NULL,  -- github, gitlab, gdrive, etc.
    name VARCHAR(255) NOT NULL,  -- e.g., "owner/repo"
    config JSONB NOT NULL DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'pending',  -- pending, syncing, synced, error
    last_sync_at TIMESTAMP,
    webhook_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Files: Indexed files from sources
CREATE TABLE files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    path VARCHAR(1024) NOT NULL,
    sha VARCHAR(64),  -- Content hash for deduplication
    size INTEGER,
    language VARCHAR(50),
    last_modified TIMESTAMP,
    indexed_at TIMESTAMP,
    UNIQUE(source_id, path)
);

-- Sync Jobs: Track sync operations
CREATE TABLE sync_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID NOT NULL REFERENCES sources(id),
    type VARCHAR(50) NOT NULL,  -- full, incremental
    status VARCHAR(50) DEFAULT 'queued',  -- queued, running, completed, failed
    progress INTEGER DEFAULT 0,  -- Percentage
    files_total INTEGER DEFAULT 0,
    files_processed INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Webhook Events: Log of received webhooks
CREATE TABLE webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id),
    source_type VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    processed BOOLEAN DEFAULT FALSE,
    processed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);
```

## Job Queue

Using Celery with Redis:

```python
# workers/tasks.py
from celery import Celery

app = Celery('data_connector')
app.config_from_object('workers.celery_config')

@app.task(bind=True, max_retries=3)
def sync_source_task(self, source_id: str, sync_type: str = "full"):
    """Main sync task for a source."""
    try:
        connector = get_connector_for_source(source_id)
        
        if sync_type == "full":
            files = connector.list_files(recursive=True)
        else:
            files = get_changed_files(source_id)
        
        for batch in chunk_list(files, size=10):
            process_file_batch.delay(source_id, batch)
            
    except Exception as e:
        self.retry(exc=e, countdown=2 ** self.request.retries)

@app.task
def process_file_batch(source_id: str, files: list):
    """Process a batch of files through the pipeline."""
    connector = get_connector_for_source(source_id)
    
    for file in files:
        content = connector.get_file_content(file.path)
        
        # Send to code-normalize-fetch
        normalized = code_normalize_fetch.process(content, file.language)
        
        # Send to chunker
        chunks = chunker.chunk(normalized)
        
        # Send to embeddings
        embeddings = embeddings_service.embed(chunks)
        
        # Send to relation-graph
        relation_graph.store(chunks, embeddings)
```
