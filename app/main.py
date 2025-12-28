"""
ConHub Data Connector - FastAPI Application

Main application factory and route configuration.
Ported from Rust main.rs.
"""

import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.exceptions import AppError
from db import close_db, init_db

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

# Track application start time (like Rust's started_at: Instant)
APP_START_TIME: float = 0.0


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager for startup/shutdown events."""
    global APP_START_TIME
    APP_START_TIME = time.time()
    
    logger.info(
        "Starting data-connector service",
        port=settings.port,
        auth_service_url=settings.auth_service_url,
        chunker_service_url=settings.chunker_service_url,
    )
    
    # Initialize database (create tables if needed in dev mode)
    if settings.debug:
        await init_db()
    
    yield
    
    # Cleanup on shutdown
    logger.info("Shutting down data-connector service")
    await close_db()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    
    app = FastAPI(
        title="ConHub Data Connector API",
        description="Data connector service for syncing content from various sources",
        version="1.0.0",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan,
    )
    
    # Configure CORS (matching Rust Cors::default() config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Accept", "Content-Type", "X-Correlation-Id"],
        max_age=3600,
    )
    
    # Exception handlers
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Handle application-specific errors."""
        return JSONResponse(
            status_code=exc.code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )
    
    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected errors."""
        logger.exception("Unhandled exception", error=str(exc))
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "message": "Internal server error",
                "details": {"error": str(exc)} if settings.debug else {},
            },
        )
    
    # Register routes
    from routes import (
        connectors_router,
        health_router,
        legacy_router,
        oauth_router,
        sync_router,
        webhooks_router,
    )
    
    # Health endpoints (no prefix)
    app.include_router(health_router, tags=["health"])
    
    # New API routes (matching OpenAPI spec)
    app.include_router(connectors_router, prefix="/connectors", tags=["connectors"])
    app.include_router(oauth_router, prefix="/connectors", tags=["oauth"])
    app.include_router(sync_router, prefix="/connectors", tags=["sync"])
    app.include_router(webhooks_router, tags=["webhooks"])
    
    # Legacy routes for backward compatibility with Rust API
    app.include_router(legacy_router, prefix="/api", tags=["legacy"])
    
    return app


# Create application instance
app = create_app()


def run() -> None:
    """Run the application with uvicorn."""
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    run()
