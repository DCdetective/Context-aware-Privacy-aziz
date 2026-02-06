"""
Tests for Prompt 3: Privacy Compliance & Event Logging.

Covers:
1. Privacy compliance – no PII reaches mock cloud LLM / Pinecone
2. Privacy event logging – all transformations logged with timestamps
"""

import pytest
import os

os.environ.setdefault("TESTING_MODE", "true")
os.environ.setdefault("GROQ_API_KEY", "test")
os.environ.setdefault("PINECONE_API_KEY", "test")
os.environ.setdefault("PINECONE_ENVIRONMENT", "test")

from agents.gatekeeper import Gatekeeper, GatekeeperAgent, _age_to_bucket


@pytest.fixture
def gk():
    """Gatekeeper with no LLM (regex fallback)."""
    return Gatekeeper(local_llm_config=None)


@pytest.fixture
def gk_with_patient(gk):
    """Gatekeeper with a registered patient."""
    gk.register_patient("uuid-123", "Aziz Ahmed", "Patient_ABC")
    return gk


# ── 1. Privacy Compliance Tests ───────────────────────────────────────

class TestPrivacyCompliance:
    def test_no_pii_in_cloud_output(self, gk_with_patient):
        """Verify NO PII reaches mock cloud LLM."""
        text = "Aziz Ahmed, 21 years old, male, lives at 123 Main St. Phone: 555-123-4567."
        result = gk_with_patient.anonymize_text(text, patient_uuid="uuid-123")
        out = result["anonymized_text"]

        # Real name must not be present
        assert "Aziz" not in out
        assert "Ahmed" not in out
        # Exact age must not be present
        assert "21 years old" not in out
        # Phone must not be present
        assert "555-123-4567" not in out
        # Address must not be present
        assert "123 Main St" not in out

    def test_no_pii_in_pinecone_storage(self, gk_with_patient):
        """Verify NO PII in data sent to Pinecone (via process_for_storage)."""
        text = "Aziz Ahmed, 30 years old, call at 555-999-8888"
        result = gk_with_patient.process_for_storage(text, patient_uuid="uuid-123")
        out = result["anonymized_text"]
        assert "Aziz" not in out
        assert "555-999-8888" not in out

    def test_various_pii_combinations(self, gk_with_patient):
        """Test with various PII combinations."""
        texts = [
            "Aziz Ahmed needs an appointment",
            "Aziz Ahmed, 21 years old, has fever",
            "Call Aziz Ahmed at 555-111-2222",
            "Aziz Ahmed lives at 456 Oak Ave, Apt 2C",
        ]
        for text in texts:
            result = gk_with_patient.anonymize_text(text, patient_uuid="uuid-123")
            assert "Aziz" not in result["anonymized_text"], f"PII leaked in: {text}"

    def test_cloud_safe_flag(self, gk_with_patient):
        """process_for_cloud should return anonymized result."""
        result = gk_with_patient.process_for_cloud(
            "Aziz Ahmed has chest pain", patient_uuid="uuid-123"
        )
        assert "Aziz" not in result["anonymized_text"]


# ── 2. Test Privacy Event Logging ─────────────────────────────────────

