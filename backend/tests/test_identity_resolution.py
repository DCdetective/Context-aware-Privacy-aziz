"""
Tests for Patient Identity Resolution System.

Tests cover:
1. Single patient resolution (auto-resolve)
2. Multiple patients with same name (disambiguation)
3. New patient creation (confirmation required)
4. Session management (active patient context)
"""

import pytest
from database.identity_vault import identity_vault
from agents.session_manager import session_manager


@pytest.fixture(autouse=True)
def cleanup():
    """Clean up sessions and database before and after each test."""
    from database.models import Base
    
    session_manager.clear_all_sessions()
    
    # Clean up database tables
    Base.metadata.drop_all(identity_vault.engine)
    Base.metadata.create_all(identity_vault.engine)
    
    yield
    
    session_manager.clear_all_sessions()


def test_single_patient_resolution():
    """Test resolution with single matching patient."""
    # Create patient
    uuid1, _ = identity_vault.pseudonymize_patient(
        patient_name="John Doe",
        age=30,
        gender="Male",
        component="test"
    )
    
    # Resolve
    resolution = identity_vault.resolve_patient_identity(
        patient_name="John Doe",
        component="test"
    )
    
    assert resolution["status"] == "resolved"
    assert resolution["patient_uuid"] == uuid1
    assert resolution["patient_name"] == "John Doe"
    assert resolution["age"] == 30
    assert resolution["gender"] == "Male"
    print(f"✓ Single patient resolution test passed: {uuid1}")


def test_multiple_patients_disambiguation():
    """Test disambiguation when multiple patients share a name."""
    # Create two patients with same name by directly adding to database
    # We bypass the normal pseudonymize_patient to simulate duplicate names
    from database.models import PatientIdentity
    from datetime import datetime
    import uuid as uuid_lib
    
    session = identity_vault._get_session()
    
    uuid1 = str(uuid_lib.uuid4())
    patient1 = PatientIdentity(
        patient_uuid=uuid1,
        patient_name="Aziz Ahmed",
        age=25,
        gender="Male",
        created_at=datetime.utcnow(),
        last_accessed=datetime.utcnow(),
        access_count=1
    )
    
    uuid2 = str(uuid_lib.uuid4())
    patient2 = PatientIdentity(
        patient_uuid=uuid2,
        patient_name="Aziz Ahmed",
        age=45,
        gender="Male",
        created_at=datetime.utcnow(),
        last_accessed=datetime.utcnow(),
        access_count=1
    )
    
    session.add(patient1)
    session.add(patient2)
    session.commit()
    session.close()
    
    # Try to resolve
    resolution = identity_vault.resolve_patient_identity(
        patient_name="Aziz Ahmed",
        component="test"
    )
    
    assert resolution["status"] == "needs_disambiguation"
    assert len(resolution["candidates"]) == 2
    assert resolution["action_required"] == "select_patient_uuid"
    
    # Verify both UUIDs are in candidates
    candidate_uuids = [c["patient_uuid"] for c in resolution["candidates"]]
    assert uuid1 in candidate_uuids
    assert uuid2 in candidate_uuids
    
    # Verify ages are different
    ages = [c["age"] for c in resolution["candidates"]]
    assert 25 in ages
    assert 45 in ages
    
    print(f"✓ Multiple patients disambiguation test passed")
    print(f"  - Patient 1: {uuid1[:8]}... (age 25)")
    print(f"  - Patient 2: {uuid2[:8]}... (age 45)")


def test_new_patient_needs_confirmation():
    """Test that new patient creation requires confirmation."""
    resolution = identity_vault.resolve_patient_identity(
        patient_name="Brand New Patient",
        age=35,
        gender="Female",
        component="test"
    )
    
    assert resolution["status"] == "needs_confirmation"
    assert resolution["action_required"] == "confirm_new_patient"
    assert "Brand New Patient" in resolution["message"]
    assert resolution["patient_name"] == "Brand New Patient"
    assert resolution["age"] == 35
    assert resolution["gender"] == "Female"
    
    print(f"✓ New patient confirmation test passed")


