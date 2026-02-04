from groq import Groq
import json
import re
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from utils.config import settings
from database.identity_vault import identity_vault

logger = logging.getLogger(__name__)


class ExecutionAgent:
    """
    Cloud Execution Agent using Groq API.
    
    PRIVACY GUARANTEE:
    - Executes tasks using ONLY UUIDs
    - Validates identity by UUID only
    - Uses refined context for decisions
    - NEVER receives patient names or PII
    """
    
    def __init__(self):
        """Initialize Execution Agent."""
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = "llama-3.3-70b-versatile"
        
        logger.info("Execution Agent initialized with Groq API")
    
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
    
    def execute_task(
        self,
        patient_uuid: str,
        intent: str,
        refined_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a medical task.
        
        Args:
            patient_uuid: Pseudonymized patient UUID
            intent: User intent
            refined_context: Refined context from Context Agent
            
        Returns:
            Task execution result
        """
        logger.info("=" * 60)
        logger.info("EXECUTION AGENT: Executing task")
        logger.info(f"UUID: {patient_uuid[:8]}...")
        logger.info(f"Intent: {intent}")
        logger.info("=" * 60)
        
        # Extract RAG context
        rag_context = refined_context.get('rag_context', {})
        
        # Build prompt with RAG context based on intent
        if intent == "appointment":
            result = self._handle_appointment_with_rag(patient_uuid, refined_context, rag_context)
        elif intent == "followup":
            result = self._handle_followup_with_rag(patient_uuid, refined_context, rag_context)
        elif intent == "summary":
            result = self._handle_summary_with_rag(patient_uuid, refined_context, rag_context)
        else:
            result = self._handle_general_query(patient_uuid, refined_context)
        
        logger.info("EXECUTION AGENT: Task executed successfully")
        logger.info("=" * 60)
        
        return result
    
    def _handle_appointment(
        self,
        patient_uuid: str,
        refined_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle appointment booking."""
        logger.info("Handling appointment booking...")
        
        # Determine appointment time based on urgency
        urgency = refined_context.get('urgency_assessment', 'routine')
        
        if urgency == "emergency":
            appointment_time = datetime.now() + timedelta(hours=2)
        elif urgency == "urgent":
            appointment_time = datetime.now() + timedelta(days=1)
        else:
            appointment_time = datetime.now() + timedelta(days=7)
        
        # Get duration
        duration = refined_context.get('estimated_duration', 30)
        
        # Store medical record
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="appointment",
            symptoms=f"Category: {refined_context.get('recommended_specialty', 'general')}",
            notes=refined_context.get('reasoning', ''),
            component="execution_agent"
        )
        
        result = {
            "success": True,
            "intent": "appointment",
            "patient_uuid": patient_uuid,
            "appointment_time": appointment_time.isoformat(),
            "consultation_duration": duration,
            "urgency_level": urgency,
            "recommended_specialty": refined_context.get('recommended_specialty'),
            "recommended_doctor": refined_context.get('recommended_doctor'),
            "record_id": record_id,
            "message": f"Appointment scheduled for patient {patient_uuid[:8]}..."
        }
        
        logger.info(f"Appointment scheduled for {appointment_time.isoformat()}")
        return result
    
    def _handle_followup(
        self,
        patient_uuid: str,
        refined_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle follow-up scheduling."""
        logger.info("Handling follow-up scheduling...")
        
        # Calculate follow-up time (default: 2 weeks)
        followup_time = datetime.now() + timedelta(days=14)
        
        # Store follow-up record
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="followup",
            treatment_plan="Follow-up based on previous visit",
            notes=refined_context.get('reasoning', ''),
            component="execution_agent"
        )
        
        # Get previous visits
        previous_records = identity_vault.get_patient_records(patient_uuid)
        
        result = {
            "success": True,
            "intent": "followup",
            "patient_uuid": patient_uuid,
            "followup_time": followup_time.isoformat(),
            "previous_visits": len(previous_records),
            "continuity_maintained": len(previous_records) > 0,
            "record_id": record_id,
            "message": f"Follow-up scheduled for patient {patient_uuid[:8]}..."
        }
        
        logger.info(f"Follow-up scheduled for {followup_time.isoformat()}")
        return result
    
    def _handle_summary(
        self,
        patient_uuid: str,
        refined_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle medical summary generation."""
        logger.info("Handling medical summary generation...")
        
        # Retrieve medical records
        records = identity_vault.get_patient_records(patient_uuid)
        
        # Generate summary using Groq
        system_prompt = """Generate a medical summary using ONLY UUID-based information.

CRITICAL RULES:
1. Use ONLY the patient UUID (NO names)
2. Summarize based on record types and counts
3. Return JSON format"""

        prompt = f"""Generate medical summary for patient UUID: {patient_uuid}

Medical Records: {len(records)} records found
Record Types: {[r['record_type'] for r in records]}

Return JSON with:
- total_visits: number
- record_types: list
- summary_text: brief summary using UUID only"""

        try:
            response = self._call_groq(prompt, system_prompt)
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                summary_data = json.loads(json_match.group())
            else:
                summary_data = {
                    "total_visits": len(records),
                    "record_types": list(set(r["record_type"] for r in records)),
                    "summary_text": f"Patient {patient_uuid[:8]}... has {len(records)} medical records."
                }
        except:
            summary_data = {
                "total_visits": len(records),
                "record_types": list(set(r["record_type"] for r in records)),
                "summary_text": f"Patient {patient_uuid[:8]}... has {len(records)} medical records."
            }
        
        # Store summary record
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="summary",
            diagnosis=summary_data["summary_text"],
            component="execution_agent"
        )
        
        result = {
            "success": True,
            "intent": "summary",
            "patient_uuid": patient_uuid,
            "summary": summary_data,
            "record_id": record_id,
            "message": f"Summary generated for patient {patient_uuid[:8]}..."
        }
        
        logger.info("Medical summary generated")
        return result
    
    def _handle_general_query(
        self,
        patient_uuid: str,
        refined_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle general query."""
        logger.info("Handling general query...")
        
        result = {
            "success": True,
            "intent": "general",
            "patient_uuid": patient_uuid,
            "message": "I can help you with appointments, follow-ups, or medical summaries. "
                      "What would you like to do?",
            "suggestions": [
                "Book an appointment",
                "Schedule a follow-up",
                "Generate medical summary"
            ]
        }
        
        return result
    
    def _format_rag_context_for_prompt(self, refined_context: Dict[str, Any]) -> str:
        """Format RAG context for inclusion in LLM prompt."""
        lines = ["RETRIEVED CONTEXT FROM KNOWLEDGE BASE:"]
        
        rag = refined_context.get('rag_context', {})
        
        if rag.get('patient_history_count', 0) > 0:
            lines.append(f"- Patient has {rag['patient_history_count']} previous interactions in system")
        
        if rag.get('relevant_doctors_count', 0) > 0:
            lines.append(f"- Found {rag['relevant_doctors_count']} relevant doctors in database")
        
        if rag.get('knowledge_retrieved', 0) > 0:
            lines.append(f"- Retrieved {rag['knowledge_retrieved']} relevant medical knowledge items")
        
        if not any([rag.get('patient_history_count'), rag.get('relevant_doctors_count'), rag.get('knowledge_retrieved')]):
            lines.append("- No prior context available (new patient or limited data)")
        
        return "\n".join(lines)
    
    def _handle_appointment_with_rag(
        self,
        patient_uuid: str,
        refined_context: Dict[str, Any],
        rag_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle appointment booking with RAG context."""
        logger.info("Handling appointment booking with RAG...")
        
        # Build prompt with RAG context
        system_prompt = """You are a medical assistant executing tasks.

CRITICAL RULES:
1. Use ONLY patient UUID - NEVER generate or use real names
2. Base recommendations on retrieved medical knowledge
3. Use doctor information from the knowledge base
4. Reference similar cases when relevant
5. Return ONLY JSON format

You have access to:
- Patient interaction history (by UUID)
- Hospital doctor database
- Medical knowledge base
- Similar case examples
"""
        
        context_summary = self._format_rag_context_for_prompt(refined_context)
        
        prompt = f"""Execute appointment booking task.

Patient UUID: {patient_uuid}
Refined Context: {json.dumps(refined_context, indent=2)}

{context_summary}

Based on the retrieved information:
1. Recommend an appropriate doctor from the knowledge base
2. Suggest appointment time based on urgency
3. Provide consultation duration estimate

Return JSON with:
- recommended_doctor: doctor name from database (or null)
- appointment_date: suggested date
- appointment_time: suggested time
- consultation_duration: minutes
- reasoning: explanation using retrieved context
"""
        
        try:
            # Call LLM
            response = self._call_groq(prompt, system_prompt)
            
            # Parse JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(response)
            
            # Add RAG metadata
            result['rag_used'] = True
            result['rag_sources'] = {
                'patient_history_count': len(rag_context.get('patient_history', [])),
                'doctors_found': len(rag_context.get('relevant_doctors', [])),
                'knowledge_items': len(rag_context.get('relevant_knowledge', []))
            }
            result['patient_uuid'] = patient_uuid
            result['success'] = True
            result['intent'] = 'appointment'
            
            logger.info("✓ Task executed successfully with RAG context")
            return result
            
        except Exception as e:
            logger.error(f"Error executing task with RAG: {str(e)}")
            return self._handle_appointment(patient_uuid, refined_context)
    
    def _handle_followup_with_rag(
        self,
        patient_uuid: str,
        refined_context: Dict[str, Any],
        rag_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle follow-up scheduling with RAG context."""
        logger.info("Handling follow-up scheduling with RAG...")
        
        system_prompt = """You are a medical assistant executing tasks.

CRITICAL RULES:
1. Use ONLY patient UUID - NEVER generate or use real names
2. Base recommendations on retrieved medical knowledge
3. Use doctor information from the knowledge base
4. Reference patient history when relevant
5. Return ONLY JSON format
"""
        
        context_summary = self._format_rag_context_for_prompt(refined_context)
        
        prompt = f"""Execute follow-up scheduling task.

Patient UUID: {patient_uuid}
Refined Context: {json.dumps(refined_context, indent=2)}

{context_summary}

Based on patient history and retrieved information:
1. Review past interactions
2. Suggest appropriate follow-up timeline
3. Recommend continuation with same doctor if applicable

Return JSON with:
- followup_date: suggested date
- recommended_doctor: doctor name (or same as before)
- notes: follow-up instructions based on history
- reasoning: explanation using retrieved context
"""
        
        try:
            response = self._call_groq(prompt, system_prompt)
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(response)
            
            result['rag_used'] = True
            result['rag_sources'] = {
                'patient_history_count': len(rag_context.get('patient_history', [])),
                'doctors_found': len(rag_context.get('relevant_doctors', [])),
                'knowledge_items': len(rag_context.get('relevant_knowledge', []))
            }
            result['patient_uuid'] = patient_uuid
            result['success'] = True
            result['intent'] = 'followup'
            
            logger.info("✓ Follow-up executed successfully with RAG context")
            return result
            
        except Exception as e:
            logger.error(f"Error executing follow-up with RAG: {str(e)}")
            return self._handle_followup(patient_uuid, refined_context)
    
    def _handle_summary_with_rag(
        self,
        patient_uuid: str,
        refined_context: Dict[str, Any],
        rag_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle medical summary generation with RAG context."""
        logger.info("Handling medical summary generation with RAG...")
        
        system_prompt = """Generate a medical summary using ONLY UUID-based information.

CRITICAL RULES:
1. Use ONLY the patient UUID (NO names)
2. Summarize based on record types and counts
3. Return JSON format"""
        
        context_summary = self._format_rag_context_for_prompt(refined_context)
        
        prompt = f"""Generate medical summary.

Patient UUID: {patient_uuid}
Refined Context: {json.dumps(refined_context, indent=2)}

{context_summary}

Based on patient history from the knowledge base:
1. Summarize past interactions (by UUID only)
2. List previous appointments/follow-ups
3. Note any patterns or recurring issues

Return JSON with:
- summary: comprehensive summary using only UUID
- interaction_count: number of past interactions
- notable_patterns: any patterns observed
- reasoning: explanation based on retrieved history
"""
        
        try:
            response = self._call_groq(prompt, system_prompt)
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(response)
            
            result['rag_used'] = True
            result['rag_sources'] = {
                'patient_history_count': len(rag_context.get('patient_history', [])),
                'doctors_found': len(rag_context.get('relevant_doctors', [])),
                'knowledge_items': len(rag_context.get('relevant_knowledge', []))
            }
            result['patient_uuid'] = patient_uuid
            result['success'] = True
            result['intent'] = 'summary'
            
            logger.info("✓ Summary generated successfully with RAG context")
            return result
            
        except Exception as e:
            logger.error(f"Error generating summary with RAG: {str(e)}")
            return self._handle_summary(patient_uuid, refined_context)


# Global instance
execution_agent = ExecutionAgent()
