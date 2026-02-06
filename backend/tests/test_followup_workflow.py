"""
Tests for Follow-up Workflow (Prompt 7).
Tests history retrieval, cross-patient isolation, status updates,
complex updates, timeline, missing history, and retrieval filters.
"""

import pytest
import asyncio
import tempfile
import os
import time

from agents.coordinator import Coordinator
from agents.execution_agent import ExecutionAgent
from agents.context_agent import ContextAgent
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
def ctx_agent():
    """Create a fresh context agent and patch the global."""
    import agents.context_agent as ca_mod
    ca = ContextAgent()
    old = ca_mod.context_agent
    ca_mod.context_agent = ca
    yield ca
    ca_mod.context_agent = old


@pytest.fixture
def exec_agent():
    """Create a fresh execution agent."""
    return ExecutionAgent()


@pytest.fixture
def vault(temp_db):
    """Create a test vault with patients."""
    _, vault_db = temp_db
    v = IdentityVault(db_path=vault_db)
    return v


@pytest.fixture
def coordinator(temp_db):
    """Create coordinator with test patients Aziz and Sara."""
    import agents.context_agent as ca_mod

    session_db, vault_db = temp_db
    coord = Coordinator()
    coord.session_manager = SessionManager(db_path=session_db)
    v = IdentityVault(db_path=vault_db)
    v.pseudonymize_patient("Aziz", age=22, gender="Male", component="test")
    v.pseudonymize_patient("Sara", age=28, gender="Female", component="test")
    coord._get_identity_vault = lambda: v

    # Use a fresh context agent so tests are isolated AND patch the global
    ca = ContextAgent()
    ca_mod.context_agent = ca
    coord._get_context_agent = lambda: ca
    coord._ctx_agent = ca
    return coord


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── 1. Test Simple Follow-up Query ───────────────────────────────────

class TestSimpleFollowup:
    def test_followup_retrieves_history(self, coordinator):
        # Setup: store some history
        ca = coordinator._ctx_agent
        vault = coordinator._get_identity_vault()
        patients = vault.find_patients_by_name("Aziz", component="test")
        patient_uuid = patients[0]["patient_uuid"]

        ca.store_interaction(patient_uuid, "appointment",
                             "Cardiology appointment for chest pain",
                             {"date": "2024-01-15", "specialty": "cardiology"})
        ca.store_interaction(patient_uuid, "symptom",
                             "Reported headache and dizziness",
                             {"date": "2024-01-20"})

        # Query
        sid = coordinator.session_manager.create_session()
        r1 = run(coordinator.process_message(sid, "How is Aziz doing?"))
        assert r1["success"]
        # Should show history info
        assert "2" in r1["response"] or "interaction" in r1["response"].lower() or "appointment" in r1["response"].lower()


# ── 2. Test Follow-up with Multiple Patients ─────────────────────────

class TestMultiplePatients:
    def test_only_correct_patient_data(self, coordinator):
        ca = coordinator._ctx_agent
        vault = coordinator._get_identity_vault()

        aziz = vault.find_patients_by_name("Aziz", component="test")[0]
        sara = vault.find_patients_by_name("Sara", component="test")[0]

        ca.store_interaction(aziz["patient_uuid"], "appointment",
                             "Aziz cardiology appointment")
        ca.store_interaction(sara["patient_uuid"], "appointment",
                             "Sara dermatology appointment")

        # Check Aziz - use the same context agent (already patched globally)
        exec_agent = ExecutionAgent()
        result_aziz = run(exec_agent.get_patient_followup(aziz["patient_uuid"]))
        assert result_aziz["total_interactions"] == 1
        assert "cardiology" in result_aziz["recent_appointments"][0]["metadata"]["content"].lower()

        # Check Sara
        result_sara = run(exec_agent.get_patient_followup(sara["patient_uuid"]))
        assert result_sara["total_interactions"] == 1
        assert "dermatology" in result_sara["recent_appointments"][0]["metadata"]["content"].lower()

        # Cross-check: Aziz should NOT have Sara's data
        for apt in result_aziz["recent_appointments"]:
            assert "dermatology" not in apt["metadata"]["content"].lower()
        for apt in result_sara["recent_appointments"]:
            assert "cardiology" not in apt["metadata"]["content"].lower()


# ── 3. Test Patient Confusion Prevention ─────────────────────────────

