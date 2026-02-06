"""
Tests for Patient Summary Generation (Prompt 8).
Tests full summary, recent summary, specific summary, empty history,
timeline ordering, statistics, key insights, date range, cross-patient
isolation, and privacy.
"""

import pytest
import asyncio
import tempfile
import os
import time

from agents.context_agent import ContextAgent
from agents.worker import SummaryWorker
from agents.session_manager import SessionManager
from database.identity_vault import IdentityVault


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
def summary_worker():
    """Create a SummaryWorker."""
    return SummaryWorker()


@pytest.fixture(autouse=True)
def _patch_context_agent(ctx_agent):
    """Ensure every test in this module uses the patched context agent."""
    pass


@pytest.fixture
def temp_db():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        vault_db = f.name
    yield vault_db
    try:
        os.remove(vault_db)
    except (PermissionError, OSError):
        pass


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _setup_diverse_history(ctx_agent, patient_uuid):
    """Helper: store diverse interaction history for a patient."""
    ctx_agent.store_interaction(patient_uuid, "appointment",
                                "Cardiology appointment for chest pain",
                                {"specialty": "cardiology"})
    time.sleep(0.02)
    ctx_agent.store_interaction(patient_uuid, "symptom",
                                "Reported headache")
    time.sleep(0.02)
    ctx_agent.store_interaction(patient_uuid, "appointment",
                                "Dermatology appointment for rash")
    time.sleep(0.02)
    ctx_agent.store_interaction(patient_uuid, "symptom",
                                "Reported headache again")
    time.sleep(0.02)
    ctx_agent.store_interaction(patient_uuid, "followup",
                                "Follow-up: feeling better after cardiology")
    time.sleep(0.02)
    ctx_agent.store_interaction(patient_uuid, "symptom",
                                "Reported headache third time")
    time.sleep(0.02)
    ctx_agent.store_interaction(patient_uuid, "appointment",
                                "Neurology appointment for recurring headache")
    time.sleep(0.02)
    ctx_agent.store_interaction(patient_uuid, "followup",
                                "Follow-up: headache medication working")
    time.sleep(0.02)
    ctx_agent.store_interaction(patient_uuid, "appointment",
                                "General checkup appointment")
    time.sleep(0.02)
    ctx_agent.store_interaction(patient_uuid, "appointment",
                                "Cardiology followup appointment")


# ── 1. Test Full Summary Generation ──────────────────────────────────

class TestFullSummary:
    def test_full_summary_includes_all(self, ctx_agent, summary_worker):
        patient_uuid = "full-summary-uuid"
        _setup_diverse_history(ctx_agent, patient_uuid)

        summary = run(summary_worker.generate_patient_summary(patient_uuid, "full"))

        assert summary["total_interactions"] == 10
        assert summary["appointments"]["total"] == 5
        assert summary["symptoms"]["total"] == 3
        assert summary["follow_ups"]["total"] == 2
        assert len(summary["timeline"]) == 10
        assert summary["summary_text"]  # Not empty
        assert summary["summary_type"] == "full"


# ── 2. Test Recent Summary ───────────────────────────────────────────

class TestRecentSummary:
    def test_recent_summary_filters(self, ctx_agent, summary_worker):
        patient_uuid = "recent-summary-uuid"

        # Store interactions (all "recent" since we just created them)
        ctx_agent.store_interaction(patient_uuid, "appointment", "Recent appointment")
        ctx_agent.store_interaction(patient_uuid, "symptom", "Recent symptom")

        summary = run(summary_worker.generate_patient_summary(patient_uuid, "recent"))

        # All should be included since they are within 30 days
        assert summary["total_interactions"] == 2
        assert summary["summary_type"] == "recent"


# ── 3. Test Specific Summary ─────────────────────────────────────────

class TestSpecificSummary:
    def test_query_cardiology(self, ctx_agent, summary_worker):
        patient_uuid = "specific-summary-uuid"
        ctx_agent.store_interaction(patient_uuid, "appointment",
                                    "Cardiology appointment for chest pain")
        ctx_agent.store_interaction(patient_uuid, "appointment",
                                    "Dermatology appointment for rash")
        ctx_agent.store_interaction(patient_uuid, "appointment",
                                    "Cardiology follow-up")

        result = run(summary_worker.generate_specific_summary(
            patient_uuid, "Show cardiology appointments"))

        # Only cardiology-related results
        for r in result["results"]:
            assert "cardiology" in r["metadata"]["content"].lower() or \
                   "chest" in r["metadata"]["content"].lower()


# ── 4. Test Empty History ────────────────────────────────────────────

class TestEmptyHistory:
    def test_no_data_graceful(self, summary_worker):
        summary = run(summary_worker.generate_patient_summary("empty-uuid"))

        assert summary["total_interactions"] == 0
        assert summary["appointments"]["total"] == 0
        assert summary["symptoms"]["total"] == 0
        assert summary["follow_ups"]["total"] == 0
        assert "no interaction" in summary["summary_text"].lower() or "no " in summary["summary_text"].lower()


# ── 5. Test Timeline Ordering ────────────────────────────────────────

