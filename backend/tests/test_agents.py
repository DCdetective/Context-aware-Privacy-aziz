import pytest
from agents.context_agent import context_agent
from agents.execution_agent import execution_agent
from agents.coordinator import coordinator


def test_context_agent_initialization():
    """Test context agent initializes."""
    assert context_agent.model is not None


def test_execution_agent_initialization():
    """Test execution agent initializes."""
    assert execution_agent.model is not None


def test_coordinator_initialization():
    """Test coordinator initializes."""
    assert coordinator is not None


def test_coordinator_process_message():
    """Test coordinator processes a message."""
    from database.identity_vault import identity_vault
    
    # First, create the patient so we don't trigger confirmation
    identity_vault.pseudonymize_patient(
        patient_name="John Doe",
        age=45,
        gender="male",
        component="test"
    )
    
    message = "Hi, I'm John Doe, 45 years old, male. I need an appointment for chest pain."
    
    result = coordinator.process_message(message)
    
    assert "success" in result
    assert "intent" in result
    assert result["privacy_safe"] is True
    
    # Should have patient_uuid after resolution (not confirmation)
    if result.get("intent") != "confirmation_required":
        assert "patient_uuid" in result
