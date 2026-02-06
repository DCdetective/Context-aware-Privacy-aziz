"""
Tests for Human-in-the-Loop (HITL) Manager (Prompt 9).
Tests confirmation requests, positive/negative confirmations,
clarification, multiple rounds, invalid responses, state preservation,
no-reset mid-workflow, timeout warning, and timeout cancellation.
"""

import pytest
import asyncio
import tempfile
import os
import time

from agents.hitl_manager import HITLManager
from agents.coordinator import Coordinator
from agents.session_manager import SessionManager
from agents.context_agent import ContextAgent
from database.identity_vault import IdentityVault


@pytest.fixture
def temp_db():
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
def session_mgr(temp_db):
    session_db, _ = temp_db
    return SessionManager(db_path=session_db)


@pytest.fixture
def hitl(session_mgr):
    mgr = HITLManager(session_manager=session_mgr)
    return mgr


@pytest.fixture
def coordinator(temp_db):
    session_db, vault_db = temp_db
    coord = Coordinator()
    coord.session_manager = SessionManager(db_path=session_db)
    v = IdentityVault(db_path=vault_db)
    v.pseudonymize_patient("Aziz", age=22, gender="Male", component="test")
    v.pseudonymize_patient("Sara", age=28, gender="Female", component="test")
    coord._get_identity_vault = lambda: v
    ca = ContextAgent()
    coord._get_context_agent = lambda: ca
    coord._ctx_agent = ca
    return coord


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── 1. Test Confirmation Request ─────────────────────────────────────

