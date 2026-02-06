"""
Tests for Context Agent (Prompt 4).
Tests interaction storage, retrieval, semantic search, summaries,
metadata filtering, and cross-patient isolation.
"""

import pytest
import time
from agents.context_agent import ContextAgent


@pytest.fixture
def ctx_agent():
    """Create a fresh ContextAgent for each test."""
    return ContextAgent()


# ── 1. Test Interaction Storage ───────────────────────────────────────

class TestInteractionStorage:
    def test_store_symptom_interaction(self, ctx_agent):
        vid = ctx_agent.store_interaction(
            patient_uuid="uuid-123",
            interaction_type="symptom",
            content="Patient_123, early 20s, reports headache",
        )
        assert vid is not None
        assert "uuid-123" in vid
        assert "symptom" in vid

    def test_store_returns_unique_ids(self, ctx_agent):
        vid1 = ctx_agent.store_interaction("uuid-1", "symptom", "headache")
        vid2 = ctx_agent.store_interaction("uuid-1", "symptom", "headache")
        assert vid1 != vid2

    def test_store_different_interaction_types(self, ctx_agent):
        for itype in ("symptom", "appointment", "followup", "question"):
            vid = ctx_agent.store_interaction("uuid-1", itype, f"content for {itype}")
            assert vid is not None
            assert itype in vid

    def test_store_invalid_type_raises(self, ctx_agent):
        with pytest.raises(ValueError, match="Invalid interaction_type"):
            ctx_agent.store_interaction("uuid-1", "invalid_type", "content")

    def test_metadata_is_correct(self, ctx_agent):
        ctx_agent.store_interaction(
            patient_uuid="uuid-meta",
            interaction_type="appointment",
            content="Cardiology appointment scheduled",
            metadata={"severity": "moderate"},
            session_id="sess-1",
            workflow="appointment",
        )
        history = ctx_agent.retrieve_patient_history("uuid-meta")
        assert len(history) == 1
        meta = history[0]["metadata"]
        assert meta["patient_id"] == "uuid-meta"
        assert meta["type"] == "appointment"
        assert meta["content"] == "Cardiology appointment scheduled"
        assert meta["session_id"] == "sess-1"
        assert meta["workflow"] == "appointment"
        assert meta["severity"] == "moderate"
        assert "timestamp" in meta


# ── 2. Test Patient History Retrieval ─────────────────────────────────

class TestPatientHistoryRetrieval:
    def test_retrieve_patient_history(self, ctx_agent):
        ctx_agent.store_interaction("uuid-A", "symptom", "headache")
        ctx_agent.store_interaction("uuid-A", "appointment", "cardiology appt")
        ctx_agent.store_interaction("uuid-A", "followup", "followup visit")

        history = ctx_agent.retrieve_patient_history("uuid-A")
        assert len(history) == 3

    def test_filter_by_interaction_type(self, ctx_agent):
        ctx_agent.store_interaction("uuid-B", "symptom", "cough")
        ctx_agent.store_interaction("uuid-B", "appointment", "pulmonology")
        ctx_agent.store_interaction("uuid-B", "symptom", "fever")

        symptoms = ctx_agent.retrieve_patient_history("uuid-B", interaction_types=["symptom"])
        assert len(symptoms) == 2
        for s in symptoms:
            assert s["metadata"]["type"] == "symptom"

    def test_limit_results(self, ctx_agent):
        for i in range(20):
            ctx_agent.store_interaction("uuid-C", "symptom", f"symptom {i}")
        history = ctx_agent.retrieve_patient_history("uuid-C", limit=5)
        assert len(history) == 5

    def test_chronological_ordering(self, ctx_agent):
        ctx_agent.store_interaction("uuid-D", "symptom", "first")
        time.sleep(0.01)
        ctx_agent.store_interaction("uuid-D", "symptom", "second")
        time.sleep(0.01)
        ctx_agent.store_interaction("uuid-D", "symptom", "third")

        history = ctx_agent.retrieve_patient_history("uuid-D")
        # Newest first
        assert history[0]["metadata"]["content"] == "third"
        assert history[-1]["metadata"]["content"] == "first"

    def test_empty_history(self, ctx_agent):
        history = ctx_agent.retrieve_patient_history("nonexistent-uuid")
        assert history == []


# ── 3. Test Semantic Search ───────────────────────────────────────────

class TestSemanticSearch:
    def test_semantic_search_returns_results(self, ctx_agent):
        ctx_agent.store_interaction("uuid-S1", "symptom", "severe chest pain and shortness of breath")
        ctx_agent.store_interaction("uuid-S1", "symptom", "mild headache and fatigue")
        ctx_agent.store_interaction("uuid-S1", "question", "what are flu symptoms")

        results = ctx_agent.semantic_search("chest pain cardiac", patient_uuid="uuid-S1")
        assert len(results) > 0
        # Should have scores
        for r in results:
            assert "score" in r
            assert "metadata" in r

    def test_semantic_search_with_patient_filter(self, ctx_agent):
        ctx_agent.store_interaction("uuid-F1", "symptom", "chest pain")
        ctx_agent.store_interaction("uuid-F2", "symptom", "chest pain different patient")

        results = ctx_agent.semantic_search("chest pain", patient_uuid="uuid-F1")
        for r in results:
            assert r["metadata"]["patient_id"] == "uuid-F1"

    def test_semantic_search_without_filter(self, ctx_agent):
        ctx_agent.store_interaction("uuid-G1", "symptom", "back pain")
        ctx_agent.store_interaction("uuid-G2", "symptom", "knee pain")

        results = ctx_agent.semantic_search("pain", patient_uuid=None)
        assert len(results) >= 2

    def test_semantic_search_top_k(self, ctx_agent):
        for i in range(10):
            ctx_agent.store_interaction("uuid-K", "symptom", f"symptom number {i}")
        results = ctx_agent.semantic_search("symptom", patient_uuid="uuid-K", top_k=3)
        assert len(results) == 3


