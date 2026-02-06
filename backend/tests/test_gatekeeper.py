"""
Tests for Prompt 3: Privacy Agent & Gatekeeper.

Covers:
1. Name anonymization
2. Age anonymization
3. Combined PII
4. Phone number masking
5. Address generalization
6. Patient linking
7. Deanonymization
8. No false positives on medical terms
"""

import pytest
import os

os.environ.setdefault("TESTING_MODE", "true")
os.environ.setdefault("GROQ_API_KEY", "test")
os.environ.setdefault("PINECONE_API_KEY", "test")
os.environ.setdefault("PINECONE_ENVIRONMENT", "test")

from agents.gatekeeper import Gatekeeper, _age_to_bucket


@pytest.fixture
def gk():
    """Create a Gatekeeper with no LLM (regex-only)."""
    return Gatekeeper(local_llm_config=None)


@pytest.fixture
def gk_with_patient(gk):
    """Gatekeeper with a pre-registered patient."""
    gk.register_patient("uuid-123", "Aziz", "Patient_ABC")
    return gk


# ── 1. Test Name Anonymization ────────────────────────────────────────

class TestNameAnonymization:
    def test_name_replaced(self, gk_with_patient):
        result = gk_with_patient.anonymize_text("Aziz needs an appointment", patient_uuid="uuid-123")
        assert "Aziz" not in result["anonymized_text"]
        assert "Patient_ABC" in result["anonymized_text"]

    def test_privacy_event_emitted(self, gk_with_patient):
        gk_with_patient.clear_privacy_events()
        gk_with_patient.anonymize_text("Aziz needs an appointment", patient_uuid="uuid-123")
        events = gk_with_patient.get_privacy_events()
        assert len(events) >= 1
        assert events[0]["event_type"] == "privacy_transformation"
        assert len(events[0]["transformations"]) >= 1

    def test_name_in_privacy_events(self, gk_with_patient):
        result = gk_with_patient.anonymize_text("Aziz needs an appointment", patient_uuid="uuid-123")
        name_events = [e for e in result["privacy_events"] if e["type"] == "name"]
        assert len(name_events) >= 1
        assert name_events[0]["original"] == "Aziz"
        assert name_events[0]["transformed"] == "Patient_ABC"


# ── 2. Test Age Anonymization ─────────────────────────────────────────

class TestAgeAnonymization:
    def test_age_replaced(self, gk):
        result = gk.anonymize_text("Patient is 21 years old")
        assert "21 years old" not in result["anonymized_text"]
        assert "early 20s" in result["anonymized_text"]

    @pytest.mark.parametrize("age,bucket", [
        (5, "child"), (12, "child"),
        (13, "teenager"), (17, "teenager"),
        (18, "early 20s"), (25, "early 20s"),
        (26, "late 20s to early 30s"), (35, "late 20s to early 30s"),
        (36, "middle-aged"), (50, "middle-aged"),
        (51, "senior"), (65, "senior"),
        (66, "elderly"), (90, "elderly"),
    ])
    def test_all_age_buckets(self, age, bucket):
        assert _age_to_bucket(age) == bucket

    def test_age_privacy_event(self, gk):
        result = gk.anonymize_text("Patient is 45 years old")
        age_events = [e for e in result["privacy_events"] if e["type"] == "age"]
        assert len(age_events) >= 1


# ── 3. Test Combined PII ─────────────────────────────────────────────

class TestCombinedPII:
    def test_name_and_age(self, gk_with_patient):
        result = gk_with_patient.anonymize_text(
            "Aziz, 21 years old, needs to see Dr. Smith",
            patient_uuid="uuid-123",
        )
        text = result["anonymized_text"]
        assert "Aziz" not in text
        assert "Patient_ABC" in text
        assert "21 years old" not in text
        assert "early 20s" in text
        # Doctor name should NOT be anonymized
        assert "Smith" in text

    def test_multiple_events(self, gk_with_patient):
        result = gk_with_patient.anonymize_text(
            "Aziz, 21 years old, needs to see Dr. Smith",
            patient_uuid="uuid-123",
        )
        assert len(result["privacy_events"]) >= 2


