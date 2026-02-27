"""
Coordinator Agent – Orchestrates all agents, manages conversation flow,
and handles intent detection WITHOUT resetting mid-workflow.
"""

from typing import Dict, Any, Optional, List
import logging
import re

from agents.session_manager import session_manager
from agents.hitl_manager import hitl_manager

logger = logging.getLogger(__name__)


class CoordinatorAgent:
    """Deterministic coordinator for test/API use (no external API calls)."""

    def __init__(self, model: str | None = None):
        self.model = model or "rule-based"

    def coordinate_request(self, patient_uuid: str, action_type: str,
                           semantic_context: Dict[str, Any]) -> Dict[str, Any]:
        valid_actions = {"appointment", "followup", "summary"}
        if action_type not in valid_actions:
            return {"success": False, "error": f"Invalid action_type: {action_type}",
                    "patient_uuid": patient_uuid, "action_type": action_type, "privacy_safe": True}
        plan = self._fallback_execution_plan(action_type, semantic_context or {})
        return {"patient_uuid": patient_uuid, "action_type": action_type,
                "execution_plan": plan, "ready_for_worker": True, "privacy_safe": True}

    def _fallback_execution_plan(self, action_type: str, semantic_context: Dict[str, Any]) -> Dict[str, Any]:
        urgency = (semantic_context or {}).get("urgency_level", "routine")
        requires_specialist = bool((semantic_context or {}).get("requires_specialist", False))
        if action_type == "appointment":
            steps, estimated_time = ["validate", "schedule", "confirm"], 3
        elif action_type == "followup":
            steps, estimated_time = ["retrieve", "schedule", "confirm"], 2
        elif action_type == "summary":
            steps, estimated_time = ["gather", "generate", "format"], 2
        else:
            steps, estimated_time = ["validate"], 1
        return {"steps": steps, "priority": urgency,
                "requires_specialist": requires_specialist, "estimated_time": estimated_time}


