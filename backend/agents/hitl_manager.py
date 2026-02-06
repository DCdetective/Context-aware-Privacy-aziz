"""
Human-in-the-Loop (HITL) Manager (Prompt 9)
Handles confirmations, clarifications, and user feedback
without resetting conversation state.
"""
from typing import Dict, Any, List, Optional
import logging
import time

logger = logging.getLogger(__name__)

# Valid response mappings
POSITIVE_RESPONSES = {'yes', 'confirm', 'ok', 'proceed', 'correct', 'sure', 'yeah', 'yep'}
NEGATIVE_RESPONSES = {'no', 'cancel', 'abort', 'stop', 'nope', 'nevermind'}
MODIFY_RESPONSES = {'change', 'modify', 'different', 'edit', 'update'}

# Default timeout in seconds
DEFAULT_TIMEOUT = 300  # 5 minutes
REMINDER_TIMEOUT = 120  # 2 minutes


class HITLManager:
    """
    Manages human-in-the-loop workflows for confirmations, clarifications,
    and medical questions.

    CRITICAL: Never resets conversation state during HITL.
    CRITICAL: Never shows main menu mid-workflow.
    """

    def __init__(self, session_manager=None):
        """Initialize HITL Manager."""
        self.session_manager = session_manager
        # In-memory store for pending HITL requests per session
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
        self._hitl_log: List[Dict[str, Any]] = []
        logger.info("HITL Manager initialized")

    def set_session_manager(self, session_manager):
        """Set the session manager (for deferred initialization)."""
        self.session_manager = session_manager

    # ── Core HITL Methods ─────────────────────────────────────────────

    def request_confirmation(
        self,
        session_id: str,
        confirmation_type: str,  # "appointment" | "update" | "action"
        details: dict
    ) -> dict:
        """
        Request user confirmation before action.
        Pauses workflow until confirmed.

        Returns: {
            "message": str,
            "requires_response": bool,
            "pending_action": dict
        }
        """
        # Build confirmation message
        message = self._build_confirmation_message(confirmation_type, details)

        # Store pending request
        pending = {
            "question_type": "confirmation",
            "confirmation_type": confirmation_type,
            "question": message,
            "details": details,
            "context": details,
            "timestamp": time.time(),
            "timeout": DEFAULT_TIMEOUT,
            "reminder_sent": False,
        }
        self._pending_requests[session_id] = pending

        # Store in session manager if available
        if self.session_manager:
            try:
                self.session_manager.set_pending_question(
                    session_id, message, {"type": "confirmation", "details": details}
                )
            except Exception as e:
                logger.warning(f"Could not set pending question in session: {e}")

        self._log_hitl_event(session_id, "confirmation_requested", confirmation_type, details)

        return {
            "message": message,
            "requires_response": True,
            "pending_action": pending,
        }

    def request_clarification(
        self,
        session_id: str,
        question: str,
        context: dict,
        options: List[str] = None
    ) -> dict:
        """
        Ask clarifying question.
        Pauses workflow until answered.

        Returns: {
            "message": str,
            "requires_response": bool,
            "options": List[str] | None,
            "pending_action": dict
        }
        """
        # Build clarification message
        message = question
        if options:
            message += "\n"
            for i, opt in enumerate(options, 1):
                message += f"\n{i}. {opt}"
            message += "\n\nPlease type the number to select."

        pending = {
            "question_type": "clarification",
            "question": message,
            "original_question": question,
            "context": context,
            "options": options,
            "timestamp": time.time(),
            "timeout": DEFAULT_TIMEOUT,
            "reminder_sent": False,
        }
        self._pending_requests[session_id] = pending

        if self.session_manager:
            try:
                self.session_manager.set_pending_question(
                    session_id, message, {"type": "clarification", "context": context}
                )
            except Exception as e:
                logger.warning(f"Could not set pending question in session: {e}")

        self._log_hitl_event(session_id, "clarification_requested", question, context)

        return {
            "message": message,
            "requires_response": True,
            "options": options,
            "pending_action": pending,
        }

    def request_medical_question(
        self,
        session_id: str,
        questions: List[str],
        context: dict
    ) -> dict:
        """
        Ask medical questions before proceeding.

        Returns: {
            "message": str,
            "requires_response": bool,
            "pending_action": dict
        }
        """
        message = "To better assist, please answer:\n"
        for q in questions:
            message += f"\n- {q}"

        pending = {
            "question_type": "medical",
            "question": message,
            "medical_questions": questions,
            "context": context,
            "timestamp": time.time(),
            "timeout": DEFAULT_TIMEOUT,
            "reminder_sent": False,
        }
        self._pending_requests[session_id] = pending

        if self.session_manager:
            try:
                self.session_manager.set_pending_question(
                    session_id, message, {"type": "medical", "context": context}
                )
            except Exception as e:
                logger.warning(f"Could not set pending question in session: {e}")

        self._log_hitl_event(session_id, "medical_question_requested", str(questions), context)

        return {
            "message": message,
            "requires_response": True,
            "pending_action": pending,
        }

    def process_hitl_response(
        self,
        session_id: str,
        user_response: str
    ) -> dict:
        """
        Process user's response to HITL request.

        Returns: {
            "action": "confirmed" | "cancelled" | "modified" | "answered" | "invalid",
            "proceed": bool,
            "data": dict
        }
        """
        pending = self._pending_requests.get(session_id)
        if not pending:
            return {
                "action": "no_pending",
                "proceed": False,
                "data": {"message": "No pending question found."}
            }

        question_type = pending.get("question_type", "confirmation")
        response_lower = user_response.lower().strip()

        if question_type == "confirmation":
            result = self._process_confirmation_response(response_lower, pending)
        elif question_type == "clarification":
            result = self._process_clarification_response(user_response, pending)
        elif question_type == "medical":
            result = self._process_medical_response(user_response, pending)
        else:
            result = {"action": "answered", "proceed": True, "data": {"response": user_response}}

        # If valid response, clear pending
        if result["action"] != "invalid":
            self._pending_requests.pop(session_id, None)
            if self.session_manager:
                try:
                    self.session_manager.clear_pending_question(session_id)
                except Exception:
                    pass
            self._log_hitl_event(session_id, f"response_{result['action']}", user_response, result.get("data", {}))

        return result

    def is_waiting_for_hitl(self, session_id: str) -> bool:
        """Check if session is waiting for HITL response."""
        return session_id in self._pending_requests

    def get_pending_request(self, session_id: str) -> Optional[dict]:
        """Get the pending HITL request for a session."""
        return self._pending_requests.get(session_id)

    def check_timeout(self, session_id: str) -> dict:
        """
        Check if HITL request has timed out.

        Returns: {
            "status": "active" | "reminder" | "timed_out",
            "message": str | None
        }
        """
        pending = self._pending_requests.get(session_id)
        if not pending:
            return {"status": "active", "message": None}

        elapsed = time.time() - pending["timestamp"]
        timeout = pending.get("timeout", DEFAULT_TIMEOUT)

        if elapsed >= timeout:
            # Timed out - cancel workflow
            self._pending_requests.pop(session_id, None)
            if self.session_manager:
                try:
                    self.session_manager.clear_pending_question(session_id)
                except Exception:
                    pass
            self._log_hitl_event(session_id, "timeout", f"Timed out after {elapsed:.0f}s", {})
            return {
                "status": "timed_out",
                "message": "Your session has timed out due to inactivity. The workflow has been cancelled."
            }

        if elapsed >= REMINDER_TIMEOUT and not pending.get("reminder_sent", False):
            pending["reminder_sent"] = True
            self._log_hitl_event(session_id, "reminder_sent", f"Reminder at {elapsed:.0f}s", {})
            return {
                "status": "reminder",
                "message": f"Reminder: {pending['question']}\n\nPlease respond to continue."
            }

        return {"status": "active", "message": None}

    def clear_pending(self, session_id: str):
        """Clear any pending HITL request for a session."""
        self._pending_requests.pop(session_id, None)
        if self.session_manager:
            try:
                self.session_manager.clear_pending_question(session_id)
            except Exception:
                pass

    # ── Legacy Methods (backward compatibility) ───────────────────────

    def generate_medical_questions(
        self,
        intent: str,
        semantic_context: Dict[str, Any]
    ) -> List[str]:
        """Generate relevant medical questions before booking."""
        symptom_category = semantic_context.get('symptom_category', 'general')
        urgency = semantic_context.get('urgency_level', 'routine')

        questions = []
        questions.append("How long have you been experiencing these symptoms?")

        if symptom_category == 'respiratory':
            questions.append("Do you have difficulty breathing or shortness of breath?")
            questions.append("Have you been in contact with anyone who is sick?")
        elif symptom_category == 'cardiac':
            questions.append("Do you experience chest pain or discomfort?")
            questions.append("Do you have a history of heart conditions?")
        elif symptom_category == 'neurological':
            questions.append("Are you experiencing any vision changes or dizziness?")
            questions.append("Have you had any recent head injuries?")
        elif symptom_category == 'digestive':
            questions.append("Are you experiencing nausea or vomiting?")
            questions.append("Any recent dietary changes?")
        else:
            questions.append("On a scale of 1-10, how would you rate your discomfort?")
            questions.append("Have you taken any medication for this?")

        if urgency == 'urgent':
            questions.append("Is this a sudden onset or has it been gradual?")

        return questions[:3]

    def create_confirmation_summary(
        self,
        intent: str,
        patient_name: str,
        action_data: Dict[str, Any],
        user_responses: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Create a summary for user confirmation."""
        lines = ["📋 **Confirmation Summary**\n"]

        if intent == "appointment":
            lines.append(f"**Patient:** {patient_name}")
            lines.append(f"**Action:** Book New Appointment")
            if action_data.get('recommended_doctor'):
                lines.append(f"**Doctor:** {action_data['recommended_doctor']}")
            if action_data.get('appointment_date'):
                lines.append(f"**Date:** {action_data['appointment_date']}")
            if action_data.get('appointment_time'):
                lines.append(f"**Time:** {action_data['appointment_time']}")
            if action_data.get('consultation_duration'):
                lines.append(f"**Duration:** {action_data['consultation_duration']} minutes")
        elif intent == "followup":
            lines.append(f"**Patient:** {patient_name}")
            lines.append(f"**Action:** Schedule Follow-up")
            if action_data.get('followup_date'):
                lines.append(f"**Date:** {action_data['followup_date']}")
            if action_data.get('recommended_doctor'):
                lines.append(f"**Doctor:** {action_data['recommended_doctor']}")
        elif intent == "update":
            lines.append(f"**Patient:** {patient_name}")
            lines.append(f"**Action:** Update Patient Status")
            if action_data.get('status_update'):
                lines.append(f"**Update:** {action_data['status_update']}")

        if user_responses:
            lines.append("\n**Your Responses:**")
            for resp in user_responses:
                lines.append(f"- Q: {resp['question']}")
                lines.append(f"  A: {resp['response']}")

        lines.append("\n**Please confirm:** Type 'yes' to proceed or 'no' to cancel.")
        return "\n".join(lines)

    def parse_confirmation_response(self, message: str) -> bool:
        """Parse user's confirmation response."""
        message_lower = message.lower().strip()
        if any(word in message_lower for word in POSITIVE_RESPONSES):
            return True
        return False

    # ── Private Helpers ───────────────────────────────────────────────

    def _build_confirmation_message(self, confirmation_type: str, details: dict) -> str:
        """Build a human-readable confirmation message."""
        lines = []

        if confirmation_type == "appointment":
            lines.append("Please confirm the appointment:")
            if details.get("patient_name"):
                lines.append(f"- Patient: {details['patient_name']}")
            if details.get("specialty"):
                lines.append(f"- Specialty: {details['specialty']}")
            if details.get("date"):
                lines.append(f"- Date: {details['date']}")
            if details.get("time"):
                lines.append(f"- Time: {details['time']}")
            if details.get("doctor"):
                doc = details["doctor"]
                doc_name = doc.get("name", "TBD") if isinstance(doc, dict) else doc
                lines.append(f"- Doctor: {doc_name}")
        elif confirmation_type == "update":
            lines.append("Please confirm the status update:")
            if details.get("patient_name"):
                lines.append(f"- Patient: {details['patient_name']}")
            if details.get("status_update"):
                lines.append(f"- Update: {details['status_update']}")
            if details.get("updates_extracted"):
                for upd in details["updates_extracted"]:
                    lines.append(f"  • {upd.get('symptom', 'N/A')}: {upd.get('status', 'N/A')}")
        elif confirmation_type == "action":
            lines.append("Please confirm the action:")
            if details.get("description"):
                lines.append(f"- {details['description']}")
        else:
            lines.append("Please confirm:")
            for k, v in details.items():
                if k not in ("timestamp", "context"):
                    lines.append(f"- {k}: {v}")

        lines.append("\nReply 'confirm' to proceed or 'cancel' to abort.")
        return "\n".join(lines)

    def _process_confirmation_response(self, response_lower: str, pending: dict) -> dict:
        """Process a confirmation response."""
        if any(word in response_lower for word in POSITIVE_RESPONSES):
            return {
                "action": "confirmed",
                "proceed": True,
                "data": pending.get("details", pending.get("context", {}))
            }
        elif any(word in response_lower for word in NEGATIVE_RESPONSES):
            return {
                "action": "cancelled",
                "proceed": False,
                "data": {"reason": "User cancelled"}
            }
        elif any(word in response_lower for word in MODIFY_RESPONSES):
            return {
                "action": "modified",
                "proceed": False,
                "data": {"reason": "User wants to modify", "original": pending.get("details", {})}
            }
        else:
            return {
                "action": "invalid",
                "proceed": False,
                "data": {"message": "Please reply 'confirm' to proceed or 'cancel' to abort."}
            }

    def _process_clarification_response(self, response: str, pending: dict) -> dict:
        """Process a clarification response."""
        options = pending.get("options")

        if options:
            # Try to parse as number
            try:
                idx = int(response.strip()) - 1
                if 0 <= idx < len(options):
                    return {
                        "action": "answered",
                        "proceed": True,
                        "data": {
                            "selected_option": options[idx],
                            "selected_index": idx,
                            "response": response
                        }
                    }
            except ValueError:
                pass

            # Try to match text
            for i, opt in enumerate(options):
                if response.lower().strip() in opt.lower():
                    return {
                        "action": "answered",
                        "proceed": True,
                        "data": {
                            "selected_option": opt,
                            "selected_index": i,
                            "response": response
                        }
                    }

        # Free-text answer
        return {
            "action": "answered",
            "proceed": True,
            "data": {"response": response}
        }

    def _process_medical_response(self, response: str, pending: dict) -> dict:
        """Process a medical question response."""
        return {
            "action": "answered",
            "proceed": True,
            "data": {
                "response": response,
                "questions_asked": pending.get("medical_questions", [])
            }
        }

    def _log_hitl_event(self, session_id: str, event_type: str, detail: str, data: dict):
        """Log HITL interaction for audit trail."""
        self._hitl_log.append({
            "session_id": session_id,
            "event_type": event_type,
            "detail": detail,
            "data": data,
            "timestamp": time.time()
        })
        logger.info(f"HITL [{session_id[:8]}]: {event_type} - {detail[:80]}")

    def get_hitl_log(self, session_id: str = None) -> List[dict]:
        """Get HITL log, optionally filtered by session."""
        if session_id:
            return [e for e in self._hitl_log if e["session_id"] == session_id]
        return list(self._hitl_log)


# Global instance
hitl_manager = HITLManager()
