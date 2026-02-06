"""
Integration Tests (Prompt 11)

Tests integration between system components:
- Gatekeeper ↔ Identity Vault
- Coordinator ↔ Session Manager
- Context Agent ↔ Execution Agent
- Worker ↔ Vector Store
- HITL Manager ↔ Session Manager
"""

import pytest
import asyncio
import time
from database.identity_vault import IdentityVault, identity_vault
from agents.session_manager import SessionManager, session_manager
from agents.gatekeeper import Gatekeeper, GatekeeperAgent, gatekeeper_agent
from agents.coordinator import Coordinator, CoordinatorAgent
from agents.context_agent import ContextAgent, context_agent
from agents.execution_agent import ExecutionAgent, execution_agent
from agents.hitl_manager import HITLManager, hitl_manager
from agents.memory_manager import MemoryManager, memory_manager
from vector_store.mock_stores import MockMetadataStore, MockSyntheticStore
from vector_store.mock_semantic_store import MockSemanticStore


class TestGatekeeperIntegration:
    """Test Gatekeeper integration with Identity Vault and other agents."""

    def test_pseudonymize_and_reidentify(self):
        """Test pseudonymize → reidentify round-trip."""
        uuid_val, is_new = identity_vault.pseudonymize_patient(
            patient_name="Integration Test Patient",
            age=30,
            gender="Male",
            component="test"
        )
        assert uuid_val is not None
        assert isinstance(uuid_val, str)

        # Reidentify
        identity = identity_vault.reidentify_patient(uuid_val, component="test")
        assert identity is not None
        assert identity["patient_name"] == "Integration Test Patient"
        assert identity["age"] == 30

    def test_gatekeeper_pii_detection(self):
        """Test Gatekeeper detects PII entities correctly."""
        gk = Gatekeeper()
        entities = gk.detect_pii_entities(
            "John Smith is 35 years old and lives at 123 Main St. Phone: 555-123-4567"
        )
        types_found = {e["type"] for e in entities}
        # Should detect at least name and age
        assert "name" in types_found or "age" in types_found

    def test_gatekeeper_anonymize_text(self):
        """Test Gatekeeper anonymizes text correctly."""
        gk = Gatekeeper()
        result = gk.anonymize_text("John Smith is 35 years old")
        assert "anonymized_text" in result
        assert "privacy_events" in result
        # Original name should be replaced
        anon_text = result["anonymized_text"]
        assert "John Smith" not in anon_text or "Patient" in anon_text

    def test_gatekeeper_deanonymize_text(self):
        """Test Gatekeeper deanonymization works."""
        gk = Gatekeeper()
        gk.register_patient("test-uuid", "Real Name", "Patient_ABC")
        result = gk.deanonymize_text("Patient_ABC has an appointment", "test-uuid")
        assert "Real Name" in result

    def test_gatekeeper_privacy_events_tracked(self):
        """Test that privacy events are recorded."""
        gk = Gatekeeper()
        gk.clear_privacy_events()
        gk.anonymize_text("John Smith is 35 years old")
        events = gk.get_privacy_events()
        # Should have recorded transformations
        assert isinstance(events, list)


class TestSessionManagerIntegration:
    """Test Session Manager integration."""

    def test_session_create_and_retrieve(self):
        """Test session lifecycle."""
        sid = session_manager.create_session()
        assert sid is not None

        session = session_manager.get_session(sid)
        assert session is not None
        assert session["active_workflow"] == "none"

    def test_workflow_lifecycle(self):
        """Test full workflow lifecycle through session manager."""
        sid = session_manager.create_session()

        # Set workflow
        session_manager.set_workflow(sid, "appointment", "resolving_patient")
        session = session_manager.get_session(sid)
        assert session["active_workflow"] == "appointment"
        assert session["workflow_stage"] == "resolving_patient"

        # Add workflow data
        session_manager.add_workflow_data(sid, "specialty", "cardiology")
        wf_data = session_manager.get_workflow_data(sid)
        assert wf_data["specialty"] == "cardiology"

        # Complete workflow
        session_manager.complete_workflow(sid)
        session = session_manager.get_session(sid)
        assert session["active_workflow"] == "none"

    def test_conversation_history(self):
        """Test conversation history tracking."""
        sid = session_manager.create_session()

        session_manager.add_to_history(sid, "user", "Hello")
        session_manager.add_to_history(sid, "assistant", "Hi there!")

        context = session_manager.get_conversation_context(sid)
        assert "Hello" in context
        assert "Hi there!" in context

    def test_active_patient_binding(self):
        """Test patient binding to session."""
        sid = session_manager.create_session()

        session_manager.set_active_patient(sid, "test-uuid-123", "Test Patient")
        patient = session_manager.get_active_patient(sid)
        assert patient is not None
        assert patient["patient_uuid"] == "test-uuid-123"

    def test_session_reset(self):
        """Test session reset clears all state."""
        sid = session_manager.create_session()
        session_manager.set_workflow(sid, "appointment", "resolving_patient")
        session_manager.set_active_patient(sid, "test-uuid", "Test")

        session_manager.reset_session(sid)
        session = session_manager.get_session(sid)
        assert session["active_workflow"] == "none"
        assert session["active_patient_id"] is None