class Coordinator:
    """
    Main Coordinator that orchestrates the multi-agent workflow.
    
    Workflow:
    1. Check session state (is workflow active?)
    2. If no workflow -> detect intent -> start workflow
    3. If workflow active -> continue workflow (NO re-detection)
    4. Anonymize with Gatekeeper
    5. Get context from Context Agent
    6. Route to appropriate handler
    7. Return response
    """

    def __init__(self):
        self.session_manager = session_manager
        self._intent_detection_count: Dict[str, int] = {}
        logger.info("Coordinator initialized")

    def _get_gatekeeper(self):
        from agents.gatekeeper import gatekeeper_agent
        return gatekeeper_agent

    def _get_context_agent(self):
        from agents.context_agent import context_agent
        return context_agent

    def _get_execution_agent(self):
        from agents.execution_agent import execution_agent
        return execution_agent

    def _get_identity_vault(self):
        from database.identity_vault import identity_vault
        return identity_vault

    def _get_memory_manager(self):
        from agents.memory_manager import memory_manager
        return memory_manager

    def _get_metadata_store(self):
        from vector_store.metadata_store import metadata_store
        return metadata_store

    async def detect_intent(self, message: str) -> str:
        """Detect user intent from message. ONLY called when workflow is 'none'."""
        msg_lower = message.lower()
        if any(w in msg_lower for w in ['appointment', 'book', 'schedule an appointment']):
            return "appointment"
        if any(w in msg_lower for w in ['follow-up', 'followup', 'follow up', 'how is', 'check on']):
            return "followup"
        if any(w in msg_lower for w in ['summary', 'summarize', 'report', 'history']):
            return "summary"
        return "general"

    async def resolve_patient(self, session_id: str, message: str) -> dict:
        """Resolve patient identity from message."""
        vault = self._get_identity_vault()
        gatekeeper = self._get_gatekeeper()

        # Extract patient name using regex
        name = self._extract_patient_name(message)
        if not name:
            return {"action": "not_found", "patients": [], "response": "Who is this appointment for?"}

        # Search in identity vault
        candidates = vault.find_patients_by_name(name, component="coordinator")
        if len(candidates) == 1:
            p = candidates[0]
            self.session_manager.set_active_patient(session_id, p["patient_uuid"], p["patient_name"])
            return {"action": "found_one", "patients": candidates,
                    "response": f"Found patient {p['patient_name']}."}
        elif len(candidates) > 1:
            return {"action": "found_multiple", "patients": candidates,
                    "response": f"Found {len(candidates)} patients named '{name}'. Please select one."}
        else:
            return {"action": "not_found", "patients": [],
                    "response": f"No patient found with name '{name}'. Would you like to create a new patient?"}

    def _extract_patient_name(self, message: str) -> Optional[str]:
        """Extract a patient name from a message using heuristics."""
        patterns = [
            r'(?:for|patient)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r"(?:I'm|I am|my name is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return match.group(1)
        # Fallback: look for capitalized words that aren't common
        skip = {'Hi', 'Hello', 'Please', 'Book', 'Schedule', 'Need', 'Want',
                'Can', 'Show', 'Get', 'How', 'What', 'The', 'Yes', 'No',
                'Cardiology', 'Tomorrow', 'Today', 'Monday', 'Tuesday',
                'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'}
        words = message.split()
        for word in words:
            clean = word.strip('.,!?')
            if clean and clean[0].isupper() and clean not in skip and len(clean) > 2:
                if not any(w in clean.lower() for w in ['appointment', 'follow', 'summary']):
                    return clean
        return None

    async def process_message(self, session_id: str, user_message: str) -> dict:
        """
        Main entry point for processing user messages.
        
        Returns: {
            "response": str,
            "privacy_events": List[dict],
            "session_state": dict,
            "requires_action": bool
        }
        """
        logger.info("=" * 70)
        logger.info("COORDINATOR: Processing message")
        logger.info("=" * 70)

        try:
            # Get or create session
            session = self.session_manager.get_session(session_id)
            if not session:
                session_id = self.session_manager.create_session()
                session = self.session_manager.get_session(session_id)

            # Add to conversation history
            self.session_manager.add_to_history(session_id, "user", user_message)

            active_workflow = session.get("active_workflow", "none")
            workflow_stage = session.get("workflow_stage", "none")

            # CRITICAL: If workflow is active, continue it - DO NOT re-detect intent
            if active_workflow != "none":
                logger.info(f"Continuing active workflow: {active_workflow}, stage: {workflow_stage}")
                result = await self._continue_workflow(
                    session_id, session, user_message, active_workflow, workflow_stage
                )
                return result

            # No active workflow - detect intent
            intent = await self.detect_intent(user_message)
            self._intent_detection_count[session_id] = self._intent_detection_count.get(session_id, 0) + 1
            logger.info(f"Detected intent: {intent}")

            # Handle based on intent
            if intent in ("appointment", "followup", "summary"):
                # Start workflow
                self.session_manager.set_workflow(session_id, intent, "resolving_patient")
                # Try to resolve patient from message
                resolution = await self.resolve_patient(session_id, user_message)
                privacy_events = []

                if resolution["action"] == "found_one":
                    # Patient found, advance to next stage
                    if intent == "appointment":
                        self.session_manager.update_session(
                            session_id, workflow_stage="collecting_specialty")
                        response = f"{resolution['response']} What specialty do you need? (e.g., Cardiology, Dermatology)"
                    elif intent == "followup":
                        patient_uuid = resolution["patients"][0]["patient_uuid"]
                        self.session_manager.add_workflow_data(session_id, "patient_uuid", patient_uuid)
                        # Retrieve history immediately
                        exec_agent = self._get_execution_agent()
                        self.session_manager.update_session(session_id, workflow_stage="retrieving_history")
                        followup_data = await exec_agent.get_patient_followup(patient_uuid)
                        self.session_manager.add_workflow_data(session_id, "followup_data", {
                            "total_interactions": followup_data.get("total_interactions", 0),
                            "no_history": followup_data.get("no_history", False),
                            "follow_up_summary": followup_data.get("follow_up_summary", ""),
                        })
                        if followup_data.get("no_history"):
                            self.session_manager.update_session(session_id, workflow_stage="collecting_updates")
                            response = (
                                f"{resolution['response']} No previous history found. "
                                f"Would you like to provide a status update?"
                            )
                        else:
                            self.session_manager.update_session(session_id, workflow_stage="answering_query")
                            summary_text = followup_data.get("follow_up_summary", "No summary.")
                            response = (
                                f"{resolution['response']}\n\n{summary_text}\n\n"
                                f"Would you like to provide a status update, or do you have questions?"
                            )
                    else:
                        # Summary - generate using SummaryWorker
                        patient_uuid = resolution["patients"][0]["patient_uuid"]
                        self.session_manager.add_workflow_data(session_id, "patient_uuid", patient_uuid)
                        from agents.worker import SummaryWorker
                        worker = SummaryWorker()
                        summary = await worker.generate_patient_summary(patient_uuid)
                        self.session_manager.complete_workflow(session_id)
                        response = summary.get("summary_text", "No summary available.")

                elif resolution["action"] == "found_multiple":
                    response = resolution["response"]
                    self.session_manager.set_pending_disambiguation(session_id, {
                        "candidates": resolution["patients"]
                    })
                else:
                    response = resolution["response"]

                return self._build_response(response, privacy_events, session_id)

            else:
                # General query
                return self._build_response(
                    "I can help you with appointments, follow-ups, or medical summaries. What would you like to do?",
                    [], session_id
                )

        except Exception as e:
            logger.error(f"Error in coordinator: {e}")
            return self._build_response(f"Error processing request: {str(e)}", [], session_id, success=False)

    async def _continue_workflow(self, session_id: str, session: dict,
                                  user_message: str, workflow: str, stage: str) -> dict:
        """Continue an active workflow without re-detecting intent."""
        msg_lower = user_message.lower().strip()

        # Check for cancellation at any stage
        if msg_lower in ('cancel', 'stop', 'abort', 'nevermind', 'quit'):
            self.session_manager.complete_workflow(session_id)
            return self._build_response("Workflow cancelled. How else can I help?", [], session_id)

        if workflow == "appointment":
            return await self._continue_appointment_workflow(session_id, session, user_message, stage)
        elif workflow == "followup":
            return await self._continue_followup_workflow(session_id, session, user_message, stage)
        elif workflow == "summary":
            return await self._continue_summary_workflow(session_id, session, user_message, stage)
        else:
            self.session_manager.complete_workflow(session_id)
            return self._build_response("Workflow completed.", [], session_id)

    async def _continue_appointment_workflow(self, session_id: str, session: dict,
                                              user_message: str, stage: str) -> dict:
        """Handle appointment workflow stages."""
        exec_agent = self._get_execution_agent()

        if stage == "resolving_patient":
            resolution = await self.resolve_patient(session_id, user_message)
            if resolution["action"] == "found_one":
                self.session_manager.update_session(session_id, workflow_stage="collecting_specialty")
                return self._build_response(
                    f"{resolution['response']} What specialty do you need?", [], session_id)
            elif resolution["action"] == "found_multiple":
                self.session_manager.set_pending_disambiguation(session_id, {
                    "candidates": resolution["patients"]})
                return self._build_response(resolution["response"], [], session_id)
            else:
                return self._build_response(resolution["response"], [], session_id)

        elif stage == "collecting_specialty":
            specialty = user_message.strip()
            valid = exec_agent.validate_specialty(specialty)
            if valid:
                self.session_manager.add_workflow_data(session_id, "specialty", specialty.lower())
                self.session_manager.update_session(session_id, workflow_stage="collecting_date")
                return self._build_response(
                    f"Specialty set to {specialty}. What date would you like? (e.g., Tomorrow, next Monday)", [], session_id)
            else:
                available = exec_agent.get_available_specialties()
                return self._build_response(
                    f"'{specialty}' is not a valid specialty. Available: {', '.join(available)}", [], session_id)

        elif stage == "collecting_date":
            date_result = exec_agent.parse_date(user_message)
            if date_result["valid"]:
                self.session_manager.add_workflow_data(session_id, "date", date_result["date"])
                self.session_manager.update_session(session_id, workflow_stage="collecting_time")
                return self._build_response(
                    f"Date set to {date_result['date']}. What time would you prefer? (9 AM - 5 PM)", [], session_id)
            else:
                return self._build_response(date_result["error"], [], session_id)

        elif stage == "collecting_time":
            time_result = exec_agent.parse_time(user_message)
            if time_result["valid"]:
                self.session_manager.add_workflow_data(session_id, "time", time_result["time"])
                self.session_manager.update_session(session_id, workflow_stage="collecting_reason")
                return self._build_response(
                    f"Time set to {time_result['time']}. What is the reason for your visit?", [], session_id)
            else:
                return self._build_response(time_result["error"], [], session_id)

        elif stage == "collecting_reason":
            self.session_manager.add_workflow_data(session_id, "reason", user_message)
            self.session_manager.update_session(session_id, workflow_stage="confirmation")
            # Build confirmation summary
            wf_data = self.session_manager.get_workflow_data(session_id)
            active_patient = self.session_manager.get_active_patient(session_id)
            patient_name = active_patient.get("patient_name", "Unknown") if active_patient else "Unknown"
            patient_uuid = active_patient.get("patient_uuid", "") if active_patient else ""

            # Assign doctor
            doctor = exec_agent.assign_doctor(wf_data.get("specialty", "general"))

            self.session_manager.add_workflow_data(session_id, "doctor", doctor)
            self.session_manager.add_workflow_data(session_id, "patient_uuid", patient_uuid)

            summary = (
                f"Please confirm the appointment details:\n"
                f"- Patient: {patient_name}\n"
                f"- Specialty: {wf_data.get('specialty', 'N/A')}\n"
                f"- Date: {wf_data.get('date', 'N/A')}\n"
                f"- Time: {wf_data.get('time', 'N/A')}\n"
                f"- Reason: {user_message}\n"
                f"- Doctor: {doctor.get('name', 'TBD')}\n\n"
                f"Reply 'confirm' to book or 'cancel' to abort."
            )
            return self._build_response(summary, [], session_id, requires_action=True)

        elif stage == "confirmation":
            if user_message.lower().strip() in ('confirm', 'yes', 'ok', 'proceed', 'sure', 'yeah'):
                wf_data = self.session_manager.get_workflow_data(session_id)
                result = await exec_agent.book_appointment(
                    patient_uuid=wf_data.get("patient_uuid", ""),
                    doctor_specialty=wf_data.get("specialty", "general"),
                    preferred_date=wf_data.get("date", ""),
                    preferred_time=wf_data.get("time", ""),
                    reason=wf_data.get("reason", ""),
                    additional_info={"doctor": wf_data.get("doctor", {})}
                )
                # Store in context agent
                ctx_agent = self._get_context_agent()
                try:
                    ctx_agent.store_interaction(
                        patient_uuid=wf_data.get("patient_uuid", ""),
                        interaction_type="appointment",
                        content=f"Appointment: {wf_data.get('specialty')} on {wf_data.get('date')} at {wf_data.get('time')} - {wf_data.get('reason')}",
                        metadata={"appointment_id": result.get("appointment_id", "")}
                    )
                except Exception:
                    pass

                self.session_manager.complete_workflow(session_id)
                return self._build_response(result.get("message", "Appointment booked!"), [], session_id)
            else:
                # Allow modification or cancel
                if user_message.lower().strip() in ('no', 'cancel', 'abort'):
                    self.session_manager.complete_workflow(session_id)
                    return self._build_response("Appointment cancelled.", [], session_id)
                else:
                    return self._build_response(
                        "Please reply 'confirm' to book or 'cancel' to abort.", [], session_id)

        else:
            self.session_manager.complete_workflow(session_id)
            return self._build_response("Workflow completed.", [], session_id)

    async def _continue_followup_workflow(self, session_id: str, session: dict,
                                           user_message: str, stage: str) -> dict:
        """Handle followup workflow stages (enhanced for Prompt 7)."""
        exec_agent = self._get_execution_agent()

        if stage == "resolving_patient":
            resolution = await self.resolve_patient(session_id, user_message)
            if resolution["action"] == "found_one":
                patient_uuid = resolution["patients"][0]["patient_uuid"]
                self.session_manager.add_workflow_data(session_id, "patient_uuid", patient_uuid)
                # Retrieve patient history immediately
                self.session_manager.update_session(session_id, workflow_stage="retrieving_history")
                followup_data = await exec_agent.get_patient_followup(patient_uuid)
                self.session_manager.add_workflow_data(session_id, "followup_data", {
                    "total_interactions": followup_data.get("total_interactions", 0),
                    "no_history": followup_data.get("no_history", False),
                    "follow_up_summary": followup_data.get("follow_up_summary", ""),
                })

                if followup_data.get("no_history"):
                    self.session_manager.update_session(session_id, workflow_stage="collecting_updates")
                    return self._build_response(
                        f"{resolution['response']} No previous history found for this patient. "
                        f"Would you like to provide a status update or any new information?",
                        [], session_id)

                self.session_manager.update_session(session_id, workflow_stage="answering_query")
                summary = followup_data.get("follow_up_summary", "No summary available.")
                return self._build_response(
                    f"{resolution['response']}\n\n{summary}\n\n"
                    f"Would you like to provide a status update, or do you have any questions?",
                    [], session_id)
            elif resolution["action"] == "found_multiple":
                self.session_manager.set_pending_disambiguation(session_id, {
                    "candidates": resolution["patients"]})
                return self._build_response(resolution["response"], [], session_id)
            else:
                return self._build_response(resolution["response"], [], session_id)

        elif stage == "retrieving_history":
            # User provided additional info during retrieval
            wf_data = self.session_manager.get_workflow_data(session_id)
            patient_uuid = wf_data.get("patient_uuid", "")
            followup_data = await exec_agent.get_patient_followup(patient_uuid, question=user_message)
            self.session_manager.update_session(session_id, workflow_stage="answering_query")
            summary = followup_data.get("follow_up_summary", "No summary available.")
            return self._build_response(
                f"{summary}\n\nWould you like to provide a status update?",
                [], session_id)

        elif stage == "answering_query":
            # Check if user is providing an update or asking a question
            msg_lower = user_message.lower()
            is_update = any(w in msg_lower for w in [
                "better", "worse", "gone", "still", "improved", "update",
                "feeling", "resolved", "new symptom", "changed"
            ])
            if is_update:
                self.session_manager.add_workflow_data(session_id, "status_update", user_message)
                # Extract updates for confirmation
                updates = exec_agent._extract_status_updates(user_message)
                self.session_manager.add_workflow_data(session_id, "updates_extracted", updates)
                self.session_manager.update_session(session_id, workflow_stage="confirmation")

                active_patient = self.session_manager.get_active_patient(session_id)
                patient_name = active_patient.get("patient_name", "Unknown") if active_patient else "Unknown"

                update_summary = f"Status update for {patient_name}:\n"
                for upd in updates:
                    update_summary += f"  • {upd.get('symptom', 'general')}: {upd.get('status', 'updated')}\n"
                update_summary += "\nReply 'confirm' to save or 'cancel' to abort."

                return self._build_response(update_summary, [], session_id, requires_action=True)
            else:
                # It's a question - try to answer from history
                wf_data = self.session_manager.get_workflow_data(session_id)
                patient_uuid = wf_data.get("patient_uuid", "")
                followup_data = await exec_agent.get_patient_followup(patient_uuid, question=user_message)
                summary = followup_data.get("follow_up_summary", "No information found.")
                return self._build_response(
                    f"{summary}\n\nAnything else? You can provide updates or ask more questions. "
                    f"Type 'done' to finish.",
                    [], session_id)

        elif stage == "collecting_updates":
            self.session_manager.add_workflow_data(session_id, "status_update", user_message)
            updates = exec_agent._extract_status_updates(user_message)
            self.session_manager.add_workflow_data(session_id, "updates_extracted", updates)
            self.session_manager.update_session(session_id, workflow_stage="confirmation")

            active_patient = self.session_manager.get_active_patient(session_id)
            patient_name = active_patient.get("patient_name", "Unknown") if active_patient else "Unknown"

            update_summary = f"Status update for {patient_name}:\n"
            for upd in updates:
                update_summary += f"  • {upd.get('symptom', 'general')}: {upd.get('status', 'updated')}\n"
            update_summary += "\nReply 'confirm' to save or 'cancel' to abort."

            return self._build_response(update_summary, [], session_id, requires_action=True)

        elif stage == "confirmation":
            confirmed = hitl_manager.parse_confirmation_response(user_message)
            if confirmed:
                wf_data = self.session_manager.get_workflow_data(session_id)
                patient_uuid = wf_data.get("patient_uuid", "")
                status_update = wf_data.get("status_update", "")
                result = await exec_agent.update_patient_status(
                    patient_uuid=patient_uuid,
                    status_update=status_update,
                )
                self.session_manager.complete_workflow(session_id)
                return self._build_response(
                    f"Status update saved successfully! {result.get('message', '')}",
                    [], session_id)
            elif user_message.lower().strip() in ('no', 'cancel', 'abort'):
                self.session_manager.complete_workflow(session_id)
                return self._build_response("Follow-up cancelled.", [], session_id)
            else:
                return self._build_response(
                    "Please reply 'confirm' to save or 'cancel' to abort.",
                    [], session_id)

        elif stage == "storing_updates":
            self.session_manager.complete_workflow(session_id)
            return self._build_response("Updates stored successfully!", [], session_id)

        else:
            if user_message.lower().strip() == "done":
                self.session_manager.complete_workflow(session_id)
                return self._build_response("Follow-up completed. How else can I help?", [], session_id)
            self.session_manager.complete_workflow(session_id)
            return self._build_response("Follow-up workflow completed.", [], session_id)

    async def _continue_summary_workflow(self, session_id: str, session: dict,
                                          user_message: str, stage: str) -> dict:
        """Handle summary workflow stages (Prompt 8)."""
        if stage == "resolving_patient":
            resolution = await self.resolve_patient(session_id, user_message)
            if resolution["action"] == "found_one":
                patient_uuid = resolution["patients"][0]["patient_uuid"]
                self.session_manager.add_workflow_data(session_id, "patient_uuid", patient_uuid)
                self.session_manager.update_session(session_id, workflow_stage="generating")

                # Generate summary
                from agents.worker import SummaryWorker
                worker = SummaryWorker()
                summary = await worker.generate_patient_summary(patient_uuid, summary_type="full")

                self.session_manager.complete_workflow(session_id)
                return self._build_response(summary.get("summary_text", "No summary available."), [], session_id)
            elif resolution["action"] == "found_multiple":
                self.session_manager.set_pending_disambiguation(session_id, {
                    "candidates": resolution["patients"]})
                return self._build_response(resolution["response"], [], session_id)
            else:
                return self._build_response(resolution["response"], [], session_id)

        elif stage == "generating":
            # If we get here, user wants a specific type of summary
            wf_data = self.session_manager.get_workflow_data(session_id)
            patient_uuid = wf_data.get("patient_uuid", "")

            from agents.worker import SummaryWorker
            worker = SummaryWorker()
            summary = await worker.generate_specific_summary(patient_uuid, query=user_message)

            self.session_manager.complete_workflow(session_id)
            return self._build_response(summary.get("summary_text", "No results found."), [], session_id)

        else:
            self.session_manager.complete_workflow(session_id)
            return self._build_response("Summary complete.", [], session_id)

    def _build_response(self, response: str, privacy_events: list,
                         session_id: str, success: bool = True,
                         requires_action: bool = False) -> dict:
        session = self.session_manager.get_session(session_id) or {}
        return {
            "response": response,
            "privacy_events": privacy_events,
            "session_state": session,
            "requires_action": requires_action,
            "success": success,
            "session_id": session_id,
        }

    def get_intent_detection_count(self, session_id: str) -> int:
        """Get how many times intent detection ran for a session."""
        return self._intent_detection_count.get(session_id, 0)


class AgentCoordinator:
    """
    Legacy coordinator that processes messages through multi-agent pipeline.
    Kept for backward compatibility with existing routes.
    """

    def __init__(self):
        self._pending_confirmations: Dict[str, Dict[str, Any]] = {}
        logger.info("Agent Coordinator initialized")

    def _extract_uuid_from_message(self, message: str) -> Optional[str]:
        uuid_pattern = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
        match = re.search(uuid_pattern, message, re.IGNORECASE)
        if match:
            return match.group(0)
        return None

    def _is_confirmation(self, message: str) -> bool:
        """Check if the message is a confirmation (yes/confirm/ok)."""
        return message.strip().lower() in (
            'yes', 'y', 'confirm', 'ok', 'sure', 'yeah', 'yep', 'proceed', 'create'
        )

    def _is_denial(self, message: str) -> bool:
        """Check if the message is a denial (no/cancel)."""
        return message.strip().lower() in (
            'no', 'n', 'cancel', 'abort', 'nope', 'nevermind', 'stop'
        )

    def process_message(self, user_message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Process user message through multi-agent pipeline (synchronous)."""
        from agents.gatekeeper import gatekeeper_agent, _age_to_bucket
        from agents.context_agent import context_agent
        from agents.execution_agent import execution_agent
        from agents.memory_manager import memory_manager
        from database.identity_vault import identity_vault
        from vector_store.metadata_store import metadata_store

        try:
            if not session_id:
                session_id = session_manager.create_session()
            session = session_manager.get_session(session_id)
            if not session:
                session_id = session_manager.create_session()

            session_manager.add_to_history(session_id, "user", user_message)

            # ── Handle pending confirmation (new patient creation) ─────
            if session_id in self._pending_confirmations:
                pending = self._pending_confirmations[session_id]
                if self._is_confirmation(user_message):
                    # Create the new patient
                    del self._pending_confirmations[session_id]
                    patient_name = pending["patient_name"]
                    age = pending.get("age")
                    gender = pending.get("gender")
                    original_intent = pending.get("intent", "general")
                    original_semantic_context = pending.get("semantic_context", {})
                    original_medical_info = pending.get("medical_info") or ""

                    patient_uuid = identity_vault.confirm_new_patient(
                        patient_name=patient_name, age=age, gender=gender,
                        component="coordinator"
                    )
                    session_manager.set_active_patient(session_id, patient_uuid, patient_name)
                    logger.info(f"New patient created: {patient_name} -> {patient_uuid[:8]}...")

                    # Build privacy report for the new patient
                    privacy_report = gatekeeper_agent.create_privacy_report(
                        {"patient_name": patient_name, "age": age, "gender": gender,
                         "medical_info": original_medical_info},
                        patient_uuid, original_semantic_context
                    )

                    # Store interaction in context agent
                    try:
                        context_agent.store_interaction(
                            patient_uuid=patient_uuid,
                            interaction_type="appointment" if original_intent in ("appointment", "followup") else "question",
                            content=f"New patient registered. Medical info: {original_medical_info}",
                        )
                    except Exception:
                        pass

                    # Store in Pinecone metadata
                    if metadata_store:
                        try:
                            metadata_store.store_patient_metadata(
                                patient_uuid=patient_uuid,
                                semantic_context=original_semantic_context,
                                intent=original_intent
                            )
                        except Exception as e:
                            logger.warning(f"Failed to store in Pinecone: {e}")

                    # Now continue with the original intent execution
                    refined_context = context_agent.refine_context(
                        patient_uuid=patient_uuid, intent=original_intent,
                        semantic_context=original_semantic_context,
                        medical_info=original_medical_info
                    )

                    execution_result = execution_agent.execute_task(
                        patient_uuid=patient_uuid, intent=original_intent,
                        refined_context=refined_context
                    )

                    # Always set patient_name from vault
                    execution_result['patient_name'] = patient_name

                    return {
                        "success": True,
                        "message": f"Patient '{patient_name}' created successfully! " + execution_result.get('message', ''),
                        "intent": original_intent,
                        "patient_uuid": patient_uuid,
                        "patient_name": patient_name,
                        "session_id": session_id,
                        "result": execution_result,
                        "privacy_safe": True,
                        "privacy_report": privacy_report,
                        "workflow_steps": [
                            "Gatekeeper (PII Anonymized)",
                            "New Patient Created",
                            "Identity Resolution (UUID assigned)",
                            "Context Agent (History stored)",
                            "Execution Agent (Task completed)"
                        ]
                    }

                elif self._is_denial(user_message):
                    del self._pending_confirmations[session_id]
                    return {
                        "success": True,
                        "message": "Patient creation cancelled. How else can I help you?",
                        "intent": "general",
                        "session_id": session_id,
                        "result": {"suggestions": ["Book an appointment", "Schedule a follow-up", "Generate summary"]},
                        "privacy_safe": True,
                        "workflow_steps": ["Cancelled"]
                    }
                else:
                    # Not a clear yes/no — ask again
                    return {
                        "success": True,
                        "message": f"Please confirm: Create new patient '{pending['patient_name']}'? Reply 'Yes' or 'No'.",
                        "intent": "confirmation_required",
                        "session_id": session_id,
                        "result": {},
                        "privacy_safe": True,
                        "workflow_steps": ["Awaiting confirmation"]
                    }

            # ── Normal message processing ─────────────────────────────
            # Gatekeeper processes input (single combined call for speed)
            gatekeeper_output = gatekeeper_agent.process_message(user_message)
            pii_data = gatekeeper_output['pii']
            intent = gatekeeper_output['intent']
            semantic_context = gatekeeper_output['semantic_context']

            # Resolve patient
            patient_uuid = None
            patient_name = None

            if pii_data.get('patient_name'):
                resolution = identity_vault.resolve_patient_identity(
                    patient_name=pii_data['patient_name'],
                    age=pii_data.get('age'), gender=pii_data.get('gender'),
                    component="coordinator"
                )
                if resolution["status"] == "resolved":
                    patient_uuid = resolution["patient_uuid"]
                    patient_name = resolution["patient_name"]
                    session_manager.set_active_patient(session_id, patient_uuid, patient_name)
                elif resolution["status"] == "needs_disambiguation":
                    session_manager.set_pending_disambiguation(session_id, resolution)
                    return {"success": True, "message": resolution["message"],
                            "intent": "disambiguation_required", "session_id": session_id,
                            "result": {"disambiguation_data": {"candidates": resolution.get("candidates", [])}},
                            "privacy_safe": True,
                            "workflow_steps": ["Gatekeeper (PII Detected)", "Identity Resolution (Multiple matches)"]}
                elif resolution["status"] == "needs_confirmation":
                    # Store pending confirmation with original intent & context
                    self._pending_confirmations[session_id] = {
                        "patient_name": pii_data['patient_name'],
                        "age": pii_data.get('age'),
                        "gender": pii_data.get('gender'),
                        "intent": intent,
                        "semantic_context": semantic_context,
                        "medical_info": pii_data.get('medical_info') or '',
                    }
                    return {"success": True, "message": resolution["message"],
                            "intent": "confirmation_required", "session_id": session_id,
                            "result": {},
                            "privacy_safe": True,
                            "workflow_steps": ["Gatekeeper (PII Detected)", "New patient detected - awaiting confirmation"]}
            else:
                active = session_manager.get_active_patient(session_id)
                if active:
                    patient_uuid = active["patient_uuid"]
                    patient_name = active.get("patient_name")

            # Fallback UUID for unknown patients
            if not patient_uuid:
                patient_uuid = "temp-uuid-" + str(abs(hash(user_message)))[:8]

            # Build privacy report ALWAYS (even if partial PII)
            privacy_report = gatekeeper_agent.create_privacy_report(
                pii_data, patient_uuid, semantic_context
            )

            # Store in Pinecone metadata index
            if metadata_store and not patient_uuid.startswith("temp-uuid"):
                try:
                    metadata_store.store_patient_metadata(
                        patient_uuid=patient_uuid,
                        semantic_context=semantic_context,
                        intent=intent
                    )
                    logger.info(f"Stored interaction in Pinecone for {patient_uuid[:8]}...")
                except Exception as e:
                    logger.warning(f"Failed to store in Pinecone metadata: {e}")

            # Store interaction in context agent (in-memory / vector store)
            if not patient_uuid.startswith("temp-uuid"):
                try:
                    interaction_type = "appointment" if intent == "appointment" else \
                                       "followup" if intent == "followup" else "question"
                    context_agent.store_interaction(
                        patient_uuid=patient_uuid,
                        interaction_type=interaction_type,
                        content=f"{intent}: {pii_data.get('medical_info', user_message)}",
                    )
                except Exception as e:
                    logger.warning(f"Failed to store in context agent: {e}")

            # Retrieve patient history from Pinecone for context
            patient_history_summary = ""
            if metadata_store and not patient_uuid.startswith("temp-uuid"):
                try:
                    history = metadata_store.retrieve_patient_history(patient_uuid, limit=10)
                    if history:
                        patient_history_summary = f"Patient has {len(history)} previous interaction(s). "
                        categories = set(h.get("metadata", {}).get("symptom_category", "") for h in history)
                        categories.discard("")
                        if categories:
                            patient_history_summary += f"Categories: {', '.join(categories)}. "
                        logger.info(f"Retrieved {len(history)} records from Pinecone for {patient_uuid[:8]}")
                except Exception as e:
                    logger.warning(f"Failed to retrieve from Pinecone: {e}")

            # Context refinement
            refined_context = context_agent.refine_context(
                patient_uuid=patient_uuid, intent=intent,
                semantic_context=semantic_context,
                medical_info=pii_data.get('medical_info') or '')

            # Add patient history to context
            if patient_history_summary:
                refined_context['patient_history_summary'] = patient_history_summary

            # Execution
            execution_result = execution_agent.execute_task(
                patient_uuid=patient_uuid, intent=intent, refined_context=refined_context)

            # Re-identify patient name — ALWAYS try to get real name
            if not patient_uuid.startswith("temp-uuid"):
                identity = identity_vault.reidentify_patient(patient_uuid, component="coordinator")
                if identity:
                    patient_name = identity['patient_name']
                    execution_result['patient_name'] = patient_name

            # Ensure patient_name is set in result
            if patient_name:
                execution_result['patient_name'] = patient_name
            final_patient_name = execution_result.get('patient_name') or patient_name or 'N/A'

            return {
                "success": True, "message": execution_result.get('message', 'Done'),
                "intent": intent, "patient_uuid": patient_uuid,
                "patient_name": final_patient_name,
                "session_id": session_id, "result": execution_result,
                "privacy_safe": True, "privacy_report": privacy_report,
                "workflow_steps": [
                    "Gatekeeper (PII Anonymized)",
                    "Identity Resolution (UUID Mapped)",
                    "Context Agent (History Retrieved)",
                    "Execution Agent (Task Completed)"
                ]
            }

        except Exception as e:
            logger.error(f"Error in coordinator workflow: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "message": f"Sorry, I encountered an error. Please try again.",
                    "intent": "error", "privacy_safe": True, "result": {},
                    "workflow_steps": []}


# Global instances
coordinator = AgentCoordinator()
coordinator_agent = coordinator
