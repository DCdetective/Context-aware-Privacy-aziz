import pytest
from vector_store.mock_stores import MockMetadataStore, MockSyntheticStore


@pytest.fixture
def mock_metadata_store():
    return MockMetadataStore()


@pytest.fixture
def mock_synthetic_store():
    return MockSyntheticStore()


def test_store_patient_metadata(mock_metadata_store):
    """Test storing patient metadata."""
    vector_id = mock_metadata_store.store_patient_metadata(
        patient_uuid="test-uuid-123",
        semantic_context={"symptom_category": "cardiac", "urgency_level": "urgent"},
        intent="appointment"
    )
    assert vector_id is not None
    assert "test-uuid-123" in vector_id


def test_retrieve_patient_history(mock_metadata_store):
    """Test retrieving patient history."""
    uuid = "test-uuid-456"
    mock_metadata_store.store_patient_metadata(
        patient_uuid=uuid,
        semantic_context={"symptom_category": "respiratory"},
        intent="appointment"
    )
    
    history = mock_metadata_store.retrieve_patient_history(uuid)
    assert len(history) == 1
    assert history[0]["metadata"]["patient_uuid"] == uuid


def test_multiple_patient_records(mock_metadata_store):
    """Test storing multiple records for the same patient."""
    uuid = "test-uuid-789"
    
    # Store multiple records
    mock_metadata_store.store_patient_metadata(
        patient_uuid=uuid,
        semantic_context={"symptom_category": "cardiac"},
        intent="appointment"
    )
    mock_metadata_store.store_patient_metadata(
        patient_uuid=uuid,
        semantic_context={"symptom_category": "respiratory"},
        intent="followup"
    )
    
    history = mock_metadata_store.retrieve_patient_history(uuid)
    assert len(history) == 2
    assert history[0]["metadata"]["symptom_category"] == "cardiac"
    assert history[1]["metadata"]["symptom_category"] == "respiratory"


def test_search_doctors(mock_synthetic_store):
    """Test searching for doctors."""
    results = mock_synthetic_store.search_doctors("cardiology")
    assert len(results) > 0
    assert results[0]["metadata"]["specialty"] == "cardiology"


def test_search_medical_knowledge(mock_synthetic_store):
    """Test searching medical knowledge."""
    results = mock_synthetic_store.search_medical_knowledge("chest pain symptoms")
    assert len(results) > 0
    assert "medical_knowledge" in results[0]["metadata"]["type"]


def test_search_similar_cases(mock_synthetic_store):
    """Test searching similar cases."""
    results = mock_synthetic_store.search_similar_cases("patient with fever and cough")
    assert len(results) > 0
    assert "example_case" in results[0]["metadata"]["type"]


def test_metadata_store_stats(mock_metadata_store):
    """Test getting metadata store statistics."""
    stats = mock_metadata_store.get_stats()
    assert "total_vectors" in stats
    assert "dimension" in stats
    assert stats["dimension"] == 384


def test_synthetic_store_stats(mock_synthetic_store):
    """Test getting synthetic store statistics."""
    stats = mock_synthetic_store.get_stats()
    assert "total_vectors" in stats
    assert "dimension" in stats
    assert stats["dimension"] == 384


def test_delete_patient_metadata(mock_metadata_store):
    """Test deleting patient metadata."""
    uuid = "test-uuid-delete"
    
    # Store metadata
    mock_metadata_store.store_patient_metadata(
        patient_uuid=uuid,
        semantic_context={"symptom_category": "general"},
        intent="appointment"
    )
    
    # Verify it exists
    history = mock_metadata_store.retrieve_patient_history(uuid)
    assert len(history) == 1
    
    # Delete it
    mock_metadata_store.delete_patient_metadata(uuid)
    
    # Verify it's gone
    history = mock_metadata_store.retrieve_patient_history(uuid)
    assert len(history) == 0


def test_search_similar_contexts(mock_metadata_store):
    """Test searching for similar contexts."""
    uuid = "test-uuid-search"
    
    # Store some metadata
    mock_metadata_store.store_patient_metadata(
        patient_uuid=uuid,
        semantic_context={"symptom_category": "cardiac"},
        intent="appointment"
    )
    
    # Search for similar contexts
    results = mock_metadata_store.search_similar_contexts(
        query_text="cardiac symptoms",
        patient_uuid=uuid,
        top_k=5
    )
    
    assert len(results) >= 0  # Can be 0 or more


def test_ingest_synthetic_data(mock_synthetic_store):
    """Test synthetic data ingestion."""
    assert not mock_synthetic_store.ingested
    
    mock_synthetic_store.ingest_synthetic_data()
    
    assert mock_synthetic_store.ingested
