from typing import Dict, Any, Optional
import uuid
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class SessionManager:
    """
    Manage user sessions and active patient context.
    
    Each session tracks:
    - Active patient UUID
    - Conversation history
    - Pending disambiguation requests
    - Session timeout
    """
    
    def __init__(self, session_timeout_minutes: int = 30):
        """Initialize session manager."""
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_timeout = timedelta(minutes=session_timeout_minutes)
        logger.info("Session Manager initialized")
    
    def create_session(self) -> str:
        """Create a new session and return session ID."""
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = {
            "session_id": session_id,
            "active_patient_uuid": None,
            "patient_name": None,
            "conversation_history": [],
            "pending_action": None,
            "pending_disambiguation": None,
            "created_at": datetime.utcnow(),
            "last_activity": datetime.utcnow()
        }
        logger.info(f"Created new session: {session_id}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID."""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        
        # Check if session expired
        if datetime.utcnow() - session["last_activity"] > self.session_timeout:
            logger.info(f"Session expired: {session_id}")
            self.clear_session(session_id)
            return None
        
        return session
    
    def set_active_patient(
        self,
        session_id: str,
        patient_uuid: str,
        patient_name: str
    ):
        """Set the active patient for a session."""
        session = self.get_session(session_id)
        if session:
            session["active_patient_uuid"] = patient_uuid
            session["patient_name"] = patient_name
            session["last_activity"] = datetime.utcnow()
            logger.info(f"Session {session_id}: Active patient set to {patient_uuid}")
    
    def get_active_patient(self, session_id: str) -> Optional[Dict[str, str]]:
        """Get the active patient for a session."""
        session = self.get_session(session_id)
        if session and session.get("active_patient_uuid"):
            return {
                "patient_uuid": session["active_patient_uuid"],
                "patient_name": session["patient_name"]
            }
        return None
    
    def set_pending_disambiguation(
        self,
        session_id: str,
        disambiguation_data: Dict[str, Any]
    ):
        """Set pending disambiguation request."""
        session = self.get_session(session_id)
        if session:
            session["pending_disambiguation"] = disambiguation_data
            session["last_activity"] = datetime.utcnow()
            logger.info(f"Session {session_id}: Disambiguation pending")
    
    def get_pending_disambiguation(
        self,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get pending disambiguation request."""
        session = self.get_session(session_id)
        if session:
            return session.get("pending_disambiguation")
        return None
    
    def clear_pending_disambiguation(self, session_id: str):
        """Clear pending disambiguation."""
        session = self.get_session(session_id)
        if session:
            session["pending_disambiguation"] = None
    
    def add_to_history(
        self,
        session_id: str,
        role: str,
        message: str
    ):
        """Add message to conversation history."""
        session = self.get_session(session_id)
        if session:
            session["conversation_history"].append({
                "role": role,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            })
            session["last_activity"] = datetime.utcnow()
    
    def get_history(self, session_id: str, limit: int = 10) -> list:
        """Get conversation history."""
        session = self.get_session(session_id)
        if session:
            return session["conversation_history"][-limit:]
        return []
    
    def clear_session(self, session_id: str):
        """Clear a session."""
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Cleared session: {session_id}")
    
    def clear_all_sessions(self):
        """Clear all sessions (for testing)."""
        self.sessions.clear()
        logger.info("Cleared all sessions")


# Global instance
session_manager = SessionManager()
