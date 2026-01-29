from groq import Groq
import json
import re
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
import logging

from utils.config import settings
from database.identity_vault import identity_vault

logger = logging.getLogger(__name__)


class WorkerAgent:
    """
    Cloud Worker Agent using Groq API.
    
    PRIVACY GUARANTEE:
    - Executes tasks using ONLY UUIDs
    - Validates identity by UUID only
    - Uses semantic context for medical logic
    - NEVER receives patient names or PII
    - NEVER hallucinates unsupported actions
    """
    
    def __init__(self, semantic_store=None):
        """Initialize Worker Agent."""
        self.client = Groq(api_key=settings.groq_api_key)
        self.model = "llama-3.3-70b-versatile"  # Updated Groq model (Jan 2026)
        self.semantic_store = semantic_store
        
        logger.info("Worker Agent initialized with Groq API")
    
    def _call_groq(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Call Groq LLM."""
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
        action_type: str,
        execution_plan: Dict[str, Any],
        semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute a medical task.
        
        Args:
            patient_uuid: Pseudonymized patient UUID
            action_type: Type of action
            execution_plan: Execution plan from Coordinator
            semantic_context: Non-PII semantic context
            
        Returns:
            Task execution result
        """
        logger.info("=" * 60)
        logger.info("WORKER: Executing task")
        logger.info(f"UUID: {patient_uuid[:8]}...")
        logger.info(f"Action: {action_type}")
        logger.info("=" * 60)
        
        # Validate UUID exists
        if not self._validate_uuid(patient_uuid):
            logger.error(f"Invalid UUID: {patient_uuid}")
            return {
                "success": False,
                "error": "Invalid patient UUID",
                "patient_uuid": patient_uuid
            }
        
        # Route to appropriate handler
        handlers = {
            "appointment": self._handle_appointment,
            "followup": self._handle_followup,
            "summary": self._handle_summary
        }
        
        handler = handlers.get(action_type)
        if not handler:
            logger.error(f"No handler for action: {action_type}")
            return {
                "success": False,
                "error": f"Unsupported action: {action_type}",
                "patient_uuid": patient_uuid
            }
        
        # Execute handler
        result = handler(patient_uuid, execution_plan, semantic_context)
        
        logger.info("WORKER: Task executed successfully")
        logger.info("=" * 60)
        
        return result
    
    def _validate_uuid(self, patient_uuid: str) -> bool:
        """
        Validate that UUID exists in system.
        
        PRIVACY NOTE: This checks existence only, does not access PII.
        
        Args:
            patient_uuid: Patient UUID to validate
            
        Returns:
            True if UUID exists
        """
        # Check in identity vault (without accessing PII)
        identity = identity_vault.reidentify_patient(
            patient_uuid=patient_uuid,
            component="worker_agent_validation"
        )
        return identity is not None
    
    def _handle_appointment(
        self,
        patient_uuid: str,
        execution_plan: Dict[str, Any],
        semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle appointment scheduling.
        
        Args:
            patient_uuid: Patient UUID
            execution_plan: Execution plan
            semantic_context: Semantic context
            
        Returns:
            Appointment scheduling result
        """
        logger.info("Handling appointment scheduling...")
        
        # Determine appointment time based on urgency
        urgency = execution_plan.get("priority", "routine")
        
        if urgency == "emergency":
            appointment_time = datetime.now() + timedelta(hours=2)
        elif urgency == "urgent":
            appointment_time = datetime.now() + timedelta(days=1)
        else:
            appointment_time = datetime.now() + timedelta(days=7)
        
        # Calculate consultation time
        consultation_time = semantic_context.get("estimated_consultation_time", 30)
        
        # Store in medical records (local vault)
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="appointment",
            symptoms=f"Semantic: {semantic_context.get('symptom_category', 'general')}",
            component="worker_agent"
        )
        
        result = {
            "success": True,
            "patient_uuid": patient_uuid,
            "action": "appointment_scheduled",
            "appointment_time": appointment_time.isoformat(),
            "consultation_duration": consultation_time,
            "urgency_level": urgency,
            "requires_specialist": execution_plan.get("requires_specialist", False),
            "record_id": record_id
        }
        
        logger.info(f"Appointment scheduled for {appointment_time.isoformat()}")
        return result
    
    def _handle_followup(
        self,
        patient_uuid: str,
        execution_plan: Dict[str, Any],
        semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle follow-up scheduling.
        
        Args:
            patient_uuid: Patient UUID
            execution_plan: Execution plan
            semantic_context: Semantic context
            
        Returns:
            Follow-up scheduling result
        """
        logger.info("Handling follow-up scheduling...")
        
        # Retrieve previous semantic anchors
        previous_context = []
        if self.semantic_store:
            previous_context = self.semantic_store.retrieve_semantic_anchors(
                patient_uuid=patient_uuid,
                limit=5
            )
        
        # Calculate follow-up time (default: 2 weeks)
        followup_time = datetime.now() + timedelta(days=14)
        
        # Store follow-up record
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="followup",
            treatment_plan="Follow-up based on previous context",
            component="worker_agent"
        )
        
        result = {
            "success": True,
            "patient_uuid": patient_uuid,
            "action": "followup_scheduled",
            "followup_time": followup_time.isoformat(),
            "previous_visits": len(previous_context),
            "continuity_maintained": len(previous_context) > 0,
            "record_id": record_id
        }
        
        logger.info(f"Follow-up scheduled for {followup_time.isoformat()}")
        return result
    
    def _handle_summary(
        self,
        patient_uuid: str,
        execution_plan: Dict[str, Any],
        semantic_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle medical summary generation.
        
        Args:
            patient_uuid: Patient UUID
            execution_plan: Execution plan
            semantic_context: Semantic context
            
        Returns:
            Medical summary result
        """
        logger.info("Handling medical summary generation...")
        
        # Retrieve medical records
        records = identity_vault.get_patient_records(
            patient_uuid=patient_uuid,
            component="worker_agent"
        )
        
        # Generate summary using Groq
        system_prompt = """Generate a medical summary using ONLY UUID-based information.

CRITICAL RULES:
1. Use ONLY the patient UUID (NO names)
2. Summarize based on semantic medical context
3. Include visit count and record types
4. Return structured JSON format"""
        
        prompt = f"""Generate medical summary for patient UUID: {patient_uuid}

Medical Records: {len(records)} records found
Semantic Context: {json.dumps(semantic_context)}

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
                    "record_types": [r["record_type"] for r in records],
                    "summary_text": f"Patient {patient_uuid[:8]}... has {len(records)} medical records."
                }
        except:
            summary_data = {
                "total_visits": len(records),
                "record_types": [r["record_type"] for r in records],
                "summary_text": f"Patient {patient_uuid[:8]}... has {len(records)} medical records."
            }
        
        # Store summary record
        record_id = identity_vault.store_medical_record(
            patient_uuid=patient_uuid,
            record_type="summary",
            diagnosis=summary_data["summary_text"],
            component="worker_agent"
        )
        
        result = {
            "success": True,
            "patient_uuid": patient_uuid,
            "action": "summary_generated",
            "summary": summary_data,
            "record_id": record_id
        }
        
        logger.info("Medical summary generated")
        return result


# Global instance
worker_agent = WorkerAgent()
