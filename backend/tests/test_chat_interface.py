"""
Chat Interface Tests (Prompt 10)

Tests the unified chat endpoint and session management:
- Chat endpoint response format
- Appointment via chat
- Follow-up via chat
- Summary via chat
- Privacy events in response
- Session persistence across turns
- Intent switching
- Error handling
"""

import pytest
from fastapi.testclient import TestClient


class TestChatEndpoint:
    """Test unified chat endpoint."""

    def test_chat_endpoint_exists(self, client):
        """Test that the chat endpoint is accessible."""
        response = client.post(
            "/api/chat/message",
            json={"message": "Hello"}
        )
        assert response.status_code == 200

    def test_chat_response_format(self, client):
        """Test chat response has expected fields."""
        response = client.post(
            "/api/chat/message",
            json={"message": "Hello, what can you do?"}
        )
        assert response.status_code == 200
        data = response.json()

        # Required fields
        assert "success" in data
        assert "message" in data
        assert "intent" in data
        assert "privacy_safe" in data
        assert "result" in data

    def test_appointment_via_chat(self, client):
        """Test appointment booking through chat endpoint."""
        from database.identity_vault import identity_vault
        identity_vault.pseudonymize_patient(
            patient_name="Chat Appointment",
            age=30,
            gender="Male",
            component="test"
        )

        response = client.post(
            "/api/chat/message",
            json={"message": "I'm Chat Appointment, 30, male. I need to schedule an appointment for chest pain."}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["intent"] in ("appointment", "confirmation_required")

    def test_followup_via_chat(self, client):
        """Test follow-up through chat endpoint."""
        response = client.post(
            "/api/chat/message",
            json={"message": "I need to schedule a follow-up for my previous visit."}
        )
        assert response.status_code in [200, 400]

    def test_summary_via_chat(self, client):
        """Test summary request through chat endpoint."""
        response = client.post(
            "/api/chat/message",
            json={"message": "Can you generate a medical summary?"}
        )
        assert response.status_code in [200, 400]

    def test_general_query_via_chat(self, client):
        """Test general query through chat endpoint."""
        response = client.post(
            "/api/chat/message",
            json={"message": "What services do you provide?"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["intent"] == "general"


class TestPrivacyEvents:
    """Test privacy events in chat responses."""

    def test_privacy_safe_flag(self, client):
        """Test that all responses include privacy_safe flag."""
        messages = [
            "Hello",
            "I need an appointment",
            "What services do you provide?"
        ]
        for msg in messages:
            response = client.post("/api/chat/message", json={"message": msg})
            if response.status_code == 200:
                assert response.json()["privacy_safe"] is True

    def test_privacy_report_accessible(self, client):
        """Test privacy report endpoint is accessible."""
        response = client.get("/api/chat/privacy-report")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "report" in data
        assert data["report"]["privacy_compliant"] is True

    def test_no_pii_leaked_in_response(self, client):
        """Test that PII is not leaked to cloud components."""
        from database.identity_vault import identity_vault
        identity_vault.pseudonymize_patient(
            patient_name="PII Leak Test",
            age=28,
            gender="Female",
            component="test"
        )

        response = client.post(
            "/api/chat/message",
            json={"message": "I'm PII Leak Test, 28, female. I need an appointment."}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["privacy_safe"] is True


class TestSessionPersistence:
    """Test session persistence across turns."""

    def test_session_id_returned(self, client):
        """Test that a session ID is returned in the response."""
        response = client.post(
            "/api/chat/message",
            json={"message": "Hello"}
        )
        assert response.status_code == 200
        data = response.json()
        # Session ID may be in result or at top level
        session_id = data.get("session_id") or data.get("result", {}).get("session_id")
        assert session_id is not None

    def test_multiple_turns(self, client):
        """Test multiple turns work correctly."""
        # Turn 1
        r1 = client.post("/api/chat/message", json={"message": "Hello"})
        assert r1.status_code == 200

        # Turn 2
        r2 = client.post("/api/chat/message", json={"message": "I need an appointment"})
        assert r2.status_code in [200, 400]

        # Turn 3
        r3 = client.post("/api/chat/message", json={"message": "What services do you have?"})
        assert r3.status_code == 200


class TestIntentSwitching:
    """Test smooth transitions between different intents."""

    def test_appointment_then_general(self, client):
        """Test switching from appointment to general query."""
        r1 = client.post(
            "/api/chat/message",
            json={"message": "I need an appointment for headache"}
        )
        assert r1.status_code in [200, 400]

        r2 = client.post(
            "/api/chat/message",
            json={"message": "What services do you provide?"}
        )
        assert r2.status_code == 200

    def test_general_then_appointment(self, client):
        """Test switching from general to appointment."""
        r1 = client.post(
            "/api/chat/message",
            json={"message": "Hello, what can you do?"}
        )
        assert r1.status_code == 200
        assert r1.json()["intent"] == "general"

        r2 = client.post(
            "/api/chat/message",
            json={"message": "I'm Test Patient, 25, male. Book an appointment."}
        )
        assert r2.status_code in [200, 400]


class TestErrorHandling:
    """Test error handling in chat interface."""

    def test_empty_message(self, client):
        """Test handling of empty message."""
        response = client.post(
            "/api/chat/message",
            json={"message": ""}
        )
        assert response.status_code in [200, 400]

    def test_whitespace_only_message(self, client):
        """Test handling of whitespace-only message."""
        response = client.post(
            "/api/chat/message",
            json={"message": "   "}
        )
        assert response.status_code in [200, 400]

    def test_invalid_session_id(self, client):
        """Test handling of invalid session ID."""
        response = client.post(
            "/api/chat/message",
            json={"message": "Hello", "session_id": "invalid-session-id-12345"}
        )
        # Should handle gracefully (create new session)
        assert response.status_code in [200, 400]

    def test_missing_content_type(self, client):
        """Test handling of missing content type."""
        response = client.post(
            "/api/chat/message",
            content=b'{"message": "Hello"}',
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code in [200, 400]