class TestPrivacyEventLogging:
    def test_all_transformations_logged(self, gk_with_patient):
        gk_with_patient.clear_privacy_events()
        gk_with_patient.anonymize_text(
            "Aziz Ahmed, 21 years old, phone 555-123-4567",
            patient_uuid="uuid-123",
        )
        events = gk_with_patient.get_privacy_events()
        assert len(events) >= 1

        # Flatten all transformations
        all_transforms = []
        for ev in events:
            all_transforms.extend(ev["transformations"])

        types = {t["pii_type"] for t in all_transforms}
        # Should have logged name, age, phone
        assert "name" in types
        assert "age" in types
        assert "phone" in types

    def test_event_timestamps(self, gk_with_patient):
        gk_with_patient.clear_privacy_events()
        gk_with_patient.anonymize_text("Aziz Ahmed has fever", patient_uuid="uuid-123")
        events = gk_with_patient.get_privacy_events()
        assert len(events) >= 1
        for event in events:
            assert "timestamp" in event
            assert event["timestamp"] is not None
            # ISO 8601 format should contain 'T'
            assert "T" in event["timestamp"]

    def test_audit_trail_complete(self, gk_with_patient):
        """Multiple anonymizations should all be logged."""
        gk_with_patient.clear_privacy_events()
        gk_with_patient.anonymize_text("Aziz Ahmed has fever", patient_uuid="uuid-123")
        gk_with_patient.anonymize_text("Aziz Ahmed has cough", patient_uuid="uuid-123")
        events = gk_with_patient.get_privacy_events()
        assert len(events) >= 2

    def test_event_type_field(self, gk_with_patient):
        gk_with_patient.clear_privacy_events()
        gk_with_patient.anonymize_text("Aziz Ahmed, 21 years old", patient_uuid="uuid-123")
        events = gk_with_patient.get_privacy_events()
        for event in events:
            assert event["event_type"] == "privacy_transformation"

    def test_event_patient_uuid(self, gk_with_patient):
        gk_with_patient.clear_privacy_events()
        gk_with_patient.anonymize_text("Aziz Ahmed has fever", patient_uuid="uuid-123")
        events = gk_with_patient.get_privacy_events()
        assert events[0]["patient_uuid"] == "uuid-123"

    def test_transformation_action_field(self, gk_with_patient):
        gk_with_patient.clear_privacy_events()
        gk_with_patient.anonymize_text("Aziz Ahmed, 21 years old", patient_uuid="uuid-123")
        events = gk_with_patient.get_privacy_events()
        for event in events:
            for t in event["transformations"]:
                assert t["action"] == "anonymized"

    def test_clear_events(self, gk_with_patient):
        gk_with_patient.anonymize_text("Aziz Ahmed has fever", patient_uuid="uuid-123")
        assert len(gk_with_patient.get_privacy_events()) > 0
        gk_with_patient.clear_privacy_events()
        assert len(gk_with_patient.get_privacy_events()) == 0


# ── 3. Legacy GatekeeperAgent compatibility ───────────────────────────

class TestLegacyGatekeeperAgent:
    def test_age_group_conversion(self):
        agent = GatekeeperAgent()
        assert agent._convert_age_to_group(10) == "child"
        assert agent._convert_age_to_group(15) == "teenager"
        assert agent._convert_age_to_group(21) == "early 20s"
        assert agent._convert_age_to_group(30) == "late 20s to early 30s"
        assert agent._convert_age_to_group(45) == "middle-aged"
        assert agent._convert_age_to_group(60) == "senior"
        assert agent._convert_age_to_group(70) == "elderly"
        assert agent._convert_age_to_group(None) == "Unknown"

    def test_privacy_report_generation(self):
        agent = GatekeeperAgent()
        pii_data = {
            "patient_name": "Aziz Ahmed",
            "age": 21,
            "gender": "Male",
            "medical_info": "fever and cough",
        }
        semantic_context = {"symptom_category": "respiratory", "urgency_level": "routine"}
        report = agent.create_privacy_report(pii_data, "12345678", semantic_context)

        assert report["cloud_safe"] is True
        assert report["pii_removed"] >= 2
        assert len(report["transformations"]) >= 3

        name_t = next(t for t in report["transformations"] if t["field"] == "Patient Name")
        assert name_t["original"] == "Aziz Ahmed"
        assert "Patient_" in name_t["transformed"]

        age_t = next(t for t in report["transformations"] if t["field"] == "Age")
        assert age_t["original"] == "21"
        assert age_t["transformed"] == "early 20s"

    def test_fallback_semantic_extraction(self):
        agent = GatekeeperAgent()
        sem = agent._fallback_semantic_extraction("Severe chest pain")
        assert sem["symptom_category"] == "cardiac"
        assert sem["urgency_level"] == "emergency"
        assert sem["requires_specialist"] is True
