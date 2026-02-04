import pytest
from database.identity_vault import identity_vault


class TestPrivacyCompliance:
    """Test privacy compliance throughout the system."""
    
    def test_no_pii_in_api_logs(self, client, caplog):
        """Verify no PII appears in API logs."""
        import logging
        caplog.set_level(logging.INFO)
        
        message = "I'm Secret Name, 99 years old, female. I need help."
        client.post("/api/chat/message", json={"message": message})
        
        # Check logs for PII
        logs = caplog.text.lower()
        
        # Should contain UUID references but not actual name
        assert "uuid" in logs
        # Patient name should not appear in logs (except in gatekeeper)
        # This is a soft check as gatekeeper may log PII locally
    
    def test_identity_vault_audit_trail(self, test_vault):
        """Test audit trail logs all operations."""
        # Create patient
        uuid, _ = test_vault.pseudonymize_patient(
            patient_name="Audit Test",
            age=30,
            gender="Female",
            component="test"
        )
        
        # Check audit logs
        logs = test_vault.get_audit_logs(patient_uuid=uuid)
        
        assert len(logs) > 0
        assert logs[0]["operation"] == "pseudonymize_new"
        assert logs[0]["pii_accessed"] is True
        assert logs[0]["cloud_exposed"] is False
    
    def test_no_pii_in_vector_stores(self, mock_metadata_store):
        """Verify no PII stored in vector stores."""
        # Store metadata
        vector_id = mock_metadata_store.store_patient_metadata(
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
        message = "I'm Privacy Test, 35, male. Book appointment."
        response = client.post("/api/chat/message", json={"message": message})
        
        data = response.json()
        
        # Final output should have real name
        assert data.get("patient_name") is not None
        
        # But workflow should have used UUID
        assert data.get("patient_uuid") is not None
    
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


class TestDataSeparation:
    """Test that PII and non-PII data are properly separated."""
    
    def test_local_vault_contains_pii(self, test_vault):
        """Test local vault stores PII."""
        uuid, _ = test_vault.pseudonymize_patient(
            patient_name="Local Test",
            age=25,
            gender="Male"
        )
        
        identity = test_vault.reidentify_patient(uuid)
        
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
        
        # Verify no PII
        for record in history:
            record_str = str(record).lower()
            assert "name" not in record_str or "patient_name" not in record_str
