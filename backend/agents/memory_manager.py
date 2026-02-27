"""
Memory Manager - Handles short-term and long-term conversational memory.

Combines local database records (PII-safe, via Identity Vault) with
cloud vector-store interaction history (semantic, UUID-only) to give
the LLM agents full patient context without ever exposing PII.
"""
from typing import Dict, Any, List, Optional
import logging
import re

from database.identity_vault import identity_vault
import vector_store.metadata_store as _ms_mod

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages conversational memory (short-term and long-term).

    Short-term: Session-based conversation history (held by SessionManager)
    Long-term:  Patient records from local DB + vector-store interactions
    """

    def __init__(self):
        """Initialize Memory Manager."""
        logger.info("Memory Manager initialized")

    # ------------------------------------------------------------------
    # Long-term memory
    # ------------------------------------------------------------------

    def get_patient_long_term_memory(
        self,
        patient_uuid: str,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """Retrieve a patient's long-term memory.

        Combines:
        - Local database records (PII-safe, via Identity Vault)
        - Vector-store interaction history (semantic, UUID-only)

        Args:
            patient_uuid: Patient UUID
            limit: Maximum records to retrieve per source

        Returns:
            Long-term memory dictionary with *medical_records*,
            *interaction_history*, and a textual *summary*.
        """
        logger.info(f"Retrieving long-term memory for patient: {patient_uuid[:8]}...")

        memory: Dict[str, Any] = {
            "patient_uuid": patient_uuid,
            "medical_records": [],
            "interaction_history": [],
            "summary": "",
        }

        try:
            # Medical records from local database
            records = identity_vault.get_patient_records(
                patient_uuid=patient_uuid,
                component="memory_manager",
            )
            memory["medical_records"] = records[:limit]
            logger.info(f"Found {len(records)} medical records")

            # Interaction history from vector store (may be None at startup)
            if _ms_mod.metadata_store is not None:
                try:
                    history = _ms_mod.metadata_store.retrieve_patient_history(
                        patient_uuid=patient_uuid,
                        limit=limit,
                    )
                    memory["interaction_history"] = history
                    logger.info(f"Found {len(history)} vector store interactions")
                except Exception as e:
                    logger.warning(f"Could not retrieve vector-store history: {e}")

            # Textual summary
            memory["summary"] = self._create_memory_summary(memory)

            return memory

        except Exception as e:
            logger.error(f"Error retrieving long-term memory: {str(e)}")
            return memory

    # ------------------------------------------------------------------
    # Combined context (convenience)
    # ------------------------------------------------------------------

    def get_combined_context(
        self,
        patient_uuid: str,
        session_id: str,
        record_limit: int = 5,
        history_limit: int = 5,
    ) -> Dict[str, Any]:
        """Retrieve and merge short-term + long-term memory in one call.

        This is a convenience wrapper used by the AgentCoordinator so that
        callers don't need to separately fetch session context and long-term
        memory.

        Args:
            patient_uuid: Patient UUID
            session_id: Current session ID
            record_limit: Max medical records to fetch
            history_limit: Max conversation turns to include

        Returns:
            Dict with *short_term*, *long_term*, and *formatted* keys.
        """
        from agents.session_manager import session_manager  # local import to avoid circular

        long_term = self.get_patient_long_term_memory(
            patient_uuid=patient_uuid,
            limit=record_limit,
        )

        short_term = session_manager.get_conversation_context(
            session_id=session_id,
            limit=history_limit,
        )

        formatted = self.format_memory_for_llm(
            short_term=short_term,
            long_term=long_term,
        )

        return {
            "short_term": short_term,
            "long_term": long_term,
            "formatted": formatted,
            "has_history": len(long_term.get("medical_records", [])) > 0,
        }

    # ------------------------------------------------------------------
    # Memory summary
    # ------------------------------------------------------------------

    def _create_memory_summary(self, memory: Dict[str, Any]) -> str:
        """Create a textual summary of patient memory."""
        lines: List[str] = []

        record_count = len(memory.get("medical_records", []))
        interaction_count = len(memory.get("interaction_history", []))

        if record_count == 0 and interaction_count == 0:
            return "New patient - no previous history available."

        lines.append(
            f"Patient has {record_count} medical records and "
            f"{interaction_count} previous interactions."
        )

        # Most-recent record
        records = memory.get("medical_records", [])
        if records:
            recent = records[0]
            lines.append(
                f"Most recent: {recent.get('record_type')} on "
                f"{recent.get('created_at', 'unknown date')}"
            )

        # Interaction-pattern summary
        interactions = memory.get("interaction_history", [])
        if interactions:
            intent_counts: Dict[Optional[str], int] = {}
            for interaction in interactions:
                intent = interaction.get("metadata", {}).get("intent")
                intent_counts[intent] = intent_counts.get(intent, 0) + 1

            # Filter out None keys before computing max
            valid_counts = {k: v for k, v in intent_counts.items() if k is not None}
            if valid_counts:
                most_common = max(valid_counts.items(), key=lambda x: x[1])
                lines.append(
                    f"Most common interaction: {most_common[0]} ({most_common[1]} times)"
                )

        return " ".join(lines)

    # ------------------------------------------------------------------
    # LLM formatting
    # ------------------------------------------------------------------

    def format_memory_for_llm(
        self,
        short_term: str,
        long_term: Dict[str, Any],
    ) -> str:
        """Format memory for injection into an LLM prompt.

        Args:
            short_term: Short-term conversation history (plain text)
            long_term: Long-term patient memory dict

        Returns:
            Formatted memory block that can be inserted into a system/user prompt.
        """
        lines = ["=== CONVERSATION MEMORY ===\n"]

        # Short-term
        lines.append("SHORT-TERM (Current Session):")
        lines.append(short_term if short_term else "(no prior turns)")
        lines.append("")

        # Long-term
        lines.append("LONG-TERM (Patient History):")
        lines.append(long_term.get("summary", "No history available"))

        if long_term.get("medical_records"):
            lines.append(
                f"\nMedical Records: {len(long_term['medical_records'])} on file"
            )
            # Include the most recent record types for richer context
            record_types = list({
                r.get("record_type", "unknown")
                for r in long_term["medical_records"]
            })
            if record_types:
                lines.append(f"Record types: {', '.join(record_types)}")

        if long_term.get("interaction_history"):
            lines.append(
                f"Previous Interactions: {len(long_term['interaction_history'])}"
            )

        lines.append("\n=== END MEMORY ===")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Context-switch detection
    # ------------------------------------------------------------------

    # Common titles / prefixes that precede a patient name
    _NAME_PREFIXES = re.compile(
        r"\b(?:my name is|i(?:'| a)m|for|patient)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
        re.IGNORECASE,
    )

    def detect_context_switch(
        self,
        current_message: str,
        active_patient_name: Optional[str],
    ) -> bool:
        """Detect if the user is switching context to a different patient.

        Uses a combination of explicit switch keywords and a lightweight
        name-extraction heuristic that checks whether a *different* name
        appears in the message.

        Args:
            current_message: Current user message
            active_patient_name: Currently active patient name (may be None)

        Returns:
            True if a context switch is detected.
        """
        message_lower = current_message.lower()

        # 1. Explicit switch keywords
        switch_keywords = [
            "now let's talk about",
            "switch to",
            "what about",
            "instead",
            "different patient",
            "another patient",
            "new patient",
        ]
        for keyword in switch_keywords:
            if keyword in message_lower:
                return True

        # 2. Name-based heuristic
        if active_patient_name:
            active_lower = active_patient_name.lower()

            # Extract candidate names from the message
            match = self._NAME_PREFIXES.search(current_message)
            if match:
                mentioned_name = match.group(1).strip().lower()
                if mentioned_name != active_lower:
                    # A *different* name was explicitly mentioned
                    return True

            # If the active patient is NOT mentioned but an action verb is,
            # the user is likely switching context.
            if active_lower not in message_lower:
                action_verbs = [
                    "appointment", "followup", "follow-up",
                    "book", "schedule", "consult",
                ]
                if any(verb in message_lower for verb in action_verbs):
                    return True

        return False

    # ------------------------------------------------------------------
    # Data management / GDPR
    # ------------------------------------------------------------------

    def clear_patient_memory(self, patient_uuid: str) -> Dict[str, Any]:
        """Delete all memory for a patient (supports right-to-deletion).

        Removes:
        - Vector-store interaction history (cloud, UUID-only)
        - Does NOT delete local database records (that's controlled by
          ``identity_vault`` separately).

        Args:
            patient_uuid: Patient UUID whose vector-store data to remove.

        Returns:
            Summary dict with counts of deleted items.
        """
        logger.info(f"Clearing memory for patient: {patient_uuid[:8]}...")
        deleted = {"metadata_deleted": 0, "errors": []}

        if _ms_mod.metadata_store is not None:
            try:
                result = _ms_mod.metadata_store.delete_patient_metadata(
                    patient_uuid=patient_uuid
                )
                deleted["metadata_deleted"] = result if isinstance(result, int) else 1
                logger.info(f"Deleted metadata store entries for {patient_uuid[:8]}")
            except Exception as e:
                msg = f"Failed to delete metadata: {e}"
                logger.error(msg)
                deleted["errors"].append(msg)
        else:
            logger.warning("Metadata store not available – skipping vector deletion")

        return deleted

    # ------------------------------------------------------------------
    # Interaction metrics
    # ------------------------------------------------------------------

    def update_interaction_metrics(
        self,
        patient_uuid: str,
        intent: str,
        semantic_context: Dict[str, Any],
    ) -> None:
        """Record an interaction in the vector store for future context.

        This is called by the coordinator after a successful pipeline run so
        that subsequent queries for the same patient benefit from richer
        historical context.

        Args:
            patient_uuid: Patient UUID
            intent: Detected intent (appointment / followup / summary / general)
            semantic_context: Semantic context dict (must not contain PII)
        """
        if _ms_mod.metadata_store is None:
            return

        try:
            _ms_mod.metadata_store.store_patient_metadata(
                patient_uuid=patient_uuid,
                semantic_context=semantic_context,
                intent=intent,
            )
            logger.info(
                f"Interaction metrics stored for {patient_uuid[:8]} (intent={intent})"
            )
        except Exception as e:
            logger.warning(f"Could not store interaction metrics: {e}")


# Global instance
memory_manager = MemoryManager()
