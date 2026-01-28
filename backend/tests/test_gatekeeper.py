import pytest
from agents.gatekeeper import GatekeeperAgent
from vector_store.mock_semantic_store import MockSemanticStore


@pytest.fixture
def gatekeeper():
    """Create gatekeeper agent with mock semantic store."""
    semantic_store = MockSemanticStore()
    return GatekeeperAgent(semantic_store=semantic_store)


def test_gatekeeper_initialization(gatekeeper):
    """Test gatekeeper initializes correctly."""
    assert gatekeeper is not None
    assert gatekeeper.model is not None


def test_extract_patient_info_structured(gatekeeper):
    """Test extracting patient info from structured input."""
    user_input = """
    Patient Name: John Doe
    Age: 45
    Gender: Male
    Symptoms: Persistent headache and dizziness for 3 days
    """
    
    patient_info = gatekeeper.extract_patient_info(user_input)
    
    assert "patient_name" in patient_info
    assert "age" in patient_info
    assert "gender" in patient_info
    assert "symptoms" in patient_info


def test_pseudonymize_input(gatekeeper):
    """Test complete pseudonymization pipeline."""
    user_input = """
    Patient: Alice Johnson, 32 years old, Female
    Symptoms: Severe cough and fever
    """
    
    result = gatekeeper.pseudonymize_input(user_input)
    
    assert "patient_uuid" in result
    assert "semantic_context" in result
    assert result["cloud_safe"] is True
    assert result["original_has_pii"] is True
    
    # Verify UUID format
    assert len(result["patient_uuid"]) == 36


def test_semantic_context_no_pii(gatekeeper):
    """Test that semantic context contains no PII."""
    patient_info = {
        "patient_name": "Bob Smith",
        "age": 50,
        "gender": "Male",
        "symptoms": "Chest pain and shortness of breath"
    }
    
    semantic_context = gatekeeper.extract_semantic_context(patient_info)
    
    # Verify no PII in semantic context
    import json
    context_str = json.dumps(semantic_context).lower()
    
    assert "bob" not in context_str
    assert "smith" not in context_str
    assert "50" not in context_str
    
    # Should contain medical semantics
    assert "symptom_category" in semantic_context or "category" in context_str


def test_reidentify_output(gatekeeper):
    """Test re-identification of patient from UUID."""
    # First pseudonymize
    user_input = "Patient: Carol Davis, 35, Female. Symptoms: Back pain"
    pseudo_result = gatekeeper.pseudonymize_input(user_input)
    
    patient_uuid = pseudo_result["patient_uuid"]
    
    # Simulate cloud response
    cloud_response = {
        "patient_uuid": patient_uuid,
        "appointment_scheduled": True,
        "appointment_time": "2024-01-15 10:00"
    }
    
    # Re-identify
    final_output = gatekeeper.reidentify_output(patient_uuid, cloud_response)
    
    assert "patient_name" in final_output
    assert final_output["reidentified"] is True
    assert "Carol Davis" in final_output["patient_name"]


def test_fallback_extraction(gatekeeper):
    """Test fallback extraction when LLM fails."""
    text = "David Miller, 40 years old, male, has severe headache"
    
    result = gatekeeper._fallback_extraction(text)
    
    assert result["patient_name"] != "Unknown Patient"
    assert result["age"] == 40
    assert result["gender"] == "Male"


@pytest.mark.skip(reason="Requires Ollama running")
def test_ollama_call(gatekeeper):
    """Test calling Ollama LLM (requires Ollama installed)."""
    response = gatekeeper._call_ollama("Say 'test successful'")
    assert response is not None
    assert len(response) > 0
