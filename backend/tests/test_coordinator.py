import pytest
from agents.coordinator import CoordinatorAgent


@pytest.fixture
def coordinator():
    """Create coordinator agent."""
    return CoordinatorAgent()


def test_coordinator_initialization(coordinator):
    """Test coordinator initializes."""
    assert coordinator is not None
    assert coordinator.model is not None


def test_coordinate_valid_request(coordinator):
    """Test coordinating a valid request."""
    result = coordinator.coordinate_request(
        patient_uuid="test-uuid-123",
        action_type="appointment",
        semantic_context={
            "symptom_category": "respiratory",
            "urgency_level": "routine"
        }
    )
    
    # Valid requests should not have "success": False
    assert result.get("success") is not False
    assert result["patient_uuid"] == "test-uuid-123"
    assert result["action_type"] == "appointment"
    assert "execution_plan" in result
    assert result.get("ready_for_worker") is True
    assert result.get("privacy_safe") is True


def test_coordinate_invalid_action(coordinator):
    """Test coordinating an invalid action type."""
    result = coordinator.coordinate_request(
        patient_uuid="test-uuid-456",
        action_type="invalid_action",
        semantic_context={}
    )
    
    assert result["success"] is False
    assert "error" in result


def test_fallback_execution_plan(coordinator):
    """Test fallback execution plan creation."""
    plan = coordinator._fallback_execution_plan(
        action_type="appointment",
        semantic_context={"urgency_level": "urgent"}
    )
    
    assert "steps" in plan
    assert "estimated_time" in plan
    assert plan["priority"] == "urgent"