def test_session_active_patient():
    """Test session maintains active patient context."""
    session_id = session_manager.create_session()
    
    # Set active patient
    session_manager.set_active_patient(
        session_id=session_id,
        patient_uuid="uuid-123",
        patient_name="Test Patient"
    )
    
    # Retrieve active patient
    active = session_manager.get_active_patient(session_id)
    assert active is not None
    assert active["patient_uuid"] == "uuid-123"
    assert active["patient_name"] == "Test Patient"
    
    print(f"✓ Session active patient test passed: {session_id}")


def test_session_pending_disambiguation():
    """Test session can store and retrieve pending disambiguation data."""
    session_id = session_manager.create_session()
    
    # Set pending disambiguation
    disambiguation_data = {
        "status": "needs_disambiguation",
        "candidates": [
            {"patient_uuid": "uuid-1", "patient_name": "John Doe", "age": 30},
            {"patient_uuid": "uuid-2", "patient_name": "John Doe", "age": 40}
        ]
    }
    
    session_manager.set_pending_disambiguation(session_id, disambiguation_data)
    
    # Retrieve pending disambiguation
    pending = session_manager.get_pending_disambiguation(session_id)
    assert pending is not None
    assert pending["status"] == "needs_disambiguation"
    assert len(pending["candidates"]) == 2
    
    # Clear disambiguation
    session_manager.clear_pending_disambiguation(session_id)
    pending_after_clear = session_manager.get_pending_disambiguation(session_id)
    assert pending_after_clear is None
    
    print(f"✓ Session pending disambiguation test passed")


def test_find_patients_by_name():
    """Test searching for patients by name."""
    # Create multiple patients
    uuid1, _ = identity_vault.pseudonymize_patient(
        patient_name="Sarah Smith",
        age=28,
        gender="Female",
        component="test"
    )
    
    uuid2, _ = identity_vault.pseudonymize_patient(
        patient_name="Sarah Johnson",
        age=35,
        gender="Female",
        component="test"
    )
    
    # Search for "Sarah"
    results = identity_vault.find_patients_by_name(
        patient_name="Sarah",
        component="test"
    )
    
    assert len(results) >= 2
    result_names = [r["patient_name"] for r in results]
    assert "Sarah Smith" in result_names
    assert "Sarah Johnson" in result_names
    
    print(f"✓ Find patients by name test passed: found {len(results)} patients")


def test_confirm_new_patient():
    """Test explicit new patient confirmation."""
    # Confirm creation of new patient
    patient_uuid = identity_vault.confirm_new_patient(
        patient_name="Confirmed Patient",
        age=42,
        gender="Male",
        component="test"
    )
    
    assert patient_uuid is not None
    assert len(patient_uuid) == 36  # UUID format
    
    # Verify patient was created
    identity = identity_vault.reidentify_patient(patient_uuid, component="test")
    assert identity is not None
    assert identity["patient_name"] == "Confirmed Patient"
    assert identity["age"] == 42
    assert identity["gender"] == "Male"
    
    print(f"✓ Confirm new patient test passed: {patient_uuid}")


def test_session_conversation_history():
    """Test session conversation history tracking."""
    session_id = session_manager.create_session()
    
    # Add messages to history
    session_manager.add_to_history(session_id, "user", "Hello")
    session_manager.add_to_history(session_id, "assistant", "Hi, how can I help?")
    session_manager.add_to_history(session_id, "user", "Book appointment for John")
    
    # Get history
    history = session_manager.get_history(session_id)
    assert len(history) == 3
    assert history[0]["role"] == "user"
    assert history[0]["message"] == "Hello"
    assert history[1]["role"] == "assistant"
    assert history[2]["message"] == "Book appointment for John"
    
    print(f"✓ Session conversation history test passed")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("Running Identity Resolution Tests")
    print("="*70 + "\n")
    
    test_single_patient_resolution()
    test_multiple_patients_disambiguation()
    test_new_patient_needs_confirmation()
    test_session_active_patient()
    test_session_pending_disambiguation()
    test_find_patients_by_name()
    test_confirm_new_patient()
    test_session_conversation_history()
    
    print("\n" + "="*70)
    print("All Identity Resolution Tests Passed!")
    print("="*70 + "\n")
