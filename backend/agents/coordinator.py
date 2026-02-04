from typing import Dict, Any, Optional
import logging
import re

from agents.gatekeeper import gatekeeper_agent
from agents.context_agent import context_agent
from agents.execution_agent import execution_agent
from agents.session_manager import session_manager
from agents.hitl_manager import hitl_manager
from agents.memory_manager import memory_manager
from database.identity_vault import identity_vault
from vector_store.metadata_store import metadata_store

logger = logging.getLogger(__name__)


class CoordinatorAgent:
    """Coordinator agent that prepares execution plans for the Worker.

    The original codebase evolved into an end-to-end `process_message` pipeline
    (`AgentCoordinator` below). The test-suite still expects a dedicated
    coordinator with:
      - `model` attribute
      - `coordinate_request(...)`
      - `_fallback_execution_plan(...)`

    This class is intentionally deterministic (no external API calls) so it can
    run in CI/testing mode without Groq credentials.
    """

    def __init__(self, model: str | None = None):
        self.model = model or "rule-based"

    def coordinate_request(self, patient_uuid: str, action_type: str, semantic_context: Dict[str, Any]) -> Dict[str, Any]:
        valid_actions = {"appointment", "followup", "summary"}
        if action_type not in valid_actions:
            return {
                "success": False,
                "error": f"Invalid action_type: {action_type}",
                "patient_uuid": patient_uuid,
                "action_type": action_type,
                "privacy_safe": True,
            }

        execution_plan = self._fallback_execution_plan(action_type=action_type, semantic_context=semantic_context or {})
        return {
            "patient_uuid": patient_uuid,
            "action_type": action_type,
            "execution_plan": execution_plan,
            "ready_for_worker": True,
            "privacy_safe": True,
        }

    def _fallback_execution_plan(self, action_type: str, semantic_context: Dict[str, Any]) -> Dict[str, Any]:
        urgency = (semantic_context or {}).get("urgency_level", "routine")
        requires_specialist = bool((semantic_context or {}).get("requires_specialist", False))

        if action_type == "appointment":
            steps = ["validate", "schedule", "confirm"]
            estimated_time = 3
        elif action_type == "followup":
            steps = ["retrieve", "schedule", "confirm"]
            estimated_time = 2
        elif action_type == "summary":
            steps = ["gather", "generate", "format"]
            estimated_time = 2
        else:
            steps = ["validate"]
            estimated_time = 1

        return {
            "steps": steps,
            "priority": urgency,
            "requires_specialist": requires_specialist,
            "estimated_time": estimated_time,
        }