class TestTimelineOrdering:
    def test_chronological_timeline(self, ctx_agent, summary_worker):
        patient_uuid = "timeline-order-uuid"

        ctx_agent.store_interaction(patient_uuid, "appointment", "First visit")
        time.sleep(0.05)
        ctx_agent.store_interaction(patient_uuid, "symptom", "Second event")
        time.sleep(0.05)
        ctx_agent.store_interaction(patient_uuid, "followup", "Third event")

        summary = run(summary_worker.generate_patient_summary(patient_uuid))
        timeline = summary["timeline"]

        assert len(timeline) == 3
        # Timeline should be in chronological order (oldest first)
        for i in range(len(timeline) - 1):
            assert timeline[i]["timestamp"] <= timeline[i + 1]["timestamp"]


# ── 6. Test Statistics Aggregation ───────────────────────────────────

class TestStatisticsAggregation:
    def test_counts_accurate(self, ctx_agent, summary_worker):
        patient_uuid = "stats-uuid"

        # 5 appointments
        for i in range(5):
            ctx_agent.store_interaction(patient_uuid, "appointment", f"Appointment {i+1}")
        # 3 symptoms
        for i in range(3):
            ctx_agent.store_interaction(patient_uuid, "symptom", f"Symptom {i+1}")
        # 2 follow-ups
        for i in range(2):
            ctx_agent.store_interaction(patient_uuid, "followup", f"Followup {i+1}")

        summary = run(summary_worker.generate_patient_summary(patient_uuid))

        assert summary["appointments"]["total"] == 5
        assert summary["symptoms"]["total"] == 3
        assert summary["follow_ups"]["total"] == 2
        assert summary["total_interactions"] == 10


# ── 7. Test Key Insights ─────────────────────────────────────────────

class TestKeyInsights:
    def test_recurring_symptom_detected(self, ctx_agent, summary_worker):
        patient_uuid = "insights-uuid"

        # Store recurring headaches (3x)
        ctx_agent.store_interaction(patient_uuid, "symptom", "Reported headache")
        ctx_agent.store_interaction(patient_uuid, "symptom", "Headache again today")
        ctx_agent.store_interaction(patient_uuid, "symptom", "Severe headache persists")

        summary = run(summary_worker.generate_patient_summary(patient_uuid))

        # Should identify recurring headache
        insights_text = " ".join(summary["key_insights"]).lower()
        assert "headache" in insights_text
        assert "recurring" in insights_text or "reported" in insights_text


# ── 8. Test Date Range Filtering ────────────────────────────────────

class TestDateRangeFiltering:
    def test_date_range_filter(self, ctx_agent, summary_worker):
        patient_uuid = "daterange-uuid"

        ctx_agent.store_interaction(patient_uuid, "appointment", "Visit 1")
        time.sleep(0.02)
        ctx_agent.store_interaction(patient_uuid, "appointment", "Visit 2")
        time.sleep(0.02)
        ctx_agent.store_interaction(patient_uuid, "appointment", "Visit 3")

        # Get all
        full = run(summary_worker.generate_patient_summary(patient_uuid))
        assert full["total_interactions"] == 3

        # With date range that includes everything (very wide range)
        wide = run(summary_worker.generate_patient_summary(
            patient_uuid, date_range={"start": "2000-01-01", "end": "9999-12-31"}))
        assert wide["total_interactions"] == 3

        # With date range that excludes everything (future-only)
        narrow = run(summary_worker.generate_patient_summary(
            patient_uuid, date_range={"start": "9999-01-01", "end": "9999-12-31"}))
        assert narrow["total_interactions"] == 0


# ── 9. Test Cross-Patient Isolation ──────────────────────────────────

class TestCrossPatientIsolation:
    def test_no_data_leakage(self, ctx_agent, summary_worker):
        uuid_a = "patient-a-uuid"
        uuid_b = "patient-b-uuid"

        ctx_agent.store_interaction(uuid_a, "appointment", "Patient A cardiology visit")
        ctx_agent.store_interaction(uuid_a, "symptom", "Patient A headache")
        ctx_agent.store_interaction(uuid_b, "appointment", "Patient B dermatology visit")
        ctx_agent.store_interaction(uuid_b, "symptom", "Patient B rash")

        summary_a = run(summary_worker.generate_patient_summary(uuid_a))
        summary_b = run(summary_worker.generate_patient_summary(uuid_b))

        # Patient A should only have A's data
        assert summary_a["total_interactions"] == 2
        for item in summary_a["timeline"]:
            assert "Patient B" not in item["content"]
            assert "dermatology" not in item["content"].lower()

        # Patient B should only have B's data
        assert summary_b["total_interactions"] == 2
        for item in summary_b["timeline"]:
            assert "Patient A" not in item["content"]
            assert "cardiology" not in item["content"].lower()


# ── 10. Test Privacy in Summary ──────────────────────────────────────

class TestPrivacyInSummary:
    def test_uses_uuid_not_name(self, ctx_agent, summary_worker):
        patient_uuid = "privacy-test-uuid"

        ctx_agent.store_interaction(patient_uuid, "appointment",
                                    "Appointment for checkup")

        summary = run(summary_worker.generate_patient_summary(patient_uuid))
        summary_text = summary["summary_text"]

        # Summary text should reference UUID prefix, not real names
        assert patient_uuid[:8] in summary_text