# ── 4. Test Patient Summary Generation ───────────────────────────────

class TestPatientSummary:
    def test_summary_with_diverse_interactions(self, ctx_agent):
        ctx_agent.store_interaction("uuid-SUM", "symptom", "headache and dizziness")
        ctx_agent.store_interaction("uuid-SUM", "appointment", "neurology appointment")
        ctx_agent.store_interaction("uuid-SUM", "followup", "followup after MRI")
        ctx_agent.store_interaction("uuid-SUM", "question", "what causes migraines?")

        summary = ctx_agent.get_patient_summary("uuid-SUM")
        assert summary["total_interactions"] == 4
        assert len(summary["appointments"]) == 1
        assert len(summary["symptoms"]) == 1
        assert len(summary["follow_ups"]) == 1
        assert isinstance(summary["summary_text"], str)
        assert len(summary["summary_text"]) > 0

    def test_summary_empty_patient(self, ctx_agent):
        summary = ctx_agent.get_patient_summary("uuid-EMPTY")
        assert summary["total_interactions"] == 0
        assert summary["appointments"] == []
        assert summary["symptoms"] == []
        assert summary["follow_ups"] == []
        assert "No interactions" in summary["summary_text"]

    def test_summary_text_coherent(self, ctx_agent):
        ctx_agent.store_interaction("uuid-COH", "appointment", "cardiology visit")
        ctx_agent.store_interaction("uuid-COH", "symptom", "chest pain")

        summary = ctx_agent.get_patient_summary("uuid-COH")
        assert "2" in summary["summary_text"] or "two" in summary["summary_text"].lower()


# ── 5. Test Metadata Filtering ───────────────────────────────────────

class TestMetadataFiltering:
    def test_filter_by_type(self, ctx_agent):
        ctx_agent.store_interaction("uuid-MF", "symptom", "cough")
        ctx_agent.store_interaction("uuid-MF", "appointment", "visit")
        ctx_agent.store_interaction("uuid-MF", "symptom", "fever")

        results = ctx_agent.filter_interactions("uuid-MF", interaction_type="symptom")
        assert len(results) == 2

    def test_filter_by_timestamp(self, ctx_agent):
        ctx_agent.store_interaction("uuid-TS", "symptom", "old symptom")
        # All stored with current timestamp, so filtering by future should return 0
        results = ctx_agent.filter_interactions(
            "uuid-TS", timestamp_gte="2099-01-01T00:00:00Z")
        assert len(results) == 0

    def test_filter_combined(self, ctx_agent):
        ctx_agent.store_interaction("uuid-CF", "symptom", "cough")
        ctx_agent.store_interaction("uuid-CF", "appointment", "visit")

        results = ctx_agent.filter_interactions("uuid-CF", interaction_type="appointment")
        assert len(results) == 1
        assert results[0]["metadata"]["type"] == "appointment"


# ── 6. Test Cross-Patient Isolation ───────────────────────────────────

class TestCrossPatientIsolation:
    def test_patient_data_isolated(self, ctx_agent):
        ctx_agent.store_interaction("patient-A", "symptom", "Patient A headache")
        ctx_agent.store_interaction("patient-A", "appointment", "Patient A cardiology")
        ctx_agent.store_interaction("patient-B", "symptom", "Patient B back pain")
        ctx_agent.store_interaction("patient-B", "followup", "Patient B followup")

        history_a = ctx_agent.retrieve_patient_history("patient-A")
        history_b = ctx_agent.retrieve_patient_history("patient-B")

        assert len(history_a) == 2
        assert len(history_b) == 2

        for h in history_a:
            assert h["metadata"]["patient_id"] == "patient-A"
            assert "Patient B" not in h["metadata"]["content"]

        for h in history_b:
            assert h["metadata"]["patient_id"] == "patient-B"
            assert "Patient A" not in h["metadata"]["content"]

    def test_search_isolated_by_patient(self, ctx_agent):
        ctx_agent.store_interaction("iso-A", "symptom", "cardiac arrest symptoms")
        ctx_agent.store_interaction("iso-B", "symptom", "cardiac arrest symptoms")

        results_a = ctx_agent.semantic_search("cardiac", patient_uuid="iso-A")
        for r in results_a:
            assert r["metadata"]["patient_id"] == "iso-A"

    def test_summary_isolated(self, ctx_agent):
        ctx_agent.store_interaction("sum-A", "symptom", "headache")
        ctx_agent.store_interaction("sum-B", "symptom", "back pain")

        summary_a = ctx_agent.get_patient_summary("sum-A")
        summary_b = ctx_agent.get_patient_summary("sum-B")

        assert summary_a["total_interactions"] == 1
        assert summary_b["total_interactions"] == 1


# ── 7. Test Context Refinement (integration) ─────────────────────────

class TestContextRefinement:
    def test_refine_context_fallback(self, ctx_agent):
        result = ctx_agent.refine_context(
            patient_uuid="uuid-ref",
            intent="appointment",
            semantic_context={"symptom_category": "cardiac", "urgency_level": "urgent"},
            medical_info="chest pain"
        )
        assert "recommended_specialty" in result
        assert "urgency_assessment" in result
        assert "rag_context" in result
