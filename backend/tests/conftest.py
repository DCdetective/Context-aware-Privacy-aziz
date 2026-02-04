import pytest
import os
import tempfile
from fastapi.testclient import TestClient

# Set testing mode before imports
os.environ['TESTING_MODE'] = 'true'

from main import app
from database.identity_vault import IdentityVault
from vector_store.mock_stores import MockMetadataStore, MockSyntheticStore


@pytest.fixture
def client():
    """Create a test client for the FastAPI application."""
    return TestClient(app)


@pytest.fixture
def test_vault():
    """Create a temporary test identity vault."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        db_path = tmp.name
    
    vault = IdentityVault(db_path=db_path)
    yield vault
    
    # Cleanup - try to close engine if it exists
    try:
        if hasattr(vault, 'engine'):
            vault.engine.dispose()
    except:
        pass
    
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except (PermissionError, OSError):
        # On Windows, file might still be locked
        pass


@pytest.fixture
def mock_metadata_store():
    """Create mock metadata store."""
    return MockMetadataStore()


@pytest.fixture
def mock_synthetic_store():
    """Create mock synthetic store."""
    return MockSyntheticStore()


@pytest.fixture
def sample_patient_data():
    """Sample patient data for testing."""
    return {
        "name": "John Doe",
        "age": 45,
        "gender": "Male",
        "symptoms": "Persistent chest pain and shortness of breath"
    }


@pytest.fixture
def sample_messages():
    """Sample chat messages for testing."""
    return {
        "appointment": "Hi, I'm Sarah Johnson, 35 years old, female. I need an appointment for severe headache.",
        "followup": "I need to schedule a follow-up for my previous visit.",
        "summary": "Can you generate a medical summary for John Doe?",
        "general": "What services do you provide?"
    }
