from typing import Dict, Any, Optional
import logging
import json
import re

from agents.gatekeeper import gatekeeper_agent
from agents.context_agent import context_agent
from agents.execution_agent import execution_agent
from agents.session_manager import session_manager
from agents.hitl_manager import hitl_manager
from agents.memory_manager import memory_manager
from database.identity_vault import identity_vault
import vector_store.metadata_store as _ms_mod
from mcp.bridge import mcp_bridge

logger = logging.getLogger(__name__)


class CoordinatorAgent:
    """Cloud Coordinator Agent that prepares execution plans for the Worker.

    Uses Groq API for intelligent task planning when available, with a
    deterministic rule-based fallback for CI/testing mode.

    PRIVACY GUARANTEE:
    - Receives ONLY pseudonymized UUIDs and semantic context
    - NEVER accesses PII or the Identity Vault directly
    - All planning operates on anonymised data

    The test-suite expects:
      - ``model`` attribute
      - ``coordinate_request(...)``
      - ``_fallback_execution_plan(...)``
    """

    def __init__(self, model: str | None = None):
        self.model = model or "groq-coordinator"
        self._groq_client = None
        self._groq_model = "llama-3.3-70b-versatile"
        self._init_groq()

    # ------------------------------------------------------------------
    # Groq integration
    # ------------------------------------------------------------------

    def _init_groq(self):
        """Initialise the Groq client when credentials are available."""
        try:
            from utils.config import settings
            if settings.testing_mode:
                logger.info("CoordinatorAgent: Testing mode – using rule-based planning")
                self.model = "rule-based"
                return
            from groq import Groq
            self._groq_client = Groq(api_key=settings.groq_api_key)
            logger.info("CoordinatorAgent: Groq client initialised for cloud planning")
        except Exception as e:
            logger.warning(f"CoordinatorAgent: Groq unavailable, using rule-based fallback: {e}")
            self.model = "rule-based"

    def _call_groq(self, prompt: str, system_prompt: str) -> Optional[str]:
        """Call the Groq LLM.  Returns *None* on any failure."""
        if not self._groq_client:
            return None
        try:
            response = self._groq_client.chat.completions.create(
                model=self._groq_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_tokens=512,
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.warning(f"CoordinatorAgent: Groq call failed, falling back: {e}")
            return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def coordinate_request(
        self,
        patient_uuid: str,
        action_type: str,
        semantic_context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create an execution plan for the given action.

        Attempts Groq-based planning first; falls back to deterministic rules.

        PRIVACY: receives only ``patient_uuid`` + ``semantic_context``, never PII.
        """
        valid_actions = {"appointment", "followup", "summary"}
        if action_type not in valid_actions:
            return {
                "success": False,
                "error": f"Invalid action_type: {action_type}",
                "patient_uuid": patient_uuid,
                "action_type": action_type,
                "privacy_safe": True,
            }

        # Try Groq-based planning first
        execution_plan = self._groq_execution_plan(
            patient_uuid=patient_uuid,
            action_type=action_type,
            semantic_context=semantic_context or {},
        )

        # Fallback to deterministic rules when Groq is unavailable
        if execution_plan is None:
            execution_plan = self._fallback_execution_plan(
                action_type=action_type,
                semantic_context=semantic_context or {},
            )

        return {
            "patient_uuid": patient_uuid,
            "action_type": action_type,
            "execution_plan": execution_plan,
            "ready_for_worker": True,
            "privacy_safe": True,
        }

    # ------------------------------------------------------------------
    # Private planning helpers
    # ------------------------------------------------------------------

    def _groq_execution_plan(
        self,
        patient_uuid: str,
        action_type: str,
        semantic_context: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Generate an execution plan with the Groq LLM.

        Returns *None* when the LLM is unavailable or the response cannot be
        parsed, allowing the caller to fall back to rule-based planning.
        """
        system_prompt = (
            "You are a medical task planner. You work ONLY with patient UUIDs – "
            "NEVER real names. Given a task type and semantic context, produce a "
            "JSON execution plan with keys: steps (list of step names), priority "
            "(emergency/urgent/routine), requires_specialist (bool), "
            "estimated_time (int, minutes)."
        )
        prompt = (
            f"Patient UUID: {patient_uuid}\n"
            f"Action: {action_type}\n"
            f"Context: {json.dumps(semantic_context)}\n\n"
            "Return ONLY a JSON object with the execution plan."
        )

        raw = self._call_groq(prompt, system_prompt)
        if raw is None:
            return None

        try:
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if json_match:
                plan = json.loads(json_match.group())
            else:
                plan = json.loads(raw)

            # Validate required keys
            if "steps" in plan and "priority" in plan:
                plan.setdefault("requires_specialist", False)
                plan.setdefault("estimated_time", 30)
                return plan
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(f"CoordinatorAgent: Could not parse Groq plan: {exc}")

        return None

    def _fallback_execution_plan(
        self, action_type: str, semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Deterministic rule-based planning (always available)."""
        urgency = (semantic_context or {}).get("urgency_level", "routine")
        requires_specialist = bool(
            (semantic_context or {}).get("requires_specialist", False)
        )

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
    """Orchestrates the full multi-agent privacy-preserving workflow.

    Workflow:
    1. Gatekeeper: Extract PII, pseudonymise
    2. Identity Resolution: Disambiguate / confirm patient
    3. Metadata Store: Persist UUID-linked context
    4. Memory Manager: Retrieve short-term + long-term memory
    5. Context Agent: Refine context using RAG
    6. Execution Agent: Perform task
    7. Gatekeeper: Re-identify for output
    """

    def __init__(self):
        """Initialise coordinator."""
        logger.info("Agent Coordinator initialized")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_uuid_from_message(message: str) -> Optional[str]:
        """Extract a UUID (full or partial 8-char prefix) from a message."""
        # Full UUID
        full = re.search(
            r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
            message,
            re.IGNORECASE,
        )
        if full:
            return full.group(0)

        # Partial (first 8 hex chars)
        partial = re.search(r'[0-9a-f]{8}', message, re.IGNORECASE)
        if partial:
            return partial.group(0)

        return None

    @staticmethod
    def _base_response(**overrides) -> Dict[str, Any]:
        """Return a response dict with all keys the ChatResponse model expects.

        Every return path in ``process_message`` should go through this helper
        so that ``routes/chat.py`` never encounters missing keys.
        """
        base: Dict[str, Any] = {
            "success": True,
            "message": "",
            "intent": "general",
            "patient_uuid": None,
            "patient_name": None,
            "session_id": None,
            "result": {},
            "privacy_safe": True,
            "workflow_steps": [],
        }
        base.update(overrides)
        return base

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    def process_message(
        self, user_message: str, session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process a user message through the multi-agent pipeline.

        Args:
            user_message: Raw user input
            session_id: Optional session ID for context

        Returns:
            Final response dict (always includes *result* and *workflow_steps*).
        """
        logger.info("=" * 70)
        logger.info("COORDINATOR: Starting multi-agent workflow")
        logger.info("=" * 70)

        try:
            # ----------------------------------------------------------
            # Session setup
            # ----------------------------------------------------------
            if not session_id:
                session_id = session_manager.create_session()

            session = session_manager.get_session(session_id)
            if not session:
                session_id = session_manager.create_session()
                session = session_manager.get_session(session_id)

            # ----------------------------------------------------------
            # Pending confirmation handling
            # ----------------------------------------------------------
            pending_action = session_manager.get_pending_action(session_id)

            if pending_action and pending_action.get('awaiting_confirmation'):
                is_confirmed = hitl_manager.parse_confirmation_response(user_message)

                if is_confirmed:
                    logger.info("User confirmed action – executing…")
                    action_type = pending_action['action_type']
                    action_data = pending_action['action_data']
                    patient_uuid = pending_action.get('patient_uuid')

                    if action_type == 'appointment':
                        result = self._finalize_appointment(patient_uuid, action_data)
                    elif action_type == 'followup':
                        result = self._finalize_followup(patient_uuid, action_data)
                    else:
                        result = {"message": "Action completed"}

                    session_manager.clear_pending_action(session_id)

                    return self._base_response(
                        message=f"✓ {result.get('message', 'Action completed successfully!')}",
                        intent=f"{action_type}_confirmed",
                        patient_uuid=patient_uuid,
                        session_id=session_id,
                        result=result,
                        workflow_steps=["User confirmation received", "Action executed"],
                    )
                else:
                    session_manager.clear_pending_action(session_id)
                    return self._base_response(
                        message="Action cancelled. How else can I help you?",
                        intent="cancelled",
                        session_id=session_id,
                        result={},
                        workflow_steps=["User cancelled action"],
                    )

            # ----------------------------------------------------------
            # Question-gathering phase (HITL)
            # ----------------------------------------------------------
            if pending_action and not pending_action.get('awaiting_confirmation'):
                questions = pending_action.get('questions_asked', [])
                responses = pending_action.get('user_responses', [])

                if len(responses) < len(questions):
                    current_question = questions[len(responses)]
                    session_manager.add_question_response(
                        session_id=session_id,
                        question=current_question,
                        response=user_message,
                    )
                    pending_action = session_manager.get_pending_action(session_id)
                    responses = pending_action.get('user_responses', [])

                if len(responses) >= len(questions):
                    # All questions answered – move to confirmation
                    pending_action['awaiting_confirmation'] = True

                    active_patient = session_manager.get_active_patient(session_id)
                    patient_name = (
                        active_patient.get('patient_name', 'Unknown')
                        if active_patient
                        else 'Unknown'
                    )

                    summary = hitl_manager.create_confirmation_summary(
                        intent=pending_action['action_type'],
                        patient_name=patient_name,
                        action_data=pending_action['action_data'],
                        user_responses=responses,
                    )

                    return self._base_response(
                        message=summary,
                        intent="awaiting_confirmation",
                        session_id=session_id,
                        result={"questions_completed": len(questions)},
                        workflow_steps=["All questions answered", "Awaiting user confirmation"],
                    )
                else:
                    next_question = questions[len(responses)]
                    return self._base_response(
                        message=next_question,
                        intent="collecting_info",
                        session_id=session_id,
                        result={"answered": len(responses), "total": len(questions)},
                        workflow_steps=[f"Collecting response {len(responses)+1}/{len(questions)}"],
                    )

            # ----------------------------------------------------------
            # Disambiguation handling
            # ----------------------------------------------------------
            pending_disambiguation = session_manager.get_pending_disambiguation(session_id)

            if pending_disambiguation:
                selected_uuid = self._extract_uuid_from_message(user_message)

                if selected_uuid:
                    candidates = pending_disambiguation.get("candidates", [])
                    valid_uuids = [c["patient_uuid"] for c in candidates]

                    matching_uuid = None
                    for uuid in valid_uuids:
                        if uuid.startswith(selected_uuid) or uuid == selected_uuid:
                            matching_uuid = uuid
                            break

                    if matching_uuid:
                        patient_name = next(
                            c["patient_name"]
                            for c in candidates
                            if c["patient_uuid"] == matching_uuid
                        )
                        session_manager.set_active_patient(session_id, matching_uuid, patient_name)
                        session_manager.clear_pending_disambiguation(session_id)

                        return self._base_response(
                            message=f"Selected patient {patient_name} (UUID: {matching_uuid[:8]}…). How can I help?",
                            intent="patient_selected",
                            patient_uuid=matching_uuid,
                            patient_name=patient_name,
                            session_id=session_id,
                            result={"selected_uuid": matching_uuid},
                            workflow_steps=["Patient identity resolved"],
                        )
                    else:
                        return self._base_response(
                            success=False,
                            message="Invalid selection. Please select a valid patient UUID from the list.",
                            intent="error",
                            session_id=session_id,
                            result={},
                            workflow_steps=["Invalid UUID selection"],
                        )
                else:
                    return self._base_response(
                        success=False,
                        message="Please select a patient by providing their UUID.",
                        intent="disambiguation_pending",
                        session_id=session_id,
                        disambiguation_data=pending_disambiguation,
                        result={},
                        workflow_steps=["Awaiting patient selection"],
                    )

            # ----------------------------------------------------------
            # Conversation history & context-switch detection
            # ----------------------------------------------------------
            session_manager.add_to_history(session_id, "user", user_message)

            active_patient = session_manager.get_active_patient(session_id)
            if active_patient:
                is_context_switch = memory_manager.detect_context_switch(
                    current_message=user_message,
                    active_patient_name=active_patient.get('patient_name'),
                )
                if is_context_switch:
                    logger.info("Context switch detected – clearing active patient")
                    session_manager.set_active_patient(session_id, None, None)
                    active_patient = None

            # ----------------------------------------------------------
            # Step 1: Gatekeeper processes input
            # ----------------------------------------------------------
            logger.info("Step 1: Gatekeeper processing…")
            gatekeeper_output = gatekeeper_agent.process_message(user_message)

            pii_data = gatekeeper_output['pii']
            intent = gatekeeper_output['intent']
            semantic_context = gatekeeper_output['semantic_context']

            # ----------------------------------------------------------
            # Step 2: Resolve patient identity
            # ----------------------------------------------------------
            if pii_data.get('patient_name'):
                logger.info("Step 2: Resolving patient identity…")

                resolution = identity_vault.resolve_patient_identity(
                    patient_name=pii_data['patient_name'],
                    age=pii_data.get('age'),
                    gender=pii_data.get('gender'),
                    component="coordinator",
                )

                if resolution["status"] == "needs_disambiguation":
                    session_manager.set_pending_disambiguation(session_id, resolution)

                    candidates_text = "\n".join([
                        f"- {c['patient_name']} (UUID: {c['patient_uuid'][:8]}…, "
                        f"Age: {c.get('age', 'N/A')}, Gender: {c.get('gender', 'N/A')}, "
                        f"Last seen: {c.get('last_accessed', 'Never')})"
                        for c in resolution["candidates"]
                    ])

                    return self._base_response(
                        message=(
                            f"{resolution['message']}\n\n{candidates_text}\n\n"
                            "Please reply with the patient UUID."
                        ),
                        intent="disambiguation_required",
                        session_id=session_id,
                        disambiguation_data=resolution,
                        result={},
                        workflow_steps=["Multiple patients found", "Requesting user disambiguation"],
                    )

                elif resolution["status"] == "needs_confirmation":
                    return self._base_response(
                        message=resolution["message"] + " Please confirm (yes/no).",
                        intent="confirmation_required",
                        session_id=session_id,
                        pending_confirmation={
                            "action": "create_patient",
                            "patient_name": resolution["patient_name"],
                            "age": resolution.get("age"),
                            "gender": resolution.get("gender"),
                        },
                        result={},
                        workflow_steps=["New patient detected", "Requesting user confirmation"],
                    )

                elif resolution["status"] == "resolved":
                    patient_uuid = resolution["patient_uuid"]
                    session_manager.set_active_patient(
                        session_id, patient_uuid, resolution["patient_name"]
                    )
                    logger.info(f"Patient resolved: {patient_uuid}")

                else:
                    logger.error(f"Unknown resolution status: {resolution['status']}")
                    patient_uuid = "temp-uuid-" + str(hash(user_message))[:8]
            else:
                active_patient = session_manager.get_active_patient(session_id)
                if active_patient:
                    patient_uuid = active_patient["patient_uuid"]
                    logger.info(f"Using active patient from session: {patient_uuid}")
                else:
                    patient_uuid = "temp-uuid-" + str(hash(user_message))[:8]
                    logger.info("No PII detected, using temporary UUID")

            # ----------------------------------------------------------
            # Step 3: Store metadata in vector store
            # ----------------------------------------------------------
            if _ms_mod.metadata_store and pii_data.get('patient_name'):
                logger.info("Step 3: Storing metadata in vector store…")
                _ms_mod.metadata_store.store_patient_metadata(
                    patient_uuid=patient_uuid,
                    semantic_context=semantic_context,
                    intent=intent,
                )

            # ----------------------------------------------------------
            # Step 3.5: Retrieve & format memory context
            # ----------------------------------------------------------
            if patient_uuid and not patient_uuid.startswith("temp-uuid"):
                logger.info("Retrieving patient long-term memory…")
                long_term_memory = memory_manager.get_patient_long_term_memory(
                    patient_uuid=patient_uuid, limit=5
                )

                short_term_memory = session_manager.get_conversation_context(
                    session_id=session_id, limit=5
                )

                memory_context = memory_manager.format_memory_for_llm(
                    short_term=short_term_memory, long_term=long_term_memory
                )

                semantic_context['memory_context'] = memory_context
                semantic_context['has_history'] = (
                    len(long_term_memory.get('medical_records', [])) > 0
                )
                logger.info(
                    f"Memory context prepared: "
                    f"{len(long_term_memory.get('medical_records', []))} records"
                )

            # ----------------------------------------------------------
            # Step 4: MCP Bridge validates outgoing -> Context Agent
            # ----------------------------------------------------------
            logger.info("Step 4a: MCP Bridge validating outgoing payload…")
            context_payload = {
                "patient_uuid": patient_uuid,
                "intent": intent,
                "semantic_context": semantic_context,
                "medical_info": pii_data.get('medical_info', ''),
            }
            mcp_bridge.route_to_cloud(
                agent_name="context_agent",
                patient_uuid=patient_uuid,
                payload=context_payload,
            )

            logger.info("Step 4b: Context Agent refining context…")
            refined_context = context_agent.refine_context(
                patient_uuid=patient_uuid,
                intent=intent,
                semantic_context=semantic_context,
                medical_info=pii_data.get('medical_info', ''),
            )

            mcp_bridge.route_from_cloud(
                agent_name="context_agent",
                patient_uuid=patient_uuid,
                response=refined_context,
            )

            # ----------------------------------------------------------
            # Step 5: MCP Bridge validates outgoing -> Execution Agent
            # ----------------------------------------------------------
            logger.info("Step 5a: MCP Bridge validating outgoing payload…")
            execution_payload = {
                "patient_uuid": patient_uuid,
                "intent": intent,
                "refined_context": refined_context,
            }
            mcp_bridge.route_to_cloud(
                agent_name="execution_agent",
                patient_uuid=patient_uuid,
                payload=execution_payload,
            )

            logger.info("Step 5b: Execution Agent executing task…")
            execution_result = execution_agent.execute_task(
                patient_uuid=patient_uuid,
                intent=intent,
                refined_context=refined_context,
            )

            mcp_bridge.route_from_cloud(
                agent_name="execution_agent",
                patient_uuid=patient_uuid,
                response=execution_result,
            )

            # ----------------------------------------------------------
            # HITL: appointments / follow-ups need user confirmation
            # ----------------------------------------------------------
            if intent in ['appointment', 'followup']:
                questions = hitl_manager.generate_medical_questions(
                    intent=intent, semantic_context=semantic_context
                )

                session_manager.set_pending_action(
                    session_id=session_id,
                    action_type=intent,
                    action_data=execution_result,
                    questions_asked=questions,
                )

                pending = session_manager.get_pending_action(session_id)
                if pending:
                    pending['patient_uuid'] = patient_uuid

                return self._base_response(
                    message=(
                        "I'll help you with that. First, I need to ask a few "
                        f"questions:\n\n{questions[0]}"
                    ),
                    intent=f"{intent}_initiated",
                    session_id=session_id,
                    patient_uuid=patient_uuid,
                    result={"hitl_questions": len(questions)},
                    workflow_steps=[
                        "Intent identified",
                        "HITL workflow initiated",
                        "Collecting medical information",
                    ],
                )

            # ----------------------------------------------------------
            # Step 6: Re-identify patient for output
            # ----------------------------------------------------------
            if not patient_uuid.startswith("temp-uuid"):
                logger.info("Step 6: Gatekeeper re-identifying patient…")
                identity = identity_vault.reidentify_patient(
                    patient_uuid=patient_uuid, component="coordinator"
                )
                if identity:
                    execution_result['patient_name'] = identity['patient_name']
                    execution_result['patient_age'] = identity['age']
                    execution_result['patient_gender'] = identity['gender']

            # ----------------------------------------------------------
            # Step 7: Format final response
            # ----------------------------------------------------------
            privacy_report = gatekeeper_output.get('privacy_report')
            mcp_compliance = mcp_bridge.get_compliance_report()

            final_response = self._base_response(
                message=execution_result.get('message', 'Task completed successfully'),
                intent=intent,
                patient_uuid=patient_uuid,
                patient_name=execution_result.get('patient_name', 'N/A'),
                session_id=session_id,
                result=execution_result,
                privacy_report=privacy_report,
                mcp_compliance=mcp_compliance,
                workflow_steps=[
                    "Gatekeeper: PII detection and pseudonymization",
                    "Identity Resolution: Patient disambiguation",
                    "Metadata Store: UUID-linked context storage",
                    "MCP Bridge: Privacy validation (outgoing)",
                    "Context Agent: RAG-based context refinement",
                    "MCP Bridge: Privacy validation (incoming)",
                    "Execution Agent: Task execution",
                    "MCP Bridge: Privacy validation (response)",
                    "Gatekeeper: Re-identification for output",
                ],
            )

            session_manager.add_to_history(
                session_id, "assistant", final_response.get("message", "")
            )

            logger.info("=" * 70)
            logger.info("COORDINATOR: Workflow completed successfully")
            logger.info("=" * 70)

            return final_response

        except Exception as e:
            logger.error(f"Error in coordinator workflow: {str(e)}")
            return self._base_response(
                success=False,
                message=f"Error processing request: {str(e)}",
                intent="error",
                result={},
                workflow_steps=["Error in processing pipeline"],
            )

    # ------------------------------------------------------------------
    # Finalisation helpers
    # ------------------------------------------------------------------

    def _finalize_appointment(
        self, patient_uuid: str, action_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Finalise appointment booking after user confirmation."""
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type='appointment',
            symptoms=action_data.get('symptoms', 'N/A'),
            notes=f"Appointment scheduled with {action_data.get('recommended_doctor', 'TBD')}",
            component="coordinator",
        )
        return {
            "message": f"Appointment booked successfully! Reference: {record_id[:8]}",
            "record_id": record_id,
            **action_data,
        }

    def _finalize_followup(
        self, patient_uuid: str, action_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Finalise follow-up scheduling after user confirmation."""
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type='followup',
            notes=f"Follow-up scheduled for {action_data.get('followup_date', 'TBD')}",
            component="coordinator",
        )
        return {
            "message": f"Follow-up scheduled successfully! Reference: {record_id[:8]}",
            "record_id": record_id,
            **action_data,
        }


# Global instances
coordinator = AgentCoordinator()

# Backward compatibility alias
coordinator_agent = coordinator
