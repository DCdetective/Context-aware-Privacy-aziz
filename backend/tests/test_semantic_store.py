import pytest
from vector_store.mock_semantic_store import MockSemanticStore
import json


@pytest.fixture
def mock_store():
    """Create a mock semantic store for testing."""
    return MockSemanticStore()


def test_store_initialization(mock_store):
    """Test semantic store initializes correctly."""
    assert mock_store is not None
    assert mock_store.dimension == 384


def test_store_valid_semantic_anchor(mock_store):
    """Test storing a valid semantic anchor."""
    anchor_id = mock_store.store_semantic_anchor(
        patient_uuid="test-uuid-123",
        anchor_type="preference",
        semantic_data={
            "appointment_preference": "morning",
            "communication_method": "email"
        }
    )
    
    assert anchor_id is not None
    assert "test-uuid-123" in anchor_id


def test_prevent_pii_storage_name(mock_store):
    """Test that storing PII (name) is prevented."""
    with pytest.raises(ValueError, match="Privacy violation"):
        mock_store.store_semantic_anchor(
            patient_uuid="test-uuid-456",
            anchor_type="invalid",
            semantic_data={
                "patient_name": "John Doe",  # PII - should be rejected
                "preference": "morning"
            }
        )


def test_prevent_pii_storage_age(mock_store):
    """Test that storing PII (age) is prevented."""
    with pytest.raises(ValueError, match="Privacy violation"):
        mock_store.store_semantic_anchor(
            patient_uuid="test-uuid-789",
            anchor_type="invalid",
            semantic_data={
                "age": 45,  # PII - should be rejected
                "preference": "morning"
            }
        )


def test_prevent_pii_storage_gender(mock_store):
    """Test that storing PII (gender) is prevented."""
    with pytest.raises(ValueError, match="Privacy violation"):
        mock_store.store_semantic_anchor(
            patient_uuid="test-uuid-101",
            anchor_type="invalid",
            semantic_data={
                "gender": "Male",  # PII - should be rejected
                "preference": "evening"
            }
        )


def test_retrieve_semantic_anchors(mock_store):
    """Test retrieving semantic anchors."""
    patient_uuid = "test-uuid-retrieve"
    
    # Store multiple anchors
    mock_store.store_semantic_anchor(
        patient_uuid=patient_uuid,
        anchor_type="preference",
        semantic_data={"appointment_time": "morning"}
    )
    
    mock_store.store_semantic_anchor(
        patient_uuid=patient_uuid,
        anchor_type="constraint",
        semantic_data={"accessibility": "wheelchair_access"}
    )
    
    # Retrieve all
    anchors = mock_store.retrieve_semantic_anchors(patient_uuid)
    
    assert len(anchors) == 2
    assert all(a["patient_uuid"] == patient_uuid for a in anchors)


def test_retrieve_filtered_anchors(mock_store):
    """Test retrieving filtered semantic anchors."""
    patient_uuid = "test-uuid-filter"
    
    # Store different types
    mock_store.store_semantic_anchor(
        patient_uuid=patient_uuid,
        anchor_type="preference",
        semantic_data={"appointment_time": "afternoon"}
    )
    
    mock_store.store_semantic_anchor(
        patient_uuid=patient_uuid,
        anchor_type="constraint",
        semantic_data={"requires": "specialist"}
    )
    
    # Retrieve only preferences
    preferences = mock_store.retrieve_semantic_anchors(
        patient_uuid=patient_uuid,
        anchor_type="preference"
    )
    
    assert len(preferences) == 1
    assert preferences[0]["anchor_type"] == "preference"


def test_search_similar_semantics(mock_store):
    """Test semantic similarity search."""
    patient_uuid = "test-uuid-search"
    
    # Store semantic anchor
    mock_store.store_semantic_anchor(
        patient_uuid=patient_uuid,
        anchor_type="context",
        semantic_data={
            "follow_up_needed": True,
            "specialty": "cardiology"
        }
    )
    
    # Search
    results = mock_store.search_similar_semantics(
        query_text="cardiology follow-up",
        patient_uuid=patient_uuid
    )
    
    assert len(results) >= 1
    assert results[0]["patient_uuid"] == patient_uuid


def test_delete_patient_anchors(mock_store):
    """Test deleting all anchors for a patient."""
    patient_uuid = "test-uuid-delete"
    
    # Store multiple anchors
    for i in range(3):
        mock_store.store_semantic_anchor(
            patient_uuid=patient_uuid,
            anchor_type=f"type_{i}",
            semantic_data={"data": f"value_{i}"}
        )
    
    # Verify stored
    anchors = mock_store.retrieve_semantic_anchors(patient_uuid)
    assert len(anchors) == 3
    
    # Delete
    deleted_count = mock_store.delete_patient_anchors(patient_uuid)
    assert deleted_count == 3
    
    # Verify deleted
    anchors_after = mock_store.retrieve_semantic_anchors(patient_uuid)
    assert len(anchors_after) == 0


def test_store_stats(mock_store):
    """Test getting store statistics."""
    # Store some data
    for i in range(5):
        mock_store.store_semantic_anchor(
            patient_uuid=f"uuid-{i}",
            anchor_type="test",
            semantic_data={"test": f"data_{i}"}
        )
    
    stats = mock_store.get_store_stats()
    
    assert stats["total_vectors"] == 5
    assert stats["contains_pii"] is False
    assert "dimension" in stats


def test_privacy_compliance_no_pii(mock_store):
    """Test that semantic store never contains PII."""
    # Store valid semantic data
    patient_uuid = "test-uuid-privacy"
    
    mock_store.store_semantic_anchor(
        patient_uuid=patient_uuid,
        anchor_type="preference",
        semantic_data={
            "preferred_time": "morning",
            "contact_method": "email",
            "language_preference": "english"
        }
    )
    
    # Retrieve and verify
    anchors = mock_store.retrieve_semantic_anchors(patient_uuid)
    
    # Check that no PII exists in semantic data
    for anchor in anchors:
        semantic_str = json.dumps(anchor["semantic_data"]).lower()
        forbidden = ['name', 'age', 'gender', 'ssn', 'dob']
        
        for field in forbidden:
            # Check as dictionary keys, not in values
            assert field not in anchor["semantic_data"].keys()
    
    print("✅ Privacy compliance verified: No PII in semantic store")