class TestConfirmationRequest:
    def test_workflow_pauses(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        result = hitl.request_confirmation(sid, "appointment", {
            "patient_name": "Aziz",
            "specialty": "cardiology",
            "date": "2026-03-01",
            "time": "14:00",
        })
        assert result["requires_response"] is True
        assert "confirm" in result["message"].lower()
        assert hitl.is_waiting_for_hitl(sid) is True

        # Pending question should be set
        pending = hitl.get_pending_request(sid)
        assert pending is not None
        assert pending["question_type"] == "confirmation"


# ── 2. Test Positive Confirmation ────────────────────────────────────

class TestPositiveConfirmation:
    def test_confirm_proceeds(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "appointment", {
            "patient_name": "Aziz", "specialty": "cardiology"
        })

        result = hitl.process_hitl_response(sid, "confirm")
        assert result["action"] == "confirmed"
        assert result["proceed"] is True
        # Pending should be cleared
        assert hitl.is_waiting_for_hitl(sid) is False

    def test_yes_proceeds(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "update", {"status": "better"})
        result = hitl.process_hitl_response(sid, "yes")
        assert result["action"] == "confirmed"
        assert result["proceed"] is True

    def test_ok_proceeds(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "action", {"desc": "test"})
        result = hitl.process_hitl_response(sid, "ok")
        assert result["action"] == "confirmed"
        assert result["proceed"] is True


# ── 3. Test Negative Confirmation ────────────────────────────────────

class TestNegativeConfirmation:
    def test_cancel_aborts(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "appointment", {"patient_name": "Aziz"})

        result = hitl.process_hitl_response(sid, "cancel")
        assert result["action"] == "cancelled"
        assert result["proceed"] is False
        assert hitl.is_waiting_for_hitl(sid) is False

    def test_no_aborts(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "appointment", {"patient_name": "Aziz"})
        result = hitl.process_hitl_response(sid, "no")
        assert result["action"] == "cancelled"
        assert result["proceed"] is False


# ── 4. Test Clarification Question ───────────────────────────────────

class TestClarificationQuestion:
    def test_clarification_with_options(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        result = hitl.request_clarification(
            sid,
            "Multiple patients found named 'Aziz':",
            {"candidates": [{"id": "a1"}, {"id": "a2"}]},
            options=["Aziz (Age: early 20s)", "Aziz (Age: middle-aged)"]
        )
        assert result["requires_response"] is True
        assert hitl.is_waiting_for_hitl(sid) is True
        assert result["options"] is not None
        assert len(result["options"]) == 2

    def test_select_option_by_number(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_clarification(
            sid, "Select patient:",
            {},
            options=["Patient A", "Patient B"]
        )
        result = hitl.process_hitl_response(sid, "1")
        assert result["action"] == "answered"
        assert result["proceed"] is True
        assert result["data"]["selected_option"] == "Patient A"

    def test_select_option_by_number_second(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_clarification(
            sid, "Select:",
            {},
            options=["Option A", "Option B", "Option C"]
        )
        result = hitl.process_hitl_response(sid, "2")
        assert result["action"] == "answered"
        assert result["data"]["selected_option"] == "Option B"


# ── 5. Test Multiple HITL Rounds ─────────────────────────────────────

class TestMultipleRounds:
    def test_sequential_hitl(self, hitl, session_mgr):
        sid = session_mgr.create_session()

        # Round 1: Clarification
        hitl.request_clarification(sid, "Which patient?", {}, options=["A", "B"])
        r1 = hitl.process_hitl_response(sid, "1")
        assert r1["action"] == "answered"
        assert r1["proceed"] is True

        # Round 2: Another clarification
        hitl.request_clarification(sid, "Which specialty?", {}, options=["Cardiology", "Neurology"])
        r2 = hitl.process_hitl_response(sid, "2")
        assert r2["action"] == "answered"
        assert r2["data"]["selected_option"] == "Neurology"

        # Round 3: Confirmation
        hitl.request_confirmation(sid, "appointment", {"specialty": "neurology"})
        r3 = hitl.process_hitl_response(sid, "confirm")
        assert r3["action"] == "confirmed"
        assert r3["proceed"] is True


# ── 6. Test Invalid Responses ────────────────────────────────────────

class TestInvalidResponses:
    def test_invalid_reprompts(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "appointment", {"patient_name": "Aziz"})

        result = hitl.process_hitl_response(sid, "maybe")
        assert result["action"] == "invalid"
        assert result["proceed"] is False
        # Should still be waiting
        assert hitl.is_waiting_for_hitl(sid) is True

    def test_valid_after_invalid(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "appointment", {"test": True})

        # Invalid
        r1 = hitl.process_hitl_response(sid, "maybe")
        assert r1["action"] == "invalid"
        assert hitl.is_waiting_for_hitl(sid) is True

        # Now valid
        r2 = hitl.process_hitl_response(sid, "confirm")
        assert r2["action"] == "confirmed"
        assert r2["proceed"] is True
        assert hitl.is_waiting_for_hitl(sid) is False


# ── 7. Test State Preservation ───────────────────────────────────────

class TestStatePreservation:
    def test_info_preserved_during_hitl(self, coordinator):
        sid = coordinator.session_manager.create_session()

        # Start appointment workflow
        r1 = run(coordinator.process_message(sid, "Book appointment for Aziz"))
        assert r1["success"]

        # Provide specialty
        r2 = run(coordinator.process_message(sid, "Cardiology"))
        session = coordinator.session_manager.get_session(sid)
        wf_data = coordinator.session_manager.get_workflow_data(sid)
        assert wf_data.get("specialty") == "cardiology"
        assert session["active_workflow"] == "appointment"

        # Provide date
        r3 = run(coordinator.process_message(sid, "Tomorrow"))
        wf_data = coordinator.session_manager.get_workflow_data(sid)
        assert "date" in wf_data

        # Provide time
        r4 = run(coordinator.process_message(sid, "2 PM"))
        wf_data = coordinator.session_manager.get_workflow_data(sid)
        assert wf_data.get("time") == "14:00"

        # Provide reason - triggers confirmation (HITL pause)
        r5 = run(coordinator.process_message(sid, "Chest pain"))
        assert "confirm" in r5["response"].lower()

        # All collected info should still be there
        wf_data = coordinator.session_manager.get_workflow_data(sid)
        assert wf_data.get("specialty") == "cardiology"
        assert "date" in wf_data
        assert wf_data.get("time") == "14:00"
        assert wf_data.get("reason") == "Chest pain"


# ── 8. Test No Reset Mid-Workflow ────────────────────────────────────

class TestNoResetMidWorkflow:
    def test_no_main_menu_during_workflow(self, coordinator):
        sid = coordinator.session_manager.create_session()

        # Start workflow
        r1 = run(coordinator.process_message(sid, "Book appointment for Aziz"))

        # During workflow, workflow should be active
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "appointment"

        # Send another message - should NOT reset to main menu
        r2 = run(coordinator.process_message(sid, "Cardiology"))
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "appointment"
        assert "what would you like to do" not in r2["response"].lower()

        # Intent detection should only have been called once
        detection_count = coordinator.get_intent_detection_count(sid)
        assert detection_count == 1


# ── 9. Test Timeout Warning ──────────────────────────────────────────

class TestTimeoutWarning:
    def test_reminder_sent(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "appointment", {"patient_name": "Aziz"})

        # Simulate 2+ minutes elapsed
        pending = hitl._pending_requests[sid]
        pending["timestamp"] = time.time() - 130  # 130 seconds ago

        result = hitl.check_timeout(sid)
        assert result["status"] == "reminder"
        assert result["message"] is not None
        assert "reminder" in result["message"].lower() or "respond" in result["message"].lower()

        # Workflow should still be active
        assert hitl.is_waiting_for_hitl(sid) is True


# ── 10. Test Timeout Cancellation ────────────────────────────────────

class TestTimeoutCancellation:
    def test_timeout_cancels(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "appointment", {"patient_name": "Aziz"})

        # Simulate 5+ minutes elapsed
        pending = hitl._pending_requests[sid]
        pending["timestamp"] = time.time() - 310  # 310 seconds ago

        result = hitl.check_timeout(sid)
        assert result["status"] == "timed_out"
        assert result["message"] is not None
        assert "timed out" in result["message"].lower() or "cancelled" in result["message"].lower()

        # Should no longer be waiting
        assert hitl.is_waiting_for_hitl(sid) is False

    def test_timeout_logged(self, hitl, session_mgr):
        sid = session_mgr.create_session()
        hitl.request_confirmation(sid, "appointment", {"test": True})

        pending = hitl._pending_requests[sid]
        pending["timestamp"] = time.time() - 310

        hitl.check_timeout(sid)

        # Check log
        log = hitl.get_hitl_log(sid)
        event_types = [e["event_type"] for e in log]
        assert "timeout" in event_types
