import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


def test_health_check(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "MedShield v2"
    assert data["version"] == "2.0.0"


def test_app_initialization():
    """Test FastAPI app initializes correctly."""
    assert app.title == "MedShield v2 - Privacy-Preserving Medical Chatbot"
    assert app.version == "2.0.0"
