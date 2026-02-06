"""
Tests for Appointment Booking Workflow (Prompt 6).
Tests complete flow, information extraction, validation,
cancellation, doctor assignment, and storage.
"""

import pytest
import asyncio
import tempfile
import os

from agents.coordinator import Coordinator
from agents.execution_agent import ExecutionAgent
from agents.session_manager import SessionManager
from database.identity_vault import IdentityVault


@pytest.fixture
def temp_db():
    """Create temp DB paths."""
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
    """Create coordinator with test patient 'Aziz'."""
    session_db, vault_db = temp_db
    coord = Coordinator()
    coord.session_manager = SessionManager(db_path=session_db)
    vault = IdentityVault(db_path=vault_db)
    vault.pseudonymize_patient("Aziz", age=22, gender="Male", component="test")
    coord._get_identity_vault = lambda: vault
    return coord


@pytest.fixture
def exec_agent():
    """Create a fresh execution agent."""
    return ExecutionAgent()


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── 1. Test Complete Appointment Flow ─────────────────────────────────

class TestCompleteAppointmentFlow:
    def test_full_booking_flow(self, coordinator):
        sid = coordinator.session_manager.create_session()

        # Step 1: Start booking
        r1 = run(coordinator.process_message(sid, "Book appointment for Aziz"))
        assert r1["success"]
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "appointment"

        # Step 2: Provide specialty
        r2 = run(coordinator.process_message(sid, "Cardiology"))
        assert r2["success"]
        assert "date" in r2["response"].lower() or "when" in r2["response"].lower()

        # Step 3: Provide date
        r3 = run(coordinator.process_message(sid, "Tomorrow"))
        assert r3["success"]
        assert "time" in r3["response"].lower()

        # Step 4: Provide time
        r4 = run(coordinator.process_message(sid, "2 PM"))
        assert r4["success"]
        assert "reason" in r4["response"].lower()

        # Step 5: Provide reason
        r5 = run(coordinator.process_message(sid, "Chest pain follow-up"))
        assert r5["success"]
        assert "confirm" in r5["response"].lower()

        # Step 6: Confirm
        r6 = run(coordinator.process_message(sid, "confirm"))
        assert r6["success"]
        assert "booked" in r6["response"].lower() or "success" in r6["response"].lower()

        # Workflow should be complete
        session = coordinator.session_manager.get_session(sid)
        assert session["active_workflow"] == "none"


# ── 2. Test Information Extraction ────────────────────────────────────

class TestInformationExtraction:
    def test_specialty_extracted(self, coordinator):
        sid = coordinator.session_manager.create_session()
        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        run(coordinator.process_message(sid, "Cardiology"))

        wf_data = coordinator.session_manager.get_workflow_data(sid)
        assert wf_data.get("specialty") == "cardiology"


# ── 3. Test Incremental Collection ────────────────────────────────────

class TestIncrementalCollection:
    def test_system_asks_for_missing_info(self, coordinator):
        sid = coordinator.session_manager.create_session()

        r1 = run(coordinator.process_message(sid, "Book appointment for Aziz"))
        # Should ask for specialty
        assert "specialty" in r1["response"].lower() or "what" in r1["response"].lower()

        r2 = run(coordinator.process_message(sid, "Cardiology"))
        # Should ask for date
        assert "date" in r2["response"].lower() or "when" in r2["response"].lower()

    def test_state_advances_correctly(self, coordinator):
        sid = coordinator.session_manager.create_session()

        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        s = coordinator.session_manager.get_session(sid)
        assert s["workflow_stage"] == "collecting_specialty"

        run(coordinator.process_message(sid, "Cardiology"))
        s = coordinator.session_manager.get_session(sid)
        assert s["workflow_stage"] == "collecting_date"

        run(coordinator.process_message(sid, "Tomorrow"))
        s = coordinator.session_manager.get_session(sid)
        assert s["workflow_stage"] == "collecting_time"

        run(coordinator.process_message(sid, "2 PM"))
        s = coordinator.session_manager.get_session(sid)
        assert s["workflow_stage"] == "collecting_reason"

        run(coordinator.process_message(sid, "Chest pain"))
        s = coordinator.session_manager.get_session(sid)
        assert s["workflow_stage"] == "confirmation"


# ── 4. Test Invalid Specialty ─────────────────────────────────────────

class TestInvalidSpecialty:
    def test_invalid_specialty_rejected(self, coordinator):
        sid = coordinator.session_manager.create_session()
        run(coordinator.process_message(sid, "Book appointment for Aziz"))

        result = run(coordinator.process_message(sid, "MadeUpSpecialty"))
        assert "not" in result["response"].lower() or "invalid" in result["response"].lower() or "available" in result["response"].lower()

        # Should still be in collecting_specialty stage
        s = coordinator.session_manager.get_session(sid)
        assert s["workflow_stage"] == "collecting_specialty"

    def test_valid_specialty_after_invalid(self, coordinator):
        sid = coordinator.session_manager.create_session()
        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        run(coordinator.process_message(sid, "FakeSpecialty"))

        # Now provide valid specialty
        result = run(coordinator.process_message(sid, "Cardiology"))
        assert result["success"]
        s = coordinator.session_manager.get_session(sid)
        assert s["workflow_stage"] == "collecting_date"


# ── 5. Test Invalid Date ─────────────────────────────────────────────

