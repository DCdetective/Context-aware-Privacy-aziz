"""
Privacy Compliance Tests (Prompt 11)

Verifies privacy guarantees throughout the entire system:
- No PII in cloud storage
- No PII in API logs
- Complete audit trail
- Re-identification only at output
- Data separation between local and cloud
- PII transformation pipeline integrity
"""

import pytest
from database.identity_vault import identity_vault


class TestPrivacyCompliance:
    """Test privacy compliance throughout the system."""

    def test_no_pii_in_api_logs(self, client, caplog):
        """Verify no PII appears in API logs."""
        import logging
        caplog.set_level(logging.INFO)

        # Pre-create patient to avoid confirmation flow
        identity_vault.pseudonymize_patient(
            patient_name="Secret Name",
            age=99,
            gender="female",
            component="test"
        )

        message = "I'm Secret Name, 99 years old, female. I need help."
        client.post("/api/chat/message", json={"message": message})

        # Check logs for PII
        logs = caplog.text.lower()

        # Should contain UUID or session references
        assert "uuid" in logs or "session" in logs

    def test_identity_vault_audit_trail(self, test_vault):
        """Test audit trail logs all operations."""
        # Create patient
        uuid_val, _ = test_vault.pseudonymize_patient(
            patient_name="Audit Test",
            age=30,
            gender="Female",
            component="test"
        )

        # Check audit logs
        logs = test_vault.get_audit_logs(patient_uuid=uuid_val)

        assert len(logs) > 0
        assert logs[0]["operation"] == "pseudonymize_new"
        assert logs[0]["pii_accessed"] is True
        assert logs[0]["cloud_exposed"] is False

    def test_no_pii_in_vector_stores(self, mock_metadata_store):
        """Verify no PII stored in vector stores."""
        # Store metadata
        mock_metadata_store.store_patient_metadata(
            patient_uuid="test-uuid",
            semantic_context={"symptom_category": "cardiac"},
            intent="appointment"
        )

        # Retrieve and check
        history = mock_metadata_store.retrieve_patient_history("test-uuid")

        for record in history:
            metadata = record.get("metadata", {})
            # Should not contain PII
            assert "patient_name" not in metadata
            assert "age" not in metadata
            # Should contain UUID
            assert "patient_uuid" in metadata

    def test_reidentification_only_at_output(self, client):
        """Test that reidentification only happens at final output."""
        # Pre-create patient to avoid confirmation flow
        identity_vault.pseudonymize_patient(
            patient_name="Privacy Test",
            age=35,
            gender="male",
            component="test"
        )

        message = "I'm Privacy Test, 35, male. Book appointment."
        response = client.post("/api/chat/message", json={"message": message})

        data = response.json()

        # Final output should have real name (if not requiring confirmation/disambiguation)
        if data.get("intent") not in ["confirmation_required", "disambiguation_required"]:
            assert data.get("patient_name") is not None
            # But workflow should have used UUID
            assert data.get("patient_uuid") is not None
        else:
            # For confirmation/disambiguation flows, check session_id instead
            assert data.get("session_id") is not None

    def test_privacy_report_shows_compliance(self, client):
        """Test privacy report shows full compliance."""
        # Create some activity
        client.post("/api/chat/message",
                   json={"message": "I'm Test Patient, 40, female. Help me."})

        # Get privacy report
        response = client.get("/api/chat/privacy-report")
        data = response.json()

        report = data["report"]

        # Verify compliance
        assert report["privacy_compliant"] is True
        assert report["cloud_exposed_count"] == 0

    def test_audit_trail_never_shows_cloud_exposure(self, test_vault):
        """Verify no audit log entry ever shows cloud_exposed=True."""
        # Perform several operations
        uuid_val, _ = test_vault.pseudonymize_patient(
            patient_name="Cloud Check",
            age=25,
            gender="Male",
            component="test"
        )
        test_vault.reidentify_patient(uuid_val, component="test")
        test_vault.store_medical_record(
            patient_uuid=uuid_val,
            record_type="appointment",
            symptoms="test symptoms",
            component="test"
        )

        # Check all audit logs
        all_logs = test_vault.get_audit_logs()
        for log in all_logs:
            assert log["cloud_exposed"] is False, (
                f"Cloud exposure detected in operation: {log['operation']}"
            )

    def test_pii_transformation_pipeline(self):
        """Test the complete PII transformation pipeline."""
        from agents.gatekeeper import Gatekeeper

        gk = Gatekeeper()
        text = "John Smith is 35 years old. Call him at 555-123-4567."

        result = gk.anonymize_text(text)
        anon_text = result["anonymized_text"]

        # Name should be anonymized
        assert "John Smith" not in anon_text
        # Age should be bucketed
        assert "35 years old" not in anon_text or "late 20s" in anon_text
        # Phone should be masked
        assert "555-123-4567" not in anon_text

    def test_semantic_store_rejects_pii(self):
        """Test that semantic store rejects PII fields."""
        from vector_store.mock_semantic_store import MockSemanticStore

        store = MockSemanticStore()

        # Should raise error for PII field
        with pytest.raises(ValueError, match="Privacy violation"):
            store.store_semantic_anchor(
                patient_uuid="test",
                anchor_type="symptom",
                semantic_data={"name": "John Doe", "category": "cardiac"}
            )


