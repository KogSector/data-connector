"""
ConHub Data Connector - Health Route Tests
"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test health check endpoint."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_status_endpoint(client: AsyncClient):
    """Test extended status endpoint."""
    response = await client.get("/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "data-connector"
    assert "version" in data
    assert "uptime_seconds" in data
    assert "config" in data
    assert "services" in data