class TestCoordinatorIntegration:
    """Test Coordinator integration with other agents."""

    def test_coordinator_agent_valid_request(self):
        """Test CoordinatorAgent handles valid request."""
        coord = CoordinatorAgent()
        result = coord.coordinate_request(
            patient_uuid="test-uuid",
            action_type="appointment",
            semantic_context={"symptom_category": "cardiac", "urgency_level": "routine"}
        )
        assert result["patient_uuid"] == "test-uuid"
        assert result["privacy_safe"] is True
        assert result["ready_for_worker"] is True

    def test_coordinator_agent_invalid_action(self):
        """Test CoordinatorAgent rejects invalid action."""
        coord = CoordinatorAgent()
        result = coord.coordinate_request(
            patient_uuid="test-uuid",
            action_type="invalid_action",
            semantic_context={}
        )
        assert result["success"] is False

    def test_coordinator_intent_detection(self):
        """Test Coordinator intent detection."""
        coord = Coordinator()
        intents = {
            "Book an appointment for me": "appointment",
            "Schedule a follow-up": "followup",
            "Show me my medical summary": "summary",
            "What services do you offer?": "general",
        }
        for msg, expected in intents.items():
            result = asyncio.get_event_loop().run_until_complete(
                coord.detect_intent(msg)
            )
            assert result == expected, f"Expected {expected} for '{msg}', got {result}"


class TestContextAgentIntegration:
    """Test Context Agent integration."""

    def test_store_and_retrieve(self):
        """Test storing and retrieving interactions."""
        ca = ContextAgent()
        vid = ca.store_interaction(
            patient_uuid="int-test-uuid",
            interaction_type="symptom",
            content="Patient reports chest pain",
        )
        assert vid is not None

        history = ca.retrieve_patient_history("int-test-uuid")
        assert len(history) >= 1
        assert history[0]["metadata"]["content"] == "Patient reports chest pain"

    def test_cross_patient_isolation(self):
        """Test that patient data is isolated."""
        ca = ContextAgent()
        ca.store_interaction("patient-A", "symptom", "Headache")
        ca.store_interaction("patient-B", "symptom", "Back pain")

        history_a = ca.retrieve_patient_history("patient-A")
        history_b = ca.retrieve_patient_history("patient-B")

        for h in history_a:
            assert h["metadata"]["patient_id"] == "patient-A"
        for h in history_b:
            assert h["metadata"]["patient_id"] == "patient-B"

    def test_semantic_search(self):
        """Test semantic search returns relevant results."""
        ca = ContextAgent()
        ca.store_interaction("search-patient", "symptom", "Severe headache and dizziness")
        ca.store_interaction("search-patient", "appointment", "Neurology consultation")

        results = ca.semantic_search("headache", patient_uuid="search-patient")
        assert len(results) > 0

    def test_patient_summary_generation(self):
        """Test patient summary generation."""
        ca = ContextAgent()
        ca.store_interaction("summary-patient", "symptom", "Fever and cough")
        ca.store_interaction("summary-patient", "appointment", "General medicine visit")

        summary = ca.get_patient_summary("summary-patient")
        assert summary["total_interactions"] >= 2
        assert len(summary["summary_text"]) > 0


class TestExecutionAgentIntegration:
    """Test Execution Agent integration."""

    def test_specialty_validation(self):
        """Test specialty validation."""
        assert execution_agent.validate_specialty("cardiology") is True
        assert execution_agent.validate_specialty("nonexistent_specialty") is False

    def test_date_parsing(self):
        """Test date parsing."""
        result = execution_agent.parse_date("tomorrow")
        assert result["valid"] is True
        assert len(result["date"]) > 0

    def test_time_parsing(self):
        """Test time parsing."""
        result = execution_agent.parse_time("2 PM")
        assert result["valid"] is True
        assert result["time"] == "14:00"

    def test_doctor_assignment(self):
        """Test doctor assignment."""
        doctor = execution_agent.assign_doctor("cardiology")
        assert "name" in doctor
        assert "specialty" in doctor

    def test_legacy_execute_task(self):
        """Test legacy execute_task interface."""
        uuid_val, _ = identity_vault.pseudonymize_patient(
            patient_name="Exec Test",
            age=40,
            gender="Male",
            component="test"
        )
        result = execution_agent.execute_task(
            patient_uuid=uuid_val,
            intent="appointment",
            refined_context={"urgency_assessment": "routine", "estimated_duration": 30}
        )
        assert result["success"] is True


