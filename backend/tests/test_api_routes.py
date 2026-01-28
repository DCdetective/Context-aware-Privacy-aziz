import pytest
from fastapi.testclient import TestClient
from main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "healthy"
    assert "components" in data
    assert data["components"]["identity_vault"] == "operational"


def test_schedule_appointment(client):
    """Test appointment scheduling endpoint."""
    request_data = {
        "patient_name": "John Doe",
        "age": 45,
        "gender": "Male",
        "symptoms": "Persistent headache and dizziness"
    }
    
    response = client.post("/api/appointments/schedule", json=request_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert "patient_uuid" in data
    assert "appointment_time" in data
    assert data["patient_name"] == "John Doe"


def test_schedule_followup(client):
    """Test follow-up scheduling endpoint."""
    # First create a patient with an appointment
    appointment_data = {
        "patient_name": "Jane Smith",
        "age": 32,
        "gender": "Female",
        "symptoms": "Follow-up test patient"
    }
    client.post("/api/appointments/schedule", json=appointment_data)
    
    # Now schedule follow-up
    followup_data = {
        "patient_name": "Jane Smith"
    }
    
    response = client.post("/api/followups/schedule", json=followup_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert "followup_time" in data


def test_generate_summary(client):
    """Test summary generation endpoint."""
    # First create a patient
    appointment_data = {
        "patient_name": "Bob Williams",
        "age": 50,
        "gender": "Male",
        "symptoms": "Test for summary generation"
    }
    client.post("/api/appointments/schedule", json=appointment_data)
    
    # Generate summary
    summary_data = {
        "patient_name": "Bob Williams"
    }
    
    response = client.post("/api/summaries/generate", json=summary_data)
    assert response.status_code == 200
    
    data = response.json()
    assert data["success"] is True
    assert "summary" in data


def test_appointment_invalid_data(client):
    """Test appointment with invalid data."""
    request_data = {
        "patient_name": "Test Patient",
        "age": 200,  # Invalid age
        "gender": "Male",
        "symptoms": "Test"
    }
    
    response = client.post("/api/appointments/schedule", json=request_data)
    assert response.status_code == 422  # Validation error
