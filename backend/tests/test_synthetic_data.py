import pytest
from rag.synthetic_data import SyntheticDataLoader


@pytest.fixture
def data_loader():
    """Create synthetic data loader instance."""
    return SyntheticDataLoader()


def test_load_doctors(data_loader):
    """Test loading doctors data."""
    doctors = data_loader.doctors
    assert "doctors" in doctors
    assert len(doctors["doctors"]) > 0


def test_load_policies(data_loader):
    """Test loading hospital policies."""
    policies = data_loader.policies
    assert "appointment_rules" in policies
    assert "working_hours" in policies


def test_load_medical_knowledge(data_loader):
    """Test loading medical knowledge."""
    knowledge = data_loader.medical_knowledge
    assert "symptom_categories" in knowledge
    assert "urgency_classification" in knowledge


def test_get_doctor_by_specialty(data_loader):
    """Test getting doctors by specialty."""
    cardiologists = data_loader.get_doctor_by_specialty("cardiology")
    assert len(cardiologists) > 0
    assert all(d["specialty"] == "cardiology" for d in cardiologists)


def test_get_specialty_for_symptoms(data_loader):
    """Test getting specialty recommendation."""
    specialty = data_loader.get_specialty_for_symptoms("cardiac")
    assert specialty == "cardiology"


def test_classify_urgency_emergency(data_loader):
    """Test emergency urgency classification."""
    urgency = data_loader.classify_urgency("severe chest pain can't breathe")
    assert urgency == "emergency"


def test_classify_urgency_routine(data_loader):
    """Test routine urgency classification."""
    urgency = data_loader.classify_urgency("mild occasional headache")
    assert urgency == "routine"


def test_get_consultation_duration(data_loader):
    """Test getting consultation duration."""
    duration = data_loader.get_consultation_duration("cardiology", "urgent")
    assert duration > 0
    assert isinstance(duration, int)


def test_get_all_synthetic_documents(data_loader):
    """Test generating all synthetic documents."""
    documents = data_loader.get_all_synthetic_documents()
    
    assert len(documents) > 0
    
    # Verify structure
    for doc in documents:
        assert "content" in doc
        assert "metadata" in doc
        assert "type" in doc["metadata"]


def test_no_pii_in_synthetic_data(data_loader):
    """Verify synthetic data contains no real PII."""
    documents = data_loader.get_all_synthetic_documents()
    
    # Check no real patient names in synthetic data
    forbidden_patterns = ["patient UUID", "patient ID", "real name"]
    
    for doc in documents:
        content_lower = doc["content"].lower()
        for pattern in forbidden_patterns:
            assert pattern not in content_lower
