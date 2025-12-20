use crate::domain::connectors::Connector;
use crate::domain::models::{ConnectorType, ContentType, DataSource, NormalizedDocument};
use crate::error::{AppError, AppResult};
use async_trait::async_trait;
use std::fs;
use std::path::Path;
use tracing::info;
use uuid::Uuid;
use walkdir::WalkDir;

/// Local file system connector.
pub struct LocalFileConnector;

impl LocalFileConnector {
    pub fn new() -> Self {
        Self
    }

    /// Determine content type from file extension.
    fn get_content_type(path: &Path) -> ContentType {
        let ext = path.extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();
        
        match ext.as_str() {
            "md" | "markdown" => ContentType::Markdown,
            "html" | "htm" => ContentType::Html,
            "json" => ContentType::Json,
            "xml" => ContentType::Xml,
            "yaml" | "yml" => ContentType::Yaml,
            "txt" => ContentType::Text,
            "rs" | "py" | "js" | "ts" | "go" | "java" | "c" | "cpp" | "h" | "hpp" 
            | "cs" | "rb" | "php" | "swift" | "kt" | "scala" | "sql" | "sh" | "bash"
            | "ps1" | "psm1" | "jsx" | "tsx" | "vue" | "svelte" => ContentType::Code,
            _ => ContentType::Unknown,
        }
    }

    /// Detect programming language from file extension.
    fn get_language(path: &Path) -> Option<String> {
        let ext = path.extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();
        
        let lang = match ext.as_str() {
            "rs" => "rust",
            "py" => "python",
            "js" => "javascript",
            "ts" => "typescript",
            "jsx" => "javascript",
            "tsx" => "typescript",
            "go" => "go",
            "java" => "java",
            "c" => "c",
            "cpp" | "cc" | "cxx" => "cpp",
            "h" | "hpp" => "c",
            "cs" => "csharp",
            "rb" => "ruby",
            "php" => "php",
            "swift" => "swift",
            "kt" => "kotlin",
            "scala" => "scala",
            "sql" => "sql",
            "sh" | "bash" => "shell",
            "ps1" | "psm1" => "powershell",
            "vue" => "vue",
            "svelte" => "svelte",
            "md" | "markdown" => "markdown",
            "json" => "json",
            "yaml" | "yml" => "yaml",
            "xml" => "xml",
            "html" | "htm" => "html",
            "css" => "css",
            "scss" | "sass" => "scss",
            _ => return None,
        };
        Some(lang.to_string())
    }

    /// Check if file should be skipped (binary files, etc.)
    fn should_skip(path: &Path) -> bool {
        let ext = path.extension()
            .and_then(|e| e.to_str())
            .unwrap_or("")
            .to_lowercase();
        
        // Skip binary and media files
        matches!(ext.as_str(), 
            "png" | "jpg" | "jpeg" | "gif" | "ico" | "svg" | "webp" | "bmp" |
            "woff" | "woff2" | "ttf" | "eot" | "otf" |
            "pdf" | "doc" | "docx" | "xls" | "xlsx" | "ppt" | "pptx" |
            "zip" | "tar" | "gz" | "rar" | "7z" |
            "exe" | "dll" | "so" | "dylib" | "bin" |
            "mp3" | "mp4" | "wav" | "avi" | "mov" | "mkv" |
            "db" | "sqlite" | "lock"
        )
    }
}

impl Default for LocalFileConnector {
    fn default() -> Self {
        Self::new()
    }
}

#[async_trait]
impl Connector for LocalFileConnector {
    fn connector_type(&self) -> ConnectorType {
        ConnectorType::LocalFile
    }

    async fn validate_access(&self, source: &DataSource, _user_id: Uuid) -> AppResult<bool> {
        let path = source.config.get("path")
            .and_then(|v| v.as_str())
            .ok_or_else(|| AppError::BadRequest("Missing path in config".to_string()))?;
        
        let path = Path::new(path);
        Ok(path.exists() && path.is_dir())
    }

    async fn fetch_content(&self, source: &DataSource, _user_id: Uuid) -> AppResult<Vec<NormalizedDocument>> {
        let base_path = source.config.get("path")
            .and_then(|v| v.as_str())
            .ok_or_else(|| AppError::BadRequest("Missing path in config".to_string()))?;
        
        let base_path = Path::new(base_path);
        if !base_path.exists() {
            return Err(AppError::NotFound(format!("Path does not exist: {}", base_path.display())));
        }

        info!("Scanning local directory: {}", base_path.display());
        
        let mut documents = Vec::new();
        
        for entry in WalkDir::new(base_path)
            .follow_links(true)
            .into_iter()
            .filter_map(|e| e.ok())
        {
            let path = entry.path();
            
            // Skip directories
            if path.is_dir() {
                continue;
            }
            
            // Skip hidden files and directories
            if path.components().any(|c| {
                c.as_os_str().to_str().map(|s| s.starts_with('.')).unwrap_or(false)
            }) {
                continue;
            }
            
            // Skip binary files
            if Self::should_skip(path) {
                continue;
            }
            
            // Read file content
            match fs::read_to_string(path) {
                Ok(content) => {
                    let relative_path = path.strip_prefix(base_path)
                        .map(|p| p.to_string_lossy().to_string())
                        .unwrap_or_else(|_| path.to_string_lossy().to_string());
                    
                    let file_name = path.file_name()
                        .and_then(|n| n.to_str())
                        .unwrap_or("unknown")
                        .to_string();
                    
                    let metadata = entry.metadata().ok();
                    let file_size = metadata.as_ref().map(|m| m.len());
                    
                    let mut doc = NormalizedDocument::new(
                        source.id,
                        ConnectorType::LocalFile,
                        path.to_string_lossy().to_string(),
                        file_name,
                        content,
                    );
                    doc.path = Some(relative_path.clone());
                    doc.content_type = Self::get_content_type(path);
                    doc.language = Self::get_language(path);
                    doc.metadata = serde_json::json!({
                        "base_path": base_path.to_string_lossy(),
                        "relative_path": relative_path,
                        "file_size": file_size,
                    });
                    
                    documents.push(doc);
                }
                Err(e) => {
                    // Log but continue with other files (may be binary that failed UTF-8 decode)
                    tracing::debug!("Skipping file {} (not valid UTF-8 or read error): {}", path.display(), e);
                }
            }
        }
        
        info!("Fetched {} documents from local directory {}", documents.len(), base_path.display());
        Ok(documents)
    }
}
