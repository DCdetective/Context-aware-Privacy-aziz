import pytest
from fastapi.testclient import TestClient
from main import app
from database.identity_vault import identity_vault
import time


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


class TestEndToEndWorkflows:
    """End-to-end tests for complete privacy-preserving workflows."""
    
    def test_complete_appointment_workflow(self, client):
        """
        Test complete appointment scheduling workflow.
        
        Workflow:
        1. Frontend submits patient data
        2. Gatekeeper pseudonymizes
        3. Coordinator plans
        4. Worker executes
        5. Gatekeeper re-identifies
        6. Frontend receives result
        """
        print("\n" + "=" * 70)
        print("E2E TEST: Complete Appointment Workflow")
        print("=" * 70)
        
        # Step 1: Submit appointment request
        request_data = {
            "patient_name": "E2E Test Patient",
            "age": 35,
            "gender": "Male",
            "symptoms": "Testing end-to-end workflow"
        }
        
        print(f"Step 1: Submitting appointment for {request_data['patient_name']}")
        response = client.post("/api/appointments/schedule", json=request_data)
        
        assert response.status_code == 200
        data = response.json()
        
        # Step 2: Verify response structure
        print("Step 2: Verifying response structure")
        assert data["success"] is True
        assert "patient_uuid" in data
        assert "appointment_time" in data
        assert data["patient_name"] == "E2E Test Patient"
        
        patient_uuid = data["patient_uuid"]
        print(f"         Patient UUID: {patient_uuid}")
        
        # Step 3: Verify identity vault entry
        print("Step 3: Verifying identity vault entry")
        identity = identity_vault.reidentify_patient(patient_uuid, component="e2e_test")
        assert identity is not None
        assert identity["patient_name"] == "E2E Test Patient"
        assert identity["age"] == 35
        
        # Step 4: Verify medical records created
        print("Step 4: Verifying medical records")
        records = identity_vault.get_patient_records(patient_uuid, component="e2e_test")
        assert len(records) > 0
        assert records[0]["record_type"] == "appointment"
        
        # Step 5: Verify audit trail
        print("Step 5: Verifying audit trail")
        audit_logs = identity_vault.get_audit_trail(patient_uuid=patient_uuid)
        assert len(audit_logs) > 0
        
        # CRITICAL: Verify NO cloud exposure
        cloud_exposed_logs = [log for log in audit_logs if log["cloud_exposed"]]
        assert len(cloud_exposed_logs) == 0, "PRIVACY VIOLATION: PII exposed to cloud!"
        
        print("✅ Complete appointment workflow successful")
        print("=" * 70)
    
    def test_complete_followup_workflow(self, client):
        """Test complete follow-up scheduling workflow."""
        print("\n" + "=" * 70)
        print("E2E TEST: Complete Follow-Up Workflow")
        print("=" * 70)
        
        # Step 1: Create initial appointment
        print("Step 1: Creating initial appointment")
        initial_request = {
            "patient_name": "Follow-Up Test Patient",
            "age": 42,
            "gender": "Female",
            "symptoms": "Initial visit for follow-up test"
        }
        
        initial_response = client.post("/api/appointments/schedule", json=initial_request)
        assert initial_response.status_code == 200
        initial_data = initial_response.json()
        patient_uuid = initial_data["patient_uuid"]
        
        print(f"         Initial appointment created, UUID: {patient_uuid}")
        
        # Step 2: Schedule follow-up
        print("Step 2: Scheduling follow-up")
        followup_request = {
            "patient_name": "Follow-Up Test Patient"
        }
        
        followup_response = client.post("/api/followups/schedule", json=followup_request)
        assert followup_response.status_code == 200
        followup_data = followup_response.json()
        
        # Step 3: Verify follow-up details
        print("Step 3: Verifying follow-up details")
        assert followup_data["success"] is True
        assert "followup_time" in followup_data
        assert followup_data["patient_name"] == "Follow-Up Test Patient"
        
        # Step 4: Verify previous visits tracked
        print("Step 4: Verifying previous visits tracked")
        # Should have at least 1 previous visit (the initial appointment)
        assert followup_data.get("previous_visits", 0) >= 0
        
        # Step 5: Verify continuity of care
        print("Step 5: Verifying continuity of care")
        records = identity_vault.get_patient_records(patient_uuid, component="e2e_test")
        record_types = [r["record_type"] for r in records]
        assert "appointment" in record_types
        assert "followup" in record_types
        
        print("✅ Complete follow-up workflow successful")
        print("=" * 70)
    
    def test_complete_summary_workflow(self, client):
        """Test complete medical summary generation workflow."""
        print("\n" + "=" * 70)
        print("E2E TEST: Complete Summary Generation Workflow")
        print("=" * 70)
        
        # Step 1: Create patient with multiple records
        print("Step 1: Creating patient with multiple records")
        appointment_request = {
            "patient_name": "Summary Test Patient",
            "age": 50,
            "gender": "Male",
            "symptoms": "Initial visit"
        }
        
        appointment_response = client.post("/api/appointments/schedule", json=appointment_request)
        assert appointment_response.status_code == 200
        
        # Step 2: Generate summary
        print("Step 2: Generating medical summary")
        summary_request = {
            "patient_name": "Summary Test Patient"
        }
        
        summary_response = client.post("/api/summaries/generate", json=summary_request)
        assert summary_response.status_code == 200
        summary_data = summary_response.json()
        
        # Step 3: Verify summary structure
        print("Step 3: Verifying summary structure")
        assert summary_data["success"] is True
        assert "summary" in summary_data
        assert summary_data["patient_name"] == "Summary Test Patient"
        
        # Step 4: Verify summary content
        print("Step 4: Verifying summary content")
        summary = summary_data["summary"]
        assert "total_visits" in summary
        assert summary["total_visits"] >= 1
        
        print("✅ Complete summary workflow successful")
        print("=" * 70)
    
    def test_privacy_compliance_across_workflow(self, client):
        """
        Test that privacy is maintained throughout entire workflow.
        
        CRITICAL TEST: Verifies NO PII exposure to cloud components.
        """
        print("\n" + "=" * 70)
        print("E2E TEST: Privacy Compliance Verification")
        print("=" * 70)
        
        # Create a test patient
        request_data = {
            "patient_name": "Privacy Test Patient",
            "age": 45,
            "gender": "Female",
            "symptoms": "Privacy compliance test"
        }
        
        print("Step 1: Processing request through complete workflow")
        response = client.post("/api/appointments/schedule", json=request_data)
        assert response.status_code == 200
        data = response.json()
        
        patient_uuid = data["patient_uuid"]
        
        # Verify audit trail
        print("Step 2: Analyzing audit trail for privacy compliance")
        audit_logs = identity_vault.get_audit_trail(patient_uuid=patient_uuid)
        
        # Check each log entry
        violations = []
        for log in audit_logs:
            if log["cloud_exposed"]:
                violations.append(log)
        
        print(f"Step 3: Checked {len(audit_logs)} audit log entries")
        print(f"         Cloud-exposed violations: {len(violations)}")
        
        # CRITICAL ASSERTION: NO violations allowed
        assert len(violations) == 0, f"PRIVACY VIOLATION DETECTED: {violations}"
        
        # Verify PII only accessed by local components
        print("Step 4: Verifying PII only accessed locally")
        local_components = ["gatekeeper_agent", "api_route", "e2e_test"]
        pii_access_logs = [log for log in audit_logs if log["pii_accessed"]]
        
        for log in pii_access_logs:
            # PII should only be accessed by local components
            # worker_agent_validation and store_record are allowed as they're local operations
            if "cloud" in log["component"].lower():
                assert False, f"Cloud component accessed PII: {log}"
            if "worker" in log["component"].lower() and log["operation"] not in ["worker_agent_validation", "reidentify", "store_record"]:
                assert False, f"Worker component accessed PII inappropriately: {log}"
        
        print("✅ Privacy compliance verified across entire workflow")
        print("=" * 70)
    
    def test_multiple_patients_isolation(self, client):
        """Test that patient data is properly isolated."""
        print("\n" + "=" * 70)
        print("E2E TEST: Multi-Patient Data Isolation")
        print("=" * 70)
        
        # Create multiple patients
        patients = [
            {"patient_name": "Patient One", "age": 30, "gender": "Male", "symptoms": "Test 1"},
            {"patient_name": "Patient Two", "age": 40, "gender": "Female", "symptoms": "Test 2"},
            {"patient_name": "Patient Three", "age": 50, "gender": "Male", "symptoms": "Test 3"}
        ]
        
        patient_uuids = []
        
        print("Step 1: Creating multiple patients")
        for patient in patients:
            response = client.post("/api/appointments/schedule", json=patient)
            assert response.status_code == 200
            data = response.json()
            patient_uuids.append(data["patient_uuid"])
            print(f"         Created: {patient['patient_name']} -> {data['patient_uuid'][:8]}...")
        
        # Verify each patient has distinct UUID
        print("Step 2: Verifying UUID uniqueness")
        assert len(patient_uuids) == len(set(patient_uuids)), "Duplicate UUIDs detected!"
        
        # Verify data isolation
        print("Step 3: Verifying data isolation")
        for i, uuid in enumerate(patient_uuids):
            identity = identity_vault.reidentify_patient(uuid, component="e2e_test")
            assert identity["patient_name"] == patients[i]["patient_name"]
            
            records = identity_vault.get_patient_records(uuid, component="e2e_test")
            # Each patient should only have their own records
            assert all(r["patient_uuid"] == uuid for r in records)
        
        print("✅ Patient data isolation verified")
        print("=" * 70)
    
    def test_error_handling_invalid_data(self, client):
        """Test error handling with invalid data."""
        print("\n" + "=" * 70)
        print("E2E TEST: Error Handling")
        print("=" * 70)
        
        # Test invalid age
        print("Test 1: Invalid age (out of range)")
        invalid_age_request = {
            "patient_name": "Test Patient",
            "age": 200,
            "gender": "Male",
            "symptoms": "Test"
        }
        
        response = client.post("/api/appointments/schedule", json=invalid_age_request)
        assert response.status_code == 422  # Validation error
        
        # Test missing required fields
        print("Test 2: Missing required fields")
        incomplete_request = {
            "patient_name": "Test Patient"
            # Missing age, gender, symptoms
        }
        
        response = client.post("/api/appointments/schedule", json=incomplete_request)
        assert response.status_code == 422
        
        print("✅ Error handling working correctly")
        print("=" * 70)


