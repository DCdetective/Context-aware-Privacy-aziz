"""
Test suite for conversational memory system.
"""
import pytest
from agents.memory_manager import memory_manager
from agents.session_manager import session_manager
from database.identity_vault import identity_vault


class TestMemorySystem:
    """Test conversational memory functionality."""
    
    def test_long_term_memory_retrieval(self):
        """Test long-term memory retrieval."""
        # Create a patient with history
        uuid, _ = identity_vault.pseudonymize_patient(
            patient_name="Memory Test Patient",
            age=30,
            gender="Male"
        )
        
        # Add a medical record
        record_id = identity_vault.store_medical_record(
            patient_uuid=uuid,
            record_type="appointment",
            symptoms="test symptoms",
            notes="test notes",
            component="test"
        )
        
        # Retrieve memory
        memory = memory_manager.get_patient_long_term_memory(uuid)
        
        assert memory['patient_uuid'] == uuid
        assert len(memory['medical_records']) >= 1
        assert memory['summary'] != ""
        assert "medical records" in memory['summary'].lower()
        
        # Verify the record we just created is in memory
        record_types = [r.get('record_type') for r in memory['medical_records']]
        assert 'appointment' in record_types
    
    def test_context_switch_detection(self):
        """Test context switch detection."""
        # Should detect switch with explicit keywords
        assert memory_manager.detect_context_switch(
            "Now let's talk about Sarah instead",
            active_patient_name="John"
        ) is True
        
        assert memory_manager.detect_context_switch(
            "Switch to another patient",
            active_patient_name="John"
        ) is True
        
        assert memory_manager.detect_context_switch(
            "What about a different patient",
            active_patient_name="John"
        ) is True
        
        # Should not detect switch when mentioning active patient
        assert memory_manager.detect_context_switch(
            "How is John doing today?",
            active_patient_name="John"
        ) is False
        
        assert memory_manager.detect_context_switch(
            "John needs a followup appointment",
            active_patient_name="John"
        ) is False
        
        # Should not detect switch for general queries
        assert memory_manager.detect_context_switch(
            "What are your office hours?",
            active_patient_name="John"
        ) is False
    
    def test_conversation_memory(self):
        """Test conversation memory in session."""
        # Create a new session
        session_id = session_manager.create_session()
        
        # Add messages to history
        session_manager.add_to_history(session_id, "user", "I need an appointment")
        session_manager.add_to_history(session_id, "assistant", "I can help with that")
        session_manager.add_to_history(session_id, "user", "For tomorrow please")
        session_manager.add_to_history(session_id, "assistant", "Let me check availability")
        
        # Get context
        context = session_manager.get_conversation_context(session_id, limit=10)
        
        assert "I need an appointment" in context
        assert "I can help with that" in context
        assert "For tomorrow please" in context
        assert "Let me check availability" in context
        
        # Test with limit
        limited_context = session_manager.get_conversation_context(session_id, limit=2)
        assert "For tomorrow please" in limited_context
        assert "Let me check availability" in limited_context
        # First messages should not be in limited context
        assert "I need an appointment" not in limited_context
    
    def test_session_summary(self):
        """Test session summary generation."""
        # Create session with active patient
        session_id = session_manager.create_session()
        
        # Initially no active patient
        summary = session_manager.get_session_summary(session_id)
        assert summary['has_active_patient'] is False
        assert summary['conversation_length'] == 0
        
        # Set active patient
        test_uuid = "test-uuid-12345"
        session_manager.set_active_patient(session_id, test_uuid, "Test Patient")
        
        # Add some history
        session_manager.add_to_history(session_id, "user", "Hello")
        session_manager.add_to_history(session_id, "assistant", "Hi there")
        
        # Get updated summary
        summary = session_manager.get_session_summary(session_id)
        assert summary['has_active_patient'] is True
        assert summary['patient_uuid'] == test_uuid
        assert summary['patient_name'] == "Test Patient"
        assert summary['conversation_length'] == 2
        assert summary['session_id'] == session_id
    
    def test_memory_formatting_for_llm(self):
        """Test memory formatting for LLM context."""
        # Create short-term memory
        short_term = "User: I need help\nAssistant: How can I assist?"
        
        # Create long-term memory
        long_term = {
            "patient_uuid": "test-uuid",
            "medical_records": [{"record_type": "appointment"}],
            "interaction_history": [{"intent": "appointment"}],
            "summary": "Patient has 1 medical record."
        }
        
        # Format for LLM
        formatted = memory_manager.format_memory_for_llm(short_term, long_term)
        
        assert "CONVERSATION MEMORY" in formatted
        assert "SHORT-TERM" in formatted
        assert "LONG-TERM" in formatted
        assert short_term in formatted
        assert "Patient has 1 medical record" in formatted
        assert "Medical Records: 1" in formatted
        assert "Previous Interactions: 1" in formatted
    
    def test_empty_memory_handling(self):
        """Test handling of empty memory."""
        # Test with non-existent patient
        memory = memory_manager.get_patient_long_term_memory("non-existent-uuid")
        
        assert memory['patient_uuid'] == "non-existent-uuid"
        assert len(memory['medical_records']) == 0
        assert len(memory['interaction_history']) == 0
        assert "new patient" in memory['summary'].lower() or "no previous history" in memory['summary'].lower()
    
    def test_conversation_context_empty(self):
        """Test conversation context with no history."""
        session_id = session_manager.create_session()
        
        context = session_manager.get_conversation_context(session_id)
        assert "no previous conversation" in context.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
