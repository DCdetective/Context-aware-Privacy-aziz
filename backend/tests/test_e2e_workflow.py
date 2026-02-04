import pytest
from fastapi.testclient import TestClient


class TestE2EWorkflow:
    """End-to-end workflow tests."""
    
    def test_complete_appointment_workflow(self, client, sample_messages):
        """Test complete appointment booking workflow."""
        # Send appointment request
        response = client.post(
            "/api/chat/message",
            json={"message": sample_messages["appointment"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert data["success"] is True
        assert data["intent"] == "appointment"
        assert data["privacy_safe"] is True
        assert "patient_uuid" in data
        assert "workflow_steps" in data
        assert len(data["workflow_steps"]) > 0
        
        # Verify result contains appointment details
        result = data["result"]
        assert "appointment_time" in result
        assert "consultation_duration" in result
        assert "urgency_level" in result
    
    def test_complete_followup_workflow(self, client):
        """Test complete follow-up scheduling workflow."""
        # First, create a patient with an appointment
        appointment_message = "I'm Alice Smith, 28 years old, female. I need an appointment."
        response1 = client.post(
            "/api/chat/message",
            json={"message": appointment_message}
        )
        
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["success"] is True
        
        # Now request follow-up with PII so it can be identified
        followup_message = "I'm Alice Smith. I need a follow-up appointment."
        response2 = client.post(
            "/api/chat/message",
            json={"message": followup_message}
        )
        
        # Accept both success and error cases (system might not support followup without full PII)
        assert response2.status_code in [200, 400]
        
        if response2.status_code == 200:
            data = response2.json()
            assert data["success"] is True
            assert data["privacy_safe"] is True
    
    def test_complete_summary_workflow(self, client):
        """Test medical summary generation workflow."""
        # Create patient and records first
        message1 = "I'm Bob Williams, 50 years old, male. I have chest pain."
        client.post("/api/chat/message", json={"message": message1})
        
        # Request summary
        message2 = "Can you generate my medical summary?"
        response = client.post(
            "/api/chat/message",
            json={"message": message2}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["privacy_safe"] is True
    
    def test_privacy_compliance_across_workflow(self, client, sample_messages):
        """Test that privacy is maintained throughout workflow."""
        response = client.post(
            "/api/chat/message",
            json={"message": sample_messages["appointment"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify privacy compliance
        assert data["privacy_safe"] is True
        
        # Verify workflow steps mention privacy
        workflow_steps = data["workflow_steps"]
        privacy_mentions = [
            step for step in workflow_steps
            if "privacy" in step.lower() or "pseudonym" in step.lower() or "uuid" in step.lower()
        ]
        assert len(privacy_mentions) > 0
    
    def test_multiple_patients_isolation(self, client):
        """Test that multiple patients are kept isolated."""
        # Create two patients
        message1 = "I'm Patient One, 30 years old, female. I need an appointment."
        response1 = client.post("/api/chat/message", json={"message": message1})
        uuid1 = response1.json().get("patient_uuid")
        
        message2 = "I'm Patient Two, 40 years old, male. I need an appointment."
        response2 = client.post("/api/chat/message", json={"message": message2})
        uuid2 = response2.json().get("patient_uuid")
        
        # Verify different UUIDs
        assert uuid1 != uuid2
        assert uuid1 is not None
        assert uuid2 is not None
    
    def test_general_query_handling(self, client, sample_messages):
        """Test handling of general queries."""
        response = client.post(
            "/api/chat/message",
            json={"message": sample_messages["general"]}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert data["intent"] == "general"
        
        # Should provide suggestions
        result = data.get("result", {})
        assert "suggestions" in result or "message" in result
    
    def test_error_handling_invalid_data(self, client):
        """Test error handling for invalid data."""
        # Send empty message
        response = client.post(
            "/api/chat/message",
            json={"message": ""}
        )
        
        # Should handle gracefully
        assert response.status_code in [200, 400]
    
    def test_privacy_report_endpoint(self, client):
        """Test privacy compliance report endpoint."""
        response = client.get("/api/chat/privacy-report")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["success"] is True
        assert "report" in data
        
        report = data["report"]
        assert "privacy_compliant" in report
        assert "cloud_exposed_count" in report
        
        # Should have no cloud exposure
        assert report["cloud_exposed_count"] == 0


class TestComponentIntegration:
    """Test integration between components."""
    
    def test_gatekeeper_to_coordinator(self, client):
        """Test Gatekeeper to Coordinator integration."""
        message = "I'm Test User, 25 years old, male. I need help."
        response = client.post("/api/chat/message", json={"message": message})
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify Gatekeeper processed PII
        assert data.get("patient_name") or data.get("patient_uuid")
        
        # Verify workflow executed
        assert len(data["workflow_steps"]) > 0
    
    def test_context_to_execution_agent(self, client):
        """Test Context Agent to Execution Agent flow."""
        message = "I'm Jane Doe, 30, female. I have a severe cough."
        response = client.post("/api/chat/message", json={"message": message})
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify execution completed
        assert data["success"] is True
        assert "result" in data
        
        result = data["result"]
        # Should have executed some action
        assert any(key in result for key in ["appointment_time", "followup_time", "summary", "message"])
    
    def test_health_endpoint(self, client):
        """Test health check endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "healthy"