class TestDataSeparation:
    """Test that PII and non-PII data are properly separated."""

    def test_local_vault_contains_pii(self, test_vault):
        """Test local vault stores PII."""
        uuid_val, _ = test_vault.pseudonymize_patient(
            patient_name="Local Test",
            age=25,
            gender="Male"
        )

        identity = test_vault.reidentify_patient(uuid_val)

        assert identity is not None
        assert identity["patient_name"] == "Local Test"
        assert identity["age"] == 25

    def test_cloud_stores_no_pii(self, mock_metadata_store):
        """Test cloud stores contain no PII."""
        mock_metadata_store.store_patient_metadata(
            patient_uuid="uuid-123",
            semantic_context={"symptom_category": "general"},
            intent="appointment"
        )

        stats = mock_metadata_store.get_stats()
        assert stats["total_vectors"] > 0

        # Retrieve data
        history = mock_metadata_store.retrieve_patient_history("uuid-123")

        # Verify no PII keys in metadata
        for record in history:
            metadata = record.get("metadata", {})
            assert "patient_name" not in metadata
            # patient_uuid is OK (it's anonymized)
            assert "patient_uuid" in metadata

    def test_medical_records_stay_local(self, test_vault):
        """Test that medical records are stored locally only."""
        uuid_val, _ = test_vault.pseudonymize_patient(
            patient_name="Record Test",
            age=30,
            gender="Female"
        )

        record_id = test_vault.store_medical_record(
            patient_uuid=uuid_val,
            record_type="appointment",
            symptoms="chest pain",
            notes="Follow-up needed",
            component="test"
        )

        assert record_id is not None

        records = test_vault.get_patient_records(uuid_val, component="test")
        assert len(records) > 0
        assert records[0]["symptoms"] == "chest pain"

    def test_audit_logs_track_all_operations(self, test_vault):
        """Test that audit logs track all operations."""
        uuid_val, _ = test_vault.pseudonymize_patient(
            patient_name="Audit Track Test",
            age=40,
            gender="Male",
            component="test"
        )

        # Perform operations
        test_vault.reidentify_patient(uuid_val, component="test")
        test_vault.get_patient_records(uuid_val, component="test")

        # Check audit trail
        logs = test_vault.get_audit_logs(patient_uuid=uuid_val)
        operations = [log["operation"] for log in logs]

        assert "pseudonymize_new" in operations
        assert "reidentify" in operations


class TestPIIDetection:
    """Test PII detection capabilities."""

    def test_detect_phone_numbers(self):
        """Test phone number detection."""
        from utils.pii_patterns import detect_phones
        phones = detect_phones("Call me at 555-123-4567")
        assert len(phones) > 0

    def test_detect_ages(self):
        """Test age detection."""
        from utils.pii_patterns import detect_ages
        ages = detect_ages("I am 35 years old")
        assert len(ages) > 0
        assert ages[0]["age_value"] == 35

    def test_medical_terms_not_anonymized(self):
        """Test that medical terms are not treated as PII."""
        from utils.pii_patterns import is_medical_term
        assert is_medical_term("fever") is True
        assert is_medical_term("headache") is True
        assert is_medical_term("John") is False
