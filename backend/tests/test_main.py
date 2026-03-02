"""
Tests for the main FastAPI application.
"""

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test that the root endpoint returns the correct message and version."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Geological Map Digitizer API"
    assert data["version"] == "0.1.0"


def test_health_check(client):
    """Test that the health check endpoint returns 'healthy' status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
