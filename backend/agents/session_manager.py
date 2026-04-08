"""
Session State Machine – Persistent SQLite-backed session management.

Tracks conversation flow, active workflows, and prevents state loss.
"""

from typing import Dict, Any, Optional, List
import uuid
import json
import logging
import threading
import os
from datetime import datetime

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import sessionmaker, scoped_session, Session

from database.models import Base, Session as SessionModel, SessionEvent

logger = logging.getLogger(__name__)

# Valid workflow stage transitions
VALID_TRANSITIONS = {
    "none": ["resolving_patient"],
    "resolving_patient": ["collecting_specialty", "collecting_info",
                          "retrieving_history", "generating"],
    "collecting_info": ["confirmation"],
    "collecting_specialty": ["collecting_date"],
    "collecting_date": ["collecting_time"],
    "collecting_time": ["collecting_reason"],
    "collecting_reason": ["confirmation"],
    "confirmation": ["executing"],
    "executing": ["completed"],
    "completed": ["none"],
    # Follow-up workflow stages (Prompt 7)
    "retrieving_history": ["answering_query", "collecting_updates"],
    "answering_query": ["confirmation", "collecting_updates"],
    "collecting_updates": ["confirmation"],
    "storing_updates": ["completed"],
    # Summary workflow stages (Prompt 8)
    "generating": ["completed"],
}

VALID_WORKFLOWS = {"appointment", "followup", "summary", "none"}

EVENT_TYPES = {
    "user_message",
    "assistant_message",
    "stream_chunk",
    "workflow_step",
    "privacy_mask",
    "appointment_card",
    "followup_card",
    "summary_card",
    "hitl_prompt",
    "system_notice",
    "error_event",
}


