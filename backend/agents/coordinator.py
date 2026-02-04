from typing import Dict, Any
import logging

from agents.gatekeeper import gatekeeper_agent
from agents.context_agent import context_agent
from agents.execution_agent import execution_agent
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
    
    def process_message(self, user_message: str) -> Dict[str, Any]:
        """
        Process user message through multi-agent pipeline.
        
        Args:
            user_message: Raw user input
            
        Returns:
            Final response with re-identified PII
        """
        logger.info("=" * 70)
        logger.info("COORDINATOR: Starting multi-agent workflow")
        logger.info("=" * 70)
        
        try:
            # Step 1: Gatekeeper processes input
            logger.info("Step 1: Gatekeeper processing...")
            gatekeeper_output = gatekeeper_agent.process_message(user_message)
            
            pii_data = gatekeeper_output['pii']
            intent = gatekeeper_output['intent']
            semantic_context = gatekeeper_output['semantic_context']
            
            # Step 2: Pseudonymize patient (if PII exists)
            if pii_data.get('patient_name'):
                logger.info("Step 2: Pseudonymizing patient...")
                patient_uuid, is_new = identity_vault.pseudonymize_patient(
                    patient_name=pii_data['patient_name'],
                    age=pii_data.get('age'),
                    gender=pii_data.get('gender'),
                    component="coordinator"
                )
                logger.info(f"Patient UUID: {patient_uuid} (new: {is_new})")
            else:
                # No PII - generate temp UUID for general queries
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
            
            # Step 7: Format final response
            final_response = {
                "success": True,
                "message": execution_result.get('message', 'Task completed successfully'),
                "intent": intent,
                "patient_uuid": patient_uuid,
                "patient_name": execution_result.get('patient_name', 'N/A'),
                "result": execution_result,
                "privacy_safe": True,
                "workflow_steps": [
                    "Gatekeeper: PII detection and pseudonymization",
                    "Metadata Store: UUID-linked context storage",
                    "Context Agent: RAG-based context refinement",
                    "Execution Agent: Task execution",
                    "Gatekeeper: Re-identification for output"
                ]
            }
            
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


# Global instance
coordinator = AgentCoordinator()

# Backward compatibility alias
coordinator_agent = coordinator
