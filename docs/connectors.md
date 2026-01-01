# Data Connector - Supported Connectors

> Complete guide to all supported data source connectors

## Overview

Data Connector supports multiple data sources through a unified connector interface. Each connector handles authentication, file listing, content fetching, and webhook processing.

## Connector Status

| Connector | Status | Auth Method | Webhooks |
|-----------|--------|-------------|----------|
| GitHub | ✅ Ready | OAuth App / PAT | ✅ |
| GitLab | ✅ Ready | OAuth / PAT | ✅ |
| Bitbucket | ✅ Ready | OAuth / App Password | ✅ |
| Google Drive | ✅ Ready | OAuth | ✅ Push |
| Dropbox | 🚧 Beta | OAuth | ✅ |
| OneDrive | 📋 Planned | OAuth | Planned |
| Notion | 📋 Planned | OAuth | Planned |
| Confluence | 📋 Planned | OAuth | Planned |
| Local FS | ✅ Ready | None | File watcher |

---

## GitHub Connector

### Features
- Repository content indexing
- Branch-specific sync
- Pull request tracking
- Issue and discussion indexing
- Wiki page indexing
- Webhook for push events

### Configuration

```json
{
  "type": "github",
  "config": {
    "owner": "organization-name",
    "repo": "repository-name",
    "branch": "main",
    "includePaths": ["src/**", "docs/**"],
    "excludePaths": ["node_modules/**", "*.lock", "dist/**"],
    "includeLanguages": ["python", "typescript", "rust"],
    "indexPRs": true,
    "indexIssues": false,
    "indexWiki": false
  }
}
```

### Supported Events
- `push` - Code changes
- `pull_request` - PR opened/updated/merged
- `issues` - Issue created/updated (if enabled)
- `create` - Branch/tag created
- `delete` - Branch/tag deleted

### Rate Limits
- GitHub API: 5000 requests/hour (authenticated)
- Handled with automatic retry and backoff

---

## GitLab Connector

### Features
- Project content indexing
- Branch-specific sync
- Merge request tracking
- CI/CD pipeline awareness
- Wiki and snippet indexing

### Configuration

```json
{
  "type": "gitlab",
  "config": {
    "projectId": "12345",
    "branch": "main",
    "includePaths": ["src/**"],
    "excludePaths": ["vendor/**"],
    "indexMRs": true,
    "gitlabUrl": "https://gitlab.com"
  }
}
```

### Self-Hosted GitLab

For self-hosted GitLab instances:

```json
{
  "type": "gitlab",
  "config": {
    "gitlabUrl": "https://gitlab.company.com",
    "projectId": "group/project"
  }
}
```

---

## Bitbucket Connector

### Features
- Repository cloning and indexing
- Branch tracking
- Pull request sync
- Bitbucket Cloud and Server support

### Configuration

```json
{
  "type": "bitbucket",
  "config": {
    "workspace": "workspace-name",
    "repo": "repository-name",
    "branch": "main"
  }
}
```

---

## Google Drive Connector

### Features
- Google Docs parsing (extracts text)
- Google Sheets (first sheet as text)
- Google Slides (slide text)
- PDF extraction
- Plain text files
- Folder structure preservation

### Configuration

```json
{
  "type": "gdrive",
  "config": {
    "folderId": "1abc...",
    "includeShared": true,
    "recursive": true,
    "fileTypes": ["document", "spreadsheet", "pdf", "text"],
    "excludeFolders": ["Archive", "Drafts"]
  }
}
```

### Supported File Types
- Google Docs → Extracted as Markdown
- Google Sheets → First sheet as CSV/text
- Google Slides → Slide text extracted
- PDF → Text extraction (OCR for images soon)
- Plain text (.txt, .md, .json)

### Push Notifications
Google Drive uses push notifications instead of webhooks:
- Registered via Google Drive API
- Receives change notifications
- Polls for full changes (API limitation)

---

## Dropbox Connector

### Features
- File and folder indexing
- Team folders support
- Shared folder access
- Real-time sync via longpoll

### Configuration

```json
{
  "type": "dropbox",
  "config": {
    "path": "/Projects",
    "recursive": true,
    "includeShared": true,
    "fileTypes": ["code", "document"]
  }
}
```

---

## Local Filesystem Connector

### Features
- Local directory indexing
- File watcher for changes
- No external dependencies
- Ideal for development

### Configuration

```json
{
  "type": "local",
  "config": {
    "rootPath": "/home/user/projects/myproject",
    "watch": true,
    "includePaths": ["src/**", "docs/**"],
    "excludePaths": ["node_modules/**", ".git/**", "target/**"]
  }
}
```

### Security Note
Local filesystem access is restricted to:
- Paths configured in `FS_ALLOWED_PATHS`
- User's home directory (if configured)
- No access to system directories

---

## Common Configuration Options

All connectors support these options:

```json
{
  "includePaths": ["pattern1/**", "pattern2/**"],
  "excludePaths": ["excluded/**"],
  "maxFileSize": 1048576,
  "includeLanguages": ["python", "rust"],
  "excludeLanguages": ["generated"],
  "syncSchedule": "*/15 * * * *"
}
```

| Option | Type | Description |
|--------|------|-------------|
| `includePaths` | string[] | Glob patterns to include |
| `excludePaths` | string[] | Glob patterns to exclude |
| `maxFileSize` | number | Max file size in bytes (default: 1MB) |
| `includeLanguages` | string[] | Only index these languages |
| `excludeLanguages` | string[] | Skip these languages |
| `syncSchedule` | string | Cron expression for periodic sync |

---

## Adding a New Connector

To implement a new connector:

1. Create connector class:

```python
# connectors/notion.py
from .base import BaseConnector

class NotionConnector(BaseConnector):
    async def validate_connection(self) -> bool:
        # Verify API key works
        pass
    
    async def list_files(self, path=None, recursive=True):
        # List all pages/databases
        pass
    
    async def get_file_content(self, path: str) -> bytes:
        # Get page content as markdown
        pass
    
    async def setup_webhook(self, callback_url: str) -> str:
        # Not supported by Notion API
        raise NotImplementedError
```

2. Register in `connectors/__init__.py`:

```python
from .notion import NotionConnector

CONNECTORS["notion"] = NotionConnector
```

3. Add OAuth flow if needed in `routes/oauth.py`

4. Add configuration schema in `schemas/sources.py`

---

## File Filtering

Default exclusion patterns (applied to all connectors):

```python
DEFAULT_EXCLUDE_PATTERNS = [
    # Directories
    "node_modules/**",
    "vendor/**",
    ".git/**",
    "__pycache__/**",
    ".venv/**",
    "target/**",
    "dist/**",
    "build/**",
    
    # Files
    "*.min.js",
    "*.min.css",
    "*.bundle.js",
    "*.map",
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "Cargo.lock",
    
    # Binary
    "*.png", "*.jpg", "*.gif", "*.ico",
    "*.pdf", "*.zip", "*.tar.gz",
    "*.exe", "*.dll", "*.so",
]
```