class SessionManager:
    """
    Persistent session state manager with workflow state machine.

    Each session tracks:
    - Active patient UUID
    - Active workflow and stage
    - Pending questions
    - Workflow-collected data
    - Conversation history
    - Pending actions and disambiguations
    """

    def __init__(self, db_path: Optional[str] = None):
        _db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "database")
        os.makedirs(_db_dir, exist_ok=True)
        self.db_path = db_path or os.path.join(_db_dir, "sessions.db")
        self._lock = threading.Lock()

        self._conversation_history: Dict[str, List[Dict[str, str]]] = {}
        self._pending_actions: Dict[str, Dict[str, Any]] = {}
        self._pending_disambiguations: Dict[str, Dict[str, Any]] = {}
        self._active_patients: Dict[str, Dict[str, Any]] = {}

        self.engine = create_engine(
            f"sqlite:///{self.db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self._SessionFactory = scoped_session(sessionmaker(bind=self.engine))
        Base.metadata.create_all(self.engine)
        logger.info(f"SessionManager initialized at {self.db_path}")

    def _get_db(self) -> Session:
        return self._SessionFactory()

    def _read_aux_state(self, row: SessionModel) -> Dict[str, Any]:
        try:
            wf_data = json.loads(row.workflow_data or "{}")
            return wf_data.get("__session_aux", {}) if isinstance(wf_data, dict) else {}
        except Exception:
            return {}

    def _write_aux_state(self, row: SessionModel, aux: Dict[str, Any]) -> None:
        try:
            wf_data = json.loads(row.workflow_data or "{}")
            if not isinstance(wf_data, dict):
                wf_data = {}
        except Exception:
            wf_data = {}
        wf_data["__session_aux"] = aux
        row.workflow_data = json.dumps(wf_data)

    # ── Core API ──────────────────────────────────────────────────────

    def create_session(self) -> str:
        """Create a new session and return session_id."""
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        db = self._get_db()
        try:
            row = SessionModel(
                session_id=session_id,
                active_patient_id=None,
                active_workflow="none",
                workflow_stage="none",
                pending_question=None,
                workflow_data="{}",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.commit()
            self._conversation_history[session_id] = []
            logger.info(f"Created session {session_id}")
            return session_id
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating session: {e}")
            raise
        finally:
            db.close()

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get session by ID. Returns None if not found."""
        db = self._get_db()
        try:
            row = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if row is None:
                return None
            return self._row_to_dict(row)
        finally:
            db.close()

    def update_session(self, session_id: str, **updates) -> dict:
        """Update arbitrary session fields."""
        db = self._get_db()
        try:
            row = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if row is None:
                raise ValueError(f"Session not found: {session_id}")
            for key, value in updates.items():
                if key == "workflow_data":
                    row.workflow_data = json.dumps(value) if isinstance(value, dict) else value
                elif key == "pending_question":
                    row.pending_question = json.dumps(value) if isinstance(value, dict) else value
                elif hasattr(row, key):
                    setattr(row, key, value)
            row.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            return self._row_to_dict(row)
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating session: {e}")
            raise
        finally:
            db.close()

    # ── Active Patient ────────────────────────────────────────────────

    def set_active_patient(self, session_id: str, patient_uuid: Optional[str], patient_name: Optional[str] = None) -> dict:
        """Bind a patient to the session."""
        db = self._get_db()
        try:
            row = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if row is None:
                raise ValueError(f"Session not found: {session_id}")

            aux = self._read_aux_state(row)
            if patient_uuid:
                active = {"patient_uuid": patient_uuid, "patient_name": patient_name}
                self._active_patients[session_id] = active
                aux["active_patient"] = active
            else:
                self._active_patients.pop(session_id, None)
                aux.pop("active_patient", None)

            row.active_patient_id = patient_uuid
            self._write_aux_state(row, aux)
            row.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            return self._row_to_dict(row)
        finally:
            db.close()

    def get_active_patient(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the active patient for a session."""
        if session_id in self._active_patients:
            return self._active_patients.get(session_id)

        session = self.get_session(session_id)
        if not session:
            return None
        aux = session.get("session_aux", {})
        active = aux.get("active_patient")
        if active:
            self._active_patients[session_id] = active
            return active
        if session.get("active_patient_id"):
            fallback = {"patient_uuid": session["active_patient_id"], "patient_name": None}
            self._active_patients[session_id] = fallback
            return fallback
        return None

    # ── Workflow Management ───────────────────────────────────────────

    def set_workflow(self, session_id: str, workflow: str, stage: str) -> dict:
        """Set workflow and stage (validates workflow name)."""
        if workflow not in VALID_WORKFLOWS:
            raise ValueError(f"Invalid workflow: {workflow}. Must be one of {VALID_WORKFLOWS}")
        return self.update_session(session_id, active_workflow=workflow, workflow_stage=stage)

    def add_workflow_data(self, session_id: str, key: str, value: Any) -> dict:
        """Add a key-value pair to workflow_data."""
        db = self._get_db()
        try:
            row = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if row is None:
                raise ValueError(f"Session not found: {session_id}")
            data = json.loads(row.workflow_data or "{}")
            data[key] = value
            row.workflow_data = json.dumps(data)
            row.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            return self._row_to_dict(row)
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error adding workflow data: {e}")
            raise
        finally:
            db.close()

    def get_workflow_data(self, session_id: str) -> dict:
        """Get workflow data for a session."""
        session = self.get_session(session_id)
        if session:
            return session.get("workflow_data", {})
        return {}

    def set_pending_question(self, session_id: str, question: str, context: dict) -> dict:
        """Set a pending question with context."""
        pending = {"question": question, "context": context}
        return self.update_session(session_id, pending_question=json.dumps(pending))

    def clear_pending_question(self, session_id: str) -> dict:
        """Clear the pending question."""
        db = self._get_db()
        try:
            row = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if row is None:
                raise ValueError(f"Session not found: {session_id}")
            row.pending_question = None
            row.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            return self._row_to_dict(row)
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()

    def advance_workflow_stage(self, session_id: str, next_stage: str) -> dict:
        """Advance to next workflow stage with transition validation."""
        db = self._get_db()
        try:
            row = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if row is None:
                raise ValueError(f"Session not found: {session_id}")
            current = row.workflow_stage
            allowed = VALID_TRANSITIONS.get(current, [])
            if next_stage not in allowed:
                raise ValueError(
                    f"Invalid transition: {current} → {next_stage}. "
                    f"Allowed: {allowed}"
                )
            row.workflow_stage = next_stage
            row.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            return self._row_to_dict(row)
        except ValueError:
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def complete_workflow(self, session_id: str) -> dict:
        """Complete the current workflow: reset workflow/stage/data, keep patient."""
        db = self._get_db()
        try:
            row = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if row is None:
                raise ValueError(f"Session not found: {session_id}")
            aux = self._read_aux_state(row)
            aux.pop("pending_action", None)
            aux.pop("pending_disambiguation", None)

            row.active_workflow = "none"
            row.workflow_stage = "none"
            row.workflow_data = "{}"
            self._write_aux_state(row, aux)
            row.pending_question = None
            row.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            self._pending_actions.pop(session_id, None)
            self._pending_disambiguations.pop(session_id, None)
            return self._row_to_dict(row)
        except ValueError:
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def reset_session(self, session_id: str) -> dict:
        """Reset all session state except session_id and timestamps."""
        db = self._get_db()
        try:
            row = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if row is None:
                raise ValueError(f"Session not found: {session_id}")
            row.active_patient_id = None
            row.active_workflow = "none"
            row.workflow_stage = "none"
            row.workflow_data = "{}"
            row.pending_question = None
            row.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            self._active_patients.pop(session_id, None)
            self._pending_actions.pop(session_id, None)
            self._pending_disambiguations.pop(session_id, None)
            self._conversation_history.pop(session_id, None)
            return self._row_to_dict(row)
        except ValueError:
            raise
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ── Events + Conversation History ─────────────────────────────────

    def add_event(
        self,
        session_id: str,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        status: str = "completed",
        agent: Optional[str] = None,
        role: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a structured event to the persistent event timeline."""
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Invalid event type: {event_type}")

        db = self._get_db()
        try:
            if not db.query(SessionModel).filter(SessionModel.session_id == session_id).first():
                raise ValueError(f"Session not found: {session_id}")
            row = SessionEvent(
                session_id=session_id,
                event_type=event_type,
                status=status,
                agent=agent,
                role=role,
                payload=json.dumps(payload or {}),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return self._event_row_to_dict(row)
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error adding event: {e}")
            raise
        finally:
            db.close()

    def list_events(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """List ordered events for a session."""
        db = self._get_db()
        try:
            q = db.query(SessionEvent).filter(SessionEvent.session_id == session_id).order_by(SessionEvent.event_id.asc())
            rows = q.all()
            events = [self._event_row_to_dict(r) for r in rows]
            if limit:
                return events[-limit:]
            return events
        finally:
            db.close()

    def add_to_history(self, session_id: str, role: str, content: str):
        """Add a message to conversation history and event log."""
        if session_id not in self._conversation_history:
            self._conversation_history[session_id] = []
        event = {
            "role": role,
            "content": content,
            "message": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        self._conversation_history[session_id].append(event)

        event_type = "user_message" if role == "user" else "assistant_message"
        try:
            self.add_event(
                session_id=session_id,
                event_type=event_type,
                role=role,
                payload={"content": content},
                status="completed",
            )
        except Exception:
            logger.debug("Unable to persist conversation history event", exc_info=True)

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        """Compatibility helper for tests and legacy routes."""
        history = self._conversation_history.get(session_id)
        if history:
            return history

        events = self.list_events(session_id)
        out: List[Dict[str, Any]] = []
        for event in events:
            if event["event_type"] in ("user_message", "assistant_message"):
                role = event.get("role") or ("user" if event["event_type"] == "user_message" else "assistant")
                content = event.get("payload", {}).get("content", "")
                out.append({
                    "role": role,
                    "content": content,
                    "message": content,
                    "timestamp": event.get("created_at"),
                })
        self._conversation_history[session_id] = out
        return out

    def get_conversation_context(self, session_id: str, limit: int = 10) -> str:
        """Get recent conversation history as formatted string."""
        history = self.get_history(session_id)
        recent = history[-limit:]
        if not recent:
            return "No previous conversation history."
        lines = []
        for msg in recent:
            lines.append(f"{msg['role'].capitalize()}: {msg['content']}")
        return "\n".join(lines)

    # ── Pending Actions (HITL) ────────────────────────────────────────

    def set_pending_action(self, session_id: str, action_type: str,
                           action_data: Dict[str, Any],
                           questions_asked: Optional[List[str]] = None):
        """Set a pending action awaiting user input."""
        pending = {
            "action_type": action_type,
            "action_data": action_data,
            "questions_asked": questions_asked or [],
            "user_responses": [],
            "awaiting_confirmation": False,
        }
        self._pending_actions[session_id] = pending
        self._persist_aux_state(session_id, "pending_action", pending)

    def get_pending_action(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get pending action for a session."""
        pending = self._pending_actions.get(session_id)
        if pending:
            return pending
        session = self.get_session(session_id) or {}
        pending = session.get("session_aux", {}).get("pending_action")
        if pending:
            self._pending_actions[session_id] = pending
        return pending

    def clear_pending_action(self, session_id: str):
        """Clear the pending action."""
        self._pending_actions.pop(session_id, None)
        self._persist_aux_state(session_id, "pending_action", None)

    def add_question_response(self, session_id: str, question: str, response: str):
        """Add a user response to a pending action question."""
        pending = self.get_pending_action(session_id)
        if pending:
            pending["user_responses"].append({
                "question": question,
                "response": response,
            })
            self._pending_actions[session_id] = pending
            self._persist_aux_state(session_id, "pending_action", pending)

    # ── Pending Disambiguation ────────────────────────────────────────

    def set_pending_disambiguation(self, session_id: str, disambiguation_data: Dict[str, Any]):
        """Set pending disambiguation for patient selection."""
        self._pending_disambiguations[session_id] = disambiguation_data
        self._persist_aux_state(session_id, "pending_disambiguation", disambiguation_data)

    def get_pending_disambiguation(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get pending disambiguation data."""
        pending = self._pending_disambiguations.get(session_id)
        if pending:
            return pending
        session = self.get_session(session_id) or {}
        pending = session.get("session_aux", {}).get("pending_disambiguation")
        if pending:
            self._pending_disambiguations[session_id] = pending
        return pending

    def clear_pending_disambiguation(self, session_id: str):
        """Clear pending disambiguation."""
        self._pending_disambiguations.pop(session_id, None)
        self._persist_aux_state(session_id, "pending_disambiguation", None)

    def _persist_aux_state(self, session_id: str, key: str, value: Any) -> None:
        db = self._get_db()
        try:
            row = db.query(SessionModel).filter(SessionModel.session_id == session_id).first()
            if row is None:
                return
            aux = self._read_aux_state(row)
            if value is None:
                aux.pop(key, None)
            else:
                aux[key] = value
            self._write_aux_state(row, aux)
            row.updated_at = datetime.utcnow()
            db.commit()
        except Exception:
            db.rollback()
            logger.debug("Failed persisting aux session state", exc_info=True)
        finally:
            db.close()

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Compatibility helper used by memory tests."""
        session = self.get_session(session_id)
        if not session:
            return {
                "session_id": session_id,
                "has_active_patient": False,
                "patient_uuid": None,
                "patient_name": None,
                "conversation_length": 0,
            }
        active = self.get_active_patient(session_id)
        history = self.get_history(session_id)
        return {
            "session_id": session_id,
            "has_active_patient": bool(active and active.get("patient_uuid")),
            "patient_uuid": active.get("patient_uuid") if active else None,
            "patient_name": active.get("patient_name") if active else None,
            "conversation_length": len(history),
            "active_workflow": session.get("active_workflow"),
            "workflow_stage": session.get("workflow_stage"),
        }

    def get_session_snapshot(self, session_id: str) -> Dict[str, Any]:
        """Return full session snapshot for frontend restore."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session not found: {session_id}")
        events = self.list_events(session_id)
        return {
            "session": session,
            "events": events,
            "pending_action": self.get_pending_action(session_id),
            "pending_disambiguation": self.get_pending_disambiguation(session_id),
            "active_patient": self.get_active_patient(session_id),
            "memory_refs": {
                "history_count": len(self.get_history(session_id)),
                "last_event_id": events[-1]["event_id"] if events else None,
            },
        }

    def clear_all_sessions(self):
        """Test utility to clear sessions and events from this DB."""
        db = self._get_db()
        try:
            db.execute(delete(SessionEvent))
            db.execute(delete(SessionModel))
            db.commit()
            self._conversation_history.clear()
            self._pending_actions.clear()
            self._pending_disambiguations.clear()
            self._active_patients.clear()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    # ── Helpers ────────────────────────────────────────────────────────

    def _event_row_to_dict(self, row: SessionEvent) -> Dict[str, Any]:
        try:
            payload = json.loads(row.payload or "{}")
        except Exception:
            payload = {}
        return {
            "event_id": row.event_id,
            "session_id": row.session_id,
            "event_type": row.event_type,
            "status": row.status,
            "agent": row.agent,
            "role": row.role,
            "payload": payload,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _row_to_dict(self, row: SessionModel) -> dict:
        pending = None
        if row.pending_question:
            try:
                pending = json.loads(row.pending_question)
            except (json.JSONDecodeError, TypeError):
                pending = row.pending_question

        wf_data = {}
        if row.workflow_data:
            try:
                wf_data = json.loads(row.workflow_data)
            except (json.JSONDecodeError, TypeError):
                wf_data = {}

        session_aux = wf_data.pop("__session_aux", {}) if isinstance(wf_data, dict) else {}

        return {
            "session_id": row.session_id,
            "active_patient_id": row.active_patient_id,
            "active_workflow": row.active_workflow,
            "workflow_stage": row.workflow_stage,
            "pending_question": pending,
            "workflow_data": wf_data,
            "session_aux": session_aux,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }

    def dispose(self):
        """Dispose engine (for test cleanup)."""
        self._SessionFactory.remove()
        self.engine.dispose()


# Global instance
_db_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "database")
os.makedirs(_db_dir, exist_ok=True)
session_manager = SessionManager(db_path=os.path.join(_db_dir, "sessions.db"))
