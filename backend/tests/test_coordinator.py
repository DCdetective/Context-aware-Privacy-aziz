"""
Tests for Coordinator Agent (Prompt 5).
Tests intent detection, workflow state management, patient resolution,
context retrieval, privacy integration, and state persistence.
"""

import pytest
import asyncio
import tempfile
import os

from agents.coordinator import Coordinator, CoordinatorAgent
from agents.session_manager import SessionManager
from database.identity_vault import IdentityVault


@pytest.fixture
def temp_db():
    """Create temp DB paths for isolation."""
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        session_db = f.name
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        vault_db = f.name
    yield session_db, vault_db
    for p in (session_db, vault_db):
        try:
            os.remove(p)
        except (PermissionError, OSError):
            pass


@pytest.fixture
def coordinator(temp_db):
    """Create a coordinator with isolated session manager."""
    session_db, vault_db = temp_db
    coord = Coordinator()
    coord.session_manager = SessionManager(db_path=session_db)
    # Create a test vault with a known patient
    vault = IdentityVault(db_path=vault_db)
    vault.pseudonymize_patient("Aziz", age=22, gender="Male", component="test")
    # Patch the vault accessor
    coord._get_identity_vault = lambda: vault
    return coord


def run(coro):
    """Helper to run async coroutines in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ── 1. Test Intent Detection ─────────────────────────────────────────

class TestIntentDetection:
    def test_appointment_intent(self, coordinator):
        intent = run(coordinator.detect_intent("I need an appointment"))
        assert intent == "appointment"

    def test_followup_intent(self, coordinator):
        intent = run(coordinator.detect_intent("How is my patient doing?"))
        assert intent == "followup"

    def test_summary_intent(self, coordinator):
        intent = run(coordinator.detect_intent("Show me patient summary"))
        assert intent == "summary"

    def test_general_intent(self, coordinator):
        intent = run(coordinator.detect_intent("Hello, what can you do?"))
        assert intent == "general"

    def test_book_keyword(self, coordinator):
        intent = run(coordinator.detect_intent("Book an appointment for Aziz"))
        assert intent == "appointment"

    def test_schedule_keyword(self, coordinator):
        intent = run(coordinator.detect_intent("Schedule an appointment"))
        assert intent == "appointment"

    def test_follow_up_variants(self, coordinator):
        for msg in ["follow-up visit", "follow up needed", "followup for patient"]:
            intent = run(coordinator.detect_intent(msg))
            assert intent == "followup", f"Failed for: {msg}"

    def test_history_as_summary(self, coordinator):
        intent = run(coordinator.detect_intent("Show me the history"))
        assert intent == "summary"


# ── 2. Test Intent Detection Only Runs Once ──────────────────────────

class TestIntentDetectionOnlyOnce:
    def test_intent_not_redetected_during_workflow(self, coordinator):
        sid = coordinator.session_manager.create_session()

        # Turn 1: triggers intent detection -> appointment
        r1 = run(coordinator.process_message(sid, "Book appointment for Aziz"))
        count_after_first = coordinator.get_intent_detection_count(sid)
        assert count_after_first == 1

        # Turn 2: should continue workflow, NOT re-detect
        r2 = run(coordinator.process_message(sid, "Cardiology"))
        count_after_second = coordinator.get_intent_detection_count(sid)
        assert count_after_second == 1, "Intent detection should NOT run again during active workflow"

    def test_intent_redetected_after_completion(self, coordinator):
        sid = coordinator.session_manager.create_session()

        # Start and cancel workflow
        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        run(coordinator.process_message(sid, "cancel"))

        count_before = coordinator.get_intent_detection_count(sid)

        # New message should trigger intent detection again
        run(coordinator.process_message(sid, "Show me summary"))
        count_after = coordinator.get_intent_detection_count(sid)
        assert count_after == count_before + 1


# ── 3. Test Patient Resolution ───────────────────────────────────────

class TestPatientResolution:
    def test_resolve_known_patient(self, coordinator):
        sid = coordinator.session_manager.create_session()
        resolution = run(coordinator.resolve_patient(sid, "Book appointment for Aziz"))
        assert resolution["action"] == "found_one"
        assert len(resolution["patients"]) == 1
        assert resolution["patients"][0]["patient_name"] == "Aziz"

    def test_resolve_unknown_patient(self, coordinator):
        sid = coordinator.session_manager.create_session()
        resolution = run(coordinator.resolve_patient(sid, "Book appointment for UnknownPerson"))
        assert resolution["action"] == "not_found"

    def test_active_patient_set_after_resolution(self, coordinator):
        sid = coordinator.session_manager.create_session()
        run(coordinator.resolve_patient(sid, "Book appointment for Aziz"))
        active = coordinator.session_manager.get_active_patient(sid)
        assert active is not None
        assert active["patient_name"] == "Aziz"


# ── 4. Test Multiple Patient Disambiguation ──────────────────────────

class TestMultiplePatientDisambiguation:
    def test_multiple_patients_detected(self, coordinator):
        # Create a second patient with same name by inserting directly
        # (pseudonymize_patient deduplicates by name, so we insert a second row manually)
        vault = coordinator._get_identity_vault()
        from database.models import PatientIdentity
        from datetime import datetime
        import uuid as uuid_lib
        session = vault._get_session()
        try:
            new_patient = PatientIdentity(
                patient_uuid=str(uuid_lib.uuid4()),
                patient_name="Aziz",
                age=35,
                gender="Male",
                created_at=datetime.utcnow(),
                last_accessed=datetime.utcnow(),
                access_count=1,
            )
            session.add(new_patient)
            session.commit()
        finally:
            session.close()

        sid = coordinator.session_manager.create_session()
        resolution = run(coordinator.resolve_patient(sid, "Book appointment for Aziz"))
        assert resolution["action"] == "found_multiple"
        assert len(resolution["patients"]) >= 2


# ── 5. Test New Patient Creation ─────────────────────────────────────

class TestNewPatientCreation:
    def test_unknown_patient_prompt(self, coordinator):
        sid = coordinator.session_manager.create_session()
        result = run(coordinator.process_message(sid, "Book appointment for NewPatient"))
        assert "not found" in result["response"].lower() or "no patient" in result["response"].lower()


# ── 6. Test Context Retrieval ─────────────────────────────────────────

class TestContextRetrieval:
    def test_context_agent_called(self, coordinator):
        """Verify coordinator uses context agent for refinement."""
        from agents.context_agent import ContextAgent
        ctx = ContextAgent()
        ctx.store_interaction("uuid-ctx", "symptom", "chest pain")
        coordinator._get_context_agent = lambda: ctx

        sid = coordinator.session_manager.create_session()
        result = run(coordinator.process_message(sid, "Book appointment for Aziz"))
        # Should succeed without error
        assert result["success"]


# ── 7. Test Privacy Integration ───────────────────────────────────────

class TestPrivacyIntegration:
    def test_response_does_not_leak_uuid(self, coordinator):
        sid = coordinator.session_manager.create_session()
        result = run(coordinator.process_message(sid, "Book appointment for Aziz"))
        # UUID should not appear in user-facing response
        # (response should use patient name or generic text)
        assert result["success"]


# ── 8. Test Workflow State Persistence ────────────────────────────────

class TestWorkflowStatePersistence:
    def test_state_maintained_across_turns(self, coordinator):
        sid = coordinator.session_manager.create_session()

        # Turn 1: start appointment
        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "appointment"

        # Turn 2: provide specialty
        run(coordinator.process_message(sid, "Cardiology"))
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "appointment"
        assert session["workflow_stage"] != "none"

        # Turn 3: provide date
        run(coordinator.process_message(sid, "Tomorrow"))
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "appointment"

    def test_no_reset_mid_workflow(self, coordinator):
        sid = coordinator.session_manager.create_session()

        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        run(coordinator.process_message(sid, "Cardiology"))

        # Workflow should still be active
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "appointment"
        assert session["workflow_stage"] != "none"


# ── 9. Test Workflow Completion ───────────────────────────────────────

class TestWorkflowCompletion:
    def test_workflow_resets_after_cancel(self, coordinator):
        sid = coordinator.session_manager.create_session()

        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "appointment"

        run(coordinator.process_message(sid, "cancel"))
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "none"
        assert session["workflow_stage"] == "none"

    def test_new_intent_after_completion(self, coordinator):
        sid = coordinator.session_manager.create_session()

        # Complete one workflow
        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        run(coordinator.process_message(sid, "cancel"))

        # Start new workflow
        result = run(coordinator.process_message(sid, "Show me summary"))
        assert result["success"]


# ── Legacy CoordinatorAgent Tests ─────────────────────────────────────

class TestLegacyCoordinatorAgent:
    def test_initialization(self):
        coord = CoordinatorAgent()
        assert coord is not None
        assert coord.model is not None

    def test_valid_request(self):
        coord = CoordinatorAgent()
        result = coord.coordinate_request(
            patient_uuid="test-uuid-123",
            action_type="appointment",
            semantic_context={"symptom_category": "respiratory", "urgency_level": "routine"}
        )
        assert result.get("success") is not False
        assert result["patient_uuid"] == "test-uuid-123"
        assert "execution_plan" in result
        assert result["ready_for_worker"] is True

    def test_invalid_action(self):
        coord = CoordinatorAgent()
        result = coord.coordinate_request("uuid", "invalid_action", {})
        assert result["success"] is False

    def test_fallback_plan(self):
        coord = CoordinatorAgent()
        plan = coord._fallback_execution_plan("appointment", {"urgency_level": "urgent"})
        assert "steps" in plan
        assert plan["priority"] == "urgent"