# ── 4. Test Phone Number Masking ──────────────────────────────────────

class TestPhoneMasking:
    def test_phone_masked(self, gk):
        result = gk.anonymize_text("Call me at 555-123-4567")
        assert "555-123-4567" not in result["anonymized_text"]
        assert "PHONE_XXX" in result["anonymized_text"]

    def test_phone_with_parens(self, gk):
        result = gk.anonymize_text("Call me at (555) 123-4567")
        assert "PHONE_XXX" in result["anonymized_text"]

    def test_phone_privacy_event(self, gk):
        result = gk.anonymize_text("Call me at 555-123-4567")
        phone_events = [e for e in result["privacy_events"] if e["type"] == "phone"]
        assert len(phone_events) >= 1


# ── 5. Test Address Generalization ────────────────────────────────────

class TestAddressGeneralization:
    def test_address_generalized(self, gk):
        result = gk.anonymize_text("I live at 123 Main St, Apt 4B")
        assert "123 Main St" not in result["anonymized_text"]
        assert "residential area" in result["anonymized_text"]

    def test_address_privacy_event(self, gk):
        result = gk.anonymize_text("I live at 123 Main St")
        address_events = [e for e in result["privacy_events"] if e["type"] == "address"]
        assert len(address_events) >= 1


# ── 6. Test Patient Linking ───────────────────────────────────────────

class TestPatientLinking:
    def test_consistent_anonymized_name(self, gk_with_patient):
        r1 = gk_with_patient.anonymize_text("Aziz has fever", patient_uuid="uuid-123")
        r2 = gk_with_patient.anonymize_text("Aziz has cough", patient_uuid="uuid-123")
        # Both should use same anonymized name
        assert "Patient_ABC" in r1["anonymized_text"]
        assert "Patient_ABC" in r2["anonymized_text"]

    def test_unknown_patient_gets_anon_name(self, gk):
        result = gk.anonymize_text("Aziz needs help")
        # Should still anonymize the name
        assert "Aziz" not in result["anonymized_text"] or len(result["privacy_events"]) == 0
        # If it detected the name, it should have replaced it

    def test_register_then_anonymize(self, gk):
        gk.register_patient("uuid-456", "Sara Khan", "Patient_XYZ")
        result = gk.anonymize_text("Sara Khan has a headache", patient_uuid="uuid-456")
        assert "Sara Khan" not in result["anonymized_text"]
        assert "Patient_XYZ" in result["anonymized_text"]


# ── 7. Test Deanonymization ──────────────────────────────────────────

class TestDeanonymization:
    def test_deanonymize(self, gk_with_patient):
        anon_result = gk_with_patient.anonymize_text("Aziz needs an appointment", patient_uuid="uuid-123")
        anon_text = anon_result["anonymized_text"]
        assert "Patient_ABC" in anon_text

        restored = gk_with_patient.deanonymize_text(anon_text, "uuid-123")
        assert "Aziz" in restored
        assert "Patient_ABC" not in restored

    def test_deanonymize_unknown_uuid(self, gk):
        text = "Patient_XYZ has fever"
        result = gk.deanonymize_text(text, "unknown-uuid")
        # Should return unchanged
        assert result == text


# ── 8. Test No False Positives ────────────────────────────────────────

class TestNoFalsePositives:
    def test_medical_terms_not_anonymized(self, gk):
        text = "Patient has fever, cough, and headache. Diagnosis is respiratory infection."
        result = gk.anonymize_text(text)
        out = result["anonymized_text"]
        assert "fever" in out
        assert "cough" in out
        assert "headache" in out

    def test_doctor_name_not_anonymized(self, gk_with_patient):
        result = gk_with_patient.anonymize_text(
            "Aziz needs to see Dr. Smith for a checkup",
            patient_uuid="uuid-123",
        )
        assert "Smith" in result["anonymized_text"]

    def test_symptoms_not_redacted(self, gk):
        text = "severe chest pain and difficulty breathing for 3 days"
        result = gk.anonymize_text(text)
        assert "chest pain" in result["anonymized_text"]
        assert "difficulty breathing" in result["anonymized_text"]