class AgentCoordinator:
    """
    Coordinates the multi-agent workflow.
    
    Workflow:
    1. Gatekeeper: Extract PII, pseudonymize
    2. Context Agent: Refine context using RAG
    3. Execution Agent: Perform task
    4. Gatekeeper: Re-identify for output
    """
    
    def __init__(self):
        """Initialize coordinator."""
        logger.info("Agent Coordinator initialized")
    
    def _extract_uuid_from_message(self, message: str) -> Optional[str]:
        """Extract UUID from user message."""
        # Look for UUID pattern
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        match = re.search(uuid_pattern, message, re.IGNORECASE)
        if match:
            return match.group(0)
        
        # Also check for partial UUID (first 8 chars)
        partial_pattern = r'[0-9a-f]{8}'
        match = re.search(partial_pattern, message, re.IGNORECASE)
        if match:
            # This is a partial match - would need to validate against candidates
            return match.group(0)
        
        return None
    
    def process_message(self, user_message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Process user message through multi-agent pipeline.
        
        Args:
            user_message: Raw user input
            session_id: Optional session ID for context
            
        Returns:
            Final response with re-identified PII
        """
        logger.info("=" * 70)
        logger.info("COORDINATOR: Starting multi-agent workflow")
        logger.info("=" * 70)
        
        try:
            # Create or get session
            if not session_id:
                session_id = session_manager.create_session()
            
            session = session_manager.get_session(session_id)
            if not session:
                session_id = session_manager.create_session()
                session = session_manager.get_session(session_id)
            
            # Check if there's a pending action awaiting confirmation
            pending_action = session_manager.get_pending_action(session_id)
            
            if pending_action and pending_action.get('awaiting_confirmation'):
                # User is responding to confirmation request
                is_confirmed = hitl_manager.parse_confirmation_response(user_message)
                
                if is_confirmed:
                    # Execute the pending action
                    logger.info("User confirmed action - executing...")
                    
                    action_type = pending_action['action_type']
                    action_data = pending_action['action_data']
                    patient_uuid = pending_action.get('patient_uuid')
                    
                    # Execute based on action type
                    if action_type == 'appointment':
                        result = self._finalize_appointment(patient_uuid, action_data)
                    elif action_type == 'followup':
                        result = self._finalize_followup(patient_uuid, action_data)
                    else:
                        result = {"message": "Action completed"}
                    
                    # Clear pending action
                    session_manager.clear_pending_action(session_id)
                    
                    return {
                        "success": True,
                        "message": f"✓ {result.get('message', 'Action completed successfully!')}",
                        "intent": f"{action_type}_confirmed",
                        "patient_uuid": patient_uuid,
                        "session_id": session_id,
                        "result": result,
                        "privacy_safe": True,
                        "workflow_steps": ["User confirmation received", "Action executed"]
                    }
                else:
                    # User declined
                    session_manager.clear_pending_action(session_id)
                    
                    return {
                        "success": True,
                        "message": "Action cancelled. How else can I help you?",
                        "intent": "cancelled",
                        "session_id": session_id,
                        "privacy_safe": True,
                        "workflow_steps": ["User cancelled action"]
                    }
            
            # Check if we're collecting responses to medical questions
            if pending_action and not pending_action.get('awaiting_confirmation'):
                # We're in question-gathering phase
                questions = pending_action.get('questions_asked', [])
                responses = pending_action.get('user_responses', [])
                
                # Record this response
                if len(responses) < len(questions):
                    current_question = questions[len(responses)]
                    session_manager.add_question_response(
                        session_id=session_id,
                        question=current_question,
                        response=user_message
                    )
                    # Refresh pending action to get updated responses
                    pending_action = session_manager.get_pending_action(session_id)
                    responses = pending_action.get('user_responses', [])
                
                # Check if all questions answered
                if len(responses) >= len(questions):
                    # Move to confirmation phase
                    pending_action['awaiting_confirmation'] = True
                    
                    # Get patient info for summary
                    active_patient = session_manager.get_active_patient(session_id)
                    patient_name = active_patient.get('patient_name', 'Unknown') if active_patient else 'Unknown'
                    
                    # Create confirmation summary
                    summary = hitl_manager.create_confirmation_summary(
                        intent=pending_action['action_type'],
                        patient_name=patient_name,
                        action_data=pending_action['action_data'],
                        user_responses=responses
                    )
                    
                    return {
                        "success": True,
                        "message": summary,
                        "intent": "awaiting_confirmation",
                        "session_id": session_id,
                        "privacy_safe": True,
                        "workflow_steps": ["All questions answered", "Awaiting user confirmation"]
                    }
                else:
                    # Ask next question
                    next_question = questions[len(responses)]
                    return {
                        "success": True,
                        "message": next_question,
                        "intent": "collecting_info",
                        "session_id": session_id,
                        "privacy_safe": True,
                        "workflow_steps": [f"Collecting response {len(responses)+1}/{len(questions)}"]
                    }
            
            # Check if there's a pending disambiguation
            pending_disambiguation = session_manager.get_pending_disambiguation(session_id)
            
            if pending_disambiguation:
                # User is responding to disambiguation request
                # Extract UUID selection from message
                selected_uuid = self._extract_uuid_from_message(user_message)
                
                if selected_uuid:
                    # Validate selection
                    candidates = pending_disambiguation.get("candidates", [])
                    valid_uuids = [c["patient_uuid"] for c in candidates]
                    
                    # Check for partial match
                    matching_uuid = None
                    for uuid in valid_uuids:
                        if uuid.startswith(selected_uuid) or uuid == selected_uuid:
                            matching_uuid = uuid
                            break
                    
                    if matching_uuid:
                        # Set active patient
                        patient_name = next(
                            c["patient_name"] for c in candidates 
                            if c["patient_uuid"] == matching_uuid
                        )
                        session_manager.set_active_patient(session_id, matching_uuid, patient_name)
                        session_manager.clear_pending_disambiguation(session_id)
                        
                        return {
                            "success": True,
                            "message": f"Selected patient {patient_name} (UUID: {matching_uuid[:8]}...). How can I help?",
                            "intent": "patient_selected",
                            "patient_uuid": matching_uuid,
                            "patient_name": patient_name,
                            "session_id": session_id,
                            "result": {},
                            "privacy_safe": True,
                            "workflow_steps": ["Patient identity resolved"]
                        }
                    else:
                        return {
                            "success": False,
                            "message": "Invalid selection. Please select a valid patient UUID from the list.",
                            "intent": "error",
                            "session_id": session_id,
                            "privacy_safe": True
                        }
                else:
                    return {
                        "success": False,
                        "message": "Please select a patient by providing their UUID.",
                        "intent": "disambiguation_pending",
                        "session_id": session_id,
                        "disambiguation_data": pending_disambiguation,
                        "privacy_safe": True
                    }
            
            # Add message to conversation history
            session_manager.add_to_history(session_id, "user", user_message)
            
            # Check for context switch
            active_patient = session_manager.get_active_patient(session_id)
            if active_patient:
                is_context_switch = memory_manager.detect_context_switch(
                    current_message=user_message,
                    active_patient_name=active_patient.get('patient_name')
                )
                
                if is_context_switch:
                    logger.info("Context switch detected - clearing active patient")
                    session_manager.set_active_patient(session_id, None, None)
                    active_patient = None
            
            # Step 1: Gatekeeper processes input
            logger.info("Step 1: Gatekeeper processing...")
            gatekeeper_output = gatekeeper_agent.process_message(user_message)
            
            pii_data = gatekeeper_output['pii']
            intent = gatekeeper_output['intent']
            semantic_context = gatekeeper_output['semantic_context']
            
            # Step 2: Resolve patient identity (with collision detection)
            if pii_data.get('patient_name'):
                logger.info("Step 2: Resolving patient identity...")
                
                resolution = identity_vault.resolve_patient_identity(
                    patient_name=pii_data['patient_name'],
                    age=pii_data.get('age'),
                    gender=pii_data.get('gender'),
                    component="coordinator"
                )
                
                if resolution["status"] == "needs_disambiguation":
                    # Multiple patients found - ask user to choose
                    session_manager.set_pending_disambiguation(session_id, resolution)
                    
                    # Format candidate list for user
                    candidates_text = "\n".join([
                        f"- {c['patient_name']} (UUID: {c['patient_uuid'][:8]}..., "
                        f"Age: {c.get('age', 'N/A')}, Gender: {c.get('gender', 'N/A')}, "
                        f"Last seen: {c.get('last_accessed', 'Never')})"
                        for c in resolution["candidates"]
                    ])
                    
                    return {
                        "success": True,
                        "message": f"{resolution['message']}\n\n{candidates_text}\n\nPlease reply with the patient UUID.",
                        "intent": "disambiguation_required",
                        "session_id": session_id,
                        "disambiguation_data": resolution,
                        "privacy_safe": True,
                        "workflow_steps": ["Multiple patients found", "Requesting user disambiguation"]
                    }
                
                elif resolution["status"] == "needs_confirmation":
                    # New patient - ask for confirmation
                    return {
                        "success": True,
                        "message": resolution["message"] + " Please confirm (yes/no).",
                        "intent": "confirmation_required",
                        "session_id": session_id,
                        "pending_confirmation": {
                            "action": "create_patient",
                            "patient_name": resolution["patient_name"],
                            "age": resolution.get("age"),
                            "gender": resolution.get("gender")
                        },
                        "privacy_safe": True,
                        "workflow_steps": ["New patient detected", "Requesting user confirmation"]
                    }
                
                elif resolution["status"] == "resolved":
                    # Unique patient found
                    patient_uuid = resolution["patient_uuid"]
                    session_manager.set_active_patient(
                        session_id,
                        patient_uuid,
                        resolution["patient_name"]
                    )
                    logger.info(f"Patient resolved: {patient_uuid}")
                
                else:
                    logger.error(f"Unknown resolution status: {resolution['status']}")
                    patient_uuid = "temp-uuid-" + str(hash(user_message))[:8]
            
            else:
                # No PII detected - check if there's an active patient in session
                active_patient = session_manager.get_active_patient(session_id)
                if active_patient:
                    patient_uuid = active_patient["patient_uuid"]
                    logger.info(f"Using active patient from session: {patient_uuid}")
                else:
                    # No patient context
                    patient_uuid = "temp-uuid-" + str(hash(user_message))[:8]
                    logger.info("No PII detected, using temporary UUID")
            
            # Step 3: Store metadata in vector store
            if metadata_store and pii_data.get('patient_name'):
                logger.info("Step 3: Storing metadata in vector store...")
                metadata_store.store_patient_metadata(
                    patient_uuid=patient_uuid,
                    semantic_context=semantic_context,
                    intent=intent
                )
            
            # Step 3.5: Retrieve and format memory context (after patient UUID is resolved)
            if patient_uuid and not patient_uuid.startswith("temp-uuid"):
                logger.info("Retrieving patient long-term memory...")
                long_term_memory = memory_manager.get_patient_long_term_memory(
                    patient_uuid=patient_uuid,
                    limit=5
                )
                
                # Get short-term memory
                short_term_memory = session_manager.get_conversation_context(
                    session_id=session_id,
                    limit=5
                )
                
                # Format for LLM
                memory_context = memory_manager.format_memory_for_llm(
                    short_term=short_term_memory,
                    long_term=long_term_memory
                )
                
                # Add memory to semantic context
                semantic_context['memory_context'] = memory_context
                semantic_context['has_history'] = len(long_term_memory.get('medical_records', [])) > 0
                
                logger.info(f"Memory context prepared: {len(long_term_memory.get('medical_records', []))} records")
            
            # Step 4: Context Agent refines context
            logger.info("Step 4: Context Agent refining context...")
            refined_context = context_agent.refine_context(
                patient_uuid=patient_uuid,
                intent=intent,
                semantic_context=semantic_context,
                medical_info=pii_data.get('medical_info', '')
            )
            
            # Step 5: Execution Agent performs task
            logger.info("Step 5: Execution Agent executing task...")
            execution_result = execution_agent.execute_task(
                patient_uuid=patient_uuid,
                intent=intent,
                refined_context=refined_context
            )
            
            # Check if HITL is needed for appointments/followups
            if intent in ['appointment', 'followup']:
                # Generate medical questions
                questions = hitl_manager.generate_medical_questions(
                    intent=intent,
                    semantic_context=semantic_context
                )
                
                # Store pending action
                session_manager.set_pending_action(
                    session_id=session_id,
                    action_type=intent,
                    action_data=execution_result,
                    questions_asked=questions
                )
                
                # Update pending action with patient UUID
                pending = session_manager.get_pending_action(session_id)
                if pending:
                    pending['patient_uuid'] = patient_uuid
                
                # Return first question
                return {
                    "success": True,
                    "message": f"I'll help you with that. First, I need to ask a few questions:\n\n{questions[0]}",
                    "intent": f"{intent}_initiated",
                    "session_id": session_id,
                    "patient_uuid": patient_uuid,
                    "privacy_safe": True,
                    "workflow_steps": [
                        "Intent identified",
                        "HITL workflow initiated",
                        "Collecting medical information"
                    ]
                }
            
            # For non-HITL intents (summary, etc.), proceed normally
            # Step 6: Re-identify patient for output (if not temp UUID)
            if not patient_uuid.startswith("temp-uuid"):
                logger.info("Step 6: Gatekeeper re-identifying patient...")
                identity = identity_vault.reidentify_patient(
                    patient_uuid=patient_uuid,
                    component="coordinator"
                )
                
                if identity:
                    execution_result['patient_name'] = identity['patient_name']
                    execution_result['patient_age'] = identity['age']
                    execution_result['patient_gender'] = identity['gender']
            
            # Step 7: Format final response (add privacy report)
            privacy_report = gatekeeper_output.get('privacy_report')
            
            final_response = {
                "success": True,
                "message": execution_result.get('message', 'Task completed successfully'),
                "intent": intent,
                "patient_uuid": patient_uuid,
                "patient_name": execution_result.get('patient_name', 'N/A'),
                "session_id": session_id,
                "result": execution_result,
                "privacy_safe": True,
                "privacy_report": privacy_report,
                "workflow_steps": [
                    "Gatekeeper: PII detection and pseudonymization",
                    "Identity Resolution: Patient disambiguation",
                    "Metadata Store: UUID-linked context storage",
                    "Context Agent: RAG-based context refinement",
                    "Execution Agent: Task execution",
                    "Gatekeeper: Re-identification for output"
                ]
            }
            
            # Add response to conversation history
            session_manager.add_to_history(
                session_id,
                "assistant",
                final_response.get("message", "")
            )
            
            logger.info("=" * 70)
            logger.info("COORDINATOR: Workflow completed successfully")
            logger.info("=" * 70)
            
            return final_response
            
        except Exception as e:
            logger.error(f"Error in coordinator workflow: {str(e)}")
            return {
                "success": False,
                "message": f"Error processing request: {str(e)}",
                "intent": "error",
                "privacy_safe": True
            }
    
    def _finalize_appointment(self, patient_uuid: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Finalize appointment booking after confirmation."""
        # Store in database
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type='appointment',
            symptoms=action_data.get('symptoms', 'N/A'),
            notes=f"Appointment scheduled with {action_data.get('recommended_doctor', 'TBD')}",
            component="coordinator"
        )
        
        return {
            "message": f"Appointment booked successfully! Reference: {record_id[:8]}",
            "record_id": record_id,
            **action_data
        }

    def _finalize_followup(self, patient_uuid: str, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Finalize follow-up scheduling after confirmation."""
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type='followup',
            notes=f"Follow-up scheduled for {action_data.get('followup_date', 'TBD')}",
            component="coordinator"
        )
        
        return {
            "message": f"Follow-up scheduled successfully! Reference: {record_id[:8]}",
            "record_id": record_id,
            **action_data
        }


# Global instance
coordinator = AgentCoordinator()

# Backward compatibility alias
coordinator_agent = coordinator
