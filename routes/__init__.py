"""
ConHub Data Connector - Routes Package

Exports all API routers for registration in the main app.
"""

from routes.connectors import router as connectors_router
from routes.health import router as health_router
from routes.legacy import router as legacy_router
from routes.oauth import router as oauth_router
from routes.sync import router as sync_router
from routes.webhooks import router as webhooks_router

__all__ = [
    "connectors_router",
    "health_router",
    "legacy_router",
    "oauth_router",
    "sync_router",
    "webhooks_router",
]
