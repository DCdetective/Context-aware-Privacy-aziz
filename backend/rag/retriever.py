from typing import Dict, Any, List
import logging

from vector_store.metadata_store import metadata_store
from vector_store.synthetic_store import synthetic_store

logger = logging.getLogger(__name__)


class RAGRetriever:
    """
    RAG (Retrieval-Augmented Generation) retriever.
    
    Retrieves relevant context from both:
    1. Patient metadata (UUID-linked)
    2. Synthetic hospital knowledge
    """
    
    def __init__(self):
        """Initialize RAG retriever."""
        logger.info("RAG Retriever initialized")
    
    def retrieve_context_for_intent(
        self,
        patient_uuid: str,
        intent: str,
        semantic_context: Dict[str, Any],
        medical_info: str
    ) -> Dict[str, Any]:
        """
        Retrieve relevant context for a user intent.
        
        Args:
            patient_uuid: Patient UUID
            intent: User intent
            semantic_context: Semantic medical context
            medical_info: Medical information text
            
        Returns:
            Retrieved context including patient history and relevant knowledge
        """
        logger.info(f"=" * 60)
        logger.info(f"RAG RETRIEVER: Retrieving context")
        logger.info(f"Patient UUID: {patient_uuid[:8]}...")
        logger.info(f"Intent: {intent}")
        logger.info(f"=" * 60)
        
        # 1. Retrieve patient history from metadata store
        patient_history = []
        if metadata_store:
            logger.info("Retrieving patient history...")
            patient_history = metadata_store.retrieve_patient_history(
                patient_uuid=patient_uuid,
                limit=5
            )
            logger.info(f"✓ Found {len(patient_history)} history records")
            
            if not patient_history:
                logger.warning(f"⚠ No patient history found for UUID: {patient_uuid}")
        else:
            logger.warning("⚠ Metadata store not available")
        
        # 2. Search for relevant doctors
        specialty = semantic_context.get("symptom_category", "general")
        relevant_doctors = []
        if synthetic_store:
            logger.info(f"Searching for {specialty} specialists...")
            relevant_doctors = synthetic_store.search_doctors(
                specialty=specialty,
                top_k=3
            )
            logger.info(f"✓ Found {len(relevant_doctors)} doctors")
            
            if not relevant_doctors:
                logger.warning(f"⚠ No doctors found for specialty: {specialty}")
        else:
            logger.warning("⚠ Synthetic store not available")
        
        # 3. Search medical knowledge
        relevant_knowledge = []
        if synthetic_store:
            logger.info(f"Searching medical knowledge...")
            relevant_knowledge = synthetic_store.search_medical_knowledge(
                query=medical_info,
                top_k=3
            )
            logger.info(f"✓ Found {len(relevant_knowledge)} knowledge items")
        
        # 4. Search similar cases
        similar_cases = []
        if synthetic_store:
            logger.info(f"Searching similar cases...")
            similar_cases = synthetic_store.search_similar_cases(
                query=medical_info,
                top_k=2
            )
            logger.info(f"✓ Found {len(similar_cases)} similar cases")
        
        context = {
            "patient_uuid": patient_uuid,
            "intent": intent,
            "patient_history": patient_history,
            "relevant_doctors": relevant_doctors,
            "relevant_knowledge": relevant_knowledge,
            "similar_cases": similar_cases,
            "semantic_context": semantic_context
        }
        
        logger.info(f"=" * 60)
        logger.info(f"RAG RETRIEVAL SUMMARY:")
        logger.info(f"  - History records: {len(patient_history)}")
        logger.info(f"  - Doctors found: {len(relevant_doctors)}")
        logger.info(f"  - Knowledge items: {len(relevant_knowledge)}")
        logger.info(f"  - Similar cases: {len(similar_cases)}")
        logger.info(f"=" * 60)
        
        return context
    
    def format_context_for_llm(self, context: Dict[str, Any]) -> str:
        """
        Format retrieved context for LLM consumption.
        
        Args:
            context: Retrieved context
            
        Returns:
            Formatted context string
        """
        formatted = []
        
        # Patient history
        if context["patient_history"]:
            formatted.append("## Patient History (UUID-based):")
            for i, record in enumerate(context["patient_history"][:3], 1):
                metadata = record["metadata"]
                formatted.append(f"{i}. Previous {metadata['intent']}: "
                               f"Category: {metadata['symptom_category']}, "
                               f"Urgency: {metadata['urgency_level']}")
        
        # Relevant doctors
        if context["relevant_doctors"]:
            formatted.append("\n## Available Doctors:")
            for i, doctor in enumerate(context["relevant_doctors"], 1):
                metadata = doctor["metadata"]
                formatted.append(f"{i}. {metadata.get('content', 'Doctor information')}")
        
        # Medical knowledge
        if context["relevant_knowledge"]:
            formatted.append("\n## Medical Knowledge:")
            for i, knowledge in enumerate(context["relevant_knowledge"], 1):
                metadata = knowledge["metadata"]
                formatted.append(f"{i}. {metadata.get('content', 'Medical information')}")
        
        # Similar cases
        if context["similar_cases"]:
            formatted.append("\n## Similar Cases:")
            for i, case in enumerate(context["similar_cases"], 1):
                metadata = case["metadata"]
                formatted.append(f"{i}. {metadata.get('content', 'Example case')}")
        
        return "\n".join(formatted)


# Global instance
rag_retriever = RAGRetriever()