class TestPatientConfusionPrevention:
    def test_context_switch_detected(self, coordinator):
        ca = coordinator._ctx_agent
        vault = coordinator._get_identity_vault()
        aziz = vault.find_patients_by_name("Aziz", component="test")[0]

        ca.store_interaction(aziz["patient_uuid"], "appointment",
                             "Aziz cardiology appointment")

        sid = coordinator.session_manager.create_session()
        # Start follow-up for Aziz
        r1 = run(coordinator.process_message(sid, "How is Aziz doing?"))
        assert r1["success"]

        # Active patient should be Aziz
        active = coordinator.session_manager.get_active_patient(sid)
        assert active is not None
        assert active["patient_name"] == "Aziz"


# ── 4. Test Status Update ────────────────────────────────────────────

class TestStatusUpdate:
    def test_update_extracted_and_confirmed(self, coordinator):
        ca = coordinator._ctx_agent
        vault = coordinator._get_identity_vault()
        aziz = vault.find_patients_by_name("Aziz", component="test")[0]
        ca.store_interaction(aziz["patient_uuid"], "symptom",
                             "Reported fever")

        sid = coordinator.session_manager.create_session()
        r1 = run(coordinator.process_message(sid, "How is Aziz doing?"))
        assert r1["success"]

        # Provide update
        r2 = run(coordinator.process_message(sid, "He is feeling better, fever is gone"))
        assert r2["success"]
        assert "confirm" in r2["response"].lower()

        # Confirm
        r3 = run(coordinator.process_message(sid, "confirm"))
        assert r3["success"]
        assert "saved" in r3["response"].lower() or "stored" in r3["response"].lower() or "update" in r3["response"].lower()


# ── 5. Test Complex Update ───────────────────────────────────────────

class TestComplexUpdate:
    def test_multiple_status_updates(self, exec_agent):
        updates = exec_agent._extract_status_updates(
            "Aziz's fever is gone but still has cough"
        )
        assert len(updates) >= 2
        symptoms_found = {u["symptom"] for u in updates}
        assert "fever" in symptoms_found
        assert "cough" in symptoms_found

        # Verify status details
        for u in updates:
            if u["symptom"] == "fever":
                assert u["status"] in ("resolved", "improved")
            if u["symptom"] == "cough":
                assert u["status"] in ("ongoing", "unknown", "improved", "resolved")


# ── 6. Test History Timeline ─────────────────────────────────────────

class TestHistoryTimeline:
    def test_chronological_summary(self, ctx_agent, exec_agent):
        patient_uuid = "timeline-test-uuid"

        # Store interactions with slight delays for ordering
        ctx_agent.store_interaction(patient_uuid, "appointment",
                                    "First appointment cardiology")
        time.sleep(0.05)
        ctx_agent.store_interaction(patient_uuid, "symptom",
                                    "Reported headache")
        time.sleep(0.05)
        ctx_agent.store_interaction(patient_uuid, "followup",
                                    "Follow-up: feeling better")

        # Retrieve history (newest first)
        history = ctx_agent.retrieve_patient_history(patient_uuid)
        assert len(history) == 3
        # Most recent should be follow-up
        assert history[0]["metadata"]["type"] == "followup"


# ── 7. Test Missing History ──────────────────────────────────────────

class TestMissingHistory:
    def test_no_history_graceful(self, ctx_agent, exec_agent):
        result = run(exec_agent.get_patient_followup("no-history-uuid"))
        assert result["no_history"] is True
        assert result["total_interactions"] == 0
        assert "no history" in result["follow_up_summary"].lower() or "no " in result["follow_up_summary"].lower()


# ── 8. Test Retrieval Filters ────────────────────────────────────────

class TestRetrievalFilters:
    def test_filter_by_type(self, ctx_agent):
        patient_uuid = "filter-test-uuid"

        ctx_agent.store_interaction(patient_uuid, "appointment", "Appointment 1")
        ctx_agent.store_interaction(patient_uuid, "symptom", "Symptom 1")
        ctx_agent.store_interaction(patient_uuid, "appointment", "Appointment 2")
        ctx_agent.store_interaction(patient_uuid, "followup", "Followup 1")

        # Filter appointments only
        appointments = ctx_agent.filter_interactions(patient_uuid, interaction_type="appointment")
        assert len(appointments) == 2
        for a in appointments:
            assert a["metadata"]["type"] == "appointment"

        # Filter symptoms only
        symptoms = ctx_agent.filter_interactions(patient_uuid, interaction_type="symptom")
        assert len(symptoms) == 1
        assert symptoms[0]["metadata"]["type"] == "symptom"

        # Filter followups only
        followups = ctx_agent.filter_interactions(patient_uuid, interaction_type="followup")
        assert len(followups) == 1
        assert followups[0]["metadata"]["type"] == "followup"