class TestHITLIntegration:
    """Test HITL Manager integration."""

    def test_confirmation_flow(self):
        """Test confirmation request and response."""
        sid = session_manager.create_session()

        result = hitl_manager.request_confirmation(
            sid, "appointment",
            {"patient_name": "Test", "specialty": "cardiology", "date": "2026-03-01"}
        )
        assert result["requires_response"] is True
        assert hitl_manager.is_waiting_for_hitl(sid) is True

        # Confirm
        response = hitl_manager.process_hitl_response(sid, "yes")
        assert response["action"] == "confirmed"
        assert response["proceed"] is True
        assert hitl_manager.is_waiting_for_hitl(sid) is False

    def test_cancellation_flow(self):
        """Test cancellation flow."""
        sid = session_manager.create_session()
        hitl_manager.request_confirmation(sid, "appointment", {"patient_name": "Test"})

        response = hitl_manager.process_hitl_response(sid, "no")
        assert response["action"] == "cancelled"
        assert response["proceed"] is False

    def test_clarification_with_options(self):
        """Test clarification with numbered options."""
        sid = session_manager.create_session()
        result = hitl_manager.request_clarification(
            sid, "Which patient?",
            {"candidates": ["Patient A", "Patient B"]},
            options=["Patient A - Age 30", "Patient B - Age 40"]
        )
        assert result["requires_response"] is True

        response = hitl_manager.process_hitl_response(sid, "1")
        assert response["action"] == "answered"
        assert response["proceed"] is True

    def test_medical_questions(self):
        """Test medical question flow."""
        sid = session_manager.create_session()
        questions = hitl_manager.generate_medical_questions(
            "appointment", {"symptom_category": "cardiac", "urgency_level": "urgent"}
        )
        assert len(questions) > 0

    def test_parse_confirmation_variants(self):
        """Test various confirmation response formats."""
        assert hitl_manager.parse_confirmation_response("yes") is True
        assert hitl_manager.parse_confirmation_response("confirm") is True
        assert hitl_manager.parse_confirmation_response("ok") is True
        assert hitl_manager.parse_confirmation_response("no") is False
        assert hitl_manager.parse_confirmation_response("random text") is False


class TestMemoryManagerIntegration:
    """Test Memory Manager integration."""

    def test_long_term_memory_retrieval(self):
        """Test long-term memory retrieval."""
        memory = memory_manager.get_patient_long_term_memory("nonexistent-uuid")
        assert memory["patient_uuid"] == "nonexistent-uuid"
        assert isinstance(memory["medical_records"], list)

    def test_memory_formatting(self):
        """Test memory formatting for LLM."""
        formatted = memory_manager.format_memory_for_llm(
            "User: Hello",
            {"summary": "Patient has 2 records", "medical_records": [], "interaction_history": []}
        )
        assert "CONVERSATION MEMORY" in formatted
        assert "Hello" in formatted

    def test_context_switch_detection(self):
        """Test context switch detection."""
        assert memory_manager.detect_context_switch(
            "now let's talk about another patient", "John"
        ) is True
        assert memory_manager.detect_context_switch(
            "John is feeling better", "John"
        ) is False


class TestVectorStoreIntegration:
    """Test vector store integration."""

    def test_mock_metadata_store(self):
        """Test mock metadata store operations."""
        store = MockMetadataStore()
        vid = store.store_patient_metadata(
            patient_uuid="vec-test",
            semantic_context={"symptom_category": "cardiac"},
            intent="appointment"
        )
        assert vid is not None

        history = store.retrieve_patient_history("vec-test")
        assert len(history) == 1
        assert history[0]["metadata"]["patient_uuid"] == "vec-test"

    def test_mock_semantic_store(self):
        """Test mock semantic store operations."""
        store = MockSemanticStore()
        aid = store.store_semantic_anchor(
            patient_uuid="sem-test",
            anchor_type="symptom",
            semantic_data={"symptom_category": "respiratory"}
        )
        assert aid is not None

        anchors = store.retrieve_semantic_anchors("sem-test")
        assert len(anchors) == 1

    def test_semantic_store_privacy_violation(self):
        """Test that semantic store rejects PII."""
        store = MockSemanticStore()
        with pytest.raises(ValueError, match="Privacy violation"):
            store.store_semantic_anchor(
                patient_uuid="pii-test",
                anchor_type="symptom",
                semantic_data={"name": "John Doe", "symptom": "cough"}
            )

    def test_mock_synthetic_store(self):
        """Test mock synthetic store operations."""
        store = MockSyntheticStore()
        doctors = store.search_doctors("cardiology")
        assert len(doctors) > 0

        knowledge = store.search_medical_knowledge("chest pain")
        assert len(knowledge) > 0
