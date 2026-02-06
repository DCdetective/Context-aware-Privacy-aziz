"""
Tests for Prompt 2: Session State Machine.

Covers:
1. Session creation
2. Session state updates
3. Workflow transitions (valid + invalid)
4. Active patient binding
5. Workflow data collection
6. Pending questions
7. Workflow completion
8. Session reset
9. Session persistence (simulated restart)
"""

import pytest
import os
import tempfile
import uuid

os.environ.setdefault("TESTING_MODE", "true")
os.environ.setdefault("GROQ_API_KEY", "test")
os.environ.setdefault("PINECONE_API_KEY", "test")
os.environ.setdefault("PINECONE_ENVIRONMENT", "test")

from agents.session_manager import SessionManager


@pytest.fixture
def sm(tmp_path):
    """Create a SessionManager with a temp DB."""
    db_path = str(tmp_path / "test_sessions.db")
    manager = SessionManager(db_path=db_path)
    yield manager
    manager.dispose()


@pytest.fixture
def session_id(sm):
    """Create a session and return its ID."""
    return sm.create_session()


# ── 1. Test Session Creation ──────────────────────────────────────────

class TestSessionCreation:
    def test_create_returns_uuid(self, sm):
        sid = sm.create_session()
        assert sid is not None
        assert len(sid) == 36  # UUID format

    def test_initial_state(self, sm, session_id):
        s = sm.get_session(session_id)
        assert s is not None
        assert s["session_id"] == session_id
        assert s["active_patient_id"] is None
        assert s["active_workflow"] == "none"
        assert s["workflow_stage"] == "none"
        assert s["pending_question"] is None
        assert s["workflow_data"] == {}

    def test_created_at_exists(self, sm, session_id):
        s = sm.get_session(session_id)
        assert s["created_at"] is not None
        assert s["updated_at"] is not None

    def test_multiple_sessions(self, sm):
        s1 = sm.create_session()
        s2 = sm.create_session()
        assert s1 != s2
        assert sm.get_session(s1) is not None
        assert sm.get_session(s2) is not None


# ── 2. Test Session State Updates ─────────────────────────────────────

class TestSessionUpdates:
    def test_update_fields(self, sm, session_id):
        result = sm.update_session(session_id, active_workflow="appointment")
        assert result["active_workflow"] == "appointment"

    def test_update_persists(self, sm, session_id):
        sm.update_session(session_id, active_workflow="followup")
        s = sm.get_session(session_id)
        assert s["active_workflow"] == "followup"

    def test_update_nonexistent_raises(self, sm):
        with pytest.raises(ValueError):
            sm.update_session("nonexistent-id", active_workflow="test")

    def test_concurrent_updates(self, sm, session_id):
        sm.update_session(session_id, active_workflow="appointment")
        sm.update_session(session_id, workflow_stage="resolving_patient")
        s = sm.get_session(session_id)
        assert s["active_workflow"] == "appointment"
        assert s["workflow_stage"] == "resolving_patient"


# ── 3. Test Workflow Transitions ──────────────────────────────────────

class TestWorkflowTransitions:
    def test_valid_full_cycle(self, sm, session_id):
        sm.set_workflow(session_id, "appointment", "none")
        sm.advance_workflow_stage(session_id, "resolving_patient")
        sm.advance_workflow_stage(session_id, "collecting_info")
        sm.advance_workflow_stage(session_id, "confirmation")
        sm.advance_workflow_stage(session_id, "executing")
        sm.advance_workflow_stage(session_id, "completed")
        s = sm.get_session(session_id)
        assert s["workflow_stage"] == "completed"

    def test_invalid_transition_raises(self, sm, session_id):
        sm.set_workflow(session_id, "appointment", "none")
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.advance_workflow_stage(session_id, "confirmation")

    def test_invalid_transition_skip_stage(self, sm, session_id):
        sm.set_workflow(session_id, "appointment", "none")
        sm.advance_workflow_stage(session_id, "resolving_patient")
        with pytest.raises(ValueError):
            sm.advance_workflow_stage(session_id, "confirmation")

    def test_set_workflow_validates(self, sm, session_id):
        with pytest.raises(ValueError, match="Invalid workflow"):
            sm.set_workflow(session_id, "invalid_workflow", "none")


# ── 4. Test Active Patient Binding ────────────────────────────────────

class TestActivePatient:
    def test_set_active_patient(self, sm, session_id):
        patient_uuid = str(uuid.uuid4())
        result = sm.set_active_patient(session_id, patient_uuid)
        assert result["active_patient_id"] == patient_uuid

    def test_patient_persists_across_operations(self, sm, session_id):
        patient_uuid = str(uuid.uuid4())
        sm.set_active_patient(session_id, patient_uuid)
        sm.set_workflow(session_id, "appointment", "none")
        s = sm.get_session(session_id)
        assert s["active_patient_id"] == patient_uuid

    def test_update_active_patient(self, sm, session_id):
        p1 = str(uuid.uuid4())
        p2 = str(uuid.uuid4())
        sm.set_active_patient(session_id, p1)
        sm.set_active_patient(session_id, p2)
        s = sm.get_session(session_id)
        assert s["active_patient_id"] == p2

    def test_clear_active_patient(self, sm, session_id):
        sm.set_active_patient(session_id, str(uuid.uuid4()))
        sm.update_session(session_id, active_patient_id=None)
        s = sm.get_session(session_id)
        assert s["active_patient_id"] is None


