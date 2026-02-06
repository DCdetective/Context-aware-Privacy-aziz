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

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Session

from database.models import Base, Session as SessionModel

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
        
        # In-memory stores for session-level data not persisted to DB
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
        if patient_uuid:
            self._active_patients[session_id] = {
                "patient_uuid": patient_uuid,
                "patient_name": patient_name
            }
        else:
            self._active_patients.pop(session_id, None)
        return self.update_session(session_id, active_patient_id=patient_uuid)

    def get_active_patient(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get the active patient for a session."""
        return self._active_patients.get(session_id)

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
        except Exception as e:
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
            row.active_workflow = "none"
            row.workflow_stage = "none"
            row.workflow_data = "{}"
            row.pending_question = None
            row.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(row)
            # Clear pending action
            self._pending_actions.pop(session_id, None)
            return self._row_to_dict(row)
        except ValueError:
            raise
        except Exception as e:
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
            # Clear in-memory state
            self._active_patients.pop(session_id, None)
            self._pending_actions.pop(session_id, None)
            self._pending_disambiguations.pop(session_id, None)
            self._conversation_history.pop(session_id, None)
            return self._row_to_dict(row)
        except ValueError:
            raise
        except Exception as e:
            db.rollback()
            raise
        finally:
            db.close()

    # ── Conversation History ──────────────────────────────────────────

    def add_to_history(self, session_id: str, role: str, content: str):
        """Add a message to conversation history."""
        if session_id not in self._conversation_history:
            self._conversation_history[session_id] = []
        self._conversation_history[session_id].append({
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat()
        })

    def get_conversation_context(self, session_id: str, limit: int = 10) -> str:
        """Get recent conversation history as formatted string."""
        history = self._conversation_history.get(session_id, [])
        recent = history[-limit:]
        lines = []
        for msg in recent:
            lines.append(f"{msg['role'].capitalize()}: {msg['content']}")
        return "\n".join(lines) if lines else "No conversation history."

    # ── Pending Actions (HITL) ────────────────────────────────────────

    def set_pending_action(self, session_id: str, action_type: str, 
                           action_data: Dict[str, Any],
                           questions_asked: Optional[List[str]] = None):
        """Set a pending action awaiting user input."""
        self._pending_actions[session_id] = {
            "action_type": action_type,
            "action_data": action_data,
            "questions_asked": questions_asked or [],
            "user_responses": [],
            "awaiting_confirmation": False
        }

    def get_pending_action(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get pending action for a session."""
        return self._pending_actions.get(session_id)

    def clear_pending_action(self, session_id: str):
        """Clear the pending action."""
        self._pending_actions.pop(session_id, None)

    def add_question_response(self, session_id: str, question: str, response: str):
        """Add a user response to a pending action question."""
        pending = self._pending_actions.get(session_id)
        if pending:
            pending["user_responses"].append({
                "question": question,
                "response": response
            })

    # ── Pending Disambiguation ────────────────────────────────────────

    def set_pending_disambiguation(self, session_id: str, disambiguation_data: Dict[str, Any]):
        """Set pending disambiguation for patient selection."""
        self._pending_disambiguations[session_id] = disambiguation_data

    def get_pending_disambiguation(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get pending disambiguation data."""
        return self._pending_disambiguations.get(session_id)

    def clear_pending_disambiguation(self, session_id: str):
        """Clear pending disambiguation."""
        self._pending_disambiguations.pop(session_id, None)

    # ── Helpers ────────────────────────────────────────────────────────

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

        return {
            "session_id": row.session_id,
            "active_patient_id": row.active_patient_id,
            "active_workflow": row.active_workflow,
            "workflow_stage": row.workflow_stage,
            "pending_question": pending,
            "workflow_data": wf_data,
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
