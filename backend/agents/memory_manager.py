"""
Memory Manager - Handles short-term and long-term memory.
"""
from typing import Dict, Any, List, Optional
import logging
from database.identity_vault import identity_vault
from vector_store.metadata_store import metadata_store

logger = logging.getLogger(__name__)


class MemoryManager:
    """
    Manages conversational memory (short-term and long-term).
    
    Short-term: Session-based conversation history
    Long-term: Patient records from database + vector store
    """
    
    def __init__(self):
        """Initialize Memory Manager."""
        logger.info("Memory Manager initialized")
    
    def get_patient_long_term_memory(
        self,
        patient_uuid: str,
        limit: int = 10
    ) -> Dict[str, Any]:
        """
        Retrieve patient's long-term memory.
        
        Combines:
        - Local database records (PII-safe)
        - Vector store interaction history (semantic)
        
        Args:
            patient_uuid: Patient UUID
            limit: Maximum records to retrieve
            
        Returns:
            Long-term memory dictionary
        """
        logger.info(f"Retrieving long-term memory for patient: {patient_uuid[:8]}...")
        
        memory = {
            "patient_uuid": patient_uuid,
            "medical_records": [],
            "interaction_history": [],
            "summary": ""
        }
        
        try:
            # Get medical records from local database
            records = identity_vault.get_patient_records(
                patient_uuid=patient_uuid,
                component="memory_manager"
            )
            memory["medical_records"] = records[:limit]
            logger.info(f"Found {len(records)} medical records")
            
            # Get interaction history from vector store
            if metadata_store:
                history = metadata_store.retrieve_patient_history(
                    patient_uuid=patient_uuid,
                    limit=limit
                )
                memory["interaction_history"] = history
                logger.info(f"Found {len(history)} vector store interactions")
            
            # Create summary
            memory["summary"] = self._create_memory_summary(memory)
            
            return memory
            
        except Exception as e:
            logger.error(f"Error retrieving long-term memory: {str(e)}")
            return memory
    
    def _create_memory_summary(self, memory: Dict[str, Any]) -> str:
        """Create a textual summary of patient memory."""
        lines = []
        
        record_count = len(memory.get("medical_records", []))
        interaction_count = len(memory.get("interaction_history", []))
        
        if record_count == 0 and interaction_count == 0:
            return "New patient - no previous history available."
        
        lines.append(f"Patient has {record_count} medical records and {interaction_count} previous interactions.")
        
        # Summarize recent records
        records = memory.get("medical_records", [])
        if records:
            recent = records[0]
            lines.append(f"Most recent: {recent.get('record_type')} on {recent.get('created_at', 'unknown date')}")
        
        # Summarize interaction patterns
        interactions = memory.get("interaction_history", [])
        if interactions:
            intents = [i.get("metadata", {}).get("intent") for i in interactions]
            intent_counts = {}
            for intent in intents:
                intent_counts[intent] = intent_counts.get(intent, 0) + 1
            
            most_common = max(intent_counts.items(), key=lambda x: x[1]) if intent_counts else None
            if most_common:
                lines.append(f"Most common interaction: {most_common[0]} ({most_common[1]} times)")
        
        return " ".join(lines)
    
    def format_memory_for_llm(
        self,
        short_term: str,
        long_term: Dict[str, Any]
    ) -> str:
        """
        Format memory for LLM context.
        
        Args:
            short_term: Short-term conversation history
            long_term: Long-term patient memory
            
        Returns:
            Formatted memory string for LLM prompt
        """
        lines = ["=== CONVERSATION MEMORY ===\n"]
        
        # Short-term memory
        lines.append("SHORT-TERM (Current Session):")
        lines.append(short_term)
        lines.append("")
        
        # Long-term memory
        lines.append("LONG-TERM (Patient History):")
        lines.append(long_term.get("summary", "No history available"))
        
        if long_term.get("medical_records"):
            lines.append(f"\nMedical Records: {len(long_term['medical_records'])} on file")
        
        if long_term.get("interaction_history"):
            lines.append(f"Previous Interactions: {len(long_term['interaction_history'])}")
        
        lines.append("\n=== END MEMORY ===")
        
        return "\n".join(lines)
    
    def detect_context_switch(
        self,
        current_message: str,
        active_patient_name: Optional[str]
    ) -> bool:
        """
        Detect if user is switching context to a different patient.
        
        Args:
            current_message: Current user message
            active_patient_name: Currently active patient name
            
        Returns:
            True if context switch detected
        """
        # Keywords that indicate context switch
        switch_keywords = [
            "now let's talk about",
            "switch to",
            "what about",
            "instead",
            "different patient",
            "another patient"
        ]
        
        message_lower = current_message.lower()
        
        # Check for switch keywords
        for keyword in switch_keywords:
            if keyword in message_lower:
                return True
        
        # Check if a different name is mentioned
        if active_patient_name:
            # If message contains a different name, it might be a switch
            # This is heuristic - would need NER for perfect detection
            if active_patient_name.lower() not in message_lower:
                # Message doesn't mention active patient, might be switching
                # But only if it mentions another appointment/followup
                if any(word in message_lower for word in ['appointment', 'followup', 'book', 'schedule']):
                    return True
        
        return False


# Global instance
memory_manager = MemoryManager()
