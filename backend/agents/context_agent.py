from groq import Groq
import json
import re
from typing import Dict, Any, Optional
import logging

from utils.config import settings
from rag.retriever import rag_retriever

logger = logging.getLogger(__name__)


class ContextRefinementAgent:
    """
    Cloud Context Refinement Agent using Groq API.
    
    PRIVACY GUARANTEE:
    - Receives ONLY pseudonymized UUIDs
    - Uses RAG to enrich context
    - Validates medical logic
    - NEVER accesses PII
    """
    
    def __init__(self):
        """Initialize Context Refinement Agent."""
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = "llama-3.3-70b-versatile"
        
        logger.info("Context Refinement Agent initialized with Groq API")
    
    def _call_groq(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Groq LLM with a prompt."""
        try:
            messages = []
            
            if system_prompt:
                messages.append({
                    "role": "system",
                    "content": system_prompt
                })
            
            messages.append({
                "role": "user",
                "content": prompt
            })
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.3,
                max_tokens=1024
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error calling Groq API: {str(e)}")
            raise
    
    def refine_context(
        self,
        patient_uuid: str,
        intent: str,
        semantic_context: Dict[str, Any],
        medical_info: str
    ) -> Dict[str, Any]:
        """
        Refine context using RAG retrieval and LLM reasoning.
        
        Args:
            patient_uuid: Pseudonymized patient UUID
            intent: User intent
            semantic_context: Semantic medical context
            medical_info: Medical information text
            
        Returns:
            Refined context with recommendations
        """
        logger.info("=" * 60)
        logger.info("CONTEXT AGENT: Refining context")
        logger.info(f"Patient UUID: {patient_uuid[:8]}...")
        logger.info(f"Intent: {intent}")
        logger.info("=" * 60)
        
        # Step 1: Retrieve relevant context via RAG
        rag_context = rag_retriever.retrieve_context_for_intent(
            patient_uuid=patient_uuid,
            intent=intent,
            semantic_context=semantic_context,
            medical_info=medical_info
        )
        
        # Step 2: Format context for LLM
        formatted_context = rag_retriever.format_context_for_llm(rag_context)
        
        # Step 3: Use LLM to refine and make recommendations
        system_prompt = """You are a medical context refinement assistant.

CRITICAL RULES:
1. You work ONLY with patient UUIDs - NEVER use or generate real names
2. Base recommendations on provided medical knowledge and patient history
3. Respect urgency levels and specialist requirements
4. Return ONLY JSON format
5. Ensure gender-appropriate doctor assignments when relevant

Your task: Analyze the context and provide refined medical recommendations."""

        prompt = f"""Analyze this medical context and provide recommendations:

Patient UUID: {patient_uuid}
Intent: {intent}
Semantic Context: {json.dumps(semantic_context)}

{formatted_context}

Provide JSON with:
- recommended_specialty: medical specialty needed
- recommended_doctor: doctor_id or null
- urgency_assessment: emergency/urgent/routine
- estimated_duration: minutes (integer)
- requires_follow_up: true/false
- reasoning: brief explanation (using UUID only, no names)"""

        try:
            response = self._call_groq(prompt, system_prompt)
            
            # Parse JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                refined = json.loads(json_match.group())
            else:
                refined = json.loads(response)
            
            # Add RAG context
            refined['rag_context'] = {
                'patient_history_count': len(rag_context.get('patient_history', [])),
                'relevant_doctors_count': len(rag_context.get('relevant_doctors', [])),
                'knowledge_retrieved': len(rag_context.get('relevant_knowledge', []))
            }
            
            logger.info("CONTEXT AGENT: Context refined successfully")
            logger.info(f"Recommended specialty: {refined.get('recommended_specialty')}")
            logger.info("=" * 60)
            
            return refined
            
        except Exception as e:
            logger.error(f"Error refining context: {str(e)}")
            # Fallback
            return self._fallback_refinement(semantic_context)
    
    def _fallback_refinement(self, semantic_context: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback refinement without LLM."""
        return {
            'recommended_specialty': semantic_context.get('symptom_category', 'general_medicine'),
            'recommended_doctor': None,
            'urgency_assessment': semantic_context.get('urgency_level', 'routine'),
            'estimated_duration': semantic_context.get('estimated_duration', 30),
            'requires_follow_up': False,
            'reasoning': 'Fallback recommendation based on semantic context',
            'rag_context': {'patient_history_count': 0, 'relevant_doctors_count': 0, 'knowledge_retrieved': 0}
        }


# Global instance
context_agent = ContextRefinementAgent()
