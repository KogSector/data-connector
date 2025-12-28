"""
ConHub Data Connector - Custom Exceptions

Application-specific exceptions ported from Rust error.rs.
"""

from typing import Any, Optional


class AppError(Exception):
    """Base application error."""
    
    def __init__(
        self,
        message: str,
        code: int = 500,
        details: Optional[dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


class BadRequestError(AppError):
    """400 Bad Request - Invalid input from client."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code=400, details=details)


class UnauthorizedError(AppError):
    """401 Unauthorized - Authentication required or failed."""
    
    def __init__(self, message: str = "Unauthorized", details: Optional[dict[str, Any]] = None):
        super().__init__(message, code=401, details=details)


class ForbiddenError(AppError):
    """403 Forbidden - Access denied to resource."""
    
    def __init__(self, message: str = "Forbidden", details: Optional[dict[str, Any]] = None):
        super().__init__(message, code=403, details=details)


class NotFoundError(AppError):
    """404 Not Found - Resource does not exist."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code=404, details=details)


class ConflictError(AppError):
    """409 Conflict - Resource already exists or state conflict."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code=409, details=details)


class ValidationError(AppError):
    """422 Validation Error - Input validation failed."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code=422, details=details)


class ExternalServiceError(AppError):
    """502 Bad Gateway - External service (chunker, embeddings, etc.) failed."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code=502, details=details)


class ServiceUnavailableError(AppError):
    """503 Service Unavailable - Service temporarily unavailable."""
    
    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message, code=503, details=details)


class RateLimitError(AppError):
    """429 Too Many Requests - Rate limit exceeded."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
        details: Optional[dict[str, Any]] = None
    ):
        details = details or {}
        if retry_after:
            details["retry_after"] = retry_after
        super().__init__(message, code=429, details=details)


class ConnectorError(AppError):
    """Error from a specific connector."""
    
    def __init__(
        self,
        connector_type: str,
        message: str,
        code: int = 500,
        details: Optional[dict[str, Any]] = None
    ):
        details = details or {}
        details["connector_type"] = connector_type
        super().__init__(message, code=code, details=details)