class TestInvalidDate:
    def test_past_date_rejected(self, exec_agent):
        result = exec_agent.parse_date("2020-01-01")
        assert result["valid"] is False
        assert "future" in result["error"].lower()

    def test_valid_date_formats(self, exec_agent):
        for date_str in ["Tomorrow", "tomorrow", "next Monday", "next week"]:
            result = exec_agent.parse_date(date_str)
            assert result["valid"] is True, f"Failed for: {date_str}"
            assert result["date"] != ""

    def test_unparseable_date(self, exec_agent):
        result = exec_agent.parse_date("blahblah")
        assert result["valid"] is False


# ── 6. Test Invalid Time ─────────────────────────────────────────────

class TestInvalidTime:
    def test_outside_business_hours(self, exec_agent):
        result = exec_agent.parse_time("7 AM")
        assert result["valid"] is False
        assert "business hours" in result["error"].lower()

    def test_late_evening_rejected(self, exec_agent):
        result = exec_agent.parse_time("10 PM")
        assert result["valid"] is False

    def test_valid_times(self, exec_agent):
        for t in ["9 AM", "2 PM", "10:00", "14:00", "morning", "afternoon"]:
            result = exec_agent.parse_time(t)
            assert result["valid"] is True, f"Failed for: {t}"

    def test_time_parsing_format(self, exec_agent):
        result = exec_agent.parse_time("2 PM")
        assert result["time"] == "14:00"

        result = exec_agent.parse_time("9 AM")
        assert result["time"] == "09:00"


# ── 7. Test Cancellation ─────────────────────────────────────────────

class TestCancellation:
    def test_cancel_at_any_stage(self, coordinator):
        sid = coordinator.session_manager.create_session()

        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        result = run(coordinator.process_message(sid, "cancel"))

        assert "cancel" in result["response"].lower()
        s = coordinator.session_manager.get_session(sid)
        assert s["active_workflow"] == "none"

    def test_cancel_mid_collection(self, coordinator):
        sid = coordinator.session_manager.create_session()
        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        run(coordinator.process_message(sid, "Cardiology"))
        run(coordinator.process_message(sid, "Tomorrow"))

        result = run(coordinator.process_message(sid, "cancel"))
        assert "cancel" in result["response"].lower()
        s = coordinator.session_manager.get_session(sid)
        assert s["active_workflow"] == "none"


# ── 8. Test Confirmation ─────────────────────────────────────────────

class TestConfirmation:
    def test_decline_at_confirmation(self, coordinator):
        sid = coordinator.session_manager.create_session()
        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        run(coordinator.process_message(sid, "Cardiology"))
        run(coordinator.process_message(sid, "Tomorrow"))
        run(coordinator.process_message(sid, "2 PM"))
        run(coordinator.process_message(sid, "Chest pain"))

        # Decline
        result = run(coordinator.process_message(sid, "no"))
        assert "cancel" in result["response"].lower()
        s = coordinator.session_manager.get_session(sid)
        assert s["active_workflow"] == "none"


# ── 9. Test Doctor Assignment ─────────────────────────────────────────

class TestDoctorAssignment:
    def test_doctor_assigned_by_specialty(self, exec_agent):
        doctor = exec_agent.assign_doctor("cardiology")
        assert doctor is not None
        assert "name" in doctor
        assert "specialty" in doctor

    def test_fallback_doctor_for_unknown_specialty(self, exec_agent):
        doctor = exec_agent.assign_doctor("unknown_specialty_xyz")
        assert doctor is not None
        assert "name" in doctor

    def test_doctor_in_confirmation(self, coordinator):
        sid = coordinator.session_manager.create_session()
        run(coordinator.process_message(sid, "Book appointment for Aziz"))
        run(coordinator.process_message(sid, "Cardiology"))
        run(coordinator.process_message(sid, "Tomorrow"))
        run(coordinator.process_message(sid, "2 PM"))

        result = run(coordinator.process_message(sid, "Chest pain"))
        # Confirmation should mention doctor
        assert "doctor" in result["response"].lower() or "dr" in result["response"].lower()


# ── 10. Test Storage ──────────────────────────────────────────────────

class TestAppointmentStorage:
    def test_appointment_stored_after_booking(self, exec_agent):
        result = run(exec_agent.book_appointment(
            patient_uuid="uuid-store-test",
            doctor_specialty="cardiology",
            preferred_date="2026-03-01",
            preferred_time="14:00",
            reason="Chest pain",
        ))
        assert result["success"]
        assert result["appointment_id"] is not None
        assert result["appointment_id"] in exec_agent._appointments


# ── Execution Agent Standalone Tests ──────────────────────────────────

class TestExecutionAgentValidation:
    def test_specialty_validation(self, exec_agent):
        assert exec_agent.validate_specialty("cardiology") is True
        assert exec_agent.validate_specialty("Cardiology") is True
        assert exec_agent.validate_specialty("fakefake") is False

    def test_specialty_aliases(self, exec_agent):
        assert exec_agent.validate_specialty("heart") is True
        assert exec_agent.validate_specialty("brain") is True
        assert exec_agent.validate_specialty("skin") is True

    def test_normalize_specialty(self, exec_agent):
        assert exec_agent.normalize_specialty("heart") == "cardiology"
        assert exec_agent.normalize_specialty("brain") == "neurology"
        assert exec_agent.normalize_specialty("cardiology") == "cardiology"

    def test_get_available_specialties(self, exec_agent):
        specs = exec_agent.get_available_specialties()
        assert len(specs) > 0
        assert "cardiology" in specs

    def test_legacy_execute_task(self, exec_agent):
        result = exec_agent.execute_task(
            patient_uuid="test-uuid",
            intent="general",
            refined_context={}
        )
        assert result["success"]
        assert result["intent"] == "general"