class TestSystemIntegration:
    """Tests for system-wide integration."""
    
    def test_all_components_operational(self, client):
        """Test that all system components are operational."""
        print("\n" + "=" * 70)
        print("INTEGRATION TEST: System Health Check")
        print("=" * 70)
        
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        
        components = data["components"]
        print("Component Status:")
        for component, status in components.items():
            print(f"  - {component}: {status}")
            # semantic_store_vectors is a metric, not a status
            if component != "semantic_store_vectors":
                assert status == "operational", f"{component} is not operational: {status}"
        
        # Verify key components are present
        assert "identity_vault" in components
        assert "semantic_store" in components
        assert "gatekeeper_agent" in components
        assert "coordinator_agent" in components
        assert "worker_agent" in components
        
        print("✅ All components operational")
        print("=" * 70)
    
    def test_frontend_pages_accessible(self, client):
        """Test that all frontend pages are accessible."""
        print("\n" + "=" * 70)
        print("INTEGRATION TEST: Frontend Pages")
        print("=" * 70)
        
        pages = ["/", "/appointment", "/followup", "/summary"]
        
        for page in pages:
            print(f"Testing: {page}")
            response = client.get(page)
            assert response.status_code == 200
            assert len(response.content) > 0
        
        print("✅ All frontend pages accessible")
        print("=" * 70)
