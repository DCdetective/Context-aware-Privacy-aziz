import pytest
from agents.gatekeeper import GatekeeperAgent
import ollama


@pytest.fixture
def gatekeeper():
    """Create a Gatekeeper agent instance."""
    return GatekeeperAgent()


def check_ollama_available():
    """Check if Ollama is available and responsive."""
    try:
        ollama.list()
        return True
    except Exception:
        return False


# Skip tests that require Ollama if it's not available
requires_ollama = pytest.mark.skipif(
    not check_ollama_available(),
    reason="Ollama is not running or not available"
)


def test_gatekeeper_initialization(gatekeeper):
    """Test Gatekeeper initializes correctly."""
    assert gatekeeper.model is not None
    assert gatekeeper.host is not None


@requires_ollama
def test_extract_pii_complete(gatekeeper):
    """Test PII extraction with complete information."""
    message = "Hi, I'm Sarah Johnson, 35 years old, female. I have a severe headache for 3 days."
    
    pii = gatekeeper.extract_pii(message)
    
    # Verify PII structure
    assert 'patient_name' in pii
    assert 'age' in pii
    assert 'gender' in pii
    assert 'medical_info' in pii


@requires_ollama
def test_extract_intent_appointment(gatekeeper):
    """Test intent extraction for appointment."""
    message = "I need to book an appointment for tomorrow"
    intent = gatekeeper.extract_intent(message)
    assert intent == "appointment"


@requires_ollama
def test_extract_intent_followup(gatekeeper):
    """Test intent extraction for follow-up."""
    message = "I need to schedule a follow-up visit"
    intent = gatekeeper.extract_intent(message)
    assert intent == "followup"


@requires_ollama
def test_extract_intent_summary(gatekeeper):
    """Test intent extraction for summary."""
    message = "Can I get my medical summary?"
    intent = gatekeeper.extract_intent(message)
    assert intent == "summary"


@requires_ollama
def test_semantic_context_no_pii(gatekeeper):
    """Test semantic context doesn't contain PII."""
    medical_info = "Severe chest pain and difficulty breathing"
    
    semantic = gatekeeper.extract_semantic_context(medical_info)
    
    # Verify structure
    assert 'symptom_category' in semantic
    assert 'urgency_level' in semantic
    assert 'requires_specialist' in semantic
    assert 'estimated_duration' in semantic
    
    # Verify no PII leaked
    semantic_str = str(semantic).lower()
    assert 'name' not in semantic_str
    assert 'age' not in semantic_str


@requires_ollama
def test_process_message_complete_workflow(gatekeeper):
    """Test complete message processing workflow."""
    message = "Hello, I'm John Doe, 45 years old, male. I have persistent cough and fever."
    
    result = gatekeeper.process_message(message)
    
    # Verify structure
    assert 'pii' in result
    assert 'intent' in result
    assert 'semantic_context' in result
    assert 'original_message' in result
    assert 'cloud_safe' in result
    
    # Verify cloud safety
    assert result['cloud_safe'] is True
    
    # Verify PII was extracted
    assert result['pii']['patient_name'] is not None
    
    # Verify intent was classified
    assert result['intent'] in ['appointment', 'followup', 'summary', 'general']


def test_fallback_semantic_extraction(gatekeeper):
    """Test fallback semantic extraction."""
    medical_info = "Severe chest pain"
    
    semantic = gatekeeper._fallback_semantic_extraction(medical_info)
    
    assert semantic['symptom_category'] == 'cardiac'
    assert semantic['urgency_level'] == 'emergency'
    assert semantic['requires_specialist'] is True


def test_extract_pii_minimal_info(gatekeeper):
    """Test PII extraction with minimal information."""
    message = "I have a headache"
    
    pii = gatekeeper.extract_pii(message)
    
    # Should still return structure
    assert 'patient_name' in pii
    assert 'medical_info' in pii
    # Medical info should contain the symptom (either full message or extracted symptom)
    assert 'headache' in pii['medical_info'].lower()
