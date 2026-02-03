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
        
        # Route to appropriate handler
        handlers = {
            "appointment": self._handle_appointment,
            "followup": self._handle_followup,
            "summary": self._handle_summary,
            "general": self._handle_general_query
        }
        
        handler = handlers.get(intent, self._handle_general_query)
        result = handler(patient_uuid, refined_context)
        
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


# Global instance
execution_agent = ExecutionAgent()
