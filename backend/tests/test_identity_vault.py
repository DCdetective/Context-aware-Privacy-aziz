import pytest
from database.identity_vault import IdentityVault
from database.models import PatientIdentity, MedicalRecord, AuditLog
import os


@pytest.fixture
def test_vault(tmp_path):
    """Create a temporary identity vault for testing."""
    db_path = tmp_path / "test_vault.db"
    vault = IdentityVault(db_path=str(db_path))
    yield vault
    # Cleanup - properly close all connections
    vault.engine.dispose()
    # Give it a moment for cleanup
    import time
    time.sleep(0.1)
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
    except PermissionError:
        pass  # File might still be locked on Windows


def test_vault_initialization(test_vault):
    """Test that the identity vault initializes correctly."""
    assert test_vault is not None
    assert test_vault.engine is not None
    assert test_vault.SessionLocal is not None


def test_pseudonymize_new_patient(test_vault):
    """Test creating a new patient identity."""
    patient_uuid, is_new = test_vault.pseudonymize_patient(
        patient_name="John Doe",
        age=45,
        gender="Male",
        component="test"
    )
    
    assert patient_uuid is not None
    assert len(patient_uuid) == 36  # UUID format
    assert is_new is True


def test_pseudonymize_existing_patient(test_vault):
    """Test retrieving an existing patient identity."""
    # Create patient first
    uuid1, is_new1 = test_vault.pseudonymize_patient(
        patient_name="Jane Smith",
        age=32,
        gender="Female",
        component="test"
    )
    assert is_new1 is True
    
    # Retrieve same patient
    uuid2, is_new2 = test_vault.pseudonymize_patient(
        patient_name="Jane Smith",
        age=32,
        gender="Female",
        component="test"
    )
    
    assert uuid2 == uuid1  # Same UUID
    assert is_new2 is False  # Not a new patient


def test_reidentify_patient(test_vault):
    """Test re-identifying a patient from UUID."""
    # Pseudonymize first
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="Alice Johnson",
        age=28,
        gender="Female",
        component="test"
    )
    
    # Re-identify
    identity = test_vault.reidentify_patient(
        patient_uuid=patient_uuid,
        component="test"
    )
    
    assert identity is not None
    assert identity["patient_name"] == "Alice Johnson"
    assert identity["age"] == 28
    assert identity["gender"] == "Female"
    assert identity["patient_uuid"] == patient_uuid


def test_reidentify_nonexistent_patient(test_vault):
    """Test re-identifying a non-existent patient."""
    identity = test_vault.reidentify_patient(
        patient_uuid="non-existent-uuid",
        component="test"
    )
    
    assert identity is None


def test_store_medical_record(test_vault):
    """Test storing a medical record."""
    # Create patient first
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="Bob Williams",
        age=50,
        gender="Male",
        component="test"
    )
    
    # Store record
    record_id = test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="appointment",
        symptoms="Headache and fever",
        diagnosis="Viral infection",
        treatment_plan="Rest and fluids",
        component="test"
    )
    
    assert record_id is not None
    assert len(record_id) == 36  # UUID format


def test_get_patient_records(test_vault):
    """Test retrieving patient medical records."""
    # Create patient
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="Carol Davis",
        age=35,
        gender="Female",
        component="test"
    )
    
    # Store multiple records
    test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="appointment",
        symptoms="Cough",
        component="test"
    )
    
    test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="followup",
        symptoms="Cough improving",
        component="test"
    )
    
    # Retrieve all records
    records = test_vault.get_patient_records(
        patient_uuid=patient_uuid,
        component="test"
    )
    
    assert len(records) == 2
    assert records[0]["record_type"] in ["appointment", "followup"]


def test_get_patient_records_filtered(test_vault):
    """Test retrieving filtered patient records."""
    # Create patient
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="David Miller",
        age=40,
        gender="Male",
        component="test"
    )
    
    # Store different types
    test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="appointment",
        symptoms="Back pain",
        component="test"
    )
    
    test_vault.store_medical_record(
        patient_uuid=patient_uuid,
        record_type="summary",
        diagnosis="Muscle strain",
        component="test"
    )
    
    # Retrieve only appointments
    appointments = test_vault.get_patient_records(
        patient_uuid=patient_uuid,
        record_type="appointment",
        component="test"
    )
    
    assert len(appointments) == 1
    assert appointments[0]["record_type"] == "appointment"


def test_audit_logs(test_vault):
    """Test audit logging."""
    # Create patient (generates audit log)
    patient_uuid, _ = test_vault.pseudonymize_patient(
        patient_name="Eve Anderson",
        age=25,
        gender="Female"
    )
    
    # Get audit logs
    logs = test_vault.get_audit_logs(patient_uuid=patient_uuid)
    
    assert len(logs) > 0
    assert logs[0]['patient_uuid'] == patient_uuid
    assert logs[0]['operation'] == "pseudonymize_new"


def test_privacy_compliance(test_vault):
    """Test privacy compliance verification."""
    # Create patient
    test_vault.pseudonymize_patient(
        patient_name="Frank Brown",
        age=55,
        gender="Male"
    )
    
    # Check compliance
    report = test_vault.verify_privacy_compliance()
    
    assert report['privacy_compliant'] is True
    assert report['cloud_exposed_count'] == 0
    assert report['total_patients'] >= 1