# ── 5. Test Workflow Data Collection ──────────────────────────────────

class TestWorkflowData:
    def test_add_workflow_data(self, sm, session_id):
        sm.add_workflow_data(session_id, "symptoms", "headache")
        s = sm.get_session(session_id)
        assert s["workflow_data"]["symptoms"] == "headache"

    def test_multiple_data_items(self, sm, session_id):
        sm.add_workflow_data(session_id, "symptoms", "headache")
        sm.add_workflow_data(session_id, "duration", "3 days")
        sm.add_workflow_data(session_id, "severity", "moderate")
        s = sm.get_session(session_id)
        assert len(s["workflow_data"]) == 3
        assert s["workflow_data"]["symptoms"] == "headache"
        assert s["workflow_data"]["duration"] == "3 days"

    def test_nested_data(self, sm, session_id):
        sm.add_workflow_data(session_id, "vitals", {"bp": "120/80", "temp": 98.6})
        s = sm.get_session(session_id)
        assert s["workflow_data"]["vitals"]["bp"] == "120/80"
        assert s["workflow_data"]["vitals"]["temp"] == 98.6


# ── 6. Test Pending Questions ─────────────────────────────────────────

class TestPendingQuestions:
    def test_set_pending_question(self, sm, session_id):
        sm.set_pending_question(session_id, "What are your symptoms?", {"step": 1})
        s = sm.get_session(session_id)
        assert s["pending_question"] is not None
        assert s["pending_question"]["question"] == "What are your symptoms?"
        assert s["pending_question"]["context"]["step"] == 1

    def test_clear_pending_question(self, sm, session_id):
        sm.set_pending_question(session_id, "Question?", {"step": 1})
        sm.clear_pending_question(session_id)
        s = sm.get_session(session_id)
        assert s["pending_question"] is None

    def test_replace_pending_question(self, sm, session_id):
        sm.set_pending_question(session_id, "Q1?", {"step": 1})
        sm.set_pending_question(session_id, "Q2?", {"step": 2})
        s = sm.get_session(session_id)
        assert s["pending_question"]["question"] == "Q2?"
        assert s["pending_question"]["context"]["step"] == 2


# ── 7. Test Workflow Completion ───────────────────────────────────────

class TestWorkflowCompletion:
    def test_complete_resets_workflow(self, sm, session_id):
        sm.set_workflow(session_id, "appointment", "collecting_info")
        sm.add_workflow_data(session_id, "doctor", "Dr. Smith")
        sm.set_pending_question(session_id, "Confirm?", {})
        result = sm.complete_workflow(session_id)
        assert result["active_workflow"] == "none"
        assert result["workflow_stage"] == "none"
        assert result["workflow_data"] == {}
        assert result["pending_question"] is None

    def test_complete_preserves_patient(self, sm, session_id):
        patient_uuid = str(uuid.uuid4())
        sm.set_active_patient(session_id, patient_uuid)
        sm.set_workflow(session_id, "appointment", "executing")
        sm.complete_workflow(session_id)
        s = sm.get_session(session_id)
        assert s["active_patient_id"] == patient_uuid


# ── 8. Test Session Reset ─────────────────────────────────────────────

class TestSessionReset:
    def test_reset_clears_all(self, sm, session_id):
        sm.set_active_patient(session_id, str(uuid.uuid4()))
        sm.set_workflow(session_id, "followup", "collecting_info")
        sm.add_workflow_data(session_id, "key", "value")
        sm.set_pending_question(session_id, "Q?", {"x": 1})

        result = sm.reset_session(session_id)
        assert result["session_id"] == session_id
        assert result["active_patient_id"] is None
        assert result["active_workflow"] == "none"
        assert result["workflow_stage"] == "none"
        assert result["workflow_data"] == {}
        assert result["pending_question"] is None

    def test_reset_keeps_session_id(self, sm, session_id):
        sm.reset_session(session_id)
        s = sm.get_session(session_id)
        assert s is not None
        assert s["session_id"] == session_id


# ── 9. Test Session Persistence ───────────────────────────────────────

class TestSessionPersistence:
    def test_persist_across_restart(self, tmp_path):
        db_path = str(tmp_path / "persist_sessions.db")

        # Create session and add data
        sm1 = SessionManager(db_path=db_path)
        sid = sm1.create_session()
        patient_uuid = str(uuid.uuid4())
        sm1.set_active_patient(sid, patient_uuid)
        sm1.set_workflow(sid, "appointment", "collecting_info")
        sm1.add_workflow_data(sid, "doctor", "Dr. Smith")
        sm1.set_pending_question(sid, "Confirm?", {"step": 3})
        sm1.dispose()

        # "Restart" – create new manager on same DB
        sm2 = SessionManager(db_path=db_path)
        s = sm2.get_session(sid)
        assert s is not None
        assert s["active_patient_id"] == patient_uuid
        assert s["active_workflow"] == "appointment"
        assert s["workflow_stage"] == "collecting_info"
        assert s["workflow_data"]["doctor"] == "Dr. Smith"
        assert s["pending_question"]["question"] == "Confirm?"
        sm2.dispose()

    def test_get_nonexistent_session(self, sm):
        assert sm.get_session("does-not-exist") is None
