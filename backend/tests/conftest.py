import pytest
import os

# Set testing mode before importing main
os.environ["TESTING_MODE"] = "true"

from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
def test_patient_data():
    """Sample patient data for testing."""
    return {
        "name": "John Doe",
        "age": 45,
        "gender": "Male",
        "symptoms": "Persistent headache and dizziness"
    }
