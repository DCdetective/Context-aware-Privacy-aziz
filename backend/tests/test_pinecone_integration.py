"""
Test Pinecone integration and RAG functionality.
Uses mock stores and in-memory embedding for CI/testing.
"""

import pytest
from rag.embeddings import embedding_generator
from rag.retriever import rag_retriever
from vector_store.mock_stores import MockMetadataStore, MockSyntheticStore
from agents.context_agent import ContextAgent


# ── 1. Test Pinecone Connection (mock) ────────────────────────────────

class TestPineconeConnection:
    def test_mock_metadata_store_init(self):
        store = MockMetadataStore()
        assert store is not None
        assert store.index_name == "mock-metadata"

    def test_mock_synthetic_store_init(self):
        store = MockSyntheticStore()
        assert store is not None
        assert store.index_name == "mock-synthetic"

    def test_error_handling_graceful(self):
        store = MockMetadataStore()
        # Should not crash on empty retrieval
        history = store.retrieve_patient_history("nonexistent-uuid")
        assert history == []


# ── 2. Test Vector Upsert ─────────────────────────────────────────────

class TestVectorUpsert:
    def test_single_upsert(self):
        store = MockMetadataStore()
        vid = store.store_patient_metadata(
            patient_uuid="test-uuid-123",
            semantic_context={"symptom_category": "respiratory", "urgency_level": "urgent"},
            intent="appointment"
        )
        assert vid is not None
        assert "test-uuid-123" in vid

    def test_batch_upsert(self):
        store = MockMetadataStore()
        ids = []
        for i in range(5):
            vid = store.store_patient_metadata(
                patient_uuid=f"batch-uuid-{i}",
                semantic_context={"symptom_category": "general"},
                intent="appointment"
            )
            ids.append(vid)
        assert len(ids) == 5
        assert len(set(ids)) == 5  # All unique

    def test_vectors_stored_correctly(self):
        store = MockMetadataStore()
        store.store_patient_metadata(
            patient_uuid="verify-uuid",
            semantic_context={"symptom_category": "cardiac", "urgency_level": "urgent"},
            intent="appointment"
        )
        history = store.retrieve_patient_history("verify-uuid")
        assert len(history) == 1
        meta = history[0]["metadata"]
        assert meta["patient_uuid"] == "verify-uuid"
        assert meta["intent"] == "appointment"
        assert meta["symptom_category"] == "cardiac"


# ── 3. Test Query with Filters ────────────────────────────────────────

class TestQueryWithFilters:
    def test_filter_by_patient_id(self):
        store = MockMetadataStore()
        store.store_patient_metadata("uuid-A", {"symptom_category": "cardiac"}, "appointment")
        store.store_patient_metadata("uuid-B", {"symptom_category": "respiratory"}, "followup")

        history_a = store.retrieve_patient_history("uuid-A")
        history_b = store.retrieve_patient_history("uuid-B")

        assert len(history_a) == 1
        assert len(history_b) == 1
        assert history_a[0]["metadata"]["patient_uuid"] == "uuid-A"
        assert history_b[0]["metadata"]["patient_uuid"] == "uuid-B"

    def test_similar_context_search(self):
        store = MockMetadataStore()
        store.store_patient_metadata("uuid-search", {"symptom_category": "cardiac"}, "appointment")

        results = store.search_similar_contexts("cardiac symptoms", patient_uuid="uuid-search")
        assert len(results) >= 1


# ── 4. Test Synthetic Data Ingestion (mock) ───────────────────────────

class TestSyntheticDataIngestion:
    def test_mock_ingestion(self):
        store = MockSyntheticStore()
        store.ingest_synthetic_data()
        assert store.ingested is True

    def test_doctor_search(self):
        store = MockSyntheticStore()
        doctors = store.search_doctors("cardiology")
        assert len(doctors) >= 1
        assert doctors[0]["metadata"]["type"] == "doctor"

    def test_knowledge_search(self):
        store = MockSyntheticStore()
        knowledge = store.search_medical_knowledge("chest pain")
        assert len(knowledge) >= 1
        assert knowledge[0]["metadata"]["type"] == "medical_knowledge"

    def test_case_search(self):
        store = MockSyntheticStore()
        cases = store.search_similar_cases("headache")
        assert len(cases) >= 1

    def test_stats(self):
        store = MockSyntheticStore()
        stats = store.get_stats()
        assert "total_vectors" in stats
        assert "dimension" in stats


# ── 5. Test Embedding Generation ──────────────────────────────────────

class TestEmbeddingGeneration:
    def test_embedding_generated(self):
        text = "Patient has respiratory symptoms requiring urgent care"
        embedding = embedding_generator.generate_embedding(text)
        assert embedding is not None
        assert len(embedding) == embedding_generator.dimension

    def test_embedding_not_all_zeros(self):
        embedding = embedding_generator.generate_embedding("Cardiology appointment")
        assert not all(val == 0.0 for val in embedding), "Embedding should not be all zeros"

    def test_embedding_has_variance(self):
        embedding = embedding_generator.generate_embedding("Follow-up visit needed")
        assert max(embedding) != min(embedding), "Embedding should have variance"

    def test_different_texts_different_embeddings(self):
        e1 = embedding_generator.generate_embedding("chest pain")
        e2 = embedding_generator.generate_embedding("broken leg")
        assert e1 != e2

    def test_batch_embeddings(self):
        texts = ["text one", "text two", "text three"]
        embeddings = embedding_generator.generate_embeddings(texts)
        assert len(embeddings) == 3
        for emb in embeddings:
            assert len(emb) == embedding_generator.dimension

    def test_caching(self):
        text = "cached text query"
        e1 = embedding_generator.generate_embedding(text)
        e2 = embedding_generator.generate_embedding(text)
        assert e1 == e2  # Same result from cache


# ── 6. Test RAG Retrieval ─────────────────────────────────────────────

class TestRAGRetrieval:
    def test_rag_retrieval_returns_context(self):
        context = rag_retriever.retrieve_context_for_intent(
            patient_uuid="test-uuid-123",
            intent="appointment",
            semantic_context={"symptom_category": "respiratory"},
            medical_info="cough and fever"
        )
        assert context is not None
        assert "patient_history" in context
        assert "relevant_doctors" in context
        assert "relevant_knowledge" in context
        assert "similar_cases" in context

    def test_rag_format_for_llm(self):
        context = {
            "patient_history": [],
            "relevant_doctors": [{"metadata": {"content": "Dr. Test"}}],
            "relevant_knowledge": [],
            "similar_cases": [],
        }
        formatted = rag_retriever.format_context_for_llm(context)
        assert isinstance(formatted, str)


# ── 7. Test Context Agent with Storage ────────────────────────────────

class TestContextAgentIntegration:
    def test_store_and_retrieve(self):
        agent = ContextAgent()
        agent.store_interaction("uuid-int", "symptom", "chest pain and dizziness")
        agent.store_interaction("uuid-int", "appointment", "cardiology visit scheduled")

        history = agent.retrieve_patient_history("uuid-int")
        assert len(history) == 2

    def test_semantic_search_relevance(self):
        agent = ContextAgent()
        agent.store_interaction("uuid-rel", "symptom", "severe chest pain cardiac")
        agent.store_interaction("uuid-rel", "symptom", "mild headache routine")

        results = agent.semantic_search("cardiac chest pain", patient_uuid="uuid-rel")
        assert len(results) >= 1
        # First result should be the cardiac one (higher similarity)
        assert "chest" in results[0]["metadata"]["content"].lower() or "cardiac" in results[0]["metadata"]["content"].lower()
