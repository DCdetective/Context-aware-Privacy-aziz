import pytest
from agents.worker import WorkerAgent
from vector_store.mock_semantic_store import MockSemanticStore
from database.identity_vault import identity_vault


@pytest.fixture
def worker():
    """Create worker agent."""
    semantic_store = MockSemanticStore()
    return WorkerAgent(semantic_store=semantic_store)


@pytest.fixture
def test_patient_uuid():
    """Create a test patient and return UUID."""
    uuid, _ = identity_vault.pseudonymize_patient(
        patient_name="Test Worker Patient",
        age=40,
        gender="Male",
        component="test"
    )
    return uuid


def test_worker_initialization(worker):
    """Test worker initializes."""
    assert worker is not None
    assert worker.model is not None


def test_validate_uuid_valid(worker, test_patient_uuid):
    """Test UUID validation with valid UUID."""
    is_valid = worker._validate_uuid(test_patient_uuid)
    assert is_valid is True


def test_validate_uuid_invalid(worker):
    """Test UUID validation with invalid UUID."""
    is_valid = worker._validate_uuid("invalid-uuid-999")
    assert is_valid is False


def test_execute_appointment(worker, test_patient_uuid):
    """Test executing appointment task."""
    execution_plan = {
        "steps": ["validate", "schedule", "confirm"],
        "priority": "routine",
        "requires_specialist": False
    }
    
    semantic_context = {
        "symptom_category": "general",
        "urgency_level": "routine"
    }
    
    result = worker.execute_task(
        patient_uuid=test_patient_uuid,
        action_type="appointment",
        execution_plan=execution_plan,
        semantic_context=semantic_context
    )
    
    assert result["success"] is True
    assert result["action"] == "appointment_scheduled"
    assert "appointment_time" in result


def test_execute_followup(worker, test_patient_uuid):
    """Test executing follow-up task."""
    execution_plan = {"steps": ["retrieve", "schedule"], "priority": "routine"}
    semantic_context = {}
    
    result = worker.execute_task(
        patient_uuid=test_patient_uuid,
        action_type="followup",
        execution_plan=execution_plan,
        semantic_context=semantic_context
    )
    
    assert result["success"] is True
    assert result["action"] == "followup_scheduled"


def test_execute_summary(worker, test_patient_uuid):
    """Test executing summary generation."""
    execution_plan = {"steps": ["gather", "generate", "format"], "priority": "routine"}
    semantic_context = {}
    
    result = worker.execute_task(
        patient_uuid=test_patient_uuid,
        action_type="summary",
        execution_plan=execution_plan,
        semantic_context=semantic_context
    )
    
    assert result["success"] is True
    assert result["action"] == "summary_generated"
    assert "summary" in result
