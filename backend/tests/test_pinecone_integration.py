"""
Test Pinecone integration and RAG functionality.
"""
import pytest
from rag.embeddings import embedding_generator
from vector_store.metadata_store import MetadataStore
from rag.retriever import rag_retriever


def test_embedding_generation():
    """Test that embeddings are generated correctly."""
    text = "Patient has respiratory symptoms requiring urgent care"
    
    embedding = embedding_generator.generate_embedding(text)
    
    assert embedding is not None
    assert len(embedding) == embedding_generator.dimension
    assert not all(val == 0.0 for val in embedding), "Embedding should not be all zeros"
    print(f"✓ Embedding generated successfully: dimension={len(embedding)}")


def test_metadata_upsert():
    """Test metadata storage and retrieval."""
    store = MetadataStore()
    
    # Store metadata
    vector_id = store.store_patient_metadata(
        patient_uuid="test-uuid-123",
        semantic_context={
            "symptom_category": "respiratory",
            "urgency_level": "urgent"
        },
        intent="appointment"
    )
    
    assert vector_id is not None
    assert "test-uuid-123" in vector_id
    print(f"✓ Metadata stored successfully: {vector_id}")
    
    # Retrieve metadata
    history = store.retrieve_patient_history("test-uuid-123", limit=5)
    assert len(history) >= 1
    print(f"✓ Metadata retrieved successfully: {len(history)} records")


def test_rag_retrieval():
    """Test RAG retrieval returns context."""
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
    print(f"✓ RAG retrieval successful")
    print(f"  - History records: {len(context['patient_history'])}")
    print(f"  - Doctors found: {len(context['relevant_doctors'])}")
    print(f"  - Knowledge items: {len(context['relevant_knowledge'])}")
    print(f"  - Similar cases: {len(context['similar_cases'])}")


def test_embedding_not_zero():
    """Test that embeddings have non-zero values."""
    texts = [
        "Cardiology appointment",
        "Follow-up visit needed",
        "Medical summary requested"
    ]
    
    for text in texts:
        embedding = embedding_generator.generate_embedding(text)
        assert not all(val == 0.0 for val in embedding), f"Embedding for '{text}' should not be all zeros"
        # Check that embedding has reasonable variance
        assert max(embedding) != min(embedding), f"Embedding for '{text}' should have variance"
    
    print(f"✓ All embeddings have non-zero values with variance")


if __name__ == "__main__":
    print("Running Pinecone Integration Tests...")
    print("=" * 60)
    
    test_embedding_generation()
    print()
    
    test_embedding_not_zero()
    print()
    
    test_metadata_upsert()
    print()
    
    test_rag_retrieval()
    print()
    
    print("=" * 60)
    print("All tests completed!")
